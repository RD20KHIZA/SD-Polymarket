"""
Polymarket Scanner v2 — módulo principal (sem side effects, sem prints).

Fetch de odds: usar fetch_active_market() de polymarket_live.py.

Funções públicas:
  fetch_btc_price()                          → float
  calibrate_min_sigma(df_hitrate, ...)       → float
  get_scanner_data(...)                      → pd.DataFrame
  decay_table(strike, btc_price, ...)        → pd.DataFrame
"""

from __future__ import annotations

import math
from datetime import datetime, timezone, timedelta
from typing import Optional

import numpy as np
import pandas as pd
import requests
from scipy import stats as scipy_stats

import scanner_config as cfg


# ── Wilson confidence interval ─────────────────────────────────────────────

def wilson_interval(hits: int, n: int, z: float = cfg.WILSON_Z) -> tuple[float, float, float]:
    """Wilson score interval for binomial proportion.
    Returns (center, lower, upper). Shrinks toward 0.5 for small N."""
    if n == 0:
        return 0.5, 0.0, 1.0
    p_hat = hits / n
    denom = 1 + z**2 / n
    center = (p_hat + z**2 / (2 * n)) / denom
    margin = z * math.sqrt(p_hat * (1 - p_hat) / n + z**2 / (4 * n**2)) / denom
    return center, max(0.0, center - margin), min(1.0, center + margin)


# ── fetch BTC spot ────────────────────────────────────────────────────────────

def fetch_btc_price() -> float:
    """Preço spot BTC/USDT via Binance REST (sem autenticação)."""
    r = requests.get(
        "https://api.binance.com/api/v3/ticker/price",
        params={"symbol": "BTCUSDT"}, timeout=5,
    )
    r.raise_for_status()
    return float(r.json()["price"])


# ── realized vol (EWMA) ────────────────────────────────────────────────────

def fetch_realized_vol(
    halflife_days: int = cfg.EWMA_HALFLIFE_DAYS, lookback: int = 120,
) -> float:
    """EWMA annualized vol from recent Binance daily klines."""
    r = requests.get(
        "https://api.binance.com/api/v3/klines",
        params={"symbol": "BTCUSDT", "interval": "1d", "limit": lookback},
        timeout=10,
    )
    r.raise_for_status()
    closes = np.array([float(k[4]) for k in r.json()])
    log_ret = np.diff(np.log(closes))
    # EWMA variance (exponential weighting, recent data weighted more)
    alpha = 1 - math.exp(-math.log(2) / halflife_days)
    var = 0.0
    for ret in log_ret:
        var = alpha * ret**2 + (1 - alpha) * var
    return math.sqrt(var * 365)


# ── Deribit implied vol (DVOL) ─────────────────────────────────────────────

def fetch_deribit_iv() -> float:
    """BTC DVOL (30-day implied vol index) from Deribit public API.
    Uses get_volatility_index_data — OHLC candles of the DVOL index.
    Returns annualized implied vol in 0-1 scale (e.g., 0.55 = 55%)."""
    import time
    now_ms = int(time.time() * 1000)
    ago_ms = now_ms - 7200_000  # 2 hours window to ensure we get data
    r = requests.get(
        "https://www.deribit.com/api/v2/public/get_volatility_index_data",
        params={
            "currency": "BTC",
            "resolution": "3600",
            "start_timestamp": str(ago_ms),
            "end_timestamp": str(now_ms),
        },
        timeout=10,
    )
    r.raise_for_status()
    data = r.json()["result"]["data"]  # [[ts, open, high, low, close], ...]
    if not data:
        raise ValueError("Empty DVOL data from Deribit")
    dvol_close = data[-1][4]  # last candle close, e.g. 54.95
    return dvol_close / 100.0


# fetch de odds removido deste módulo — usar fetch_active_market() de polymarket_live.py


# ── modelo de barreira ────────────────────────────────────────────────────────

