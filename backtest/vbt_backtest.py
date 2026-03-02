"""
VectorBT portfolio simulation layer.

This module is the second stage after the event study:
  - Event study → "what is the forward return distribution?"
  - VectorBT    → "if I actually traded this, what would my equity curve look like?"

Strategy simulated:
  Entry : close of the first 4H bar that touches the zone
  Exit  : close of bar (entry_bar + hold_k)  — timed exit
  Direction:
    demand zones → long
    supply zones → short

Key distinction from the event study:
  VectorBT won't open a new trade while one is already open (accumulate=False).
  If two touches occur within hold_k bars of each other for the same zone, the
  second touch is skipped. The event study captures all touches regardless.
  Both views are useful; they answer different questions.

Usage:
    from vbt_backtest import run_single, sweep_params, plot_equity

    # Single combination
    pf = run_single(df_4h, events, sigma=1.0, direction="demand", hold_k=18)
    print(pf.stats())

    # Full parameter sweep
    results = sweep_params(df_4h, events, hold_k_values=[6, 12, 18, 30, 42, 90])
    print(results.sort_values("sharpe", ascending=False).head(20))

Requirements:
    pip install vectorbt
"""

from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd

from zone_calculator import ZONE_SIGMAS

try:
    import vectorbt as vbt
    _VBT_AVAILABLE = True
except ImportError:
    _VBT_AVAILABLE = False


def _require_vbt() -> None:
    if not _VBT_AVAILABLE:
        raise ImportError(
            "vectorbt is not installed. Run: pip install vectorbt"
        )


# ── single run ────────────────────────────────────────────────────────────────

def run_single(
    df: pd.DataFrame,
    events: pd.DataFrame,
    sigma: float,
    direction: str,
    hold_k: int,
    init_cash: float = 10_000.0,
    tc: float = 0.001,
) -> "vbt.Portfolio":
    """
    Run a VectorBT portfolio simulation for one (sigma, direction, hold_k) combo.

    Args:
        df:         Full 4H OHLCV DataFrame (indexed by UTC timestamp)
        events:     Output of event_study.detect_zone_touches()
        sigma:      Zone level, e.g. 1.0
        direction:  'supply' (short) or 'demand' (long)
        hold_k:     Exit after this many bars
        init_cash:  Starting equity in USD
        tc:         One-way transaction cost (default 0.1%, covers fees + slippage)

    Returns:
        vbt.Portfolio object — call .stats() for the full metrics suite

    Example:
        pf = run_single(df_4h, events, sigma=1.0, direction="demand", hold_k=18)
        pf.stats()
    """
    _require_vbt()

    # ── build entry signal ────────────────────────────────────────────────────
    ev = events[(events["sigma"] == sigma) & (events["direction"] == direction)]
    entries = pd.Series(False, index=df.index, dtype=bool)
    valid_ts = ev["timestamp"][ev["timestamp"].isin(df.index)]
    entries.loc[valid_ts] = True

    # ── timed exit: k bars after each entry ───────────────────────────────────
    exits = entries.shift(hold_k).fillna(False).astype(bool)

    price = df["close"]

    if direction == "supply":
        pf = vbt.Portfolio.from_signals(
            price,
            entries=pd.Series(False, index=df.index),  # no longs
            exits=pd.Series(False, index=df.index),
            short_entries=entries,
            short_exits=exits,
            init_cash=init_cash,
            fees=tc,
            freq="4h",
            accumulate=False,
        )
    else:
        pf = vbt.Portfolio.from_signals(
            price,
            entries=entries,
            exits=exits,
            init_cash=init_cash,
            fees=tc,
            freq="4h",
            accumulate=False,
        )

    return pf


# ── parameter sweep ───────────────────────────────────────────────────────────

