"""
Polymarket vs Indicador — análise de 30 dias
Para cada evento 2.25σ demand, computa:
  - max_high e min_low dentro de k=1..180 bars (= 30 dias em 4H)
  - % dos eventos que atingiram cada alvo do Polymarket dentro da janela
Referência: close da touch bar de cada evento
"""

import sys
sys.stdout.reconfigure(encoding="utf-8")

from pathlib import Path
import numpy as np
import pandas as pd

# ── paths ──────────────────────────────────────────────────────────────────
BASE = Path(__file__).parent.parent
DATA = BASE / "data"
sys.path.insert(0, str(Path(__file__).parent))

from data_fetcher import resample_to_daily
from zone_calculator import compute_zones
from event_study import detect_zone_touches

K_WINDOW = 180   # 180 bars × 4H = 30 dias
SIGMA_TARGET = 2.25

# ── Polymarket levels (absolutos, março 2026) ──────────────────────────────
POLY_UPSIDE   = [75_000, 80_000, 85_000]
POLY_DOWNSIDE = [65_000, 60_000, 55_000, 50_000]

# ── 1. Carregar e mesclar dados ────────────────────────────────────────────
print("Carregando dados...")

old  = pd.read_parquet(DATA / "BTC_USDT_4h_2018-01-01.parquet")
new  = pd.read_parquet(DATA / "BTCUSDT_4h_binance.parquet")

# normalizar colunas
for df in (old, new):
    df.columns = [c.lower() for c in df.columns]
    df.index.name = "timestamp"

df_4h = (
    pd.concat([old, new])
    .pipe(lambda x: x[~x.index.duplicated(keep="last")])
    .sort_index()
)
print(f"Total bars: {len(df_4h):,}  ({df_4h.index[0].date()} → {df_4h.index[-1].date()})")

# ── 2. Zones ───────────────────────────────────────────────────────────────
daily = resample_to_daily(df_4h)
df_zones = compute_zones(df_4h, daily, lookback=360)

# ── 3. Eventos 2.25σ demand ────────────────────────────────────────────────
events_all = detect_zone_touches(df_zones)
events = events_all[
    (events_all["sigma"] == SIGMA_TARGET) &
    (events_all["direction"] == "demand")
].copy().reset_index(drop=True)

print(f"\nEventos 2.25σ demand encontrados: {len(events)}")
print(events[["timestamp", "month", "bar_close", "zone_level"]].to_string(index=True))

# ── 4. Índices posicionais ─────────────────────────────────────────────────
closes = df_4h["close"].values
highs  = df_4h["high"].values
lows   = df_4h["low"].values
ts_idx = {ts: i for i, ts in enumerate(df_4h.index)}

# ── 5. Para cada evento: max_high e min_low em k=1..180 ───────────────────
print(f"\n{'─'*72}")
print(f"Janela de análise: k = 1 a {K_WINDOW} bars = {K_WINDOW//6:.0f} dias\n")

rows = []
for _, ev in events.iterrows():
    iloc = ts_idx.get(ev["timestamp"])
    if iloc is None:
        continue
    ref = closes[iloc]                      # close da touch bar (referência)
    end = min(iloc + K_WINDOW, len(highs) - 1)
    n   = end - iloc

    if n <= 0:
        continue

    fwd_highs = highs[iloc + 1 : end + 1]
    fwd_lows  = lows [iloc + 1 : end + 1]

    max_high = fwd_highs.max() if len(fwd_highs) else np.nan
    min_low  = fwd_lows.min()  if len(fwd_lows)  else np.nan

    max_pct = (max_high / ref - 1) * 100
    min_pct = (min_low  / ref - 1) * 100

    rows.append({
        "month"    : ev["month"],
        "timestamp": ev["timestamp"].date(),
        "ref_close": round(ref, 0),
        "max_high" : round(max_high, 0),
        "max_pct"  : round(max_pct, 1),
        "min_low"  : round(min_low, 0),
        "min_pct"  : round(min_pct, 1),
        "n_bars"   : n,
    })