def barrier_prob(
    strike: float, current: float, annual_vol: float, days: int,
    drift: float = 0.0,
) -> float:
    """
    P(ever touch strike during [0, T]) — GBM with drift.

    When drift=0, reduces to the classic reflection formula:
        P = 2 × Φ(−|b| / σ√T)

    With drift μ (annualized, risk-neutral adjusted internally as m = μ − σ²/2):
        For upper barrier (strike > current):
            P = Φ((b − mT) / σ√T) + exp(2mb/σ²) × Φ((−b − mT) / σ√T)
            where b = ln(strike/current)
        For lower barrier (strike < current):
            P = Φ((−b + mT) / σ√T) + exp(−2mb/σ²) × Φ((b + mT) / σ√T)
            where b = ln(current/strike) > 0

    Reference: Shreve, "Stochastic Calculus for Finance II", Ch. 7.
    """
    if days <= 0:
        return 0.0

    T     = days / 365
    sigma = annual_vol
    vol_t = sigma * math.sqrt(T)
    m     = drift - 0.5 * sigma**2  # drift-adjusted (GBM log-space drift)

    if strike > current:
        # upper barrier
        b = math.log(strike / current)  # > 0
    else:
        # lower barrier
        b = math.log(current / strike)  # > 0 (distance, always positive)
        m = -m  # flip drift for lower barrier symmetry

    if vol_t < 1e-12:
        return 0.0

    # P(max of GBM path >= barrier)
    d1 = (b - m * T) / vol_t
    d2 = (-b - m * T) / vol_t

    # Guard against overflow in exp(2mb/σ²)
    exponent = 2 * m * b / (sigma**2)
    if exponent > 500:
        exp_term = float("inf")
    elif exponent < -500:
        exp_term = 0.0
    else:
        exp_term = math.exp(exponent)

    p = scipy_stats.norm.cdf(-d1) + exp_term * scipy_stats.norm.cdf(d2)
    return float(min(max(p, 0.0), 1.0))


def estimate_drift(
    halflife_days: int = cfg.DRIFT_HALFLIFE_DAYS,
    shrinkage: float = cfg.DRIFT_SHRINKAGE,
    lookback: int = 120,
) -> float:
    """Estimate annualized BTC drift via EWMA of daily log-returns.
    Applies shrinkage toward zero to avoid overfitting to recent momentum."""
    r = requests.get(
        "https://api.binance.com/api/v3/klines",
        params={"symbol": "BTCUSDT", "interval": "1d", "limit": lookback},
        timeout=10,
    )
    r.raise_for_status()
    closes = np.array([float(k[4]) for k in r.json()])
    log_ret = np.diff(np.log(closes))
    # EWMA mean
    alpha = 1 - math.exp(-math.log(2) / halflife_days)
    ewma_mean = 0.0
    for ret in log_ret:
        ewma_mean = alpha * ret + (1 - alpha) * ewma_mean
    mu_annual = ewma_mean * 365
    return mu_annual * shrinkage


# ── sigma e regime ────────────────────────────────────────────────────────────

def current_sigma(btc_price: float, monthly_open: float, annual_vol: float) -> float:
    """Distância do preço atual ao monthly_open em σ mensais."""
    monthly_vol = annual_vol / math.sqrt(12)
    return abs(math.log(btc_price / monthly_open)) / monthly_vol


def get_regime(btc_price: float, monthly_open: float) -> str:
    if btc_price > monthly_open * 1.001:
        return "above_open"
    elif btc_price < monthly_open * 0.999:
        return "below_open"
    return "neutral"


# ── calibração empírica do threshold ─────────────────────────────────────────

