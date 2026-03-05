"""
Análise completa: todos os strikes do mercado
"What price will Bitcoin hit in March 2026?" vs modelo de barreira + indicador SD.

Para cada strike calcula:
  - YES token price (live)
  - NO  token price (live)
  - Barrier model P(YES) — reflexão log-normal, sem drift, from CURRENT price
  - Indicador SD P(YES)  — histórico N=4 eventos 2.25σ demand, 30 dias, from touch bar
  - Delta vs cada estimativa
  - EV de comprar YES e de comprar NO
"""

import sys
sys.stdout.reconfigure(encoding="utf-8")

import requests
import numpy as np
from scipy import stats
from datetime import datetime, timezone

GAMMA_BASE  = "https://gamma-api.polymarket.com"
CLOB_BASE   = "https://clob.polymarket.com"
HEADERS     = {"Accept": "application/json", "User-Agent": "polymarket-research/1.0"}
EVENT_SLUG  = "what-price-will-bitcoin-hit-in-march-2026"

# ── parâmetros de mercado ─────────────────────────────────────────────────
CURRENT     = 68_830      # preço BTC hoje
TOUCH_BAR   = 64_168      # close do touch bar Feb-06
DAYS_LEFT   = 28          # dias restantes em março
ANN_VOL     = 0.65        # vol realizada BTC (65% a.a.)
DAILY_VOL   = ANN_VOL / np.sqrt(365)
VOL_PERIOD  = DAILY_VOL * np.sqrt(DAYS_LEFT)  # σ√T

# ── indicador SD: P(YES) por nível, N=4 eventos, 30 dias, ref = touch bar ─
# Converte o alvo absoluto em % necessário DO TOUCH BAR (não do preço atual)
# e então compara com os max/min históricos de 30 dias
# Para upside:  hit se max_high_30d ≥ alvo × (touch_bar / current) ← equivalente
# Para downside: hit se min_low_30d  ≤ alvo × (touch_bar / current) ← equivalente
# Nota: esta conversão não é trivialmente correta (path-dependent) mas é
# a melhor aproximação disponível com N=4

# Resultados do polymarket_30d.py para cada evento (max_pct, min_pct em 30d):
# Mar-20:  ref=$4800,  max=+55.4%, min=-21.2%
# Mai-21:  ref=$37319, max=+13.8%, min=-16.9%
# Jun-22:  ref=$19259, max=+17.0%, min=-8.5%
# Nov-25:  ref=$84049, max=+12.5%, min=-4.1%

EVENTS_30D = [
    {"month": "Mar-20", "max_pct": 55.4, "min_pct": -21.2},
    {"month": "Mai-21", "max_pct": 13.8, "min_pct": -16.9},
    {"month": "Jun-22", "max_pct": 17.0, "min_pct": -8.5},
    {"month": "Nov-25", "max_pct": 12.5, "min_pct": -4.1},
]

# distância do preço atual vs touch bar: +7.3%
# Para comparar com o indicador (que mede do touch bar):
# um alvo absoluto $X corresponde a % do touch bar = (X/TOUCH_BAR - 1)*100
# Porém já estamos +7.3% acima do touch bar, então a distância remanescente
# a partir do current é menor do que a distância do touch bar.
# Uso duas referências e reporto ambas com transparência.

def sd_hit_rate(target_abs: float, direction: str) -> dict:
    """
    Calcula o hit rate do indicador SD para um alvo absoluto.
    direction: 'up' (reach) ou 'dn' (dip)
    Retorna hit rate medido do touch bar e do preço atual (proxy).
    """
    # % necessário DO TOUCH BAR
    pct_from_touch = (target_abs / TOUCH_BAR - 1) * 100
    # % necessário DO PREÇO ATUAL
    pct_from_current = (target_abs / CURRENT - 1) * 100

    hits_touch = 0
    hits_current_proxy = 0  # proxy: ajusta o evento pelo deslocamento atual

    for ev in EVENTS_30D:
        if direction == "up":
            # hit se max_pct >= pct_from_touch (medido do touch bar)
            if ev["max_pct"] >= pct_from_touch:
                hits_touch += 1
            # proxy: precisaria de (pct_from_current + 7.3%) a partir do touch bar
            # i.e., já percorremos 7.3% — precisamos mais pct_from_current
            # conservador: só conta se max_pct >= pct_from_touch (mesma métrica)
        else:  # dn
            if ev["min_pct"] <= pct_from_touch:
                hits_touch += 1

    n = len(EVENTS_30D)
    return {
        "pct_from_touch"  : round(pct_from_touch, 1),
        "pct_from_current": round(pct_from_current, 1),
        "hits"            : hits_touch,
        "n"               : n,
        "rate"            : round(hits_touch / n * 100),
    }


