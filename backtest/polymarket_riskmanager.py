"""
Risk management analysis: Buy No em <$50k Polymarket (março 2026)
Cobre três dimensões: preço, tempo, e zones do indicador SD.
"""

import sys
sys.stdout.reconfigure(encoding="utf-8")

from pathlib import Path
import numpy as np
import pandas as pd
from scipy import stats

BASE = Path(__file__).parent.parent
DATA = BASE / "data"
sys.path.insert(0, str(Path(__file__).parent))

from data_fetcher import resample_to_daily
from zone_calculator import compute_zones, ZONE_SIGMAS, _sigma_col

# ── parâmetros do trade ────────────────────────────────────────────────────
CURRENT_PRICE   = 68_830
ENTRY_DATE      = pd.Timestamp("2026-02-06", tz="UTC")
CURRENT_DATE    = pd.Timestamp("2026-03-03", tz="UTC")
EXPIRY_DATE     = pd.Timestamp("2026-03-31 23:59:59", tz="UTC")
TARGET_BARRIER  = 50_000
POLY_COST_NO    = 0.12      # custo de 1 contrato de NO (12¢)
POLY_PAYOUT_NO  = 1.00
PROFIT_NO       = POLY_PAYOUT_NO - POLY_COST_NO  # 88¢ se NO resolve

DAYS_ELAPSED    = (CURRENT_DATE - ENTRY_DATE).days        # 25 dias
DAYS_REMAINING  = (EXPIRY_DATE  - CURRENT_DATE).days      # ~28 dias
BTC_ANN_VOL     = 0.65                                     # vol realizada BTC
DAILY_VOL       = BTC_ANN_VOL / np.sqrt(365)

# ── carregar dados e zonas ─────────────────────────────────────────────────
print("Carregando dados e zonas...")
old  = pd.read_parquet(DATA / "BTC_USDT_4h_2018-01-01.parquet")
new  = pd.read_parquet(DATA / "BTCUSDT_4h_binance.parquet")
for df in (old, new):
    df.columns = [c.lower() for c in df.columns]
    df.index.name = "timestamp"
df_4h = pd.concat([old, new]).pipe(
    lambda x: x[~x.index.duplicated(keep="last")]).sort_index()

daily   = resample_to_daily(df_4h)
df_z    = compute_zones(df_4h, daily, lookback=360)

# ── zonas de março 2026 ────────────────────────────────────────────────────
mar_bars = df_z.loc["2026-03-01":"2026-03-31"]
march_open = mar_bars["monthly_open"].iloc[0]
march_vol  = mar_bars["monthly_vol"].iloc[0]

print(f"\n{'='*65}")
print("ZONAS DE MARCO 2026")
print(f"{'='*65}")
print(f"Monthly open : ${march_open:>10,.2f}")
print(f"Monthly vol  : {march_vol*100:>9.2f}%")
print()
print(f"{'Sigma':>6}  {'Supply':>12}  {'Demand':>12}  {'Dist atual (demand)':>20}")
print(f"{'─'*55}")
for s in ZONE_SIGMAS:
    sup = march_open * (1 + s * march_vol)
    dem = march_open * (1 - s * march_vol)
    pct_dist = (dem / CURRENT_PRICE - 1) * 100
    marker = " ◄ $50k" if abs(dem - TARGET_BARRIER) < 2000 else ""
    print(f"  {s:>4.2f}  ${sup:>11,.0f}  ${dem:>11,.0f}  {pct_dist:>+18.1f}%{marker}")

# ── sigma do $50k em relação ao monthly open de março ─────────────────────
sigma_50k = (march_open - TARGET_BARRIER) / (march_open * march_vol)
print(f"\n$50k corresponde a {sigma_50k:.2f}σ demand de março")
print(f"Distância atual até $50k: {(TARGET_BARRIER/CURRENT_PRICE-1)*100:.1f}%")

# ── 1. ANÁLISE DE PREÇO — O que precisa acontecer? ────────────────────────
print(f"\n{'='*65}")
print("1. ANALISE DE PRECO — NIVEIS CRITICOS")
print(f"{'='*65}")

levels = [
    ("Máx 30d (Feb-26)",        72_271, "já atingido"),
    ("Atual",                   68_830, "referência"),
    ("Monthly open março",      march_open, "suporte-pivot"),
    ("1σ demand março",         march_open*(1 - 1.0*march_vol), "suporte técnico"),
    ("Touch bar Feb-26",        64_168, "suporte histórico"),
    ("Low Feb 23-24",           62_510, "suporte recente"),
    ("Touch low Feb-26",        60_000, "fundo absoluto Feb"),
    ("1.5σ demand março",       march_open*(1 - 1.5*march_vol), "suporte SD"),
    ("2σ demand março",         march_open*(1 - 2.0*march_vol), "zona crítica"),
    ("2.5σ demand março",       march_open*(1 - 2.5*march_vol), "zona extrema"),
    ("BARREIRA POLYMARKET",     50_000, "<<< KNOCK-OUT >>>"),
    ("3σ demand março",         march_open*(1 - 3.0*march_vol), "≈ $50k"),
]

