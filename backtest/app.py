"""
Streamlit app — Monthly Volatility Zone Forward Return Study

Run with:
    python -m streamlit run app.py
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, str(Path(__file__).parent))

from data_fetcher import fetch_crypto_ohlcv, resample_to_daily
from event_study import compute_forward_returns, detect_zone_touches, summarize_events
from visualization import (
    DEMAND_COLOR,
    SUPPLY_COLOR,
    full_report,
    plot_distribution,
    plot_hit_rate,
    plot_price_zones,
    plot_return_curve,
    plot_sharpe_vs_k,
    _hex_to_rgba,
    _color,
)
from zone_calculator import ZONE_SIGMAS, compute_zones

try:
    from vbt_backtest import run_single, sweep_params
    _VBT_OK = True
except ImportError:
    _VBT_OK = False

# ── page config ───────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="Vol Zone Study",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── sidebar ───────────────────────────────────────────────────────────────────

with st.sidebar:
    st.title("⚙️ Settings")

    symbol_preset = st.selectbox(
        "Symbol",
        ["BTC/USDT", "HYPE/USDT", "ETH/USDT", "SOL/USDT"],
        index=0,
    )
    custom_symbol = st.text_input("Or enter custom symbol", placeholder="e.g. WIF/USDT")
    symbol = custom_symbol.strip().upper() if custom_symbol.strip() else symbol_preset

    since = st.text_input("From (YYYY-MM-DD)", "2020-01-01")

    st.divider()

    lookback = st.slider(
        "Vol Lookback (days)", 90, 500, 360, step=10,
        help="Rolling window for daily vol — 360 matches the Pine Script indicator.",
    )
    max_k = st.slider(
        "Max Holding Period (4H bars)", 30, 200, 120, step=6,
        help="120 bars = 20 days at 4H granularity.",
    )

    st.divider()

    sigmas_selected = st.multiselect(
        "Zone levels (σ)",
        options=ZONE_SIGMAS,
        default=ZONE_SIGMAS,
    )

    run = st.button("▶  Run Study", type="primary", use_container_width=True)

# ── data pipeline ─────────────────────────────────────────────────────────────

@st.cache_data(show_spinner=False)
def load_and_compute(symbol: str, since: str, lookback: int, max_k: int):
    df_4h    = fetch_crypto_ohlcv(symbol, "4h", since)
    daily    = resample_to_daily(df_4h)
    df_zones = compute_zones(df_4h, daily, lookback=lookback)
    events   = detect_zone_touches(df_zones)
    study    = compute_forward_returns(df_zones, events, max_k=max_k)
    return study, df_zones

# ── main ──────────────────────────────────────────────────────────────────────

st.title("Monthly Volatility Zone — Forward Return Study")
st.caption(
    "Detects the first 4H bar each month where price wicks to a σ zone (OHLC-based). "
    "Reports forward return distributions at each holding period k."
)

if run:
    with st.spinner(f"Loading data for **{symbol}**..."):
        try:
            study, df_zones = load_and_compute(symbol, since, lookback, max_k)
            st.session_state.update({
                "study": study, "df_zones": df_zones, "symbol": symbol,
                "max_k": max_k, "sigmas": sigmas_selected, "since": since,
            })
        except Exception as e:
            st.error(f"Error: {e}")
            st.stop()

if "study" not in st.session_state:
    st.info("Configure settings in the sidebar and click **▶ Run Study**.")
    st.stop()

study:    pd.DataFrame = st.session_state["study"]
df_zones: pd.DataFrame = st.session_state["df_zones"]
symbol:   str          = st.session_state["symbol"]
_max_k:   int          = st.session_state["max_k"]
_sigmas:  list         = st.session_state.get("sigmas", ZONE_SIGMAS)
_since:   str          = st.session_state.get("since", since)

# ── summary metrics ───────────────────────────────────────────────────────────

sub_s = study[study["direction"] == "supply"]
sub_d = study[study["direction"] == "demand"]

c1, c2, c3, c4 = st.columns(4)
c1.metric("Total events",        len(study))
c2.metric("Supply touch events", len(sub_s))
c3.metric("Demand touch events", len(sub_d))
c4.metric(
    "Date range",
    f"{study['timestamp'].min().strftime('%b %Y')} – {study['timestamp'].max().strftime('%b %Y')}",
)

if len(study) < 50:
    st.warning(f"⚠️  Only {len(study)} events for {symbol}. Limited history — interpret with caution.")

st.divider()

# ── tabs ──────────────────────────────────────────────────────────────────────

_tab_names = ["Price Chart", "Return Curves", "Hit Rate", "Sharpe vs k", "Distribution", "Full Report", "Data"]
if _VBT_OK:
    _tab_names.append("VectorBT Sweep")

_tabs = st.tabs(_tab_names)
tab_price, tab_curves, tab_hit, tab_sharpe, tab_dist, tab_report, tab_data = _tabs[:7]
tab_vbt = _tabs[7] if _VBT_OK else None

# ── Price Chart ───────────────────────────────────────────────────────────────

with tab_price:
    st.subheader("Price History with Zone Levels")
    st.caption(
        "Candlestick chart with monthly volatility zones overlaid. "
        "Zones reset at every new month. Triangles mark first-touch events."
    )

    pc_c1, pc_c2 = st.columns([3, 1])
    with pc_c2:
        pc_sigmas = st.multiselect(
            "Sigma levels to show",
            options=ZONE_SIGMAS,
            default=[s for s in ZONE_SIGMAS if s in [0.5, 1.0, 1.5, 2.0, 3.0, 4.0]],
            key="pc_sigmas",
        )
        pc_touches = st.toggle("Show touch events", value=True, key="pc_touches")

    with pc_c1:
        st.plotly_chart(
            plot_price_zones(
                df_zones, study,
                symbol=symbol,
                sigmas=pc_sigmas or None,
                show_touches=pc_touches,
            ),
            use_container_width=True,
        )


# ── Return Curves ─────────────────────────────────────────────────────────────

with tab_curves:
    st.subheader("Mean Forward Return vs Holding Period")
    st.caption(
        "Supply: negative return = favorable (price fell). "
        "Demand: positive return = favorable. Band = ±1σ across events."
    )
    c1, c2 = st.columns(2)
    with c1:
        st.plotly_chart(
            plot_return_curve(study, "supply", sigmas=_sigmas, title_suffix=f" | {symbol}"),
            use_container_width=True,
        )
    with c2:
        st.plotly_chart(
            plot_return_curve(study, "demand", sigmas=_sigmas, title_suffix=f" | {symbol}"),
            use_container_width=True,
        )

# ── Hit Rate ──────────────────────────────────────────────────────────────────

with tab_hit:
    st.subheader("Hit Rate vs Holding Period")
    st.caption("Fraction of events where price moved in the expected direction. 50% = random baseline.")
    c1, c2 = st.columns(2)
    with c1:
        st.plotly_chart(plot_hit_rate(study, "supply", sigmas=_sigmas), use_container_width=True)
    with c2:
        st.plotly_chart(plot_hit_rate(study, "demand", sigmas=_sigmas), use_container_width=True)

# ── Sharpe vs k ───────────────────────────────────────────────────────────────

with tab_sharpe:
    st.subheader("Per-Trade Sharpe vs Holding Period")
    st.caption("Peak = empirically optimal holding period for each zone level.")
    c1, c2 = st.columns(2)
    with c1:
        st.plotly_chart(plot_sharpe_vs_k(study, "supply", sigmas=_sigmas), use_container_width=True)
    with c2:
        st.plotly_chart(plot_sharpe_vs_k(study, "demand", sigmas=_sigmas), use_container_width=True)

# ── Distribution ──────────────────────────────────────────────────────────────

with tab_dist:
    st.subheader("Forward Return Distribution at a Single Holding Period")
    st.caption("Violin plot — full return distribution per zone level at a chosen k.")

    k_for_dist = st.select_slider(
        "Holding period k (4H bars)",
        options=list(range(1, _max_k + 1)),
        value=min(18, _max_k),
        format_func=lambda k: f"k={k}  ({k/6:.1f}d)",
    )

    c1, c2 = st.columns(2)
    with c1:
        st.plotly_chart(
            plot_distribution(study, "supply", k=k_for_dist, sigmas=_sigmas),
            use_container_width=True,
        )
    with c2:
        st.plotly_chart(
            plot_distribution(study, "demand", k=k_for_dist, sigmas=_sigmas),
            use_container_width=True,
        )

# ── Full Report ───────────────────────────────────────────────────────────────

with tab_report:
    st.subheader("Full Report")
    st.caption("All panels in one interactive view.")
    if st.button("Generate Full Report"):
        with st.spinner("Rendering..."):
            st.plotly_chart(full_report(study, symbol=symbol), use_container_width=True)

# ── Data ──────────────────────────────────────────────────────────────────────

with tab_data:
    st.subheader("Event Data")

    st.write("**Summary statistics at key holding periods**")
    summary = summarize_events(study, max_k=_max_k)
    key_ks  = [k for k in [6, 12, 18, 30, 42, 60, 90, 120] if k <= _max_k]
    pivot   = summary[summary["k"].isin(key_ks)].copy()
    pivot["mean_ret_%"] = (pivot["mean_ret"] * 100).round(2)
    pivot["hit_rate_%"] = (pivot["hit_rate"] * 100).round(1)
    pivot["sharpe"]     = pivot["sharpe"].round(3)
    st.dataframe(
        pivot[["direction", "sigma", "k", "n_events", "mean_ret_%", "hit_rate_%", "sharpe"]]
        .sort_values(["direction", "sigma", "k"]),
        use_container_width=True,
    )

    st.write("**Raw event list (first 100 rows)**")
    preview_cols = ["timestamp", "month", "sigma", "direction", "zone_level",
                    "monthly_open", "monthly_vol", "fwd_6", "fwd_18", "fwd_42", "fwd_90"]
    available = [c for c in preview_cols if c in study.columns]
    st.dataframe(study[available].head(100), use_container_width=True)

    st.download_button(
        "⬇ Download full event CSV",
        data=study.to_csv(index=False),
        file_name=f"zone_study_{symbol.replace('/', '_')}.csv",
        mime="text/csv",
        use_container_width=True,
    )

# ── VectorBT Sweep ────────────────────────────────────────────────────────────

if _VBT_OK and tab_vbt is not None:
    with tab_vbt:
        st.subheader("VectorBT Portfolio Simulation")
        st.caption(
            "Simulates an actual portfolio: enter at touch-bar close, exit after k bars. "
            "Overlapping trades within hold_k bars are skipped (accumulate=False)."
        )

        vbt_c1, vbt_c2 = st.columns(2)
        with vbt_c1:
            vbt_tc = st.number_input(
                "Transaction cost (one-way)", value=0.001, step=0.0005, format="%.4f",
                help="0.001 = 0.1% per side",
            )
            vbt_hold_ks = st.multiselect(
                "Holding periods (bars)", options=[6, 12, 18, 24, 30, 42, 60, 90, 120],
                default=[6, 18, 42, 90],
            )
        with vbt_c2:
            vbt_sigmas = st.multiselect(
                "Zone levels (σ)", options=ZONE_SIGMAS, default=[0.5, 1.0, 1.5, 2.0],
            )

        if st.button("▶  Run VectorBT Sweep", type="primary"):
            if not vbt_hold_ks or not vbt_sigmas:
                st.warning("Select at least one holding period and zone level.")
            else:
                with st.spinner("Running portfolio simulations..."):
                    try:
                        _df_base = fetch_crypto_ohlcv(symbol, "4h", _since)
                        sweep_results = sweep_params(
                            _df_base, study,
                            hold_k_values=vbt_hold_ks, sigmas=vbt_sigmas, tc=vbt_tc,
                        )
                        st.session_state["vbt_results"] = sweep_results
                    except Exception as e:
                        st.error(f"VectorBT error: {e}")

        if "vbt_results" in st.session_state:
            vbt_res = st.session_state["vbt_results"]

            st.write("**Sweep Results — sorted by Sharpe**")
            display_cols = ["direction", "sigma", "hold_k", "hold_days", "n_trades",
                            "skipped_events", "total_return_%", "cagr_%", "ann_vol_%",
                            "sharpe", "sortino", "calmar", "max_dd_%", "win_rate_%"]
            st.dataframe(
                vbt_res[[c for c in display_cols if c in vbt_res.columns]],
                use_container_width=True,
            )

            st.write("**Equity Curve — pick a combination**")
            ec_c1, ec_c2, ec_c3 = st.columns(3)
            with ec_c1:
                ec_dir   = st.selectbox("Direction", ["demand", "supply"])
            with ec_c2:
                ec_sigma = st.selectbox("Zone σ", vbt_sigmas)
            with ec_c3:
                ec_k     = st.selectbox("Hold k (bars)", vbt_hold_ks)

            if st.button("Plot Equity Curve"):
                with st.spinner("Simulating..."):
                    try:
                        _df_base = fetch_crypto_ohlcv(symbol, "4h", _since)
                        pf       = run_single(_df_base, study, ec_sigma, ec_dir, ec_k, tc=vbt_tc)
                        equity   = pf.value()
                        drawdown = pf.drawdown() * 100
                        stats    = pf.stats()
                        color    = DEMAND_COLOR if ec_dir == "demand" else SUPPLY_COLOR

                        from plotly.subplots import make_subplots as _msp
                        fig = _msp(rows=2, cols=1, row_heights=[0.7, 0.3],
                                   shared_xaxes=True, vertical_spacing=0.04)

                        fig.add_trace(go.Scatter(
                            x=equity.index, y=equity.values,
                            line=dict(color=color, width=1.5), name="Equity",
                        ), row=1, col=1)
                        fig.add_trace(go.Scatter(
                            x=drawdown.index, y=drawdown.values,
                            fill="tozeroy",
                            fillcolor=_hex_to_rgba("#d63031", 0.3),
                            line=dict(color="#d63031", width=0.8), name="Drawdown",
                        ), row=2, col=1)

                        sharpe_val = stats.get("Sharpe Ratio", 0)
                        maxdd_val  = stats.get("Max Drawdown [%]", 0)
                        ret_val    = stats.get("Total Return [%]", 0)
                        n_trades   = int(stats.get("Total Trades", 0))

                        fig.update_layout(
                            template="plotly_white",
                            title=dict(
                                text=(f"<b>{symbol}</b>  |  {ec_dir} {ec_sigma}σ  |  "
                                      f"hold={ec_k} bars ({ec_k/6:.1f}d)  |  "
                                      f"Sharpe {sharpe_val:.2f}  Max DD {maxdd_val:.1f}%  "
                                      f"Return {ret_val:.1f}%  Trades {n_trades}"),
                                font=dict(size=12),
                            ),
                            yaxis=dict(title="Portfolio Value ($)", type="log"),
                            yaxis2=dict(title="Drawdown (%)"),
                            height=520,
                            hovermode="x unified",
                            showlegend=False,
                        )
                        st.plotly_chart(fig, use_container_width=True)
                    except Exception as e:
                        st.error(f"Error: {e}")
