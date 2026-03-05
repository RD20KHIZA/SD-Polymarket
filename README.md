# Monthly Volatility Zones — Research Dashboard

A quantitative research dashboard that turns a TradingView volatility indicator into a full decision pipeline — from historical event study to live Polymarket trade signals.

---

## Research Foundation

This project is grounded in the methodology proposed by **Leandro Guerra** in:

> *Supply and Demand Levels Forecasting Based on Returns Volatility* — Diurnalis Series, 2022
> [academia.edu/90754102](https://www.academia.edu/90754102/Supply_and_Demand_Levels_Forecasting_Based_on_Returns_Volatility)

The paper introduces a quantitative framework for identifying supply and demand zones using returns-based volatility, replacing subjective chart interpretation with measurable, scale-free metrics generalizable across asset classes. This dashboard operationalizes that framework on BTC/USDT 4H data, extending it with an empirical event study and a live Polymarket edge scanner.

---

## Overview

The project is built in two layers:

**Layer 1 — Vol Zone Study**
Detects monthly volatility zone touches on 4H OHLCV data and measures the forward return distribution at every holding period up to 180 days. Answers: *"when price touches a σ zone, what happens next?"*

**Layer 2 — Polymarket Scanner**
Takes the empirical hit-rate surface from Layer 1 and applies it to live Polymarket binary markets ("Will Bitcoin reach $X in [month]?"). Blends a GBM barrier model (with drift, Deribit implied vol) with Wilson CI–adjusted historical data via adaptive consensus weights to compute edge, expected value, and half-Kelly position sizing per strike.

---

## The Indicator

The volatility zones are derived from a Pine Script v6 indicator (`INDICATOR` file). Zone formula:

```
src         = hlcc4 = (high + low + close + close) / 4
log_ret     = log(src[t] / src[t-1])
annual_vol  = rolling_std(log_ret, 360 days) × √365
monthly_vol = annual_vol / √12
zone        = monthly_open × (1 ± n_sigma × monthly_vol)
```

Zones are fixed for the entire month and reset on the first bar of each new month. Supply zones sit above the monthly open; demand zones below.

---

## Architecture

```
backtest/
├── app.py                    # Streamlit app — main entry point
├── zone_calculator.py        # Zone formula (Python replica of Pine Script)
├── data_fetcher.py           # OHLCV fetch from Binance via vectorbt/CCXT (Parquet cache)
├── event_study.py            # Zone touch detection + forward return computation
├── visualization.py          # Plotly charts (TradingView dark theme)
├── vbt_backtest.py           # VectorBT portfolio simulation (optional)
├── scanner_config.py         # Model constants and weights
├── polymarket_live.py        # Live odds fetch from Polymarket Gamma + CLOB APIs
├── polymarket_scanner.py     # Barrier model, Kelly, edge computation
└── tab_polymarket_scanner.py # Polymarket Scanner Streamlit tab

data/                         # Auto-created — Parquet cache (git-ignored)
INDICATOR                     # Pine Script v6 source
```

---

## Installation

**Requirements:** Python 3.10+

```bash
git clone https://github.com/YOUR_USERNAME/monthly-volatility-zones-indicator.git
cd monthly-volatility-zones-indicator

python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

pip install -r backtest/requirements.txt
```

> **Note:** `vectorbt` installation can take a few minutes. If you don't need the VectorBT Sweep tab, it will be automatically hidden if the package is not installed.

---

## Running the Dashboard

```bash
cd backtest
streamlit run app.py
```

Opens at `http://localhost:8501`.

---

## Usage

### Vol Zone Study

1. Select symbol (default: BTC/USDT) and start date in the sidebar
2. Adjust vol lookback (default: 360 days) and max holding period
3. Click **▶ Run Study**

On first run, data is downloaded from Binance and cached as Parquet. Subsequent runs use the cache with incremental updates only.

### Polymarket Scanner

The scanner tab is always visible. It fetches live odds automatically from Polymarket for the current month's BTC event (`what-price-will-bitcoin-hit-in-[month]-[year]`).

- **Run the Vol Zone Study first** to enable historical SD (empirical hit-rate blending)
- Without the study, the scanner runs on barrier model only (still functional)
- Volatility inputs are **auto-fetched** (Deribit DVOL for barrier, EWMA realized for zones, drift from EWMA 90d) — no manual entry needed
- Click **🔄 Refresh all** to force re-fetch of odds, vol, and drift (cache TTL = 5–10 minutes)

---

## Model Details

### Barrier Probability (GBM with Drift)

First-passage probability under Geometric Brownian Motion with drift (Shreve Ch. 7):

```
T = days_remaining / 365
m = drift − 0.5 × σ²          (log-space drift)
b = |ln(K / S)|                (log-distance to strike)

Upper barrier (K > S):
  P = Φ(−d₁) + exp(2mb/σ²) × Φ(d₂)
  where d₁ = (b − mT) / (σ√T),  d₂ = (−b − mT) / (σ√T)

Lower barrier (K < S): flip drift sign, same formula.

drift = 0 collapses to:  P = 2 × Φ(−b / (σ√T))
```

**Volatility inputs (auto-fetched):**
- `σ_barrier` = Deribit DVOL (30-day implied vol index) — forward-looking
- `σ_zone` = Vol Zone Study realized vol or EWMA 30d — for σ distance calculation
- `drift` = EWMA of daily log-returns (halflife 90d) × 50% shrinkage toward zero

### Historical SD (Wilson CI + Sigma Interpolation)

The Vol Zone Study produces a hit-rate surface over (σ, k, direction). The scanner queries this surface using:

1. **1D linear interpolation in σ** between the two adjacent buckets (not nearest-neighbor)
2. **Wilson score CI** center estimate (shrinks toward 50% for small N)
3. **N_eff** via weighted harmonic mean of the two interpolated nodes

### Adaptive Consensus

```
confidence_n = 1 − 1 / (1 + N/25)
precision    = clamp((0.70 − CI_width) / 0.40, 0, 1)
w_sd_eff     = W_SD × confidence_n × precision
p_internal   = (1 − w_sd_eff) × p_barrier + w_sd_eff × p_sd
```

SD weight scales from ~0% (N=4) to ~32% (N=100). Barrier dominates when SD data is weak.

### Edge & Signal

```
edge_pp = (p_internal − poly_yes) × 100

edge_pp > min_edge  →  BUY YES   (cost = ask price, bid-ask adjusted)
edge_pp < −min_edge →  BUY NO    (cost = 1 − bid price)
else                →  MONITOR
```

### Position Sizing (Half-Kelly)

```
b         = (1 − exec_cost) / exec_cost
full_kelly = max(0, (p × b − q) / b)
kelly_%   = full_kelly × 0.5 × 100
```

Execution cost is bid-ask adjusted (ask for BUY YES, 1−bid for BUY NO).

### Calibration

`min_sigma` threshold is calibrated via exact binomial test (`scipy.stats.binomtest`, α=0.05) per sigma level. Falls back to a 5pp-divergence heuristic if no sigma rejects H₀.

### Signal Strength

| Label | Condition |
|---|---|
| `★★ STRONG` | Barrier and SD agree on direction + \|edge\| ≥ 12pp |
| `★ MODERATE` | Models agree but \|edge\| < 12pp, or SD unavailable |
| `⚠ CONFLICTING` | Barrier and SD disagree on direction |

---

## Dashboard Tabs

| Tab | Description |
|---|---|
| Price Chart | 4H candlestick + zone overlays + first-touch markers |
| Return Curves | Mean ± 1σ forward return vs holding period k |
| Hit Rate | Directional hit rate vs k (50% = random baseline) |
| Sharpe vs k | Per-trade Sharpe — identifies empirically optimal exit |
| Distribution | Violin plot of returns at a chosen k |
| Full Report | All panels in a single 4×2 grid |
| Data | Summary table + raw events + CSV download |
| VectorBT Sweep | Portfolio simulation with no-overlap constraint *(requires vectorbt)* |
| Polymarket Scanner | Live edge scanner with barrier + SD model |

---

## Configuration

Key constants in `backtest/scanner_config.py`:

| Parameter | Default | Description |
|---|---|---|
| `MIN_N_EVENTS` | 8 | Minimum events in SD bucket to use historical data |
| `MIN_EDGE_PP` | 8.0 | Minimum edge (pp) to generate a BUY signal |
| `STRONG_EDGE_PP` | 12.0 | Edge threshold for STRONG classification |
| `ANNUAL_VOL` | 0.65 | Fallback annualized vol (used only if API fetch fails) |
| `W_BARRIER` | 0.6 | Base barrier weight in consensus (adaptive scaling applied) |
| `W_SD` | 0.4 | Base SD weight — scaled by confidence_n × precision |
| `KELLY_FRACTION` | 0.5 | Half-Kelly multiplier |
| `EWMA_HALFLIFE_DAYS` | 30 | Halflife for EWMA realized vol |
| `DRIFT_HALFLIFE_DAYS` | 90 | Halflife for EWMA drift estimation |
| `DRIFT_SHRINKAGE` | 0.5 | Shrink drift 50% toward zero |
| `WILSON_Z` | 1.96 | Z-score for Wilson CI (95%) |
| `CALIBRATION_ALPHA` | 0.05 | Significance level for binomial calibration test |

---

## Data Sources

| Source | Used For |
|---|---|
| Binance (via vectorbt/CCXT) | 4H OHLCV for the event study |
| Binance REST API | Live BTC/USDT spot price, daily klines for EWMA vol & drift |
| Deribit public API | BTC DVOL (30-day implied vol index) for barrier model |
| Polymarket Gamma API | Event metadata and market list |
| Polymarket CLOB API | Live YES/NO token mid-prices + bid/ask |

No API keys required — all public endpoints.

---

## Disclaimer

This tool is for research and educational purposes only. Nothing here constitutes financial advice. Polymarket markets involve real financial risk. Past hit rates do not guarantee future results.

---

## License

MIT