for name, price, note in levels:
    pct = (price / CURRENT_PRICE - 1) * 100
    bar = "█" * max(0, int((price / CURRENT_PRICE) * 30)) if price < CURRENT_PRICE else "·"
    print(f"  {name:<25} ${price:>9,.0f}   {pct:>+7.1f}%   {note}")

# ── SEQUÊNCIA DE SUPORTES ATÉ $50k ────────────────────────────────────────
print(f"\n  Para chegar a $50k, o mercado precisaria quebrar:")
supports = [
    ("Monthly open março", march_open, -((march_open - 68830)/68830)*100),
    ("1σ demand março",    march_open*(1 - 1.0*march_vol), None),
    ("Touch low Feb-26",   60_000, None),
    ("1.5σ demand março",  march_open*(1 - 1.5*march_vol), None),
    ("2σ demand março",    march_open*(1 - 2.0*march_vol), None),
    ("2.5σ demand março",  march_open*(1 - 2.5*march_vol), None),
    ("$50k (barreira)",    50_000, None),
]
prev = CURRENT_PRICE
for name, price, _ in supports:
    drop = (price/prev - 1)*100
    prev = price
    print(f"    → {name:<25} ${price:>9,.0f}   ({drop:+.1f}% do nível anterior)")

# ── 2. ANÁLISE DE TEMPO — Decaimento da probabilidade ─────────────────────
print(f"\n{'='*65}")
print("2. ANALISE DE TEMPO — DECAIMENTO DA PROBABILIDADE")
print(f"{'='*65}")
print(f"\n  Modelo: barreira log-normal, vol = {BTC_ANN_VOL*100:.0f}% ann, S = ${CURRENT_PRICE:,}")
print(f"  Barreira: ${TARGET_BARRIER:,}  |  Distância: {np.log(TARGET_BARRIER/CURRENT_PRICE)*100:.1f}% (log)")
print()
print(f"  {'Data':<14} {'Dias rest.':>10} {'σ√T (vol do período)':>22} {'P(tocar $50k)':>15} {'P(NO vence)':>12}")
print(f"  {'─'*73}")

barrier_log = np.log(TARGET_BARRIER / CURRENT_PRICE)
checkpoints = list(range(0, DAYS_REMAINING + 1, 3)) + [DAYS_REMAINING]
checkpoints = sorted(set(checkpoints))

for d in checkpoints:
    days_left = DAYS_REMAINING - d
    if days_left <= 0:
        p_touch = 0.0
    else:
        vol_period = DAILY_VOL * np.sqrt(days_left)
        # barrier probability (absorbing at lower barrier, no drift)
        p_touch = 2 * stats.norm.cdf(barrier_log / vol_period)

    p_no_wins = 1 - p_touch
    date_str  = (CURRENT_DATE + pd.Timedelta(days=d)).strftime("%d/%m/%Y")
    days_left_str = f"{DAYS_REMAINING - d}d"
    vol_str   = f"{DAILY_VOL * np.sqrt(max(DAYS_REMAINING-d,0))*100:.1f}%"
    marker    = " ◄ hoje" if d == 0 else ""

    print(f"  {date_str:<14} {days_left_str:>10} {vol_str:>22} {p_touch*100:>13.1f}% {p_no_wins*100:>10.1f}%{marker}")

# ── 3. KELLY E SIZING ──────────────────────────────────────────────────────
print(f"\n{'='*65}")
print("3. SIZING — KELLY CRITERION")
print(f"{'='*65}")

for p_est_label, p_no in [
    ("Indicador SD (0/4 histórico)", 1.00),
    ("Modelo barreira (log-normal)", 1 - 2 * stats.norm.cdf(barrier_log / (DAILY_VOL * np.sqrt(DAYS_REMAINING)))),
    ("Polymarket (12%)",             0.88),
    ("Conservador (10% margem extra)", 0.90),
]:
    p_yes = 1 - p_no
    b     = PROFIT_NO / POLY_COST_NO  # odds: ganho / custo
    kelly = (p_no * b - p_yes) / b
    half  = kelly / 2
    print(f"\n  Estimativa: {p_est_label}")
    print(f"    P(NO vence) = {p_no*100:.0f}%  |  Odds = {b:.2f}x")
    print(f"    Full Kelly  = {kelly*100:.1f}%  →  Half-Kelly = {half*100:.1f}% do capital alocável")

