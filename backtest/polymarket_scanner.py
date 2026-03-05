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


# ── fetch BTC spot ────────────────────────────────────────────────────────────

def fetch_btc_price() -> float:
    """Preço spot BTC/USDT via Binance REST (sem autenticação)."""
    r = requests.get(
        "https://api.binance.com/api/v3/ticker/price",
        params={"symbol": "BTCUSDT"}, timeout=5,
    )
    r.raise_for_status()
    return float(r.json()["price"])


# fetch de odds removido deste módulo — usar fetch_active_market() de polymarket_live.py


# ── modelo de barreira ────────────────────────────────────────────────────────

def barrier_prob(strike: float, current: float, annual_vol: float, days: int) -> float:
    """P(ever touch strike) — reflexão log-normal, sem drift."""
    if days <= 0:
        return 0.0
    vol_t = annual_vol * math.sqrt(days / 365)
    z     = abs(math.log(strike / current)) / vol_t
    return float(2 * scipy_stats.norm.cdf(-z))


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
) -> float:
    """
    Encontra o menor sigma onde o hit rate diverge significativamente
    do baseline (sigma baixo ≈ 50% = ruído).
    Retorna fallback conservador se df_hitrate for None ou vazio.
    """
    if df_hitrate is None or df_hitrate.empty:
        return cfg.MIN_SIGMA_THRESHOLD

    sigma_col = "sigma" if "sigma" in df_hitrate.columns else "sigma_level"
    if sigma_col not in df_hitrate.columns:
        return cfg.MIN_SIGMA_THRESHOLD

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


def get_p_sd(
    sigma_atual: float,
    direction: str,
    df_hitrate: Optional[pd.DataFrame],
    k_target: int,
    min_n_events: int = cfg.MIN_N_EVENTS,
) -> tuple[Optional[float], Optional[int]]:
    """
    Busca hit rate histórico para o sigma_atual e direção correntes.
    Interpola para o k mais próximo se necessário.
    Retorna (hit_rate, n_events) ou (None, None) se indisponível.
    """
    if df_hitrate is None or df_hitrate.empty:
        return None, None

    sigma_col = "sigma" if "sigma" in df_hitrate.columns else "sigma_level"
    if sigma_col not in df_hitrate.columns:
        return None, None

    available_sigmas = sorted(df_hitrate[sigma_col].unique())
    if not available_sigmas:
        return None, None

    closest_sigma = min(available_sigmas, key=lambda s: abs(s - sigma_atual))

    # bucket filtrado por sigma e direção
    sub = df_hitrate[
        (df_hitrate[sigma_col] == closest_sigma) &
        (df_hitrate["direction"] == direction)
    ]
    if sub.empty:
        return None, None

    available_ks = sorted(sub["k"].unique())
    if not available_ks:
        return None, None

    k_used = _closest_k(k_target, available_ks)

    row = sub[sub["k"] == k_used]
    if row.empty:
        return None, None

    n = int(row["n_events"].values[0])
    if n < min_n_events:
        return None, None

    return float(row["hit_rate"].values[0]), n


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
    annual_vol:      float,
    days_remaining:  int,
    polymarket_odds: dict,
    df_hitrate:      Optional[pd.DataFrame] = None,
    df_returns:      Optional[pd.DataFrame] = None,
    *,
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
    SD histórico lido de df_hitrate (Vol Zone Study) — sem valores hardcoded.

    Retorna DataFrame com colunas:
        strike, direction, dist_pct,
        poly_yes, poly_no,
        p_barrier, p_sd, n_sd, p_internal,
        edge_pp, signal, signal_strength,
        kelly_pct, cost_¢, gain_¢, ev_¢,
        consensus_source, sd_active, sigma_atual, regime, source
    """
    sigma_at   = current_sigma(btc_price, monthly_open, annual_vol)
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

        # ── barreira ──────────────────────────────────────────────────────────
        p_barr = barrier_prob(strike, btc_price, annual_vol, days_remaining)

        # ── SD histórico via df_hitrate ───────────────────────────────────────
        p_sd: Optional[float] = None
        n_sd: Optional[int]   = None
        if sd_active:
            p_sd, n_sd = get_p_sd(
                sigma_at, relevant_dir, df_hitrate, k_target, min_n_events
            )

        # ── consenso ponderado ────────────────────────────────────────────────
        if p_sd is not None:
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

        # ── sizing ────────────────────────────────────────────────────────────
        # BUY YES: cost = poly_yes, gain = 1 - poly_yes, p_win = p_int
        # BUY NO:  cost = poly_no,  gain = 1 - poly_no = poly_yes, p_win = 1 - p_int
        _has_trade = trade_prob is not None and cost is not None
        kelly_pct = kelly(trade_prob, cost, kelly_frac) * 100 if _has_trade else 0.0
        ev_c  = (trade_prob * (1 - cost) - (1 - trade_prob) * cost) * 100 if _has_trade else 0.0
        cost_c = cost * 100         if cost is not None else None
        gain_c = (1 - cost) * 100   if cost is not None else None

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
) -> pd.DataFrame:
    """
    Retorna série temporal de P(toque) e P(não toque) pelo modelo de barreira
    para os próximos `days_remaining` dias em steps de `step_days`.
    """
    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    rows  = []
    for d in range(0, days_remaining + 1, step_days):
        days_left = days_remaining - d
        p_yes     = barrier_prob(strike, btc_price, annual_vol, days_left)
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
