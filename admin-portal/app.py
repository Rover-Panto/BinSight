from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from binsight.config import load_config, required_controller_sites
from binsight.dispatch import (
    build_dispatch_plan,
    load_last_valid_readings,
    load_mock_dispatches,
    make_demo_snapshot,
    make_snapshot_template,
    mock_dispatch_payload,
    parse_snapshot_bytes,
    parse_snapshot_json,
    route_loads_kg,
    save_last_valid_readings,
    save_mock_dispatch,
    validate_snapshot,
    update_last_valid_readings,
)
from binsight.maps import build_dispatch_map, build_overview_map, build_tracking_map
from binsight.network import load_cached_service_network, route_coordinates
from binsight.pipeline import run_experiment
from binsight.tracking import build_tracking_manifest


ROOT = Path(__file__).resolve().parent
ARTIFACTS = ROOT / "artifacts"
DATA = ROOT / "data"
DISPATCH_LOG = DATA / "mock_truck_dispatches.jsonl"
LAST_VALID_READINGS = DATA / "last_valid_sensor_readings.json"
CONFIG = load_config(ROOT / "config.json")


st.set_page_config(
    page_title="BinSight Operations",
    page_icon=":material/recycling:",
    layout="wide",
    initial_sidebar_state="auto",
)

st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Barlow:wght@400;500;600;700&family=JetBrains+Mono:wght@500;600&display=swap');

    :root {
      --primary-blue: #006dae;
      --dark-blue: #00527f;
      --soft-blue: #e7f2f8;
      --graphite: #171d20;
      --graphite-2: #242c30;
      --concrete: #f3f5f3;
      --paper: #ffffff;
      --steel: #d7dddc;
      --steel-dark: #aab5b4;
      --ink: #172126;
      --muted: #5f6b70;
      --green: #2f7d5b;
      --soft-green: #e7f2ec;
      --teal: #287f83;
      --soft-teal: #e3f1f1;
      --amber: #d99a24;
      --soft-amber: #fff3da;
      --red: #c64045;
      --soft-red: #fbe9ea;
    }
    * {letter-spacing: 0 !important;}
    html {scroll-behavior: smooth;}
    .stApp {
      background: var(--concrete);
      color: var(--ink);
      font-family: "Barlow", "Segoe UI", sans-serif;
    }
    [data-testid="stHeader"] {
      background: rgba(243, 245, 243, .88);
      border-bottom: 1px solid rgba(170, 181, 180, .55);
      backdrop-filter: blur(14px);
    }
    .block-container {
      max-width: 1240px;
      padding: 2.4rem 2.5rem 5rem;
    }
    h1, h2, h3 {color: var(--ink); font-family: "Barlow", "Segoe UI", sans-serif;}
    h1 {font-size: 2.25rem; font-weight: 600; line-height: 1.05;}
    h2 {font-size: 1.75rem; font-weight: 600; margin-top: .3rem;}
    h3 {font-size: 1.3rem; font-weight: 600;}
    p, label, [data-testid="stCaptionContainer"] {color: var(--muted);}
    code, pre, [data-testid="stMetricValue"] {
      font-family: "JetBrains Mono", "Consolas", monospace !important;
    }
    [data-testid="stSidebar"] {
      background: var(--graphite);
      border-right: 1px solid rgba(255,255,255,.08);
      min-width: 232px !important;
      max-width: 232px !important;
    }
    [data-testid="stSidebarContent"] {
      padding-top: 1.25rem;
    }
    [data-testid="stSidebar"] h1,
    [data-testid="stSidebar"] h2,
    [data-testid="stSidebar"] h3,
    [data-testid="stSidebar"] p,
    [data-testid="stSidebar"] label,
    [data-testid="stSidebar"] [data-testid="stMetricValue"],
    [data-testid="stSidebar"] [data-testid="stMetricLabel"] {color: #f6f8f8 !important;}
    [data-testid="stSidebar"] [data-testid="stMetric"] {
      background: rgba(255,255,255,.035);
      border: 1px solid rgba(255,255,255,.10);
      border-left: 4px solid rgba(0,109,174,.9);
      border-radius: 4px;
      padding: .7rem .8rem;
      box-shadow: none;
    }
    .binsight-brand {
      display: flex;
      align-items: center;
      gap: .7rem;
      color: white;
      font-size: 1.25rem;
      font-weight: 600;
      margin-bottom: .3rem;
    }
    .brand-mark {
      display: grid;
      width: 2.5rem;
      height: 2.5rem;
      place-items: center;
      border: 1px solid rgba(255,255,255,.22);
      border-left: 5px solid var(--primary-blue);
      border-radius: 4px;
      background: var(--graphite-2);
      font-family: "JetBrains Mono", monospace;
      font-size: 1rem;
      font-weight: 600;
    }
    .brand-name strong {color: #67b4df; font-weight: 600;}
    .brand-name small {
      display: block;
      margin-top: .05rem;
      color: #aeb9bd;
      font-family: "JetBrains Mono", monospace;
      font-size: .58rem;
      font-weight: 500;
      text-transform: uppercase;
    }
    .sidebar-label {
      margin: 1.7rem 0 .75rem;
      color: #8da0a8;
      font-family: "JetBrains Mono", monospace;
      font-size: .65rem;
      font-weight: 600;
      text-transform: uppercase;
    }
    .environment-note {
      margin-top: 1.2rem;
      padding: .8rem;
      border: 1px solid rgba(255,255,255,.1);
      border-left: 4px solid var(--amber);
      border-radius: 4px;
      color: #c6ced1;
      font-size: .78rem;
      line-height: 1.45;
    }
    .hero {
      display: grid;
      grid-template-columns: minmax(0, 1fr) 17rem;
      gap: 2rem;
      align-items: stretch;
      padding: 2rem 2.1rem;
      margin-bottom: 1.25rem;
      border: 1px solid #354045;
      border-left: 6px solid var(--primary-blue);
      border-radius: 6px;
      background: var(--graphite);
      box-shadow: 0 14px 40px rgba(23, 29, 32, .09);
    }
    .hero-kicker {
      display: inline-flex;
      color: #69b8e5;
      font-family: "JetBrains Mono", monospace;
      font-size: .68rem;
      font-weight: 600;
      text-transform: uppercase;
    }
    .hero h1 {
      margin: .75rem 0 .55rem;
      max-width: 42rem;
      color: white;
      font-size: 2rem;
      font-weight: 600;
      line-height: 1.06;
    }
    .hero p {margin: 0; max-width: 47rem; color: #c4ced2; font-size: .98rem; line-height: 1.55;}
    .hero-context {
      display: flex;
      flex-direction: column;
      justify-content: center;
      gap: .15rem;
      padding-left: 1.5rem;
      border-left: 1px solid #455158;
    }
    .hero-context-label {
      margin-bottom: .45rem;
      color: #87969d;
      font-family: "JetBrains Mono", monospace;
      font-size: .62rem;
      font-weight: 600;
      text-transform: uppercase;
    }
    .hero-context-row {
      display: grid;
      grid-template-columns: 1.75rem 1fr;
      gap: .5rem;
      padding: .42rem 0;
      color: #edf1f2;
      font-size: .82rem;
      line-height: 1.3;
    }
    .hero-context-row b {color: #69b8e5; font-family: "JetBrains Mono", monospace; font-size: .66rem;}
    [data-testid="stMetric"] {
      background: var(--paper);
      border: 1px solid var(--steel);
      border-radius: 6px;
      padding: .9rem 1rem;
      box-shadow: none;
    }
    [data-testid="stMetricValue"] {color: var(--ink); font-size: 1.65rem; font-weight: 600;}
    [data-testid="stMetricDelta"] svg {display: none;}
    [data-testid="stMetricDelta"] > div {border-radius: 4px !important;}
    .status-card {
      border-radius: 4px;
      padding: 1.15rem 1.3rem;
      margin: .4rem 0 1.1rem;
      border: 1px solid;
      border-left-width: 5px;
    }
    .status-card strong {display: block; font-size: 1.12rem; margin-bottom: .16rem;}
    .status-card span {font-size: .92rem;}
    .status-danger {background: var(--soft-red); border-color: #e8b7ba; color: #7f292d;}
    .status-warning {background: var(--soft-amber); border-color: #e6c77f; color: #76510e;}
    .status-safe {background: var(--soft-green); border-color: #b9d7c7; color: #245f47;}
    .status-neutral {background: var(--soft-blue); border-color: #b9d5e4; color: var(--dark-blue);}
    div[data-baseweb="tab-list"] {
      position: sticky;
      top: 3.6rem;
      z-index: 50;
      gap: 0;
      margin-bottom: 1.35rem;
      padding: 0;
      background: rgba(243,245,243,.94);
      border: 0;
      border-bottom: 1px solid var(--steel-dark);
      border-radius: 0;
      backdrop-filter: blur(12px);
    }
    button[data-baseweb="tab"] {
      min-height: 3.15rem;
      padding: 0 1.1rem;
      border: 0;
      border-bottom: 3px solid transparent;
      border-radius: 0;
      color: var(--muted);
      font-weight: 600;
    }
    button[data-baseweb="tab"][aria-selected="true"] {
      background: var(--soft-blue);
      border-bottom-color: var(--primary-blue);
      color: var(--dark-blue);
    }
    [data-baseweb="tab-highlight"] {background-color: var(--primary-blue) !important;}
    [data-testid="stMain"] h3 {
      padding-left: .8rem;
      border-left: 4px solid var(--primary-blue);
    }
    .stButton > button, .stDownloadButton > button {
      min-height: 2.9rem;
      border: 1px solid var(--steel-dark);
      border-radius: 4px;
      background: var(--paper);
      color: var(--ink);
      font-weight: 600;
      transition: background-color 180ms ease, border-color 180ms ease, color 180ms ease;
    }
    .stButton > button[kind="primary"] {
      background: var(--primary-blue);
      border-color: var(--primary-blue);
      color: white;
      box-shadow: none;
    }
    .stButton > button[kind="primary"] * {color: white !important;}
    .stButton > button[kind="primary"]:hover {background: var(--dark-blue); border-color: var(--dark-blue);}
    .stButton > button:focus-visible, .stDownloadButton > button:focus-visible,
    button[data-baseweb="tab"]:focus-visible {
      outline: 3px solid rgba(0,109,174,.24);
      outline-offset: 2px;
    }
    [data-testid="stAlert"] p {color: inherit !important;}
    [data-testid="stAlert"] {border-radius: 4px; border-left-width: 5px;}
    [data-testid="stFileUploaderDropzone"] {background: var(--paper); border: 1px dashed var(--steel-dark); border-radius: 4px;}
    [data-testid="stDataFrame"] {border: 1px solid var(--steel); border-radius: 4px; overflow: hidden;}
    [data-testid="stExpander"] {background: rgba(255,255,255,.78); border-color: var(--steel); border-radius: 4px;}
    textarea, input {border-radius: 4px !important;}
    .micro-label {
      color: var(--primary-blue);
      font-family: "JetBrains Mono", monospace;
      text-transform: uppercase;
      font-size: .68rem;
      font-weight: 600;
    }
    .mock-note {
      padding: .9rem 1rem;
      border: 1px solid #ecd39a;
      border-left: 5px solid var(--amber);
      background: var(--soft-amber);
      color: #735514;
      border-radius: 4px;
    }
    @media (prefers-reduced-motion: reduce) {
      *, *::before, *::after {scroll-behavior: auto !important; transition: none !important; animation: none !important;}
    }
    @media (max-width: 1024px) {
      .block-container {padding: 1.5rem 1.5rem 5rem;}
      .hero {grid-template-columns: 1fr; gap: 1.25rem;}
      .hero-context {padding: 1rem 0 0; border-left: 0; border-top: 1px solid #455158;}
    }
    @media (max-width: 760px) {
      [data-testid="stHeader"] {background: rgba(23,29,32,.97); border-bottom-color: #354045;}
      .block-container {padding: 1rem 1rem 7rem;}
      .hero {grid-template-columns: 1fr; gap: 1.25rem; padding: 1.45rem 1.25rem;}
      .hero h1 {font-size: 1.88rem;}
      .hero-context {display: flex; padding: 1rem 0 0; border-left: 0; border-top: 1px solid #455158;}
      div[data-baseweb="tab-list"] {
        position: fixed;
        top: auto;
        right: 0;
        bottom: 0;
        left: 0;
        z-index: 999;
        display: grid;
        grid-template-columns: repeat(3, minmax(0, 1fr));
        min-height: 4.6rem;
        margin: 0;
        padding: 0 0 env(safe-area-inset-bottom);
        background: rgba(23,29,32,.98);
        border-top: 1px solid #455158;
        border-bottom: 0;
      }
      button[data-baseweb="tab"] {
        min-width: 0;
        min-height: 4.6rem;
        padding: .55rem .35rem;
        border-top: 4px solid transparent;
        border-bottom: 0;
        color: #b9c4c8;
        font-size: .75rem;
      }
      button[data-baseweb="tab"][aria-selected="true"] {
        background: var(--graphite-2);
        border-top-color: #4aa3d5;
        border-bottom-color: transparent;
        color: white;
      }
      [data-testid="stMetric"] {padding: .8rem .85rem;}
      [data-testid="stMain"] h3 {font-size: 1.18rem;}
    }
    </style>
    """,
    unsafe_allow_html=True,
)


def _render_map(route_map, height: int = 610) -> None:
    components.html(route_map.get_root().render(), height=height)


def _site_frame(bins: pd.DataFrame) -> pd.DataFrame:
    return bins.groupby(
        ["site_id", "site_label", "controller_id", "latitude", "longitude", "area_type"],
        as_index=False,
    ).agg(
        households=("households", "sum"),
        commercial_units=("commercial_units", "sum"),
    )


def _overview_map(
    bins: pd.DataFrame,
    routes: dict,
    snapshot_rows: list[dict],
):
    return build_overview_map(CONFIG, bins, routes, snapshot_rows)


def _dispatch_geometries(plan, bins: pd.DataFrame) -> tuple[list[list[tuple[float, float]]], str | None]:
    network = load_cached_service_network(DATA / "subang_jaya_osrm_network.json")
    geometries: list[list[tuple[float, float]]] = []
    fallback_used = False
    for route in plan.route_plan.routes:
        service_indices = [
            0 if index == -1 else int(bins.iloc[index]["service_index"])
            for index in route
        ]
        try:
            geometry = route_coordinates(
                network,
                service_indices,
                DATA / "osrm_route_geometry_cache.json",
            )
        except Exception:
            fallback_used = True
            deduplicated = [service_indices[0]]
            for index in service_indices[1:]:
                if index != deduplicated[-1]:
                    deduplicated.append(index)
            geometry = [network.snapped_coordinates[index] for index in deduplicated]
        geometries.append(geometry)
    note = None
    if fallback_used:
        note = "OSRM route geometry was unavailable, so the preview uses straight stop-to-stop lines. The distance and stop order still use the cached OSM road matrix."
    return geometries, note


def _dispatch_map(plan, bins: pd.DataFrame, geometries):
    return build_dispatch_map(CONFIG, bins, geometries, plan.audit_rows)


def _clear_dispatch_state() -> None:
    for key in ("dispatch_plan", "dispatch_snapshot", "dispatch_geometries", "geometry_note"):
        st.session_state.pop(key, None)


required_files = [
    ARTIFACTS / "paired_effects.csv",
    ARTIFACTS / "district_bins.csv",
    ARTIFACTS / "representative_routes.geojson",
    ARTIFACTS / "representative_route_events.json",
    ARTIFACTS / "road_distance_matrix_m.npy",
    ARTIFACTS / "road_duration_matrix_s.npy",
    DATA / "subang_jaya_osrm_network.json",
]

with st.sidebar:
    st.markdown(
        '<div class="binsight-brand"><span class="brand-mark">B</span>'
        '<span class="brand-name">Bin<strong>Sight</strong><small>Operations prototype</small></span></div>',
        unsafe_allow_html=True,
    )
    st.markdown('<div class="sidebar-label">Pilot configuration</div>', unsafe_allow_html=True)
    st.write(CONFIG.pilot.label)
    st.metric("Underground bins", CONFIG.pilot.bin_count)
    st.metric("Three-bin controller sites", required_controller_sites(CONFIG))
    st.metric("Truck payload", f"{CONFIG.operations.truck_capacity_kg:,.0f} kg")
    st.metric("Paired runs", f"{CONFIG.operations.replications} × 5 scenarios")
    if st.button("Run 30-day experiment", type="primary", width="stretch"):
        with st.spinner("Running paired 30-day simulations…"):
            run_experiment(ROOT)
        st.success("Experiment complete")
        st.rerun()
    st.markdown(
        '<div class="environment-note"><strong>Prototype environment</strong><br>'
        'Routes and dispatches are simulated locally. No municipal fleet is connected.</div>',
        unsafe_allow_html=True,
    )

st.markdown(
    """
    <div class="hero">
      <div>
        <span class="hero-kicker">Focus Area C · Subang Jaya</span>
        <h1>Which bins need collection?</h1>
        <p>Check predicted overflow risk, build a capacity-safe truck route, and review the road plan before recording a mock dispatch.</p>
      </div>
      <div class="hero-context" aria-label="Available operator tasks">
        <div class="hero-context-label">Available now</div>
        <div class="hero-context-row"><b>01</b><span>Validate one bin snapshot</span></div>
        <div class="hero-context-row"><b>02</b><span>Build an OSM road route</span></div>
        <div class="hero-context-row"><b>03</b><span>Review simulation evidence</span></div>
      </div>
    </div>
    """,
    unsafe_allow_html=True,
)

if not all(path.exists() for path in required_files):
    st.info("Generate the project artifacts with `python -m binsight.cli run`, or use Run full experiment.")
    st.stop()

effects_all = pd.read_csv(ARTIFACTS / "paired_effects.csv")
if "scenario" not in effects_all.columns:
    effects_all["scenario"] = "base"
forecast = json.loads((ARTIFACTS / "forecast_evaluation.json").read_text(encoding="utf-8"))
bins = pd.read_csv(ARTIFACTS / "district_bins.csv")
distance_matrix = np.load(ARTIFACTS / "road_distance_matrix_m.npy")
routes = json.loads((ARTIFACTS / "representative_routes.geojson").read_text(encoding="utf-8"))
route_events = json.loads(
    (ARTIFACTS / "representative_route_events.json").read_text(encoding="utf-8")
)
base_route_events = route_events.get("base", route_events)
completed_smart_events = [
    event for event in base_route_events["smart"] if event.get("completed", False)
]
representative_smart_event = max(
    completed_smart_events or base_route_events["smart"],
    key=lambda event: event["distance_km"],
)
sites = _site_frame(bins)
service_network = load_cached_service_network(DATA / "subang_jaya_osrm_network.json")
tracking_manifest = build_tracking_manifest(
    representative_smart_event,
    bins,
    service_network,
    DATA / "osrm_route_geometry_cache.json",
)

input_tab, overview_tab, tracking_tab, log_tab = st.tabs(
    [
        ":material/route: Route input",
        ":material/monitoring: Operations",
        ":material/local_shipping: Mock live tracking",
        ":material/receipt_long: Dispatch log",
    ]
)

with overview_tab:
    st.markdown('<p class="micro-label">Simulation evidence · 30-day paired experiment</p>', unsafe_allow_html=True)
    filter_left, filter_right = st.columns(2)
    scenario = filter_left.selectbox(
        "Evaluation scenario",
        sorted(effects_all["scenario"].unique()),
        format_func=lambda value: str(value).replace("_", " ").title(),
    )
    analysis_scope = filter_right.radio(
        "Analysis window",
        ["After shared warm-up", "Raw 30 days"],
        horizontal=True,
    )
    suffix = "_post_warmup" if analysis_scope == "After shared warm-up" else ""
    effects = effects_all[effects_all["scenario"] == scenario].set_index("metric")

    def scoped(metric: str) -> str:
        candidate = f"{metric}{suffix}"
        return candidate if candidate in effects.index else metric

    top = st.columns(5)
    cards = [
        ("Overflow change", "overflow_incidents"),
        ("Distance change", "distance_km"),
        ("Fuel change", "fuel_l"),
        ("CO₂ change", "co2_kg"),
        ("Wasted pickups", "wasted_pickups"),
    ]
    for column, (label, metric) in zip(top, cards):
        metric = scoped(metric)
        value = effects.loc[metric, "beneficial_change_pct_vs_fixed"]
        if pd.isna(value):
            absolute = effects.loc[metric, "beneficial_difference"]
            unit = effects.loc[metric, "unit"]
            column.metric(label, "n/a", delta=f"{absolute:+.2f} {unit} beneficial")
        else:
            direction = "better" if value >= 0 else "worse"
            column.metric(label, f"{abs(value):.1f}%", delta=direction)

    left, right = st.columns([1.55, 1], gap="large")
    with left:
        st.subheader("Representative road routes")
        st.caption(
            f"Smart dispatch from simulation day {representative_smart_event['day']}, "
            f"{representative_smart_event['hour'] % 24:02d}:00. Each marker is one ESP32 site with three co-located bins."
        )
        _render_map(
            _overview_map(
                bins,
                routes,
                representative_smart_event["snapshot_rows"],
            )
        )
    with right:
        st.subheader("Forecast validation")
        horizon = int(forecast["forecast_horizon_hours"])
        st.metric(
            f"Tree model · {horizon}h MAE",
            f"{forecast['model_mae_growth_pct_horizon']:.2f} pp",
            delta="lower is better",
        )
        st.metric(
            f"Naive model · {horizon}h MAE",
            f"{forecast['naive_mae_growth_pct_horizon']:.2f} pp",
        )
        st.metric("Forecast error improvement", f"{forecast['model_improvement_pct']:.1f}%")
        st.caption("MAE is mean absolute error. The model is tested on later observations it did not train on.")
        st.subheader("Paired scenario comparison")
        display_metrics = [
            scoped(metric)
            for metric in (
                "overflow_incidents",
                "overflow_spilled_kg",
                "distance_km",
                "travel_time_hours",
                "fuel_l",
                "unserved_required_bins",
            )
        ]
        display = effects.loc[
            display_metrics,
            [
                "fixed_mean",
                "smart_mean",
                "beneficial_difference_ci95_low",
                "beneficial_difference_ci95_high",
                "paired_sign_flip_p",
            ],
        ].copy()
        display.columns = ["Fixed", "Smart", "CI low", "CI high", "Paired p"]
        st.dataframe(display.round(3), width="stretch")
        st.warning("The comparison measures this configured simulation, not proven real-world impact.")

    with st.expander("Controller-site schedule · 11 sites / 33 bins"):
        site_table = sites[
            [
                "site_id",
                "site_label",
                "controller_id",
                "latitude",
                "longitude",
                "households",
                "commercial_units",
            ]
        ].copy()
        site_table.insert(3, "underground_bins", CONFIG.pilot.bins_per_controller)
        st.dataframe(site_table, hide_index=True, width="stretch")

    st.subheader("All KPI effects")
    chart_metrics = [
        scoped(metric)
        for metric in (
            "overflow_incidents",
            "overflow_spilled_kg",
            "distance_km",
            "travel_time_hours",
            "fuel_l",
            "co2_kg",
            "collection_stops",
            "wasted_pickups",
            "unserved_required_bins",
        )
    ]
    chart = (
        effects.loc[chart_metrics]
        .reset_index()[["metric", "beneficial_change_pct_vs_fixed"]]
        .dropna()
    )
    st.bar_chart(chart.set_index("metric"), horizontal=True)
    st.caption("Positive values mean the smart policy improved the metric in its beneficial direction.")

with input_tab:
    st.markdown('<p class="micro-label">Predictive data handoff</p>', unsafe_allow_html=True)
    st.subheader("Build a collection route")
    st.caption(
        "Provide all 33 bins at one timestamp. BinSight validates the data, applies the smart collection policy, "
        "and uses the cached OpenStreetMap road matrix with OR-Tools to build capacity-safe trips."
    )

    if "dispatch_plan" not in st.session_state:
        st.markdown(
            '<div class="status-card status-neutral"><strong>Waiting for a bin snapshot</strong>'
            '<span>No collection decision has been calculated in this session.</span></div>',
            unsafe_allow_html=True,
        )

    schema_rows = [
        ("timestamp", "ISO 8601 + timezone", "2026-08-17T10:00:00+08:00", "Same value for all rows"),
        ("bin_id", "text", "UGB-001", "Every ID from UGB-001 to UGB-033 once"),
        ("fill_pct", "number", "82.4", "0–100; ultrasonic-derived"),
        ("weight_kg", "number", "442.8", f"0–{CONFIG.operations.crane_lift_limit_kg:g}; pressure/load-cell estimate"),
        ("time_to_overflow_hours", "number", "30", "0 or greater"),
        ("risk_level", "category", "high", "low, medium, high, or critical"),
        ("confidence_flag", "boolean", "true", "true or false"),
    ]
    with st.expander("Required input format", expanded=False):
        st.dataframe(
            pd.DataFrame(schema_rows, columns=["Field", "Type", "Example", "Rule"]),
            hide_index=True,
            width="stretch",
        )
        st.code(
            "timestamp,bin_id,fill_pct,weight_kg,time_to_overflow_hours,risk_level,confidence_flag\n"
            "2026-08-17T10:00:00+08:00,UGB-001,82.4,442.8,30,high,true",
            language="csv",
        )
        download_left, download_right = st.columns(2)
        template = make_snapshot_template(bins["bin_id"])
        demo = make_demo_snapshot(bins)
        download_left.download_button(
            "Download blank 33-bin CSV template",
            template.to_csv(index=False).encode("utf-8"),
            file_name="binsight_predictive_snapshot_template.csv",
            mime="text/csv",
            width="stretch",
        )
        download_right.download_button(
            "Download working JSON example",
            json.dumps({"bins": demo.to_dict(orient="records")}, indent=2).encode("utf-8"),
            file_name="binsight_predictive_snapshot_example.json",
            mime="application/json",
            width="stretch",
        )

    input_method = st.radio(
        "Input method",
        ["Upload CSV or JSON", "Paste JSON", "Use built-in demo"],
        horizontal=True,
    )
    uploaded = None
    pasted_json = ""
    demo_snapshot = None
    if input_method == "Upload CSV or JSON":
        uploaded = st.file_uploader(
            "Predictive AI snapshot",
            type=["csv", "json"],
            help="One row per bin. Extra columns are allowed but ignored.",
        )
    elif input_method == "Paste JSON":
        pasted_json = st.text_area(
            "JSON array or {\"bins\": [...]} object",
            height=210,
            placeholder='{"bins": [{"timestamp": "2026-08-17T10:00:00+08:00", "bin_id": "UGB-001", ...}]}',
        )
    else:
        demo_snapshot = make_demo_snapshot(bins)
        st.info("The demo contains critical, high-risk, co-located, and one low-confidence bin so every decision state is visible.")
        st.dataframe(demo_snapshot.head(8), hide_index=True, width="stretch")

    if st.button("Check bins and build collection route", type="primary", width="stretch"):
        _clear_dispatch_state()
        try:
            if input_method == "Upload CSV or JSON":
                if uploaded is None:
                    raise ValueError("Choose a CSV or JSON file first")
                raw_snapshot = parse_snapshot_bytes(uploaded.getvalue(), uploaded.name)
            elif input_method == "Paste JSON":
                if not pasted_json.strip():
                    raise ValueError("Paste the JSON snapshot first")
                raw_snapshot = parse_snapshot_json(pasted_json)
            else:
                raw_snapshot = demo_snapshot
            normalized = validate_snapshot(
                raw_snapshot,
                bins["bin_id"],
                CONFIG.operations.crane_lift_limit_kg,
                stale_after_hours=CONFIG.sensor.stale_after_hours,
                future_tolerance_minutes=CONFIG.sensor.future_tolerance_minutes,
            )
            with st.spinner("Applying collection rules and optimizing OSM-road trips…"):
                last_valid = load_last_valid_readings(LAST_VALID_READINGS)
                plan = build_dispatch_plan(
                    normalized,
                    bins,
                    distance_matrix,
                    CONFIG,
                    last_valid,
                )
                geometries, geometry_note = _dispatch_geometries(plan, bins)
                save_last_valid_readings(
                    update_last_valid_readings(last_valid, normalized, bins, CONFIG),
                    LAST_VALID_READINGS,
                )
            st.session_state["dispatch_plan"] = plan
            st.session_state["dispatch_snapshot"] = normalized
            st.session_state["dispatch_geometries"] = geometries
            st.session_state["geometry_note"] = geometry_note
            st.rerun()
        except ValueError as exc:
            st.error(str(exc))
        except Exception as exc:
            st.error(f"The route could not be built: {exc}")

    if "dispatch_plan" in st.session_state:
        plan = st.session_state["dispatch_plan"]
        snapshot = st.session_state["dispatch_snapshot"]
        geometries = st.session_state["dispatch_geometries"]
        geometry_note = st.session_state.get("geometry_note")
        if plan.collection_required:
            st.markdown(
                f'<div class="status-card status-danger"><strong>Bin collection required</strong>'
                f'<span>{len(plan.required_bin_indices)} required bin(s); the optimized route serves '
                f'{plan.selected_count} bin(s) across {len(plan.route_plan.routes)} trip(s).</span></div>',
                unsafe_allow_html=True,
            )
        elif plan.inspection_required:
            st.markdown(
                f'<div class="status-card status-warning"><strong>Inspection/data review required</strong>'
                f'<span>{len(plan.review_bin_indices)} bin(s) have stale, missing, contradictory, or '
                f'low-confidence data. A final no-collection decision is blocked.</span></div>',
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                '<div class="status-card status-safe"><strong>No collection required</strong>'
                '<span>No bin crossed the current-fill, risk, or 48-hour overflow trigger.</span></div>',
                unsafe_allow_html=True,
            )

        if plan.inspection_required:
            st.warning(
                "Safety review remains open. Low-confidence readings were retained conservatively; "
                "see the 33-bin audit for the reason attached to every affected bin."
            )

        if plan.collection_required:
            loads = route_loads_kg(plan, snapshot)
            summary_columns = st.columns(4)
            summary_columns[0].metric("Selected bins", plan.selected_count)
            summary_columns[1].metric("Truck trips", len(plan.route_plan.routes))
            summary_columns[2].metric("Road distance", f"{plan.route_plan.distance_m / 1000:.1f} km")
            summary_columns[3].metric("Planned load", f"{sum(loads):,.0f} kg")
            map_col, list_col = st.columns([1.5, 1], gap="large")
            with map_col:
                st.subheader("Dispatch route preview")
                st.caption("Road shape from OSRM/OpenStreetMap; route order and capacity from OR-Tools.")
                _render_map(_dispatch_map(plan, bins, geometries), height=590)
                if geometry_note:
                    st.warning(geometry_note)
            with list_col:
                st.subheader("Bins selected")
                selection_table = pd.DataFrame(plan.selection_rows)
                st.dataframe(
                    selection_table[
                        [
                            "bin_id",
                            "site_id",
                            "selection",
                            "fill_pct",
                            "weight_kg",
                            "time_to_overflow_hours",
                            "risk_level",
                            "confidence_flag",
                        ]
                    ],
                    hide_index=True,
                    width="stretch",
                    height=330,
                )
                for trip_number, (route, load) in enumerate(
                    zip(plan.route_plan.routes, loads), start=1
                ):
                    labels = [
                        "DEPOT" if index == -1 else str(bins.iloc[index]["bin_id"])
                        for index in route
                    ]
                    st.markdown(f"**Trip {trip_number} · {load:,.0f} kg**")
                    st.write(" → ".join(labels))
                st.caption(f"Solver: {plan.route_plan.solver_method}")

            for warning in plan.warnings:
                st.warning(warning)
            if plan.unserved_required_bin_indices:
                st.error("Mock dispatch is blocked because at least one required bin could not be assigned within daily capacity.")

            st.markdown(
                '<div class="mock-note"><strong>Mock connection only.</strong> The button below writes a local JSON dispatch record. It does not contact a real truck, driver, or municipality.</div>',
                unsafe_allow_html=True,
            )
            if st.button(
                "Send mock route to garbage truck",
                type="primary",
                width="stretch",
                disabled=bool(plan.unserved_required_bin_indices),
            ):
                payload = mock_dispatch_payload(plan, snapshot, bins, CONFIG)
                save_mock_dispatch(payload, DISPATCH_LOG)
                st.session_state["last_mock_dispatch"] = payload
                st.success(f"Mock route sent to MOCK-TRUCK-01 · dispatch {payload['dispatch_id']}")
                st.toast("Mock truck dispatch recorded locally", icon="✅")
        elif plan.inspection_required:
            st.subheader("Inspection map")
            st.caption(
                "Amber controller sites require a sensor or data review. No mock truck route was created."
            )
            _render_map(_dispatch_map(plan, bins, geometries), height=590)
            if geometry_note:
                st.warning(geometry_note)
        else:
            st.info("No truck route was created because collection is not currently required.")

        with st.expander("Full 33-bin decision audit", expanded=plan.inspection_required):
            audit_table = pd.DataFrame(plan.audit_rows)
            st.dataframe(
                audit_table[
                    [
                        "bin_id",
                        "site_id",
                        "collection_state",
                        "reason",
                        "fill_pct",
                        "weight_kg",
                        "conservative_upper_fill_pct",
                        "time_to_overflow_hours",
                        "risk_level",
                        "confidence_flag",
                        "reading_age_hours",
                    ]
                ],
                hide_index=True,
                width="stretch",
            )

with tracking_tab:
    st.markdown('<p class="micro-label">Local playback · simulated vehicle only</p>', unsafe_allow_html=True)
    st.subheader("Mock live truck tracking")
    st.caption(
        "This replays one completed smart-policy dispatch using its timestamped OSRM travel, "
        "collection-service, unloading, and turnaround events. No GPS device or real truck is connected."
    )
    tracking_summary = st.columns(4)
    tracking_summary[0].metric("Route ID", tracking_manifest["route_id"])
    tracking_summary[1].metric("Bins served", tracking_manifest["total_bins"])
    tracking_summary[2].metric(
        "Playback duration", f"{tracking_manifest['duration_minutes']:.0f} sim min"
    )
    tracking_summary[3].metric(
        "Truck capacity", f"{tracking_manifest['payload_capacity_kg']:,.0f} kg"
    )
    st.info(
        "Use Resume, Pause, Reset, and the speed selector inside the map. Site markers turn green "
        "only after collection service completes."
    )
    _render_map(
        build_tracking_map(
            CONFIG,
            bins,
            tracking_manifest,
            representative_smart_event["snapshot_rows"],
        ),
        height=720,
    )
    with st.expander("Timestamped execution audit"):
        timeline_table = pd.DataFrame(representative_smart_event["timeline"])
        preferred = [
            column
            for column in (
                "day",
                "simulation_hour",
                "status",
                "trip_number",
                "origin",
                "destination",
                "bin_id",
                "payload_kg",
                "travel_minutes",
                "duration_minutes",
            )
            if column in timeline_table.columns
        ]
        st.dataframe(timeline_table[preferred], hide_index=True, width="stretch")


with log_tab:
    st.markdown('<p class="micro-label">Prototype audit trail</p>', unsafe_allow_html=True)
    st.subheader("Dispatch records")
    st.caption("Stored locally in data/mock_truck_dispatches.jsonl. These records are not external transmissions.")
    records = load_mock_dispatches(DISPATCH_LOG)
    if not records:
        st.info("No mock routes have been sent yet.")
    else:
        log_rows = [
            {
                "dispatch_id": record.get("dispatch_id"),
                "created_at_utc": record.get("created_at_utc"),
                "truck": record.get("vehicle_id"),
                "bins": record.get("selected_bin_count"),
                "trips": record.get("trip_count"),
                "distance_km": record.get("route_distance_km"),
                "status": record.get("status"),
            }
            for record in records
        ]
        st.dataframe(pd.DataFrame(log_rows), hide_index=True, width="stretch")
        st.download_button(
            "Download latest dispatch JSON",
            json.dumps(records[0], indent=2).encode("utf-8"),
            file_name=f"{records[0].get('dispatch_id', 'mock-dispatch')}.json",
            mime="application/json",
        )
        with st.expander("View latest mock payload"):
            st.json(records[0])

st.caption("BinSight Focus Area C · OpenStreetMap/OSRM routing · prototype operator decision support")
