"""
Zone touch detection and forward return computation.

Touch rules (OHLC-based, matches user spec):
    Supply zone Z: bar high  >= Z  → price wicked into or through the zone
    Demand zone Z: bar low   <= Z  → price wicked into or through the zone

Only the FIRST touch per zone per month is recorded.
Supply and demand sides are kept separate.

Forward return at holding period k (bars after the touch bar):
    fwd_k = log(close[t+k] / close[t])

For supply zones a negative fwd_k means price fell — i.e., the short worked.
For demand zones a positive fwd_k means price rose — i.e., the long worked.
The sign is NOT flipped here; the caller / visualization layer interprets direction.
"""

import numpy as np
import pandas as pd

from zone_calculator import ZONE_SIGMAS, _sigma_col

MAX_K_DEFAULT = 120  # 120 × 4H = 20 days


# ── touch detection ───────────────────────────────────────────────────────────

def detect_zone_touches(df: pd.DataFrame) -> pd.DataFrame:
    """
    Find the first 4H bar per month where price touches each zone level.

    Args:
        df: 4H DataFrame returned by zone_calculator.compute_zones()

    Returns:
        Events DataFrame with columns:
            timestamp, month, sigma, direction, zone_level,
            monthly_open, monthly_vol,
            bar_open, bar_high, bar_low, bar_close

    Example:
        events = detect_zone_touches(df_zones)
        events.groupby(["direction", "sigma"]).size()
    """
    records: list[dict] = []

    df = df.copy()
    df["_period"] = df.index.to_period("M")

    for sigma in ZONE_SIGMAS:
        sup_col = _sigma_col(sigma, "supply")
        dem_col = _sigma_col(sigma, "demand")

        if sup_col not in df.columns or dem_col not in df.columns:
            continue

        # ── supply: high touches or exceeds the zone ─────────────────────────
        sup_touch = df["high"] >= df[sup_col]
        sup_valid = sup_touch & df[sup_col].notna()

        sup_events = (
            df[sup_valid]
            .reset_index()      # DatetimeIndex named "timestamp" → regular column
            .groupby("_period")
            .first()
            .reset_index()
        )
        for _, row in sup_events.iterrows():
            records.append(
                {
                    "timestamp": row["timestamp"],
                    "month": str(row["_period"]),
                    "sigma": sigma,
                    "direction": "supply",
                    "zone_level": row[sup_col],
                    "monthly_open": row["monthly_open"],
                    "monthly_vol": row["monthly_vol"],
                    "bar_open": row["open"],
                    "bar_high": row["high"],
                    "bar_low": row["low"],
                    "bar_close": row["close"],
                }
            )

        # ── demand: low touches or falls below the zone ───────────────────────
        dem_touch = df["low"] <= df[dem_col]
        dem_valid = dem_touch & df[dem_col].notna()

        dem_events = (
            df[dem_valid]
            .reset_index()      # DatetimeIndex named "timestamp" → regular column
            .groupby("_period")
            .first()
            .reset_index()
        )
        for _, row in dem_events.iterrows():
            records.append(
                {
                    "timestamp": row["timestamp"],
                    "month": str(row["_period"]),
                    "sigma": sigma,
                    "direction": "demand",
                    "zone_level": row[dem_col],
                    "monthly_open": row["monthly_open"],
                    "monthly_vol": row["monthly_vol"],
                    "bar_open": row["open"],
                    "bar_high": row["high"],
                    "bar_low": row["low"],
                    "bar_close": row["close"],
                }
            )

    if not records:
        return pd.DataFrame()

    events = (
        pd.DataFrame(records)
        .sort_values("timestamp")
        .reset_index(drop=True)
    )
    events.index.name = "event_id"
    return events


# ── forward returns ───────────────────────────────────────────────────────────

def compute_forward_returns(
    df: pd.DataFrame,
    events: pd.DataFrame,
    max_k: int = MAX_K_DEFAULT,
) -> pd.DataFrame:
    """
    For each touch event, compute log forward returns at k = 1 … max_k bars.

    Forward return definition:
        fwd_k = log(close[bar_index + k] / close[bar_index])

    The reference close is the close of the touch bar itself.
    This approximates entering at the touch-bar close.

    Args:
        df:     Full 4H DataFrame (indexed by UTC timestamp), needs 'close' column
        events: Output of detect_zone_touches()
        max_k:  Number of forward bars (default 120 = 20 days at 4H)

    Returns:
        events DataFrame with additional columns fwd_1 … fwd_{max_k}

    Example:
        study = compute_forward_returns(df_zones, events, max_k=120)
        study[["sigma", "direction", "fwd_6", "fwd_18", "fwd_42"]].head()
    """
    closes: np.ndarray = df["close"].values
    # Map each timestamp to its integer position in the array
    ts_to_iloc: dict = {ts: i for i, ts in enumerate(df.index)}

    fwd_matrix = np.full((len(events), max_k), np.nan, dtype=np.float64)

    for ev_idx, (_, ev) in enumerate(events.iterrows()):
        iloc = ts_to_iloc.get(ev["timestamp"])
        if iloc is None:
            continue
        ref_close = closes[iloc]
        if ref_close == 0 or np.isnan(ref_close):
            continue
        # last_idx: the furthest index we can read (inclusive)
        last_idx = min(iloc + max_k, len(closes) - 1)
        n_valid = last_idx - iloc  # number of forward bars actually available
        if n_valid <= 0:
            continue
        fwd_matrix[ev_idx, :n_valid] = np.log(closes[iloc + 1 : last_idx + 1] / ref_close)

    fwd_cols = {f"fwd_{k}": fwd_matrix[:, k - 1] for k in range(1, max_k + 1)}
    result = events.copy()
    for col, vals in fwd_cols.items():
        result[col] = vals

    return result


# ── summary statistics ────────────────────────────────────────────────────────

def summarize_events(study: pd.DataFrame, max_k: int = MAX_K_DEFAULT) -> pd.DataFrame:
    """
    Per (direction, sigma) summary at each holding period k.

    Returns a long-form DataFrame with columns:
        direction, sigma, k, n_events,
        mean_ret, median_ret, std_ret,
        hit_rate,   — fraction of events where signed return was favorable
        sharpe      — mean(signed_ret) / std(signed_ret)

    'Favorable' is defined as:
        supply → fwd_k < 0  (price dropped, short profited)
        demand → fwd_k > 0  (price rose,   long  profited)
    """
    rows: list[dict] = []
    k_values = range(1, max_k + 1)

    for direction in ("supply", "demand"):
        sign = -1 if direction == "supply" else 1
        for sigma in ZONE_SIGMAS:
            sub = study[(study["direction"] == direction) & (study["sigma"] == sigma)]
            if sub.empty:
                continue
            fwd_cols = [f"fwd_{k}" for k in k_values]
            mat = sub[fwd_cols].values.astype(float)  # (n_events, max_k)

            for k in k_values:
                col_idx = k - 1
                raw = mat[:, col_idx]
                valid = raw[~np.isnan(raw)]
                if len(valid) == 0:
                    continue
                signed = sign * valid
                std = signed.std()
                rows.append(
                    {
                        "direction": direction,
                        "sigma": sigma,
                        "k": k,
                        "n_events": len(valid),
                        "mean_ret": valid.mean(),
                        "median_ret": np.median(valid),
                        "std_ret": valid.std(),
                        "mean_signed": signed.mean(),
                        "hit_rate": (signed > 0).mean(),
                        "sharpe": signed.mean() / std if std > 0 else np.nan,
                    }
                )

    return pd.DataFrame(rows)
