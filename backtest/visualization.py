"""
Plotly-based visualization — TradingView-inspired dark theme.

All charts are interactive (hover tooltips, zoom, pan).
Public API matches the previous matplotlib version.
"""

from typing import Optional

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from zone_calculator import ZONE_SIGMAS

# ── Bloomberg-style palette ───────────────────────────────────────────────────
# Colors are generated automatically so the palette scales with any number of sigmas.

import plotly.colors as _pc

def _build_palette(colorscale: str, n: int, low: float, high: float) -> list[str]:
    """Sample n evenly-spaced colors from a Plotly colorscale."""
    fracs = [low + (high - low) * i / max(n - 1, 1) for i in range(n)]
    return _pc.sample_colorscale(colorscale, fracs)

_N = len(ZONE_SIGMAS)
# Sample mid-range of each colorscale so no color is too pale or too dark.
# On the dark background these ranges give ~10:1 contrast (weakest zone) down
# to ~3:1 (strongest zone) — all clearly readable.
_SUPPLY_COLORS = _build_palette("Oranges", _N, low=0.25, high=0.72)  # light peach → saturated orange-red
_DEMAND_COLORS = _build_palette("Blues",   _N, low=0.25, high=0.72)  # light sky → medium steel-blue

SUPPLY_COLOR  = _SUPPLY_COLORS[_N // 2]   # mid-supply reference
DEMAND_COLOR  = _DEMAND_COLORS[_N // 2]   # mid-demand reference

_DAY_TICKS = {
    6: "1d", 30: "5d", 60: "10d", 120: "20d",
    180: "30d", 300: "50d", 360: "60d", 540: "90d",
    720: "120d", 900: "150d", 1080: "180d",
}


def _color(sigma: float, direction: str) -> str:
    idx = ZONE_SIGMAS.index(sigma)
    return _SUPPLY_COLORS[idx] if direction == "supply" else _DEMAND_COLORS[idx]


def _hex_to_rgba(color: str, alpha: float) -> str:
    """Convert '#rrggbb' or 'rgb(r,g,b)' to 'rgba(r,g,b,alpha)'."""
    color = color.strip()
    if color.startswith("#"):
        h = color.lstrip("#")
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    else:
        # plotly returns 'rgb(r, g, b)'
        inner = color[color.index("(") + 1 : color.index(")")]
        r, g, b = (int(float(v.strip())) for v in inner.split(","))
    return f"rgba({r},{g},{b},{alpha})"


# ── shared layout — TradingView dark theme ────────────────────────────────────

_BASE_LAYOUT = dict(
    template="plotly_dark",
    font=dict(family="Helvetica Neue, Arial, sans-serif", size=11, color="#d1d4dc"),
    plot_bgcolor="#131722",
    paper_bgcolor="#131722",
    legend=dict(
        bgcolor="#1e222d",
        bordercolor="#2a2e39",
        borderwidth=1,
        font=dict(size=10, color="#d1d4dc"),
    ),
    margin=dict(l=60, r=20, t=50, b=60),
    hovermode="x unified",
)

# Applied separately via update_xaxes / update_yaxes
_AXIS_STYLE = dict(gridcolor="#1e222d", linecolor="#2a2e39", zeroline=False)


def _add_day_vlines(fig: go.Figure, max_k: int, row: int = 1, col: int = 1) -> None:
    """Add dotted vertical lines at day boundaries. Labels come from custom x-axis ticks."""
    for k in _DAY_TICKS:
        if k <= max_k:
            fig.add_vline(
                x=k,
                line=dict(color="#2a2e39", width=0.8, dash="dot"),
                row=row, col=col,
            )


def _day_tick_axis(max_k: int) -> dict:
    """Return xaxis kwargs that show day labels at the boundary tick positions."""
    tick_vals  = [k for k in _DAY_TICKS if k <= max_k]
    tick_texts = [f"{k}<br><span style='font-size:9px;color:#8892a4'>{_DAY_TICKS[k]}</span>"
                  for k in tick_vals]
    return dict(
        tickmode="array",
        tickvals=tick_vals,
        ticktext=tick_texts,
        gridcolor="#1e222d",
        linecolor="#2a2e39",
        zeroline=False,
    )


# ── price chart with zone overlay ─────────────────────────────────────────────

def plot_price_zones(
    df_zones: pd.DataFrame,
    study_df: Optional[pd.DataFrame] = None,
    symbol: str = "BTC/USDT",
    sigmas: Optional[list] = None,
    show_touches: bool = True,
) -> go.Figure:
    """
    Candlestick price chart with monthly volatility zone levels overlaid.

    Args:
        df_zones:     output of compute_zones() — 4H OHLCV + all zone columns
        study_df:     output of compute_forward_returns() — used for touch markers
        symbol:       chart title label
        sigmas:       which sigma levels to draw (default: [0.5,1.0,1.5,2.0,3.0,4.0])
        show_touches: whether to mark first-touch events with markers
    """
    if sigmas is None:
        sigmas = [s for s in ZONE_SIGMAS if s in [0.5, 1.0, 1.5, 2.0, 3.0, 4.0]]

    def _col(sigma: float, direction: str) -> str:
        return f"{direction}_{str(sigma).replace('.', '_')}sd"

    fig = go.Figure()

    # ── candlestick ──────────────────────────────────────────────────────────
    fig.add_trace(go.Candlestick(
        x=df_zones.index,
        open=df_zones["open"],
        high=df_zones["high"],
        low=df_zones["low"],
        close=df_zones["close"],
        name="Price",
        increasing_line_color="#26a69a",
        decreasing_line_color="#ef5350",
        showlegend=False,
        hovertext=[
            f"O: {o:,.2f}  H: {h:,.2f}  L: {l:,.2f}  C: {c:,.2f}"
            for o, h, l, c in zip(
                df_zones["open"], df_zones["high"],
                df_zones["low"],  df_zones["close"],
            )
        ],
        hoverinfo="x+text",
    ))

    # ── monthly open reference ───────────────────────────────────────────────
    if "monthly_open" in df_zones.columns:
        fig.add_trace(go.Scatter(
            x=df_zones.index,
            y=df_zones["monthly_open"],
            line=dict(color="#8892a4", width=0.8, dash="dot"),
            name="Monthly Open",
            hovertemplate="Monthly Open: %{y:,.2f}<extra></extra>",
        ))

    # ── zone lines ───────────────────────────────────────────────────────────
    # Only show legend entry for the first direction of each sigma to avoid clutter
    for sigma in sigmas:
        for direction in ["supply", "demand"]:
            col = _col(sigma, direction)
            if col not in df_zones.columns:
                continue
            color = _color(sigma, direction)
            fig.add_trace(go.Scatter(
                x=df_zones.index,
                y=df_zones[col],
                name=f"{sigma}σ",
                line=dict(color=color, width=0.9),
                legendgroup=f"sigma_{sigma}",
                showlegend=(direction == "supply"),
                hovertemplate=f"{sigma}σ {direction}: %{{y:,.2f}}<extra></extra>",
            ))

    # ── touch markers ────────────────────────────────────────────────────────
    if show_touches and study_df is not None and not study_df.empty:
        for direction in ["supply", "demand"]:
            sub = study_df[study_df["direction"] == direction]
            if sub.empty:
                continue
            color  = _SUPPLY_COLORS[len(ZONE_SIGMAS) // 2] if direction == "supply" else _DEMAND_COLORS[len(ZONE_SIGMAS) // 2]
            marker = "triangle-down" if direction == "supply" else "triangle-up"
            fig.add_trace(go.Scatter(
                x=sub["timestamp"],
                y=sub["zone_level"],
                mode="markers",
                name=f"Touch ({direction})",
                marker=dict(symbol=marker, size=9, color=color,
                            opacity=0.9, line=dict(color="#131722", width=0.5)),
                hovertemplate=(
                    f"<b>{direction} touch</b><br>"
                    "Time: %{x}<br>"
                    "Zone: %{y:,.2f}<br>"
                    "σ: %{customdata:.2f}<extra></extra>"
                ),
                customdata=sub["sigma"],
            ))

    # ── layout ───────────────────────────────────────────────────────────────
    # Set initial view to last 18 months while keeping full history available
    last_ts  = df_zones.index[-1]
    first_ts = last_ts - pd.DateOffset(months=18)

    fig.update_layout(
        **_BASE_LAYOUT,
        title=dict(text=f"<b>Price & Volatility Zones</b>  |  {symbol}", font=dict(size=13)),
        yaxis_title="Price",
        height=620,
        xaxis_rangeslider_visible=False,
        xaxis_range=[first_ts, last_ts],
    )
    fig.update_xaxes(**_AXIS_STYLE)
    fig.update_yaxes(**_AXIS_STYLE)
    return fig


# ── return curve ──────────────────────────────────────────────────────────────

def plot_return_curve(
    study_df: pd.DataFrame,
    direction: str,
    sigmas: Optional[list] = None,
    title_suffix: str = "",
) -> go.Figure:
    """
    Mean ± 1σ forward return vs holding period k.
    Interactive: hover shows exact return per sigma at each k.
    """
    if sigmas is None:
        sigmas = ZONE_SIGMAS

    fwd_cols = sorted(
        [c for c in study_df.columns if c.startswith("fwd_")],
        key=lambda c: int(c.split("_")[1]),
    )
    k_values = [int(c.split("_")[1]) for c in fwd_cols]
    max_k = max(k_values) if k_values else 120

    fig = go.Figure()

    for sigma in sigmas:
        sub = study_df[(study_df["direction"] == direction) & (study_df["sigma"] == sigma)]
        if sub.empty:
            continue

        mat = sub[fwd_cols].values.astype(float)
        means = np.nanmean(mat, axis=0) * 100
        stds  = np.nanstd(mat, axis=0) * 100
        n     = int((~np.isnan(mat[:, 0])).sum())
        color = _color(sigma, direction)

        # ±1σ band
        fig.add_trace(go.Scatter(
            x=k_values + k_values[::-1],
            y=list(means + stds) + list((means - stds)[::-1]),
            fill="toself",
            fillcolor=_hex_to_rgba(color, 0.08),
            line=dict(width=0),
            showlegend=False,
            hoverinfo="skip",
        ))

        # Mean line
        fig.add_trace(go.Scatter(
            x=k_values,
            y=means,
            name=f"{sigma}σ  (n={n})",
            line=dict(color=color, width=2),
            hovertemplate=f"<b>{sigma}σ</b>  k=%{{x}}<br>Return: %{{y:.2f}}%<extra></extra>",
        ))

    # Zero reference
    fig.add_hline(y=0, line=dict(color="#8892a4", width=1.0, dash="dot"))
    _add_day_vlines(fig, max_k)

    dir_label = "Supply zones — short bias" if direction == "supply" else "Demand zones — long bias"
    fig.update_layout(
        **_BASE_LAYOUT,
        title=dict(text=f"<b>Mean Forward Return</b> — {dir_label}{title_suffix}", font=dict(size=13)),
        yaxis_title="Forward return (%)",
        height=420,
    )
    fig.update_xaxes(**_day_tick_axis(max_k))
    fig.update_yaxes(**_AXIS_STYLE)
    return fig


# ── hit rate ──────────────────────────────────────────────────────────────────

def plot_hit_rate(
    study_df: pd.DataFrame,
    direction: str,
    sigmas: Optional[list] = None,
) -> go.Figure:
    """Fraction of events where price moved in the favorable direction."""
    if sigmas is None:
        sigmas = ZONE_SIGMAS

    fwd_cols = sorted(
        [c for c in study_df.columns if c.startswith("fwd_")],
        key=lambda c: int(c.split("_")[1]),
    )
    k_values = [int(c.split("_")[1]) for c in fwd_cols]
    max_k = max(k_values) if k_values else 120

    fig = go.Figure()

    for sigma in sigmas:
        sub = study_df[(study_df["direction"] == direction) & (study_df["sigma"] == sigma)]
        if sub.empty:
            continue

        mat = sub[fwd_cols].values.astype(float)
        hits = (mat < 0) if direction == "supply" else (mat > 0)
        hit_rate = np.nanmean(hits, axis=0) * 100
        color = _color(sigma, direction)

        fig.add_trace(go.Scatter(
            x=k_values,
            y=hit_rate,
            name=f"{sigma}σ",
            line=dict(color=color, width=2),
            hovertemplate=f"<b>{sigma}σ</b>  k=%{{x}}<br>Hit rate: %{{y:.1f}}%<extra></extra>",
        ))

    # 50% random baseline
    fig.add_hline(y=50, line=dict(color="#8892a4", width=1.0, dash="dot"))
    _add_day_vlines(fig, max_k)

    dir_label = "Supply" if direction == "supply" else "Demand"
    fig.update_layout(
        **_BASE_LAYOUT,
        title=dict(text=f"<b>Hit Rate</b> — {dir_label} zones", font=dict(size=13)),
        yaxis_title="Hit rate (%)",
        height=380,
    )
    fig.update_xaxes(**_day_tick_axis(max_k))
    fig.update_yaxes(**_AXIS_STYLE, range=[25, 75])
    return fig


# ── sharpe vs k ───────────────────────────────────────────────────────────────

def plot_sharpe_vs_k(
    study_df: pd.DataFrame,
    direction: str,
    sigmas: Optional[list] = None,
) -> go.Figure:
    """
    Per-trade Sharpe vs holding period k.
    Peak = empirically optimal holding period.
    """
    if sigmas is None:
        sigmas = ZONE_SIGMAS

    fwd_cols = sorted(
        [c for c in study_df.columns if c.startswith("fwd_")],
        key=lambda c: int(c.split("_")[1]),
    )
    k_values = [int(c.split("_")[1]) for c in fwd_cols]
    max_k = max(k_values) if k_values else 120
    sign = -1 if direction == "supply" else 1

    fig = go.Figure()

    for sigma in sigmas:
        sub = study_df[(study_df["direction"] == direction) & (study_df["sigma"] == sigma)]
        if sub.empty:
            continue

        mat   = sign * sub[fwd_cols].values.astype(float)
        means = np.nanmean(mat, axis=0)
        stds  = np.nanstd(mat, axis=0)
        sharpes = np.where(stds > 1e-9, means / stds, np.nan)
        color = _color(sigma, direction)

        fig.add_trace(go.Scatter(
            x=k_values,
            y=sharpes,
            name=f"{sigma}σ",
            line=dict(color=color, width=2),
            hovertemplate=f"<b>{sigma}σ</b>  k=%{{x}}<br>Sharpe: %{{y:.3f}}<extra></extra>",
        ))

    fig.add_hline(y=0, line=dict(color="#8892a4", width=1.0, dash="dot"))
    _add_day_vlines(fig, max_k)

    dir_label = "Supply" if direction == "supply" else "Demand"
    fig.update_layout(
        **_BASE_LAYOUT,
        title=dict(text=f"<b>Per-Trade Sharpe vs Holding Period</b> — {dir_label}", font=dict(size=13)),
        yaxis_title="Sharpe (per-trade)",
        height=380,
    )
    fig.update_xaxes(**_day_tick_axis(max_k))
    fig.update_yaxes(**_AXIS_STYLE)
    return fig


# ── distribution ──────────────────────────────────────────────────────────────

def plot_distribution(
    study_df: pd.DataFrame,
    direction: str,
    k: int = 18,
    sigmas: Optional[list] = None,
) -> go.Figure:
    """Violin plot of forward returns at holding period k, one violin per σ level."""
    if sigmas is None:
        sigmas = ZONE_SIGMAS

    col = f"fwd_{k}"
    fig = go.Figure()

    if col not in study_df.columns:
        return fig

    for sigma in sigmas:
        sub = study_df[
            (study_df["direction"] == direction) & (study_df["sigma"] == sigma)
        ][col].dropna() * 100

        if sub.empty:
            continue

        color = _color(sigma, direction)
        fig.add_trace(go.Violin(
            y=sub,
            name=f"{sigma}σ",
            box_visible=True,
            meanline_visible=True,
            fillcolor=_hex_to_rgba(color, 0.35),
            line_color=color,
            points="outliers",
            hovertemplate=f"<b>{sigma}σ</b><br>%{{y:.2f}}%<extra></extra>",
        ))

    fig.add_hline(y=0, line=dict(color="#8892a4", width=1.0, dash="dot"))

    days = k / 6
    dir_label = "Supply" if direction == "supply" else "Demand"
    fig.update_layout(
        **_BASE_LAYOUT,
        title=dict(
            text=f"<b>Return Distribution</b> — {dir_label}  |  k={k} ({days:.1f}d)",
            font=dict(size=13),
        ),
        xaxis_title="Zone level (σ)",
        yaxis_title="Forward return (%)",
        showlegend=False,
        height=420,
        violingap=0.3,
    )
    return fig


# ── full report (2×4 subplot grid) ───────────────────────────────────────────

def full_report(
    study_df: pd.DataFrame,
    symbol: str = "BTC/USDT",
) -> go.Figure:
    """
    4-row × 2-col interactive report:
        Row 1: Return curves   (supply | demand)
        Row 2: Hit rate        (supply | demand)
        Row 3: Sharpe vs k     (supply | demand)
        Row 4: Distribution k=18 (supply | demand)
    """
    fig = make_subplots(
        rows=4, cols=2,
        subplot_titles=[
            "Return Curve — Supply", "Return Curve — Demand",
            "Hit Rate — Supply",     "Hit Rate — Demand",
            "Sharpe vs k — Supply",  "Sharpe vs k — Demand",
            "Distribution k=18 — Supply", "Distribution k=18 — Demand",
        ],
        vertical_spacing=0.08,
        horizontal_spacing=0.08,
    )

    fwd_cols = sorted(
        [c for c in study_df.columns if c.startswith("fwd_")],
        key=lambda c: int(c.split("_")[1]),
    )
    k_values = [int(c.split("_")[1]) for c in fwd_cols]

    for col_idx, direction in enumerate(["supply", "demand"], start=1):
        sign = -1 if direction == "supply" else 1

        for sigma in ZONE_SIGMAS:
            sub = study_df[(study_df["direction"] == direction) & (study_df["sigma"] == sigma)]
            if sub.empty:
                continue

            mat   = sub[fwd_cols].values.astype(float)
            means = np.nanmean(mat, axis=0) * 100
            stds  = np.nanstd(mat, axis=0) * 100
            hits  = np.nanmean((mat < 0) if direction == "supply" else (mat > 0), axis=0) * 100
            s_mat = sign * sub[fwd_cols].values.astype(float)
            s_means, s_stds = np.nanmean(s_mat, axis=0), np.nanstd(s_mat, axis=0)
            sharpes = np.where(s_stds > 1e-9, s_means / s_stds, np.nan)
            n = int((~np.isnan(mat[:, 0])).sum())
            color = _color(sigma, direction)
            show = sigma == ZONE_SIGMAS[0]  # only first sigma shows in legend per group

            # Row 1 — return curves
            fig.add_trace(go.Scatter(
                x=k_values, y=means, name=f"{sigma}σ (n={n})",
                line=dict(color=color, width=1.8),
                legendgroup=f"{direction}_{sigma}", showlegend=show,
                hovertemplate=f"{sigma}σ: %{{y:.2f}}%<extra></extra>",
            ), row=1, col=col_idx)

            # Row 2 — hit rate
            fig.add_trace(go.Scatter(
                x=k_values, y=hits, name=f"{sigma}σ",
                line=dict(color=color, width=1.8),
                legendgroup=f"{direction}_{sigma}", showlegend=False,
                hovertemplate=f"{sigma}σ: %{{y:.1f}}%<extra></extra>",
            ), row=2, col=col_idx)

            # Row 3 — sharpe
            fig.add_trace(go.Scatter(
                x=k_values, y=sharpes, name=f"{sigma}σ",
                line=dict(color=color, width=1.8),
                legendgroup=f"{direction}_{sigma}", showlegend=False,
                hovertemplate=f"{sigma}σ: %{{y:.3f}}<extra></extra>",
            ), row=3, col=col_idx)

            # Row 4 — violin at k=18
            dist_col = "fwd_18" if "fwd_18" in study_df.columns else fwd_cols[0]
            dist_data = sub[dist_col].dropna() * 100
            if not dist_data.empty:
                fig.add_trace(go.Violin(
                    y=dist_data, name=f"{sigma}σ", x=[f"{sigma}σ"] * len(dist_data),
                    fillcolor=_hex_to_rgba(color, 0.35),
                    line_color=color, box_visible=True, meanline_visible=True,
                    legendgroup=f"{direction}_{sigma}", showlegend=False,
                    points=False,
                ), row=4, col=col_idx)

    fig.update_layout(
        **_BASE_LAYOUT,
        title=dict(
            text=f"<b>Monthly Volatility Zone — Forward Return Study</b>  |  {symbol}",
            font=dict(size=15),
        ),
        height=1400,
    )
    return fig