def sweep_params(
    df: pd.DataFrame,
    events: pd.DataFrame,
    hold_k_values: Optional[list[int]] = None,
    sigmas: Optional[list[float]] = None,
    tc: float = 0.001,
) -> pd.DataFrame:
    """
    Run VectorBT across all (sigma, direction, hold_k) combinations.

    Returns a summary DataFrame sorted by Sharpe ratio, with columns:
        direction, sigma, hold_k, n_trades, total_return_%,
        cagr_%, ann_vol_%, sharpe, sortino, calmar, max_dd_%,
        win_rate_%, skipped_events

    'skipped_events' = how many study events were not executed due to overlap.

    Args:
        df:              Full 4H OHLCV DataFrame
        events:          Output of detect_zone_touches()
        hold_k_values:   Holding periods to test (default: [6, 12, 18, 30, 42, 90])
        sigmas:          Zone levels to test (default: all ZONE_SIGMAS)
        tc:              One-way transaction cost

    Example:
        results = sweep_params(df_4h, events, hold_k_values=[6, 18, 42])
        results.sort_values("sharpe", ascending=False).head(10)
    """
    _require_vbt()

    if hold_k_values is None:
        hold_k_values = [6, 12, 18, 30, 42, 60, 90, 120]
    if sigmas is None:
        sigmas = ZONE_SIGMAS

    rows: list[dict] = []
    total = len(sigmas) * 2 * len(hold_k_values)
    done = 0

    for direction in ("supply", "demand"):
        n_study_events = {}
        for s in sigmas:
            n_study_events[s] = len(
                events[(events["sigma"] == s) & (events["direction"] == direction)]
            )

        for sigma in sigmas:
            for k in hold_k_values:
                done += 1
                try:
                    pf = run_single(df, events, sigma, direction, k, tc=tc)
                    stats = pf.stats()

                    n_executed = int(stats.get("Total Trades", 0))
                    skipped = n_study_events[sigma] - n_executed

                    # Compute CAGR from equity curve (not in stats directly)
                    try:
                        years = pf.wrapper.shape[0] * (4 / 24 / 365)  # 4H bars → years
                        total_ret = stats.get("Total Return [%]", np.nan)
                        cagr = ((1 + total_ret / 100) ** (1 / max(years, 1e-6)) - 1) * 100
                        # Annualized vol from daily returns
                        ann_vol = float(pf.returns().dropna().std() * np.sqrt(365 * 6) * 100)
                    except Exception:
                        cagr = np.nan
                        ann_vol = np.nan

                    rows.append(
                        {
                            "direction": direction,
                            "sigma": sigma,
                            "hold_k": k,
                            "hold_days": round(k / 6, 1),
                            "n_trades": n_executed,
                            "skipped_events": skipped,
                            "total_return_%": round(stats.get("Total Return [%]", np.nan), 2),
                            "cagr_%": round(cagr, 2),
                            "ann_vol_%": round(ann_vol, 2),
                            "sharpe": round(stats.get("Sharpe Ratio", np.nan), 3),
                            "sortino": round(stats.get("Sortino Ratio", np.nan), 3),
                            "calmar": round(stats.get("Calmar Ratio", np.nan), 3),
                            "max_dd_%": round(stats.get("Max Drawdown [%]", np.nan), 2),
                            "win_rate_%": round(stats.get("Win Rate [%]", np.nan), 1),
                        }
                    )
                except Exception as e:
                    rows.append(
                        {
                            "direction": direction,
                            "sigma": sigma,
                            "hold_k": k,
                            "hold_days": round(k / 6, 1),
                            "error": str(e),
                        }
                    )

                if done % 20 == 0:
                    print(f"[sweep] {done}/{total} done...")

    return pd.DataFrame(rows).sort_values("sharpe", ascending=False).reset_index(drop=True)


# ── equity curve plot ─────────────────────────────────────────────────────────

def plot_equity(
    pf: "vbt.Portfolio",
    sigma: float,
    direction: str,
    hold_k: int,
    symbol: str = "BTC/USDT",
) -> None:
    """
    Plot equity curve and drawdown series for a single portfolio.

    Args:
        pf:        vbt.Portfolio from run_single()
        sigma:     Zone level used (for title)
        direction: 'supply' or 'demand' (for title)
        hold_k:    Holding period used (for title)
        symbol:    Asset name for title
    """
    _require_vbt()
    import matplotlib.pyplot as plt
    import matplotlib.gridspec as gridspec

    plt.style.use("dark_background")

    fig = plt.figure(figsize=(14, 8))
    gs = gridspec.GridSpec(2, 1, figure=fig, height_ratios=[3, 1], hspace=0.1)
    ax_eq = fig.add_subplot(gs[0])
    ax_dd = fig.add_subplot(gs[1], sharex=ax_eq)

    equity = pf.value()
    drawdown = pf.drawdown() * 100

    color = "#00ff9d" if direction == "demand" else "#ff4444"

    ax_eq.plot(equity.index, equity.values, color=color, linewidth=1.2)
    ax_eq.set_ylabel("Portfolio Value ($)")
    ax_eq.set_yscale("log")
    ax_eq.set_title(
        f"Equity Curve — {symbol}  |  {direction} {sigma}σ  |  hold={hold_k} bars ({hold_k/6:.1f}d)"
    )
    ax_eq.grid(axis="y", color="#333333", linewidth=0.4)

    ax_dd.fill_between(drawdown.index, drawdown.values, 0, color="#ff4444", alpha=0.5)
    ax_dd.set_ylabel("Drawdown (%)")
    ax_dd.set_xlabel("Date")
    ax_dd.grid(axis="y", color="#333333", linewidth=0.4)

    stats = pf.stats()
    summary = (
        f"Sharpe: {stats.get('Sharpe Ratio', 0):.2f}  |  "
        f"Max DD: {stats.get('Max Drawdown [%]', 0):.1f}%  |  "
        f"Total Return: {stats.get('Total Return [%]', 0):.1f}%  |  "
        f"Win Rate: {stats.get('Win Rate [%]', 0):.1f}%  |  "
        f"Trades: {int(stats.get('Total Trades', 0))}"
    )
    fig.text(0.5, 0.01, summary, ha="center", fontsize=9, color="#aaaaaa")
    plt.tight_layout(rect=[0, 0.03, 1, 1])
    plt.show()
