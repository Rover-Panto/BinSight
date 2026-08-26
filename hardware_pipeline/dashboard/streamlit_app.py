"""
BinSight Live Dashboard (Streamlit)
=====================================================================
Visualizes raw + filtered telemetry pulled from the BinSight cloud
backend (FastAPI). No ML inference happens here — the "overflow risk"
indicator below is a simple threshold rule on fill_pct, clearly labeled
as a placeholder for the cloud-hosted ML model that will replace it.

Run:
    pip install -r requirements.txt
    streamlit run streamlit_app.py

Color usage follows the project's dataviz method: categorical hues are
assigned to bins in a fixed order (never re-cycled as bins are added/
removed), the overflow-risk badge uses the reserved status palette
(never a categorical color), and every color cue ships with an icon +
text label alongside it — never color alone.
"""
from datetime import datetime, timezone

import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st
from streamlit_autorefresh import st_autorefresh

# ---------------------------------------------------------------------
# Palette (validated default instance — see project dataviz skill).
# Light-mode values; swap for your brand's palette.md if rebranding.
# ---------------------------------------------------------------------
CATEGORICAL = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100",
               "#e87ba4", "#008300", "#4a3aa7", "#e34948"]  # fixed order, slot = bin index
STATUS = {"good": "#0ca30c", "warning": "#fab219", "serious": "#ec835a", "critical": "#d03b3b"}
INK_MUTED = "#898781"
INK_SECONDARY = "#52514e"
GRIDLINE = "#e1e0d9"

st.set_page_config(page_title="BinSight Live Dashboard", layout="wide", page_icon="🗑️")

# ---------------------------------------------------------------------
# Sidebar — connection & display controls
# ---------------------------------------------------------------------
with st.sidebar:
    st.header("BinSight")
    api_base = st.text_input("Cloud backend URL", value="http://localhost:8000")
    refresh_seconds = st.slider("Auto-refresh interval (s)", min_value=5, max_value=60, value=10)
    history_limit = st.slider("History window (readings per bin)", min_value=20, max_value=1000, value=200)
    st.caption("estimated_density is a pseudo-density proxy (no physical load cell) — "
               "treat it as relative, not an absolute kg/L measurement.")

st_autorefresh(interval=refresh_seconds * 1000, key="binsight_autorefresh")


# ---------------------------------------------------------------------
# Data access
# ---------------------------------------------------------------------
@st.cache_data(ttl=5)
def fetch_bin_summaries(base_url: str):
    resp = requests.get(f"{base_url}/api/v1/bins/summary", timeout=5)
    resp.raise_for_status()
    return resp.json()


@st.cache_data(ttl=5)
def fetch_history(base_url: str, bin_id: str, limit: int):
    resp = requests.get(f"{base_url}/api/v1/telemetry/{bin_id}/history", params={"limit": limit}, timeout=5)
    resp.raise_for_status()
    return resp.json()["readings"]


def overflow_risk(fill_pct: float) -> tuple[str, str, str]:
    """Threshold placeholder for the future ML overflow-risk model.
    Returns (label, icon, status_color) — status color is reserved and
    never reused as a categorical series color."""
    if fill_pct >= 95:
        return "Critical", "🔴", STATUS["critical"]
    if fill_pct >= 80:
        return "Serious", "🟠", STATUS["serious"]
    if fill_pct >= 60:
        return "Warning", "🟡", STATUS["warning"]
    return "Good", "🟢", STATUS["good"]


st.title("🗑️ BinSight — Live Telemetry Dashboard")
st.caption(f"Last refreshed {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')} "
           f"· auto-refreshing every {refresh_seconds}s")

try:
    summaries = fetch_bin_summaries(api_base)
except requests.exceptions.RequestException as e:
    st.error(f"Could not reach the BinSight cloud backend at `{api_base}`.\n\n{e}")
    st.stop()

if not summaries:
    st.info("No telemetry received yet. Waiting for the first reading from a bin...")
    st.stop()

bin_ids = sorted(s["bin_id"] for s in summaries)

# ---------------------------------------------------------------------
# Top metric row
# ---------------------------------------------------------------------
avg_fill = sum(s["latest"]["fill_pct"] for s in summaries) / len(summaries)
total_low_conf = sum(s["low_confidence_count_last_20"] for s in summaries)
fullest = max(summaries, key=lambda s: s["latest"]["fill_pct"])