def calibrate_min_sigma(
    df_hitrate: Optional[pd.DataFrame],
    min_n_events: int   = 8,
    min_hit_rate_diff: float = 0.05,
    alpha: float = cfg.CALIBRATION_ALPHA,
) -> float:
    """
    Encontra o menor sigma onde o hit rate diverge significativamente de 50%.

    Uses exact binomial test (H0: p = 0.5) per sigma level.
    Falls back to the original 5pp-divergence heuristic if no sigma passes
    the statistical test.
    """
    if df_hitrate is None or df_hitrate.empty:
        return cfg.MIN_SIGMA_THRESHOLD

    sigma_col = "sigma" if "sigma" in df_hitrate.columns else "sigma_level"
    if sigma_col not in df_hitrate.columns:
        return cfg.MIN_SIGMA_THRESHOLD

    # ── primary: binomial test per sigma ────────────────────────────────
    for sigma in sorted(df_hitrate[sigma_col].unique()):
        sub = df_hitrate[
            (df_hitrate[sigma_col] == sigma) &
            (df_hitrate["n_events"] >= min_n_events)
        ]
        if sub.empty:
            continue

        # Aggregate across all k values and directions for this sigma
        total_n    = int(sub["n_events"].sum())
        total_hits = int((sub["hit_rate"] * sub["n_events"]).round().sum())

        if total_n < min_n_events:
            continue

        p_value = float(scipy_stats.binomtest(total_hits, total_n, 0.5).pvalue)
        if p_value < alpha:
            return float(sigma)

    # ── fallback: original heuristic ────────────────────────────────────
    low_sigma = df_hitrate[df_hitrate[sigma_col] <= 0.75]
    baseline  = low_sigma["hit_rate"].mean() if not low_sigma.empty else 0.5
    if pd.isna(baseline):
        baseline = 0.5

    significant = df_hitrate[
        (df_hitrate["n_events"] >= min_n_events) &
        (abs(df_hitrate["hit_rate"] - baseline) >= min_hit_rate_diff)
    ]

    if significant.empty:
        return cfg.MIN_SIGMA_THRESHOLD

    return float(significant[sigma_col].min())


# ── SD histórico via df_hitrate ───────────────────────────────────────────────

def _closest_k(k_target: int, available_ks: list[int]) -> int:
    """Retorna o k disponível mais próximo do alvo."""
    return min(available_ks, key=lambda k: abs(k - k_target))


def _lookup_node(
    df_hitrate: pd.DataFrame,
    sigma_col: str,
    sigma: float,
    direction: str,
    k_target: int,
    min_n_events: int,
) -> Optional[tuple[float, int]]:
    """Lookup a single (sigma, direction, k) node in df_hitrate.
    Returns (hit_rate_raw, n_events) or None if N < min_n_events."""
    sub = df_hitrate[
        (df_hitrate[sigma_col] == sigma) &
        (df_hitrate["direction"] == direction)
    ]
    if sub.empty:
        return None
    available_ks = sorted(sub["k"].unique())
    if not available_ks:
        return None
    k_used = _closest_k(k_target, available_ks)
    row = sub[sub["k"] == k_used]
    if row.empty:
        return None
    n = int(row["n_events"].values[0])
    if n < min_n_events:
        return None
    return float(row["hit_rate"].values[0]), n