def barrier_prob(target: float) -> float:
    """
    P(ever touch target from CURRENT in DAYS_LEFT) — reflexão log-normal, sem drift.
    Formula: P = 2 × Φ(−|ln(target/CURRENT)| / (σ√T))
    """
    log_dist = abs(np.log(target / CURRENT))
    z = log_dist / VOL_PERIOD
    return 2 * stats.norm.cdf(-z)


def ev(yes_price: float, p_yes: float) -> float:
    """EV de comprar YES a yes_price, dado P(YES) = p_yes. Em ¢ por contrato."""
    return p_yes * (1 - yes_price) - (1 - p_yes) * yes_price


# ── 1. Buscar mercados ao vivo ────────────────────────────────────────────
def get_live_markets() -> list[dict]:
    r = requests.get(f"{GAMMA_BASE}/events/slug/{EVENT_SLUG}", headers=HEADERS, timeout=10)
    r.raise_for_status()
    return r.json().get("markets", [])


def get_midpoint(token_id: str) -> float | None:
    try:
        r = requests.get(f"{CLOB_BASE}/midpoints",
                         params={"token_id": token_id}, headers=HEADERS, timeout=8)
        r.raise_for_status()
        mid = r.json().get("mid") or r.json().get("midpoint")
        return float(mid) if mid else None
    except Exception:
        return None


print("Buscando quotes ao vivo...")
markets_raw = get_live_markets()

# extrai nível de preço e preços yes/no
import json as _json
rows = []
for m in markets_raw:
    q       = m.get("question") or m.get("title") or ""
    tokens  = m.get("clobTokenIds") or []
    if isinstance(tokens, str):
        try: tokens = _json.loads(tokens)
        except: tokens = [tokens]

    yes_tok = tokens[0] if tokens else None
    yes_mid = get_midpoint(yes_tok) if yes_tok else None
    if yes_mid is None:
        ltp = m.get("lastTradePrice")
        yes_mid = float(ltp) if ltp else None

    bid = float(m["bestBid"]) if m.get("bestBid") else None
    ask = float(m["bestAsk"]) if m.get("bestAsk") else None

    # extrai nível de preço numérico
    level = None
    for p in [150,110,105,100,95,90,85,80,75,70,65,60,55,50,45,40,35,30,25,20]:
        if f"{p},000" in q or f"{p*1000}" in q:
            level = p * 1_000
            break

    direction = "dn" if "dip" in q.lower() else "up"
    rows.append({
        "question" : q, "level": level, "direction": direction,
        "yes_bid"  : bid, "yes_ask": ask, "yes_mid": yes_mid,
    })

rows = [r for r in rows if r["level"] is not None]
rows.sort(key=lambda x: x["level"], reverse=True)

# ── 2. Tabela completa ────────────────────────────────────────────────────
NOW = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
print(f"\n{'='*100}")
print(f"ANALISE COMPLETA — What price will Bitcoin hit in March 2026?")
print(f"BTC atual: ${CURRENT:,}  |  Touch bar: ${TOUCH_BAR:,}  |  Vol período: {VOL_PERIOD*100:.1f}%  |  {NOW}")
print(f"{'='*100}")

print(f"\n{'Strike':>10}  {'Dir':>4}  "
      f"{'YES bid':>8}  {'YES mid':>8}  {'YES ask':>8}  "
      f"{'NO mid':>7}  "
      f"{'Barreira':>10}  "
      f"{'SD (N=4)':>10}  {'hits':>6}  "
      f"{'Δ Barr':>8}  {'Δ SD':>8}  "
      f"{'Trade':>18}")