c1, c2, c3, c4 = st.columns(4)
c1.metric("Active bins", len(summaries))
c2.metric("Fleet avg. fill", f"{avg_fill:.1f}%")
c3.metric("Fullest bin", f"{fullest['bin_id']}", f"{fullest['latest']['fill_pct']:.1f}%")
c4.metric("Low-confidence readings (last 20/bin)", total_low_conf,
          delta=None if total_low_conf == 0 else "check sensors", delta_color="inverse")

st.divider()

# ---------------------------------------------------------------------
# Per-bin risk badges (status palette, icon + text label — never color alone)
# ---------------------------------------------------------------------
st.subheader("Overflow risk (threshold placeholder — ML model integration point)")
badge_cols = st.columns(len(summaries))
for col, s in zip(badge_cols, sorted(summaries, key=lambda x: x["bin_id"])):
    label, icon, color = overflow_risk(s["latest"]["fill_pct"])
    with col:
        st.markdown(
            f"""<div style="border:1px solid {GRIDLINE}; border-radius:8px; padding:12px; text-align:center;">
                    <div style="font-size:0.85em; color:{INK_SECONDARY};">{s['bin_id']}</div>
                    <div style="font-size:1.6em; font-weight:600;">{s['latest']['fill_pct']:.1f}%</div>
                    <div style="color:{color}; font-weight:600;">{icon} {label}</div>
                </div>""",
            unsafe_allow_html=True,
        )

st.divider()

# ---------------------------------------------------------------------
# Time-series charts — one categorical color per bin, fixed slot order
# ---------------------------------------------------------------------
selected_bins = st.multiselect("Bins to chart", options=bin_ids, default=bin_ids)

histories = {b: pd.DataFrame(fetch_history(api_base, b, history_limit)) for b in selected_bins}
for b, df in histories.items():
    if not df.empty:
        df["timestamp"] = pd.to_datetime(df["timestamp"])

col_left, col_right = st.columns(2)

with col_left:
    st.markdown("**Fill level over time**")
    fig = go.Figure()
    for i, b in enumerate(selected_bins):
        df = histories[b]
        if df.empty:
            continue
        color = CATEGORICAL[i % len(CATEGORICAL)]
        fig.add_trace(go.Scatter(
            x=df["timestamp"], y=df["fill_pct"], mode="lines", name=b,
            line=dict(color=color, width=2),
        ))
    fig.update_layout(
        yaxis_title="Fill %", yaxis_range=[0, 100],
        plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
        margin=dict(l=10, r=10, t=30, b=10),
        xaxis=dict(gridcolor=GRIDLINE, color=INK_MUTED),
        yaxis=dict(gridcolor=GRIDLINE, color=INK_MUTED),
    )
    st.plotly_chart(fig, use_container_width=True)

with col_right:
    st.markdown("**Estimated density (pseudo-proxy) over time**")
    fig2 = go.Figure()
    for i, b in enumerate(selected_bins):
        df = histories[b]
        if df.empty:
            continue
        color = CATEGORICAL[i % len(CATEGORICAL)]
        fig2.add_trace(go.Scatter(
            x=df["timestamp"], y=df["estimated_density"], mode="lines", name=b,
            line=dict(color=color, width=2),
        ))
    fig2.update_layout(
        yaxis_title="Estimated density (relative units)",
        plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
        margin=dict(l=10, r=10, t=30, b=10),
        xaxis=dict(gridcolor=GRIDLINE, color=INK_MUTED),
        yaxis=dict(gridcolor=GRIDLINE, color=INK_MUTED),
    )
    st.plotly_chart(fig2, use_container_width=True)

st.divider()

# ---------------------------------------------------------------------
# Raw log table — confidence flag shown as icon + label, not color alone
# ---------------------------------------------------------------------
st.subheader("Raw telemetry log")
log_bin = st.selectbox("Bin", options=bin_ids, key="log_bin_select")
raw = pd.DataFrame(fetch_history(api_base, log_bin, history_limit))
if not raw.empty:
    raw = raw.sort_values("timestamp", ascending=False).reset_index(drop=True)
    raw["Confidence"] = raw["confidence_flag"].map({1: "✅ Good", 0: "⚠️ Low"})
    display_cols = ["timestamp", "bin_id", "fill_pct", "estimated_density", "Confidence", "ingested_at"]
    st.dataframe(
        raw[display_cols].rename(columns={
            "timestamp": "Sensor timestamp", "bin_id": "Bin",
            "fill_pct": "Fill %", "estimated_density": "Est. density", "ingested_at": "Ingested at",
        }),
        use_container_width=True, height=400,
    )
else:
    st.info(f"No history yet for {log_bin}.")