def get_p_sd(
    sigma_atual: float,
    direction: str,
    df_hitrate: Optional[pd.DataFrame],
    k_target: int,
    min_n_events: int = cfg.MIN_N_EVENTS,
) -> tuple[Optional[float], Optional[int], Optional[float], Optional[float]]:
    """
    Hit rate histórico com interpolação linear 1D em sigma.

    1. Encontra os dois sigmas adjacentes (lo, hi) que encaixam sigma_atual.
    2. Faz lookup de (hit_rate, N) em cada nó (nearest-neighbor em k).
    3. Interpola Wilson centers, computa N_eff (média harmônica ponderada).
    4. Recomputa CI a partir de (center_interp, N_eff).
    5. Fallback para nearest-neighbor se um dos nós não tiver dados.

    Returns (p_sd_wilson, n_eff, ci_lower, ci_upper) or (None,)*4.
    """
    _none = (None, None, None, None)

    if df_hitrate is None or df_hitrate.empty:
        return _none

    sigma_col = "sigma" if "sigma" in df_hitrate.columns else "sigma_level"
    if sigma_col not in df_hitrate.columns:
        return _none

    available_sigmas = sorted(df_hitrate[sigma_col].unique())
    if not available_sigmas:
        return _none

    # ── find bracketing sigmas ──────────────────────────────────────────────
    sigma_q = sigma_atual

    # Clamp to grid bounds
    if sigma_q <= available_sigmas[0]:
        sigma_lo = sigma_hi = available_sigmas[0]
    elif sigma_q >= available_sigmas[-1]:
        sigma_lo = sigma_hi = available_sigmas[-1]
    else:
        # Find lo and hi such that lo <= sigma_q <= hi
        sigma_lo = max(s for s in available_sigmas if s <= sigma_q)
        sigma_hi = min(s for s in available_sigmas if s >= sigma_q)

    # ── lookup both nodes ───────────────────────────────────────────────────
    node_lo = _lookup_node(df_hitrate, sigma_col, sigma_lo, direction, k_target, min_n_events)
    node_hi = _lookup_node(df_hitrate, sigma_col, sigma_hi, direction, k_target, min_n_events)

    # ── fallback logic ──────────────────────────────────────────────────────
    if node_lo is None and node_hi is None:
        return _none
    if node_lo is None:
        # Only hi available — use it directly (nearest-neighbor fallback)
        hr, n = node_hi
        hits = round(hr * n)
        center, ci_lo, ci_hi = wilson_interval(hits, n)
        return center, n, ci_lo, ci_hi
    if node_hi is None:
        hr, n = node_lo
        hits = round(hr * n)
        center, ci_lo, ci_hi = wilson_interval(hits, n)
        return center, n, ci_lo, ci_hi

    hr_lo, n_lo = node_lo
    hr_hi, n_hi = node_hi

    # ── same bucket (clamped or exact match) ────────────────────────────────
    if sigma_lo == sigma_hi:
        hits = round(hr_lo * n_lo)
        center, ci_lo_w, ci_hi_w = wilson_interval(hits, n_lo)
        return center, n_lo, ci_lo_w, ci_hi_w

    # ── interpolation weight ────────────────────────────────────────────────
    t = (sigma_q - sigma_lo) / (sigma_hi - sigma_lo)  # 0 = at lo, 1 = at hi

    # Wilson centers at each node
    hits_lo = round(hr_lo * n_lo)
    hits_hi = round(hr_hi * n_hi)
    center_lo, _, _ = wilson_interval(hits_lo, n_lo)
    center_hi, _, _ = wilson_interval(hits_hi, n_hi)

    # Interpolate Wilson centers
    center_interp = (1 - t) * center_lo + t * center_hi

    # N_eff: weighted harmonic mean (conservative — penalizes low-N node)
    w_lo, w_hi = 1 - t, t
    # Guard against division by zero (already checked N >= min_n_events above)
    n_eff = int(round(1.0 / (w_lo / n_lo + w_hi / n_hi)))
    n_eff = max(n_eff, min(n_lo, n_hi))  # never below the smaller N

    # Recompute CI from interpolated center and N_eff
    _, ci_lo_w, ci_hi_w = wilson_interval(round(center_interp * n_eff), n_eff)

    return center_interp, n_eff, ci_lo_w, ci_hi_w


# ── Kelly ─────────────────────────────────────────────────────────────────────

def kelly(p_win: float, cost: float, kelly_fraction: float = cfg.KELLY_FRACTION) -> float:
    """Half-Kelly fraction do capital alocável."""
    if cost <= 0 or cost >= 1:
        return 0.0
    b      = (1 - cost) / cost
    q      = 1 - p_win
    full_k = (p_win * b - q) / b
    return max(0.0, full_k * kelly_fraction)


# ── função principal ──────────────────────────────────────────────────────────