results = pd.DataFrame(rows)
print(results.to_string(index=False))

# ── 6. Probabilidades por alvo ─────────────────────────────────────────────
# Para o Feb-26, o ref_close é ~64.168 (touch bar close)
# Convertemos os alvos Polymarket em % do ref_close do Feb-26
feb26 = results[results["month"] == "2026-02"].iloc[0] if not results[results["month"] == "2026-02"].empty else None
ref_feb26 = feb26["ref_close"] if feb26 is not None else 64_168

print(f"\nRef close Feb-26: ${ref_feb26:,.0f}")
print(f"{'─'*72}")

# Upside: % dos eventos (excl. Feb-26 atual) cujo max_high dentro de 30d
# atingiu >= target_pct
hist = results[results["month"] != "2026-02"].copy()  # excl. evento atual

print(f"\n{'='*60}")
print(f"UPSIDE — alvos Polymarket março 2026")
print(f"{'='*60}")
print(f"{'Alvo':>10}  {'% do ref Feb-26':>16}  {'N hits / N-1':>14}  {'P histórica':>12}  {'Poly odds':>10}")
print(f"{'─'*60}")

for target in POLY_UPSIDE:
    pct_needed = (target / ref_feb26 - 1) * 100
    hits = (hist["max_pct"] >= pct_needed).sum()
    n    = len(hist)
    prob = hits / n if n > 0 else np.nan

    # odds Polymarket (da imagem)
    poly_map = {75_000: "42%", 80_000: "21%", 85_000: "10%"}

    print(f"${target:>8,.0f}  {pct_needed:>+14.1f}%  {hits:>5} / {n:<7}  {prob*100:>10.0f}%  {poly_map.get(target,'?'):>10}")

print(f"\n{'='*60}")
print(f"DOWNSIDE — alvos Polymarket março 2026")
print(f"{'='*60}")
print(f"{'Alvo':>10}  {'% do ref Feb-26':>16}  {'N hits / N-1':>14}  {'P histórica':>12}  {'Poly odds':>10}")
print(f"{'─'*60}")

for target in POLY_DOWNSIDE:
    pct_needed = (target / ref_feb26 - 1) * 100
    hits = (hist["min_pct"] <= pct_needed).sum()
    n    = len(hist)
    prob = hits / n if n > 0 else np.nan

    poly_map = {65_000: "84%", 60_000: "48%", 55_000: "22%", 50_000: "12%"}

    print(f"${target:>8,.0f}  {pct_needed:>+14.1f}%  {hits:>5} / {n:<7}  {prob*100:>10.0f}%  {poly_map.get(target,'?'):>10}")

# ── 7. Detalhes por evento (quem chegou onde) ──────────────────────────────
print(f"\n{'='*72}")
print("DETALHE POR EVENTO — quais alvos foram atingidos dentro de 30 dias")
print(f"{'='*72}")

all_targets = [("up", t) for t in POLY_UPSIDE] + [("dn", t) for t in POLY_DOWNSIDE]

header = f"{'Mês':<12} {'Ref':>10} {'Max 30d':>10} {'Min 30d':>10} | " + \
         "  ".join(f"${t//1000:>2}k" for _, t in all_targets)
print(header)
print("─" * len(header))

for _, r in results.iterrows():
    ref = r["ref_close"]
    cells = []
    for direction, target in all_targets:
        pct = (target / ref_feb26 - 1) * 100
        if direction == "up":
            hit = r["max_pct"] >= pct
        else:
            hit = r["min_pct"] <= pct
        cells.append("  Y " if hit else "  . ")
    row = (f"{str(r['month']):<12} ${r['ref_close']:>9,.0f} ${r['max_high']:>9,.0f} "
           f"${r['min_low']:>9,.0f} |" + "".join(cells))
    print(row)

print(f"\n(Y = atingiu dentro de {K_WINDOW} bars / 30 dias | . = não atingiu)")
print(f"\nNota: Feb-26 é excluído dos denominadores — evento em curso.")