print("─" * 120)

best_trades = []

for r in rows:
    lv   = r["level"]
    dire = r["direction"]
    ymid = r["yes_mid"]
    if ymid is None:
        continue

    no_mid  = round(1 - ymid, 3)
    b_prob  = barrier_prob(lv)           # P(YES) pelo modelo
    sd_data = sd_hit_rate(lv, dire)
    sd_prob = sd_data["rate"] / 100      # P(YES) pelo indicador

    # deltas: positivo = nossa estimativa MAIOR que o mercado
    delta_barr = (b_prob - ymid) * 100
    delta_sd   = (sd_prob - ymid) * 100

    # EV de comprar YES (usando modelo barreira como P)
    ev_yes  = ev(ymid, b_prob) * 100   # em ¢
    ev_no   = ev(ymid, b_prob) * (-1) * 100  # simetria: EV(NO) = -EV(YES) em ¢ ajustado

    # EV correto:
    # Comprar YES a ymid: EV = b_prob*(1-ymid) - (1-b_prob)*ymid
    ev_yes_val = b_prob * (1 - ymid) - (1 - b_prob) * ymid
    # Comprar NO a (1-ymid): EV = (1-b_prob)*ymid - b_prob*(1-ymid)  [= -ev_yes_val]
    ev_no_val  = -ev_yes_val

    # sinal de trade
    if ev_yes_val > 0.02:
        trade = f"BUY YES @ {ymid*100:.0f}¢"
    elif ev_no_val > 0.02:
        trade = f"BUY NO  @ {no_mid*100:.0f}¢"
    else:
        trade = "fair / neutro"

    # coleta melhores trades
    if abs(ev_yes_val) > 0.02 or abs(ev_no_val) > 0.02:
        best_trades.append({
            "level"      : lv,
            "direction"  : dire,
            "question"   : r["question"],
            "yes_mid"    : ymid,
            "no_mid"     : no_mid,
            "b_prob"     : b_prob,
            "sd_rate"    : sd_data["rate"],
            "sd_hits"    : sd_data["hits"],
            "sd_n"       : sd_data["n"],
            "ev_yes"     : ev_yes_val,
            "ev_no"      : ev_no_val,
            "delta_barr" : delta_barr,
            "delta_sd"   : delta_sd,
            "trade"      : trade,
            "pct_cur"    : sd_data["pct_from_current"],
        })

    print(f"${lv:>9,}  {'▲' if dire=='up' else '▼':>4}  "
          f"{(r['yes_bid'] or 0)*100:>7.1f}%  {ymid*100:>7.1f}%  {(r['yes_ask'] or 0)*100:>7.1f}%  "
          f"{no_mid*100:>6.1f}%  "
          f"{b_prob*100:>9.1f}%  "
          f"{sd_data['rate']:>9}%  {sd_data['hits']:>1}/{sd_data['n']:<4}  "
          f"{delta_barr:>+7.1f}pp  {delta_sd:>+7.1f}pp  "
          f"{trade}")

# ── 3. Ranking de trades por EV ───────────────────────────────────────────
print(f"\n{'='*100}")
print("RANKING POR EV (modelo barreira como estimativa de P)")
print(f"{'='*100}\n")
print(f"  {'#':>3}  {'Strike':>10}  {'Dir':>4}  {'Trade':>22}  "
      f"{'Custo':>8}  {'Ganho':>8}  {'EV/contrato':>13}  {'ROI EV':>9}  "
      f"{'Barreira':>10}  {'SD':>6}")
print(f"  {'─'*100}")

# ordena por |EV| decrescente
best_sorted = sorted(best_trades, key=lambda x: abs(x["ev_yes"]), reverse=True)

