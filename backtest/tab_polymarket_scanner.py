"""
Polymarket Scanner v2 — Streamlit tab.
Call via: render_polymarket_scanner_tab(df_hitrate, df_returns, df_events)
"""

from __future__ import annotations

from datetime import datetime, timezone, date
import calendar
import math
from typing import Optional

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import scanner_config as cfg
from polymarket_live import fetch_active_market, _current_event_slug
from polymarket_scanner import (
    fetch_btc_price,
    get_scanner_data,
    calibrate_min_sigma,
    current_sigma,
    get_regime,
    decay_table,
    barrier_prob,
)


# ── helpers ───────────────────────────────────────────────────────────────────

def _days_remaining_in_month() -> int:
    today = date.today()
    last  = calendar.monthrange(today.year, today.month)[1]
    return last - today.day


def _color_edge(val: float) -> str:
    if pd.isna(val):
        return ""
    if val > 12:
        return "background-color:#1a6e3c; color:white"
    if val > 8:
        return "background-color:#27ae60; color:white"
    if val > 4:
        return "background-color:#f39c12; color:black"
    if val < -8:
        return "background-color:#c0392b; color:white"
    if val < -4:
        return "background-color:#e74c3c; color:white"
    return "background-color:#636e72; color:white"


def _color_signal(val: str) -> str:
    if "STRONG" in str(val):
        return "background-color:#1a6e3c; color:white; font-weight:bold"
    if "MODERATE" in str(val):
        return "background-color:#27ae60; color:white"
    if "CONFLICT" in str(val):
        return "background-color:#e67e22; color:white"
    return "color:#b2bec3"


def _price_to_activate_sd(
    btc_price: float, monthly_open: float, annual_vol: float, threshold: float
) -> tuple[float, float]:
    monthly_vol  = annual_vol / math.sqrt(12)
    demand_price = monthly_open * math.exp(-threshold * monthly_vol)
    supply_price = monthly_open * math.exp(+threshold * monthly_vol)
    return demand_price, supply_price


# ── market data cache ─────────────────────────────────────────────────────────

@st.cache_data(ttl=300, show_spinner=False)
def _fetch_market_data(slug_override: str | None, refresh_key: int) -> tuple[float, dict, datetime]:
    """TTL=5min. slug_override=None → auto-detect current month. refresh_key busts the cache."""
    btc_price = fetch_btc_price()
    odds      = fetch_active_market(slug=slug_override)
    ts        = datetime.now(timezone.utc)
    return btc_price, odds, ts


# ── main tab ──────────────────────────────────────────────────────────────────

