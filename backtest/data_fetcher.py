"""
Fetch and cache crypto OHLCV data via vectorbt's CCXTData (Binance default).

vbt.CCXTData handles pagination, retries, and rate limiting automatically.
Results are cached as Parquet files in ../data/ for fast reuse.

Incremental refresh: on a cache hit, only missing bars since the last cached
timestamp are fetched and appended — no full re-download needed.
"""

from pathlib import Path
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import vectorbt as vbt

DATA_DIR = Path(__file__).parent.parent / "data"
DATA_DIR.mkdir(exist_ok=True)


# ── helpers ───────────────────────────────────────────────────────────────────

def _cache_path(symbol: str, timeframe: str, since: str) -> Path:
    safe = symbol.replace("/", "_").replace(":", "_")
    return DATA_DIR / f"{safe}_{timeframe}_{since[:10]}.parquet"


def _vbt_to_df(raw: pd.DataFrame) -> pd.DataFrame:
    """Normalise a CCXTData frame to lowercase columns + 'timestamp' index name."""
    df = raw.copy()
    df.columns = [c.lower() for c in df.columns]
    df.index.name = "timestamp"
    return df


# ── main fetch ────────────────────────────────────────────────────────────────

def fetch_crypto_ohlcv(
    symbol: str,
    timeframe: str = "4h",
    since: str = "2020-01-01",
    exchange: str = "bybit",
    force_refresh: bool = False,
) -> pd.DataFrame:
    """
    Fetch OHLCV for a crypto pair from Bybit (or any CCXT exchange).

    Uses vectorbt's CCXTData under the hood (handles pagination + retries).
    Results are cached as Parquet; subsequent calls only fetch new bars.

    Args:
        symbol:        e.g. "BTC/USDT", "HYPE/USDT"
        timeframe:     e.g. "4h", "1d"
        since:         ISO date string — start of the study window
        exchange:      CCXT exchange id (default: "binance")
        force_refresh: ignore cache and re-download everything

    Returns:
        DataFrame indexed by UTC timestamp with columns [open, high, low, close, volume]

    Example:
        df = fetch_crypto_ohlcv("BTC/USDT", "4h", "2020-01-01")
    """
    cache = _cache_path(symbol, timeframe, since)

    # ── cache hit: load and do incremental refresh ────────────────────────────
    if cache.exists() and not force_refresh:
        cached = pd.read_parquet(cache)
        last_ts = cached.index[-1]
        now_utc = pd.Timestamp.now(tz="UTC")

        # Nothing to update if last bar is recent enough (< 1 candle old)
        tf_hours = {"4h": 4, "1d": 24, "1h": 1}.get(timeframe, 24)
        if (now_utc - last_ts).total_seconds() < tf_hours * 3600:
            print(f"[cache] {symbol} {timeframe}: {len(cached):,} bars (up to date)")
            return cached

        # Incremental: fetch only bars after the last cached timestamp
        fetch_from = (last_ts + pd.Timedelta(hours=tf_hours)).strftime("%Y-%m-%d %H:%M:%S")
        print(f"[update] {symbol} {timeframe}: fetching new bars from {fetch_from}...")
        try:
            new_raw = vbt.CCXTData.download_symbol(
                symbol, exchange=exchange, timeframe=timeframe,
                start=fetch_from, end="now UTC", show_progress=False,
            )
            if not new_raw.empty:
                new_bars = _vbt_to_df(new_raw)
                combined = pd.concat([cached, new_bars])
                combined = combined[~combined.index.duplicated(keep="last")].sort_index()
                combined.to_parquet(cache)
                print(f"[update] Added {len(new_bars)} new bars → {len(combined):,} total")
                return combined
        except Exception as e:
            print(f"[warn] Incremental update failed ({e}), returning cached data")
        return cached

    # ── full download ─────────────────────────────────────────────────────────
    print(f"[fetch] {symbol} {timeframe} from {since} via {exchange}...")
    raw = vbt.CCXTData.download_symbol(
        symbol,
        exchange=exchange,
        timeframe=timeframe,
        start=since,
        end="now UTC",
        show_progress=True,
    )

    df = _vbt_to_df(raw)
    df = df[~df.index.duplicated(keep="last")].sort_index()
    df.to_parquet(cache)
    print(f"[fetch] Done — {len(df):,} bars cached to {cache.name}")
    return df


# ── resampling ────────────────────────────────────────────────────────────────

def resample_to_daily(df: pd.DataFrame) -> pd.DataFrame:
    """
    Resample intraday (e.g. 4H) bars to daily OHLCV.
    Used to compute daily log returns for the volatility calculation.
    """
    daily = df.resample("1D").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
    )
    return daily.dropna(subset=["open", "close"])