for i, t in enumerate(best_sorted, 1):
    if t["ev_yes"] > 0:  # BUY YES
        cost   = t["yes_mid"]
        profit = 1 - t["yes_mid"]
        ev_val = t["ev_yes"]
        side   = f"BUY YES @ {cost*100:.0f}¢"
    else:  # BUY NO
        cost   = t["no_mid"]
        profit = 1 - t["no_mid"]
        ev_val = t["ev_no"]
        side   = f"BUY NO  @ {cost*100:.0f}¢"

    roi_ev = ev_val / cost * 100  # EV como % do capital investido

    print(f"  {i:>3}  ${t['level']:>9,}  {'▲' if t['direction']=='up' else '▼':>4}  "
          f"{side:>22}  {cost*100:>7.1f}¢  {profit*100:>7.1f}¢  "
          f"{ev_val*100:>+11.1f}¢  {roi_ev:>+8.1f}%  "
          f"{t['b_prob']*100:>9.1f}%  {t['sd_rate']:>5}%")

# ── 4. Foco nas posições recomendadas ─────────────────────────────────────
print(f"\n{'='*100}")
print("DETALHE DAS POSIÇÕES COM MAIOR EDGE")
print(f"{'='*100}")

for t in best_sorted[:5]:
    if t["ev_yes"] > 0:
        cost  = t["yes_mid"]
        side  = "BUY YES"
        ev_v  = t["ev_yes"]
        p_win = t["b_prob"]
    else:
        cost  = t["no_mid"]
        side  = "BUY NO"
        ev_v  = t["ev_no"]
        p_win = 1 - t["b_prob"]

    print(f"""
  ── ${t['level']:,} ({'reach' if t['direction']=='up' else 'dip'}) ──────────────────────────────────
  Trade          : {side} a {cost*100:.1f}¢
  Ganho máx      : {(1-cost)*100:.1f}¢  |  Perda máx: {cost*100:.1f}¢
  P(ganho) barr  : {p_win*100:.1f}%  |  EV: {ev_v*100:+.1f}¢ por contrato
  P(ganho) SD    : {t['sd_rate']}% ({t['sd_hits']}/{t['sd_n']} eventos, 30d, ref touch bar)
  Distância atual: {t['pct_cur']:+.1f}% de ${CURRENT:,}""")

# ── 5. Múltiplas entradas para a posição $50k NO ─────────────────────────
t50 = next((t for t in best_trades if t["level"] == 50_000), None)
if t50:
    print(f"\n{'='*100}")
    print("ESTRUTURA DE ENTRADAS — BUY NO em <$50,000")
    print(f"{'='*100}")
    print(f"""
  Lógica: quando BTC cai (mas permanece acima do stop $60k),
  o YES token sobe (mercado fica nervoso) e o NO fica mais barato.
  A tese fundamental NÃO muda enquanto BTC > $60k.
  Cada queda do BTC que não viola o stop é uma oportunidade de entrada melhor.
""")

    # estimativa de NO price em diferentes BTC levels (usando modelo barreira)
    btc_scenarios = [68_830, 65_000, 62_500, 61_000]
    days_scenarios = [28, 24, 20, 16]  # dias restantes estimados (proxy)

    print(f"  {'BTC nível':>12}  {'Dias est.':>10}  {'YES (barr)':>12}  {'NO (barr)':>10}  "
          f"{'Custo NO':>10}  {'Ganho NO':>10}  {'ROI':>8}  {'P(NO) barr':>12}")
    print(f"  {'─'*90}")

    for btc, days in zip(btc_scenarios, days_scenarios):
        vol_p   = DAILY_VOL * np.sqrt(days)
        log_d   = abs(np.log(50_000 / btc))
        p_yes   = 2 * stats.norm.cdf(-log_d / vol_p)
        p_no    = 1 - p_yes
        no_cost = p_yes   # proxy: NO price ≈ 1 - YES_market (assume spread zero)
        no_gain = 1 - no_cost
        roi     = no_gain / no_cost * 100

        marker = " ◄ hoje" if btc == 68_830 else (" ◄ STOP" if btc <= 60_000 else "")
        print(f"  ${btc:>11,}  {days:>10}d  {p_yes*100:>11.1f}%  {p_no*100:>9.1f}%  "
              f"{no_cost*100:>9.1f}¢  {no_gain*100:>9.1f}¢  {roi:>7.1f}%  {p_no*100:>11.1f}%{marker}")

    print(f"""
  Stop absoluto: BTC < $60,000 → fechar 100% imediatamente.
  Abaixo de $60k a tese invalida — $50k deixa de ser impossível.
""")