# ── 4. CONTEXTO HISTÓRICO DOS N=4 EVENTOS ─────────────────────────────────
print(f"\n{'='*65}")
print("4. CONTEXTO HISTORICO — MINIMOS EM 30 DIAS (N=4 excl. Feb-26)")
print(f"{'='*65}")
print()
events_hist = [
    ("Mar-20 (COVID crash)", 4_800,  3_782,  -21.2, "pior evento; ainda -21.2% do touch"),
    ("Mai-21 (China ban)",   37_319, 31_000, -16.9, "Elon tweets + mining ban"),
    ("Jun-22 (3AC/Celsius)", 19_259, 17_622,  -8.5, "DeFi/CeFi collapse"),
    ("Nov-25",               84_049, 80_600,  -4.1, "evento mais recente pre-Feb26"),
]

print(f"  {'Evento':<25} {'Touch close':>12} {'Min 30d':>10} {'%':>7}  {'Nota'}")
print(f"  {'─'*75}")
for ev, ref, lo, pct, note in events_hist:
    needed_equiv = ref * (TARGET_BARRIER / CURRENT_PRICE)  # não diretamente comparável
    print(f"  {ev:<25} ${ref:>10,.0f} ${lo:>9,.0f} {pct:>+6.1f}%  {note}")

print(f"""
  Conclusão: o pior evento histórico (COVID) só chegou a -21.2% em 30 dias.
  Para $50k a partir de $68,830: precisa de -27.4%.
  Nenhum evento 2.25σ jamais caiu tanto dentro da janela de 30 dias.
""")

# ── 5. CENARIOS DE SAÍDA / STOP ────────────────────────────────────────────
print(f"{'='*65}")
print("5. GESTAO DE RISCO — GATILHOS DE SAIDA")
print(f"{'='*65}")
print(f"""
  NIVEL 1 — Monitoramento (sem ação):
    Preço < ${march_open:,.0f} (monthly open março)  → -{ (1 - march_open/CURRENT_PRICE)*100:.1f}% do atual
    Sinal: perda do pivot mensal. Atenção redobrada.

  NIVEL 2 — Alerta (reduzir 50% da posição):
    Preço < $62,510 (low de 23-24 fev) → -{(1-62510/CURRENT_PRICE)*100:.1f}% do atual
    Sinal: suporte recente quebrado; momentum bearish confirmado.
    Custo de sair: sacrifica 88¢ de ganho potencial, mas elimina risco de perda total.

  NIVEL 3 — Stop total (fechar posição):
    Preço < $60,000 (touch low Feb-26)  → -{(1-60000/CURRENT_PRICE)*100:.1f}% do atual
    Sinal: fundo absoluto de fevereiro perdido. Cenário novo.
    A partir daqui, $50k não é mais improvável.

  KEEP (não fazer nada):
    Cada dia que passa SEM quebrar $62,510 reduz a P($50k) via tempo.
    A partir de {(CURRENT_DATE + pd.Timedelta(days=14)).strftime("%d/%b")}: vol de período < 10%,
    P($50k) cai abaixo de 5% mesmo com drift negativo.
""")

print(f"{'='*65}")
print("RESUMO EXECUTIVO")
print(f"{'='*65}")
print(f"""
  Posição : Buy NO em <$50k a 12¢  (ganho 88¢ se BTC > $50k em 31/mar)
  Edge    : Indicador 0/4 histórico, modelo barreira ~5%, Poly diz 12%
  Sizing  : Half-Kelly conservador → ~15–20% do capital destinado a Poly

  Checkpoints de preço:
    ${march_open:,.0f}  → atenção (monthly open)
    $62,510 → reduzir 50% (low fev 23-24)
    $60,000 → fechar tudo (fundo fev-26 quebrado)

  Checkpoints de tempo:
    {(CURRENT_DATE + pd.Timedelta(days=7)).strftime("%d/%b")}  → P($50k) ≈ {2*stats.norm.cdf(barrier_log/(DAILY_VOL*np.sqrt(DAYS_REMAINING-7)))*100:.0f}%  — confirma tese se preço sustenta
    {(CURRENT_DATE + pd.Timedelta(days=14)).strftime("%d/%b")}  → P($50k) ≈ {2*stats.norm.cdf(barrier_log/(DAILY_VOL*np.sqrt(DAYS_REMAINING-14)))*100:.0f}%  — posição confortável
    {(CURRENT_DATE + pd.Timedelta(days=21)).strftime("%d/%b")}  → P($50k) ≈ {2*stats.norm.cdf(barrier_log/(DAILY_VOL*np.sqrt(max(DAYS_REMAINING-21,1))))*100:.0f}%  — praticamente resolvida
""")