def render_polymarket_scanner_tab(
    df_hitrate: Optional[pd.DataFrame] = None,
    df_returns: Optional[pd.DataFrame] = None,
    df_events:  Optional[pd.DataFrame] = None,
) -> None:
    """
    Renders the Polymarket Scanner tab.

    Parameters
    ----------
    df_hitrate : output of summarize_events() from the Vol Zone Study
                 Columns: direction, sigma, k, hit_rate, n_events, sharpe, ...
    df_returns : same DataFrame (or None)
    df_events  : full study DataFrame with fwd_k columns (for historical scatter)
    """

    study_available = df_hitrate is not None and not df_hitrate.empty

    # ── sidebar ───────────────────────────────────────────────────────────────
    with st.sidebar:
        with st.expander("⚙ Scanner Config", expanded=False):
            monthly_open = st.number_input(
                "Monthly open ($)", value=66_973.0, step=100.0, format="%.2f",
                help=(
                    "BTC opening price at the start of the current month. "
                    "Reference for all zone calculations: zone = monthly_open × (1 ± σ × monthly_vol). "
                    "Update this manually at the beginning of each month."
                ),
            )
            _monthly_vol_study = st.session_state.get("current_monthly_vol")
            _default_annual_vol = (
                round(min(max(_monthly_vol_study * math.sqrt(12), 0.30), 1.20) / 0.05) * 0.05
                if _monthly_vol_study else cfg.ANNUAL_VOL
            )
            annual_vol = st.slider(
                "Annualized BTC vol", 0.30, 1.20, _default_annual_vol, step=0.05,
                format="%.2f",
                help=(
                    "BTC annualized volatility for the barrier model and σ calculation. "
                    f"{'Auto-synced from Vol Zone Study: ' + f'{_default_annual_vol:.0%}.' if _monthly_vol_study else 'Run the Vol Zone Study to enable auto-sync.'} "
                    "Formula: monthly_vol = annual_vol / √12. "
                    "Higher vol → wider zones → lower barrier probabilities."
                ),
            )
            days_remaining = st.number_input(
                "Days remaining in month",
                value=_days_remaining_in_month(),
                min_value=1, max_value=31, step=1,
                help=(
                    "Calendar days until month end. Determines time horizon T for the "
                    "log-normal barrier model: T = days / 365. "
                    "Fewer days → lower P(touch) for far-away strikes."
                ),
            )
            _auto_slug = _current_event_slug()
            slug_override = st.text_input(
                "Slug override (leave blank = auto)",
                value="",
                placeholder=_auto_slug,
                help=(
                    f"Polymarket event slug. Leave blank to auto-detect the current month's BTC event. "
                    f"Auto-detected: {_auto_slug}. "
                    "Use override only if Polymarket changes the event naming convention."
                ),
            )
            event_slug = slug_override.strip() or None
            min_edge = st.slider(
                "Min edge (pp)", 4, 20, int(cfg.MIN_EDGE_PP), step=1,
                help=(
                    "Minimum edge in percentage points to generate a BUY signal. "
                    "Edge = Consensus% − Poly YES%. "
                    "Below this threshold the row shows MONITOR. "
                    "Higher threshold = fewer but higher-conviction signals."
                ),
            )
            w_barrier = st.slider(
                "Barrier weight", 0.1, 1.0, cfg.W_BARRIER, step=0.05,
                help=(
                    "Weight assigned to the log-normal barrier model in the blended consensus probability. "
                    "SD (historical hit-rate) weight = 1 − barrier weight. "
                    "Default 0.6 / 0.4. Increase to trust the model more over historical data."
                ),
            )
            w_sd = round(1.0 - w_barrier, 2)
            min_sigma_override = st.slider(
                "Min σ to activate SD", 0.0, 3.0, 0.0, step=0.25, format="%.2f",
                help=(
                    "Minimum distance from monthly open (in monthly-σ units) before the "
                    "historical SD data is blended into the consensus. "
                    "0 = SD always active regardless of current position. "
                    "Increase to restrict SD contribution to high-conviction regime entries only."
                ),
            )

    # ── session state ─────────────────────────────────────────────────────────
    if "scanner_refresh" not in st.session_state:
        st.session_state["scanner_refresh"] = 0

    # ── calibrate threshold ───────────────────────────────────────────────────
    min_sigma_calibrated = calibrate_min_sigma(
        df_hitrate, min_n_events=cfg.MIN_N_EVENTS, min_hit_rate_diff=0.05
    )

    # ── fetch market data ─────────────────────────────────────────────────────
    with st.spinner("Fetching live strikes from Polymarket..."):
        try:
            btc_price, odds, ts = _fetch_market_data(
                event_slug, st.session_state["scanner_refresh"]
            )
            load_error = None
        except Exception as e:
            load_error = str(e)
            btc_price  = None
            odds       = {}
            ts         = datetime.now(timezone.utc)

    # ── run scanner ───────────────────────────────────────────────────────────
    try:
        df = get_scanner_data(
            btc_price       = btc_price or 0.0,
            monthly_open    = monthly_open,
            annual_vol      = annual_vol,
            days_remaining  = int(days_remaining),
            polymarket_odds = odds,
            df_hitrate      = df_hitrate,
            df_returns      = df_returns,
            min_sigma       = min_sigma_override,
            min_edge        = float(min_edge),
            w_barrier       = w_barrier,
            w_sd            = w_sd,
            min_n_events    = cfg.MIN_N_EVENTS,
        )
        scanner_error = None
    except Exception as e:
        scanner_error = str(e)
        df = pd.DataFrame()

    # ── header ────────────────────────────────────────────────────────────────
    col_title, col_refresh = st.columns([4, 1])
    with col_title:
        st.subheader("🎯 Polymarket Scanner")
        _slug_display = event_slug or _current_event_slug()
        _poly_url     = f"https://polymarket.com/event/{_slug_display}"
        _slug_label   = "(auto)" if event_slug is None else "(override)"
        st.caption(f"Market: [{_slug_display}]({_poly_url}) {_slug_label}")
    with col_refresh:
        st.write("")
        if st.button("🔄 Refresh odds", use_container_width=True):
            _fetch_market_data.clear()
            st.session_state["scanner_refresh"] += 1
            st.rerun()
        st.caption(f"*{ts.strftime('%H:%M UTC')}*")

    if load_error:
        st.error(f"**Failed to fetch strikes from Polymarket:**\n\n{load_error}")
        st.info(
            "Check your connection and click **🔄 Refresh odds**. "
            "No live data = no fallback — strikes are 100% API-sourced."
        )
        return
    if scanner_error:
        st.error(f"Scanner error: {scanner_error}")
    if not study_available:
        st.warning(
            "⚠ Vol Zone Study not yet run — historical SD is **inactive**. "
            "Run the study in the **📈 Vol Zone Study** tab to enable empirical hit-rate data."
        )

    if df.empty:
        st.warning("No data available.")
        return

    # ── KPIs ──────────────────────────────────────────────────────────────────
    sigma_at  = current_sigma(btc_price, monthly_open, annual_vol)
    regime    = get_regime(btc_price, monthly_open)
    sd_active = df["sd_active"].iloc[0] if not df.empty else False

    regime_label = {
        "above_open": "Above open — supply bias",
        "below_open": "Below open — demand bias",
        "neutral"   : "Neutral",
    }.get(regime, regime)

    n_signals = len(df[df["signal"] != "MONITOR"])
    n_strong  = len(df[df["signal_strength"].str.contains("STRONG", na=False)])

    effective_threshold = min_sigma_override

    if sd_active and study_available:
        n_sd_bucket = df["n_sd"].dropna()
        n_sd_val    = int(n_sd_bucket.iloc[0]) if not n_sd_bucket.empty else 0
        sigma_badge = f"SD active — N={n_sd_val} events in bucket"
        sigma_delta_color = "normal"
    else:
        sigma_badge = f"SD inactive (threshold: {effective_threshold:.2f}σ)"
        sigma_delta_color = "off"

    k1, k2, k3, k4 = st.columns(4)
    k1.metric(
        "BTC / USDT", f"${btc_price:,.0f}",
        help="Live BTC/USDT spot price fetched from Binance REST API.",
    )
    k2.metric(
        "Current σ vs open", f"{sigma_at:.2f}σ",
        delta=f"{regime_label} | {sigma_badge}",
        delta_color=sigma_delta_color,
        help=(
            "Distance from current BTC price to the monthly open, measured in monthly-vol units. "
            "Formula: |log(BTC / monthly_open)| / (annual_vol / √12). "
            "Higher σ = BTC has moved further from the month's opening price."
        ),
    )
    k3.metric(
        "Days remaining", f"{int(days_remaining)}d",
        help="Calendar days until end of month. Drives time-to-expiry T in the barrier model: T = days / 365.",
    )
    k4.metric(
        "Active signals", f"{n_signals}",
        delta=f"{n_strong} STRONG" if n_strong else "no STRONG",
        delta_color="normal" if n_strong else "off",
        help=(
            "Number of strikes where |edge| > min_edge threshold. "
            "STRONG = both barrier model and historical SD agree on direction + |edge| ≥ 12pp."
        ),
    )

    st.divider()

    # ── strikes table ─────────────────────────────────────────────────────────
    st.markdown("**Strikes Table**")

    display_cols = [
        "strike", "direction", "dist_pct",
        "poly_yes", "p_barrier", "p_sd", "n_sd", "p_internal",
        "edge_pp", "signal", "signal_strength", "cost_¢", "gain_¢", "ev_¢", "kelly_pct",
    ]
    display_cols = [c for c in display_cols if c in df.columns]

    rename = {
        "strike"         : "Strike",
        "direction"      : "Dir",
        "dist_pct"       : "Dist %",
        "poly_yes"       : "Poly YES %",
        "p_barrier"      : "Barrier %",
        "p_sd"           : "SD %",
        "n_sd"           : "N",
        "p_internal"     : "Consensus %",
        "edge_pp"        : "Edge pp",
        "signal"         : "Action",
        "signal_strength": "Strength",
        "cost_¢"         : "Cost ¢",
        "gain_¢"         : "Gain ¢",
        "ev_¢"           : "EV ¢",
        "kelly_pct"      : "Kelly %",
    }

    table = df[display_cols].rename(columns=rename).copy()
    table["Strike"] = table["Strike"].apply(lambda x: f"${x:,}")

    if "SD %" in table.columns and "N" in table.columns:
        def _fmt_sd(row):
            if pd.isna(row["SD %"]) or row["SD %"] is None:
                return "—"
            n = int(row["N"]) if pd.notna(row["N"]) else "?"
            return f'{row["SD %"]:.1f}% (N={n})'
        table["SD % (N)"] = table.apply(_fmt_sd, axis=1)
        table = table.drop(columns=["SD %", "N"])
        cols = list(table.columns)
        barr_idx = cols.index("Barrier %") if "Barrier %" in cols else -1
        if barr_idx >= 0:
            cols.remove("SD % (N)")
            cols.insert(barr_idx + 1, "SD % (N)")
            table = table[cols]

    def _color_action(val: str) -> str:
        if val == "BUY YES":
            return "background-color:#1a4a8a; color:white; font-weight:bold"
        if val == "BUY NO":
            return "background-color:#6b2d8a; color:white; font-weight:bold"
        return "color:#636e72"

    fmt_cols = {
        "Dist %"      : "{:+.1f}%",
        "Poly YES %"  : "{:.1f}%",
        "Barrier %"   : "{:.1f}%",
        "Consensus %" : "{:.1f}%",
        "Edge pp"     : "{:+.1f}",
        "EV ¢"        : "{:+.1f}¢",
        "Kelly %"     : "{:.1f}%",
    }
    fmt_cols = {k: v for k, v in fmt_cols.items() if k in table.columns}

    applymap_cols = {}
    if "Edge pp"  in table.columns: applymap_cols["Edge pp"]  = _color_edge
    if "Strength" in table.columns: applymap_cols["Strength"] = _color_signal
    if "Action"   in table.columns: applymap_cols["Action"]   = _color_action

    styler = table.style.format(fmt_cols, na_rep="—")
    for col, fn in applymap_cols.items():
        styler = styler.applymap(fn, subset=[col])
    styler = styler.format(
        lambda x: f"{x:.1f}¢" if pd.notna(x) else "—",
        subset=[c for c in ["Cost ¢", "Gain ¢"] if c in table.columns]
    ).set_properties(**{"font-size": "13px"})

    def _row_highlight(row):
        if "STRONG" in str(row.get("Strength", "")):
            return ["background-color:#0d3321"] * len(row)
        return [""] * len(row)

    styler = styler.apply(_row_highlight, axis=1)
    st.dataframe(styler, use_container_width=True, height=420)

    # ── column guide ──────────────────────────────────────────────────────────
    with st.expander("📖 Column Guide", expanded=False):
        st.markdown("""
| Column | Description |
|---|---|
| **Strike** | BTC price level this Polymarket market resolves at (end of month) |
| **Dir** | *reach* = "Will BTC reach this price from below?" / *dip* = "Will BTC dip to this price from above?" |
| **Dist %** | Distance from current BTC spot to the strike. Positive = strike is above spot. |
| **Poly YES %** | Mid-price of the YES token on Polymarket — the market-implied probability of the event occurring |
| **Barrier %** | Log-normal barrier model probability: `2 × Φ(−\|ln(K/S)\| / (σ√T))`. No drift assumed. Pure mathematical estimate. |
| **SD % (N)** | Historical hit-rate from the Vol Zone Study at the closest σ bucket. N = number of past events used. Only shown when SD is active. |
| **Consensus %** | Blended internal probability: `barrier_weight × Barrier + sd_weight × SD`. Uses barrier only when SD is inactive. |
| **Edge pp** | `Consensus% − Poly YES%` in percentage points. **Positive → market underprices YES → BUY YES**. **Negative → market overprices YES → BUY NO**. |
| **Action** | Trade direction: **BUY YES** (buy the YES token) / **BUY NO** (buy the NO token) / **MONITOR** (edge below threshold) |
| **Strength** | **STRONG** = barrier and SD agree on direction + \|edge\| ≥ 12pp. **MODERATE** = models agree but edge < 12pp. **CONFLICTING** = models disagree. |
| **Cost ¢** | Price paid per share in cents. For BUY YES = Poly YES price. For BUY NO = Poly NO price (= 100 − Poly YES). |
| **Gain ¢** | Maximum profit per share if correct: `(100 − cost)¢`. Each share pays $1 at resolution. |
| **EV ¢** | Expected value per share: `p × gain − (1−p) × cost`. Positive = positive expectancy trade. |
| **Kelly %** | Half-Kelly position size as % of bankroll per trade: `0.5 × max(0, (p×b − q) / b)` where `b = gain/cost`. |
""")

    # ── model context ─────────────────────────────────────────────────────────
    with st.expander("📐 Model Context", expanded=False):
        c1, c2 = st.columns(2)

        with c1:
            st.markdown("**Parameters**")
            sigma_sqrt_t = annual_vol * math.sqrt(int(days_remaining) / 365)
            st.code(
                f"S (BTC spot)      = ${btc_price:,.2f}\n"
                f"Monthly open      = ${monthly_open:,.2f}\n"
                f"T (days left)     = {int(days_remaining)}d\n"
                f"Annual vol        = {annual_vol:.0%}\n"
                f"sigma x sqrt(T)   = {sigma_sqrt_t:.1%}\n"
                f"Current sigma     = {sigma_at:.3f}s\n"
                f"Regime            = {regime_label}\n"
                f"Effective min σ   = {effective_threshold:.2f}σ (slider)\n"
                f"Calibrated min σ  = {min_sigma_calibrated:.2f}σ (reference only)\n"
                f"Weights           = barrier {w_barrier:.0%} / SD {w_sd:.0%}\n"
                f"Min edge          = {min_edge}pp"
            )

        with c2:
            st.markdown("**Historical SD**")
            if not study_available:
                st.warning(
                    "⚠ Vol Zone Study not run.  \n"
                    "Run the study to activate empirical SD with real event data."
                )
            elif sd_active:
                sigma_col    = "sigma" if "sigma" in df_hitrate.columns else "sigma_level"
                avail_sigmas = sorted(df_hitrate[sigma_col].unique())
                closest_sig  = min(avail_sigmas, key=lambda s: abs(s - sigma_at))
                k_target     = int(days_remaining) * 6
                subset = df_hitrate[
                    (df_hitrate[sigma_col] == closest_sig) &
                    (df_hitrate["direction"] == ("supply" if regime == "above_open" else "demand"))
                ].sort_values("k")

                st.success(
                    f"SD **active** — bucket σ≈{closest_sig}  \n"
                    f"Target k: {k_target} bars ({int(days_remaining)}d)"
                )
                if not subset.empty:
                    disp = subset[["k", "n_events", "hit_rate", "sharpe"]].copy()
                    disp["k_days"]   = (disp["k"] / 6).round(1)
                    disp["hit_rate"] = (disp["hit_rate"] * 100).round(1)
                    disp["sharpe"]   = disp["sharpe"].round(3)
                    disp = disp.rename(columns={
                        "k": "k (bars)", "k_days": "k (days)",
                        "n_events": "N", "hit_rate": "Hit rate %",
                    })
                    st.dataframe(
                        disp[["k (bars)", "k (days)", "N", "Hit rate %", "sharpe"]],
                        use_container_width=True, hide_index=True,
                    )
            else:
                demand_price, supply_price = _price_to_activate_sd(
                    btc_price, monthly_open, annual_vol, effective_threshold
                )
                st.warning(
                    f"⚠ SD **inactive** — current σ ({sigma_at:.2f}σ) below effective threshold "
                    f"({effective_threshold:.2f}σ — slider)  \n\n"
                    f"Empirically calibrated threshold: {min_sigma_calibrated:.2f}σ  \n\n"
                    f"Model is using barrier-only probability.  \n\n"
                    f"To activate SD at current threshold:  \n"
                    f"- Demand: BTC drops to **${demand_price:,.0f}**  \n"
                    f"- Supply: BTC rises to **${supply_price:,.0f}**  \n\n"
                    f"Or lower the **Min σ to activate SD** slider to ≤ {sigma_at:.2f}σ"
                )

    # ── historical scatter ─────────────────────────────────────────────────────
    if sd_active and study_available and df_events is not None and not df_events.empty:
        st.divider()
        st.markdown("**Historical Events — Active Bucket**")
        st.caption(
            "Forward returns of historical zone-touch events that underpin the SD signal. "
            "Each dot = one monthly touch event in the current σ bucket."
        )

        sigma_col    = "sigma" if "sigma" in df_hitrate.columns else "sigma_level"
        avail_sigmas = sorted(df_hitrate[sigma_col].unique())
        closest_sig  = min(avail_sigmas, key=lambda s: abs(s - sigma_at))
        hist_dir     = "supply" if regime == "above_open" else "demand"

        events_bucket = df_events[
            (df_events["sigma"] == closest_sig) &
            (df_events["direction"] == hist_dir)
        ].copy()

        if not events_bucket.empty:
            max_k_in_events = int(days_remaining) * 6
            available_fwd   = [c for c in events_bucket.columns if c.startswith("fwd_")]
            if available_fwd:
                fwd_nums  = sorted([int(c.split("_")[1]) for c in available_fwd])
                k_display = min(fwd_nums, key=lambda k: abs(k - max_k_in_events))

                c_scatter, c_slider = st.columns([3, 1])
                with c_slider:
                    k_pick = st.select_slider(
                        "Holding period (bars)",
                        options=fwd_nums,
                        value=k_display,
                        key="scatter_k_slider",
                        format_func=lambda k: f"k={k} ({k/6:.0f}d)",
                        help="Forward return horizon shown on the scatter. 6 bars = 1 day. Default = closest to current days remaining.",
                    )
                    fwd_col_pick = f"fwd_{k_pick}"
                    if fwd_col_pick in events_bucket.columns:
                        events_bucket["fwd_pct"] = events_bucket[fwd_col_pick] * 100

                with c_scatter:
                    color_map = {"supply": "#e74c3c", "demand": "#27ae60"}
                    fig = go.Figure()
                    fig.add_trace(go.Scatter(
                        x=events_bucket["timestamp"].astype(str),
                        y=events_bucket["fwd_pct"],
                        mode="markers",
                        marker=dict(
                            color=color_map.get(hist_dir, "#74b9ff"),
                            size=9, opacity=0.8,
                            line=dict(width=1, color="white"),
                        ),
                        text=[
                            f"{row['timestamp'].strftime('%b %Y')}<br>"
                            f"Zone: {row['zone_level']:,.0f}<br>"
                            f"Ret {k_pick}b: {row['fwd_pct']:+.1f}%"
                            for _, row in events_bucket.iterrows()
                        ],
                        hovertemplate="%{text}<extra></extra>",
                        name=f"{hist_dir} σ={closest_sig}",
                    ))
                    fig.add_hline(y=0, line_dash="dash", line_color="#636e72", line_width=1)
                    fig.update_layout(
                        template="plotly_dark",
                        height=300,
                        margin=dict(l=0, r=0, t=30, b=0),
                        title=dict(
                            text=(
                                f"σ≈{closest_sig} {hist_dir} — {len(events_bucket)} events | "
                                f"Forward return k={k_pick} ({k_pick/6:.0f}d)"
                            ),
                            font=dict(size=12),
                        ),
                        xaxis_title="",
                        yaxis_title="Forward return (%)",
                        yaxis=dict(tickformat="+.1f"),
                        showlegend=False,
                    )
                    st.plotly_chart(fig, use_container_width=True)
        else:
            st.info(f"No historical events found for σ≈{closest_sig} {hist_dir}.")

    # ── time decay ────────────────────────────────────────────────────────────
    strong_rows = df[df["signal_strength"].str.contains("STRONG", na=False)]

    if not strong_rows.empty:
        st.divider()
        st.markdown("**Time Decay — STRONG Signals**")
        st.caption(
            "P(touch) from the log-normal barrier model at each 6-day step until month end. "
            "Shows how the probability of hitting the strike decreases as time runs out."
        )

        for _, row in strong_rows.iterrows():
            strike    = row["strike"]
            signal    = row["signal"]
            direction = row["direction"]
            edge      = row["edge_pp"]

            label = (
                f"${strike:,} {'▲ reach' if direction == 'reach' else '▼ dip'}  "
                f"| {signal}  | Edge {edge:+.1f}pp"
            )
            st.markdown(f"*{label}*")

            dec = decay_table(strike, btc_price, annual_vol, int(days_remaining))

            def _color_ptouch(val):
                if val > 15: return "color:#e74c3c; font-weight:bold"
                if val > 8:  return "color:#f39c12"
                return "color:#27ae60"

            dec_styler = (
                dec.style
                .applymap(_color_ptouch, subset=["P(touch) %"])
                .format({"P(touch) %": "{:.1f}%", "P(no touch) %": "{:.1f}%"})
                .set_properties(**{"font-size": "12px"})
            )
            st.dataframe(dec_styler, use_container_width=True, hide_index=True)

    # ── footer ────────────────────────────────────────────────────────────────
    st.divider()
    source_tag = "live" if df["source"].iloc[0] == "live" else "fallback"
    sd_tag = (
        f"SD: Vol Zone Study hit-rate (N={len(df_events)} events)"
        if study_available and df_events is not None
        else "SD: inactive (study not run)"
    )
    st.caption(
        f"Odds source: {source_tag}  |  "
        f"Model: drift-free log-normal barrier  |  "
        f"{sd_tag}  |  "
        f"Calibrated min σ: {min_sigma_calibrated:.2f}σ  |  "
        f"Updated: {ts.strftime('%Y-%m-%d %H:%M UTC')}"
    )