def get_scanner_data(
    btc_price:       float,
    monthly_open:    float,
    barrier_vol:     float,
    days_remaining:  int,
    polymarket_odds: dict,
    df_hitrate:      Optional[pd.DataFrame] = None,
    df_returns:      Optional[pd.DataFrame] = None,
    *,
    zone_vol:     Optional[float] = None,
    drift:        Optional[float] = None,
    min_sigma:    Optional[float] = None,
    min_edge:     float = cfg.MIN_EDGE_PP,
    strong_edge:  float = cfg.STRONG_EDGE_PP,
    w_barrier:    float = cfg.W_BARRIER,
    w_sd:         float = cfg.W_SD,
    kelly_frac:   float = cfg.KELLY_FRACTION,
    min_n_events: int   = cfg.MIN_N_EVENTS,
) -> pd.DataFrame:
    """
    Calcula edge e sinais para todos os strikes disponíveis no polymarket_odds.

    Vol separation:
        barrier_vol — implied vol (Deribit DVOL) → barrier_prob P(touch)
        zone_vol    — realized vol (Vol Zone Study or EWMA) → current_sigma, SD bucket lookup
        If zone_vol is None, falls back to barrier_vol.

    Retorna DataFrame com colunas:
        strike, direction, dist_pct,
        poly_yes, poly_no,
        p_barrier, p_sd, n_sd, p_internal,
        edge_pp, signal, signal_strength,
        kelly_pct, cost_¢, gain_¢, ev_¢,
        consensus_source, sd_active, sigma_atual, regime, source,
        spread_¢, ci_width
    """
    _zone_vol  = zone_vol if zone_vol is not None else barrier_vol
    _drift     = drift if drift is not None else 0.0
    sigma_at   = current_sigma(btc_price, monthly_open, _zone_vol)
    regime     = get_regime(btc_price, monthly_open)
    threshold  = min_sigma if min_sigma is not None else cfg.MIN_SIGMA_THRESHOLD
    sd_active  = sigma_at >= threshold

    # direção relevante do regime para busca no df_hitrate
    if regime == "above_open":
        relevant_dir = "supply"
    elif regime == "below_open":
        relevant_dir = "demand"
    else:
        relevant_dir = "demand"  # neutro — usar demand como default

    # holding period em bars 4H
    k_target = days_remaining * 6

    rows = []
    for strike, mkt in polymarket_odds.items():
        poly_yes  = mkt["yes_mid"]
        poly_no   = mkt["no_mid"]
        direction = mkt.get("direction", "reach")
        dist_pct  = (strike / btc_price - 1) * 100

        # ── bid/ask spread ────────────────────────────────────────────────────
        bid       = mkt.get("bid")
        ask       = mkt.get("ask")
        spread_c  = ((ask - bid) * 100) if (bid is not None and ask is not None) else None

        # ── barreira ──────────────────────────────────────────────────────────
        p_barr = barrier_prob(strike, btc_price, barrier_vol, days_remaining, drift=_drift)

        # ── SD histórico via df_hitrate (Wilson-adjusted) ─────────────────────
        p_sd: Optional[float] = None
        n_sd: Optional[int]   = None
        ci_lo: Optional[float] = None
        ci_hi: Optional[float] = None
        if sd_active:
            p_sd, n_sd, ci_lo, ci_hi = get_p_sd(
                sigma_at, relevant_dir, df_hitrate, k_target, min_n_events
            )

        # ── consenso ponderado (adaptive weights) ──────────────────────────
        if p_sd is not None and ci_lo is not None and ci_hi is not None:
            ci_width = ci_hi - ci_lo
            # SD confidence: saturating function of N (N=8→0.24, N=25→0.50, N=50→0.67, N=100→0.80)
            confidence_n = 1 - 1 / (1 + n_sd / 25)
            # Penalize wide CI (>70pp → zero weight, <30pp → full weight)
            precision = max(0.0, min(1.0, (0.70 - ci_width) / 0.40))
            # Adaptive SD weight: scale the user's w_sd by confidence × precision
            w_sd_eff = w_sd * confidence_n * precision
            w_barr_eff = 1.0 - w_sd_eff
            p_int = w_barr_eff * p_barr + w_sd_eff * p_sd
            consensus_source = (
                f"barreira({w_barr_eff:.0%}) + SD(N={n_sd}, {w_sd_eff:.0%})"
            )
        elif p_sd is not None:
            p_int = w_barrier * p_barr + w_sd * p_sd
            consensus_source = f"barreira({w_barrier:.0%}) + SD(N={n_sd}, {w_sd:.0%})"
        else:
            p_int = p_barr
            reason = "SD inativo" if not sd_active else f"N<{min_n_events}"
            consensus_source = f"barreira only ({reason})"

        # ── edge e sinal ──────────────────────────────────────────────────────
        edge_pp = (p_int - poly_yes) * 100

        if edge_pp > min_edge:
            signal    = "BUY YES"
            trade_prob = p_int
            cost       = poly_yes
        elif edge_pp < -min_edge:
            signal    = "BUY NO"
            trade_prob = 1 - p_int
            cost       = poly_no
        else:
            signal     = "MONITOR"
            trade_prob = None
            cost       = None

        # ── execution price (bid-ask adjusted) ───────────────────────────────
        if signal == "BUY YES":
            exec_cost = ask if ask is not None else poly_yes
        elif signal == "BUY NO":
            exec_cost = (1 - bid) if bid is not None else poly_no
        else:
            exec_cost = None

        # ── força do sinal ────────────────────────────────────────────────────
        if signal == "MONITOR":
            signal_strength = "— MONITOR"
        elif p_sd is not None:
            barrier_dir = "YES" if p_barr > poly_yes else "NO"
            sd_dir      = "YES" if p_sd > poly_yes else "NO"
            if barrier_dir == sd_dir and abs(edge_pp) >= strong_edge:
                signal_strength = "★★ STRONG"
            elif barrier_dir != sd_dir:
                signal_strength = "⚠ CONFLICTING"
            else:
                signal_strength = "★ MODERATE"
        else:
            signal_strength = "★ MODERATE"

        # ── sizing (uses execution price for realistic Kelly/EV) ─────────────
        _has_trade = trade_prob is not None and exec_cost is not None
        kelly_pct = kelly(trade_prob, exec_cost, kelly_frac) * 100 if _has_trade else 0.0
        ev_c  = (trade_prob * (1 - exec_cost) - (1 - trade_prob) * exec_cost) * 100 if _has_trade else 0.0
        cost_c = exec_cost * 100    if exec_cost is not None else None
        gain_c = (1 - exec_cost) * 100 if exec_cost is not None else None

        rows.append({
            "strike"          : strike,
            "direction"       : direction,
            "dist_pct"        : round(dist_pct, 1),
            "poly_yes"        : round(poly_yes * 100, 1),
            "poly_no"         : round(poly_no * 100, 1),
            "p_barrier"       : round(p_barr * 100, 1),
            "p_sd"            : round(p_sd * 100, 1) if p_sd is not None else None,
            "n_sd"            : n_sd,
            "p_internal"      : round(p_int * 100, 1),
            "edge_pp"         : round(edge_pp, 1),
            "signal"          : signal,
            "signal_strength" : signal_strength,
            "kelly_pct"       : round(kelly_pct, 1),
            "cost_¢"          : round(cost_c, 1) if cost_c is not None else None,
            "gain_¢"          : round(gain_c, 1) if gain_c is not None else None,
            "ev_¢"            : round(ev_c, 1),
            "consensus_source": consensus_source,
            "sd_active"       : sd_active,
            "sigma_atual"     : round(sigma_at, 3),
            "regime"          : regime,
            "source"          : mkt.get("source", "live"),
            "spread_¢"       : round(spread_c, 1) if spread_c is not None else None,
            "ci_width"        : round((ci_hi - ci_lo) * 100, 1) if (ci_lo is not None and ci_hi is not None) else None,
        })

    df = pd.DataFrame(rows)
    if df.empty:
        return df
    return df.sort_values("edge_pp", key=abs, ascending=False).reset_index(drop=True)


# ── tabela de decaimento temporal ─────────────────────────────────────────────

def decay_table(
    strike: float,
    btc_price: float,
    annual_vol: float,
    days_remaining: int,
    step_days: int = 6,
    drift: float = 0.0,
) -> pd.DataFrame:
    """
    Retorna série temporal de P(toque) e P(não toque) pelo modelo de barreira
    para os próximos `days_remaining` dias em steps de `step_days`.
    """
    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    rows  = []
    for d in range(0, days_remaining + 1, step_days):
        days_left = days_remaining - d
        p_yes     = barrier_prob(strike, btc_price, annual_vol, days_left, drift=drift)
        rows.append({
            "Date"         : (today + timedelta(days=d)).strftime("%m/%d"),
            "Days left"    : days_left,
            "P(touch) %"   : round(p_yes * 100, 1),
            "P(no touch) %" : round((1 - p_yes) * 100, 1),
        })
    # always include the final day
    if days_remaining % step_days != 0:
        rows.append({
            "Date"         : (today + timedelta(days=days_remaining)).strftime("%m/%d"),
            "Days left"    : 0,
            "P(touch) %"   : 0.0,
            "P(no touch) %" : 100.0,
        })
    return pd.DataFrame(rows)
