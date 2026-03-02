"""
Compute monthly volatility zones — a vectorized Python replica of the Pine Script indicator.

Zone construction (matches the indicator exactly):
  src          = hlcc4 = (high + low + close + close) / 4
  daily_return = log(src[t] / src[t-1])
  monthly_vol  = rolling_stdev(daily_return, 360) * sqrt(365) / sqrt(12)
  zone         = monthly_open * (1 ± n_sigma * monthly_vol)

At every new month:
  - monthly_open = first 4H bar's open for that month
  - monthly_vol  = last available rolling vol from daily series (no lookahead)

All zone levels are then held constant until the next month starts.
"""

import numpy as np
import pandas as pd

ZONE_SIGMAS = [
    0.5, 0.75, 1.0, 1.25, 1.5, 1.75,
    2.0, 2.25, 2.5, 2.75,
    3.0, 3.25, 3.5, 3.75, 4.0,
]


def _sigma_col(sigma: float, direction: str) -> str:
    """Canonical column name, e.g. supply_1_0sd or demand_0_5sd."""
    return f"{direction}_{str(sigma).replace('.', '_')}sd"


def compute_monthly_vol(daily_df: pd.DataFrame, lookback: int = 360) -> pd.Series:
    """
    Compute monthly volatility from a daily OHLCV DataFrame.

    Formula:
        src     = (high + low + close + close) / 4   (hlcc4)
        ret     = log(src / src.shift(1))
        ann_vol = rolling_stdev(ret, lookback) * sqrt(365)
        m_vol   = ann_vol / sqrt(12)

    Args:
        daily_df: DataFrame with [high, low, close] columns, daily frequency
        lookback: rolling window in days (default 360, matches the indicator)

    Returns:
        pd.Series of monthly volatility values, same index as daily_df

    Example:
        daily = resample_to_daily(df_4h)
        vol   = compute_monthly_vol(daily)
    """
    src = (daily_df["high"] + daily_df["low"] + daily_df["close"] + daily_df["close"]) / 4
    log_ret = np.log(src / src.shift(1))
    daily_vol = log_ret.rolling(lookback, min_periods=lookback).std()
    return daily_vol * np.sqrt(365) / np.sqrt(12)


def compute_zones(
    df_4h: pd.DataFrame,
    daily_df: pd.DataFrame,
    lookback: int = 360,
) -> pd.DataFrame:
    """
    Add monthly volatility zone columns to a 4H OHLCV DataFrame.

    For each 4H bar the following columns are added:
        monthly_open        — open price of the first bar in that month
        monthly_vol         — monthly volatility in force for that month
        supply_{n}sd        — zone level above monthly_open at +n × monthly_vol
        demand_{n}sd        — zone level below monthly_open at -n × monthly_vol

    Zone levels: 0.5σ, 0.75σ, 1.0σ, 1.25σ, 1.5σ, 1.75σ, 2.0σ

    Args:
        df_4h:    4H OHLCV DataFrame indexed by UTC timestamp
        daily_df: Daily OHLCV DataFrame (used only for vol calculation)
        lookback: vol rolling window in days

    Returns:
        df_4h copy with all zone columns appended (NaN for first ~360 days)

    Example:
        df_zones = compute_zones(df_4h, daily_df)
        df_zones[["monthly_open", "supply_1_0sd", "demand_1_0sd"]].tail()
    """
    # ── 1. Monthly volatility series (daily index) ───────────────────────────
    vol_series = compute_monthly_vol(daily_df, lookback)

    # ── 2. Period label for each 4H bar ──────────────────────────────────────
    result = df_4h.copy()
    result["_period"] = result.index.to_period("M")

    # ── 3. Monthly open: first 4H bar's open per month ───────────────────────
    monthly_opens: pd.Series = (
        result.reset_index()
        .groupby("_period")["open"]
        .first()
    )

    # ── 4. Monthly vol: last available daily vol at the start of each month ──
    # Strip timezone so asof() label comparison works (periods are tz-naive).
    vol_tz_naive = vol_series.copy()
    vol_tz_naive.index = vol_series.index.tz_localize(None)

    # asof(label) returns the last value with index <= label — O(log n) per call.
    monthly_vol_map: dict = {
        period: vol_tz_naive.asof(period.to_timestamp(how="start"))
        for period in monthly_opens.index
    }
    monthly_vol_series = pd.Series(monthly_vol_map)

    # ── 5. Map back to every 4H bar ──────────────────────────────────────────
    result["monthly_open"] = result["_period"].map(monthly_opens)
    result["monthly_vol"] = result["_period"].map(monthly_vol_series)

    # ── 6. Compute all zone levels ───────────────────────────────────────────
    for sigma in ZONE_SIGMAS:
        result[_sigma_col(sigma, "supply")] = result["monthly_open"] * (
            1 + sigma * result["monthly_vol"]
        )
        result[_sigma_col(sigma, "demand")] = result["monthly_open"] * (
            1 - sigma * result["monthly_vol"]
        )

    result.drop(columns=["_period"], inplace=True)
    return result


def zone_summary(df_zones: pd.DataFrame) -> pd.DataFrame:
    """
    Return a per-month summary table: monthly_open, monthly_vol, and all zone levels
    at the first bar of each month. Useful for quick inspection.
    """
    cols = ["monthly_open", "monthly_vol"] + [
        _sigma_col(s, d) for d in ("supply", "demand") for s in ZONE_SIGMAS
    ]
    available = [c for c in cols if c in df_zones.columns]
    monthly = df_zones[available].resample("MS").first()
    return monthly.dropna(subset=["monthly_vol"])
