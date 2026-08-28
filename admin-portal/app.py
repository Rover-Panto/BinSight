from __future__ import annotations

import json
import hashlib
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from binsight.config import load_config, required_service_sites
from binsight.dispatch import (
    load_last_valid_readings,
    load_mock_dispatches,
    make_demo_snapshot,
    mock_dispatch_payload,
    route_loads_kg,
    save_mock_dispatch,
    update_last_valid_readings_file,
)
from binsight.maps import build_dispatch_map, build_overview_map, build_tracking_map
from binsight.network import load_cached_service_network, route_coordinates
from binsight.pipeline import run_experiment
from binsight.planner import PlanningService
from binsight.planning_store import PlanningStore
from binsight.runtime import configure_logging, error_reference
from binsight.tracking import build_tracking_manifest


ROOT = Path(__file__).resolve().parent
ARTIFACTS = ROOT / "artifacts"
DATA = ROOT / "data"
DISPATCH_LOG = DATA / "mock_truck_dispatches.jsonl"
LAST_VALID_READINGS = DATA / "last_valid_sensor_readings.json"
PLANNING_DB = DATA / "routing_plans.sqlite3"
CONFIG = load_config(ROOT / "config.json")
LOGGER = configure_logging(ROOT)
CONFIG_SHA256 = hashlib.sha256(
    json.dumps(CONFIG.to_dict(), sort_keys=True, separators=(",", ":")).encode("utf-8")
).hexdigest()
EVIDENCE_ARTIFACTS = ARTIFACTS
EVIDENCE_PROVENANCE: dict = {}
for candidate in (
    ARTIFACTS / "dynamic_v2",
    ARTIFACTS / "four-bin-smoke",
    ARTIFACTS,
):
    provenance_path = candidate / "run_provenance.json"
    if not provenance_path.exists():
        continue
    candidate_provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
    if candidate_provenance.get("config_sha256") == CONFIG_SHA256:
        EVIDENCE_ARTIFACTS = candidate
        EVIDENCE_PROVENANCE = candidate_provenance
        break


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
    for route_number, route in enumerate(plan.route_plan.routes):
        service_indices = [
            0 if index == -1 else int(bins.iloc[index]["service_index"])
            for index in route
        ]
        route_destinations = getattr(plan.route_plan, "route_destinations", [])
        destination_id = (
            route_destinations[route_number]
            if route_number < len(route_destinations)
            else (
                str(bins.iloc[route[1]].get("destination_id", "waste_depot"))
                if len(route) > 2
                else "waste_depot"
            )
        )
        if destination_id == "recycling_facility" and service_indices[-1] == 0:
            service_indices.insert(-1, 1)
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
    for key in (
        "dispatch_plan",
        "dispatch_snapshot",
        "dispatch_bins",
        "dispatch_profile_id",
        "dispatch_plan_record",
        "dispatch_geometries",
        "geometry_note",
    ):
        st.session_state.pop(key, None)


required_files = [
    EVIDENCE_ARTIFACTS / "paired_effects.csv",
    ARTIFACTS / "district_bins.csv",
    EVIDENCE_ARTIFACTS / "representative_routes.geojson",
    EVIDENCE_ARTIFACTS / "representative_route_events.json",
    ARTIFACTS / "road_distance_matrix_m.npy",
    ARTIFACTS / "road_duration_matrix_s.npy",
    ARTIFACTS / "recycling_road_distance_matrix_m.npy",
    ARTIFACTS / "recycling_road_duration_matrix_s.npy",
    DATA / "subang_jaya_osrm_network.json",
    EVIDENCE_ARTIFACTS / "run_provenance.json",
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
    st.metric("Four-bin service sites", required_service_sites(CONFIG))
    st.metric("Truck payload", f"{CONFIG.operations.truck_capacity_kg:,.0f} kg")
    st.metric(
        "Paired runs",
        (
            f"{EVIDENCE_PROVENANCE.get('paired_replications_per_scenario', 0)} × "
            f"{EVIDENCE_PROVENANCE.get('scenario_count', 0)} scenario(s)"
        ),
    )
    if st.button("Run 30-day experiment", type="primary", width="stretch"):
        with st.spinner("Running paired 30-day simulations…"):
            run_experiment(ROOT, artifact_set="dynamic_v2")
        st.success("Experiment complete")
        st.rerun()
    st.markdown(
        '<div class="environment-note"><strong>Prototype environment</strong><br>'
        'Localhost-only server · mock dispatches only. No municipal fleet is connected.</div>',
        unsafe_allow_html=True,
    )

st.markdown(
    """
    <div class="hero">
      <div>
        <span class="hero-kicker">Focus Area C · Subang Jaya</span>
        <h1>Which bins need collection?</h1>
        <p>Check overflow service risk, compare a trip with waiting or merging, and review the capacity-safe road plan before recording a mock dispatch.</p>
      </div>
      <div class="hero-context" aria-label="Available operator tasks">
        <div class="hero-context-label">Available now</div>
        <div class="hero-context-row"><b>01</b><span>Run the built-in routing demonstration</span></div>
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

effects_all = pd.read_csv(EVIDENCE_ARTIFACTS / "paired_effects.csv")
if "scenario" not in effects_all.columns:
    effects_all["scenario"] = "base"
forecast = json.loads((EVIDENCE_ARTIFACTS / "forecast_evaluation.json").read_text(encoding="utf-8"))
bins = pd.read_csv(ARTIFACTS / "district_bins.csv")
distance_matrix = np.load(ARTIFACTS / "road_distance_matrix_m.npy")
duration_matrix = np.load(ARTIFACTS / "road_duration_matrix_s.npy")
recycling_distance_matrix = np.load(
    ARTIFACTS / "recycling_road_distance_matrix_m.npy"
)
recycling_duration_matrix = np.load(
    ARTIFACTS / "recycling_road_duration_matrix_s.npy"
)
routes = json.loads((EVIDENCE_ARTIFACTS / "representative_routes.geojson").read_text(encoding="utf-8"))
route_events = json.loads(
    (EVIDENCE_ARTIFACTS / "representative_route_events.json").read_text(encoding="utf-8")
)
base_route_events = route_events.get(
    "normal_patterned", route_events.get("base", route_events)
)
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
    {CONFIG.pilot.recycling_facility_id: 1},
)

input_tab, overview_tab, tracking_tab, log_tab = st.tabs(
    [
        ":material/route: Routing demo",
        ":material/monitoring: Operations",
        ":material/local_shipping: Mock live tracking",
        ":material/receipt_long: Dispatch log",
    ]
)

with overview_tab:
    evidence_replications = int(
        EVIDENCE_PROVENANCE.get("paired_replications_per_scenario", 0)
    )
    st.markdown(
        '<p class="micro-label">Simulation evidence · bounded 30-day paired run</p>',
        unsafe_allow_html=True,
    )
    if evidence_replications < 10:
        st.warning(
            f"Integration smoke evidence only: {evidence_replications} paired replication(s) "
            "per scenario. Use this to verify execution, not to claim statistical performance."
        )
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
            f"{representative_smart_event['hour'] % 24:02d}:00. Each marker is one simulated service site with four co-located bins."
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

    with st.expander("Simulated service-site schedule · 11 sites / 44 bins"):
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
        site_table.insert(3, "underground_bins", CONFIG.pilot.bins_per_service_site)
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
    st.markdown('<p class="micro-label">Built-in routing demonstration</p>', unsafe_allow_html=True)
    st.subheader("Run the demonstration route")
    st.caption(
        "The demonstration supplies all 44 configured bins automatically. Each of the 11 sites has "
        "one general-waste bin and separate plastic, metal, and glass recycling bins. "
        "Recyclables unload at the marked USJ 9 recycling facility; general waste returns to the waste depot. "
        "BinSight validates the snapshot, evaluates trip value, separates incompatible collection streams, "
        "and proposes capacity-feasible road routes."
    )

    if "dispatch_plan" not in st.session_state:
        st.markdown(
            '<div class="status-card status-neutral"><strong>Demonstration ready</strong>'
            '<span>Run the built-in scenario to calculate a collection decision.</span></div>',
            unsafe_allow_html=True,
        )

    demo_snapshot = make_demo_snapshot(bins)
    demo_preview = demo_snapshot.merge(
        bins[["bin_id", "site_id", "material_type", "waste_stream", "capacity_kg"]],
        on="bin_id",
        how="left",
    )
    st.info(
        "The scenario includes critical, high-risk, optional, deferred, and low-confidence bins "
        "so every routing decision state is visible."
    )
    st.dataframe(
        demo_preview[
            [
                "site_id",
                "bin_id",
                "material_type",
                "fill_pct",
                "weight_kg",
                "capacity_kg",
                "time_to_overflow_hours",
                "risk_level",
                "confidence_flag",
            ]
        ].head(12),
        hide_index=True,
        width="stretch",
    )
    st.caption("Preview shows 12 of 44 bins; the route evaluation always uses the complete demonstration snapshot.")

    if st.button("Run demonstration and build collection route", type="primary", width="stretch"):
        _clear_dispatch_state()
        try:
            raw_snapshot = demo_snapshot
            active_bins = bins.reset_index(drop=True)
            active_distance = distance_matrix
            active_duration = duration_matrix
            profile_id = "competition-simulation"
            with st.spinner("Applying collection rules and optimizing OSM-road trips…"):
                last_valid = load_last_valid_readings(LAST_VALID_READINGS)
                store = PlanningStore(PLANNING_DB)
                service = PlanningService(
                    CONFIG,
                    active_bins,
                    active_distance,
                    active_duration,
                    store,
                    network_version="subang-jaya-osrm-v1",
                    model_version="forecast-synthetic-q90-v2",
                    destination_matrices={
                        "recycling_facility": (
                            recycling_distance_matrix,
                            recycling_duration_matrix,
                        )
                    },
                )
                result = service.evaluate(
                    raw_snapshot,
                    decision_at=datetime.now(timezone.utc),
                    last_valid_readings=last_valid,
                )
                plan = result.plan
                normalized = result.snapshot
                plan_record = result.stored_record
                store.close()
                geometries, geometry_note = _dispatch_geometries(plan, active_bins)
                update_last_valid_readings_file(
                    normalized, active_bins, CONFIG, LAST_VALID_READINGS
                )
            st.session_state["dispatch_plan"] = plan
            st.session_state["dispatch_snapshot"] = normalized
            st.session_state["dispatch_bins"] = active_bins
            st.session_state["dispatch_profile_id"] = profile_id
            st.session_state["dispatch_plan_record"] = plan_record
            st.session_state["dispatch_geometries"] = geometries
            st.session_state["geometry_note"] = geometry_note
            st.rerun()
        except ValueError as exc:
            st.error(str(exc))
        except Exception:
            reference = error_reference()
            LOGGER.exception("%s route demonstration failed", reference)
            st.error(
                "The route could not be built safely. No dispatch was recorded. "
                f"Reference: {reference}"
            )

    if "dispatch_plan" in st.session_state:
        plan = st.session_state["dispatch_plan"]
        snapshot = st.session_state["dispatch_snapshot"]
        plan_bins = st.session_state.get("dispatch_bins", bins)
        plan_record = st.session_state.get("dispatch_plan_record", {"status": "DRAFT"})
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
                '<span>Waiting or merging with a later route has lower expected cost while the overflow service constraint remains satisfied.</span></div>',
                unsafe_allow_html=True,
            )

        if plan.inspection_required:
            st.warning(
                "Safety review remains open. Low-confidence readings were retained conservatively; "
                "see the decision audit for the reason attached to every affected bin."
            )

        st.caption(
            f"Plan {plan.plan_id} · {plan.source_mode} · {plan.policy_version} · "
            f"lifecycle {plan_record.get('status', 'DRAFT')}"
        )

        if plan.collection_required and plan.route_plan.routes:
            loads = route_loads_kg(plan, snapshot)
            summary_columns = st.columns(5)
            summary_columns[0].metric("Selected bins", plan.selected_count)
            summary_columns[1].metric("Truck trips", len(plan.route_plan.routes))
            summary_columns[2].metric("Road distance", f"{plan.route_plan.distance_m / 1000:.1f} km")
            summary_columns[3].metric("Planned load", f"{sum(loads):,.0f} kg")
            summary_columns[4].metric(
                "Net trip value",
                f"{plan.route_plan.net_value_m_equivalent:,.0f} m-eq",
                help="Prototype metre-equivalent avoided-loss value minus route operating cost.",
            )
            map_col, list_col = st.columns([1.5, 1], gap="large")
            with map_col:
                st.subheader("Dispatch route preview")
                st.caption("Road shape from OSRM/OpenStreetMap; route order and capacity from OR-Tools.")
                _render_map(_dispatch_map(plan, plan_bins, geometries), height=590)
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
                    labels = ["DEPOT"] + [
                        str(plan_bins.iloc[index]["bin_id"])
                        for index in route
                        if index != -1
                    ]
                    route_position = trip_number - 1
                    destination_id = (
                        plan.route_plan.route_destinations[route_position]
                        if route_position < len(plan.route_plan.route_destinations)
                        else "waste_depot"
                    )
                    if destination_id == "recycling_facility":
                        labels.extend(["USJ 9 RECYCLING", "DEPOT"])
                    else:
                        labels.append("DEPOT")
                    st.markdown(f"**Trip {trip_number} · {load:,.0f} kg**")
                    st.write(" → ".join(labels))
                st.caption(f"Solver: {plan.route_plan.solver_method}")
                st.caption(
                    f"Decision: {plan.route_plan.dispatch_reason}; operating cost "
                    f"{plan.route_plan.operating_cost_m_equivalent:,.0f} m-eq; avoided loss "
                    f"{plan.route_plan.avoided_loss_value_m_equivalent:,.0f} m-eq."
                )

            for warning in plan.warnings:
                st.warning(warning)
            if plan.unserved_required_bin_indices:
                st.error("Mock dispatch is blocked because at least one required bin could not be assigned within daily capacity.")

            st.markdown(
                '<div class="mock-note"><strong>Draft and mock connection only.</strong> Approving freezes this version; sending records one idempotent local mock dispatch. Mark complete only after the simulated service finishes so delayed pre-service readings cannot schedule the same bin again. No action contacts a real truck, driver, or municipality.</div>',
                unsafe_allow_html=True,
            )
            state_store = PlanningStore(PLANNING_DB)
            mock_dispatch_exists = state_store.has_mock_dispatch(plan.plan_id)
            state_store.close()
            lifecycle_left, lifecycle_middle, lifecycle_right = st.columns(3)
            if lifecycle_left.button(
                "Approve route proposal",
                width="stretch",
                disabled=plan_record.get("status") != "DRAFT",
            ):
                store = PlanningStore(PLANNING_DB)
                st.session_state["dispatch_plan_record"] = store.accept(
                    plan.plan_id, "local-operator", "Approved in Streamlit preview"
                )
                store.close()
                st.rerun()
            if lifecycle_middle.button(
                "Cancel route proposal",
                width="stretch",
                disabled=plan_record.get("status") != "DRAFT",
            ):
                store = PlanningStore(PLANNING_DB)
                st.session_state["dispatch_plan_record"] = store.cancel(
                    plan.plan_id, "local-operator", "Cancelled in Streamlit preview"
                )
                store.close()
                st.rerun()
            if lifecycle_right.button(
                "Mark mock route completed",
                width="stretch",
                disabled=(
                    plan_record.get("status") != "ACCEPTED"
                    or not mock_dispatch_exists
                ),
                help="Records every served bin as emptied after the mock route has been recorded.",
            ):
                store = PlanningStore(PLANNING_DB)
                st.session_state["dispatch_plan_record"] = store.complete(
                    plan.plan_id,
                    "local-operator",
                    "Mock route marked complete in Streamlit preview",
                )
                store.close()
                st.rerun()
            if st.button(
                "Send mock route to garbage truck",
                type="primary",
                width="stretch",
                disabled=(
                    bool(plan.unserved_required_bin_indices)
                    or plan_record.get("status") != "ACCEPTED"
                ),
            ):
                payload = mock_dispatch_payload(plan, snapshot, plan_bins, CONFIG)
                store = PlanningStore(PLANNING_DB)
                recorded, created = store.record_mock_dispatch(plan.plan_id, payload)
                store.close()
                st.session_state["last_mock_dispatch"] = recorded
                verb = "recorded" if created else "already recorded"
                st.success(
                    f"Mock route {verb} for MOCK-TRUCK-01 · dispatch {recorded['dispatch_id']}"
                )
                st.toast("Mock dispatch audit updated", icon="✅")
        elif plan.collection_required:
            st.error(
                "Collection is safety-required, but no feasible route was produced. Dispatch remains blocked until capacity, time, or data constraints are resolved."
            )
        elif plan.inspection_required:
            st.subheader("Inspection map")
            st.caption(
                "Amber controller sites require a sensor or data review. No mock truck route was created."
            )
            _render_map(_dispatch_map(plan, plan_bins, geometries), height=590)
            if geometry_note:
                st.warning(geometry_note)
        else:
            st.info("No truck route was created because collection is not currently required.")

        with st.expander(
            f"Full {len(plan.audit_rows)}-bin decision audit",
            expanded=plan.inspection_required,
        ):
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
                        "forecast_status",
                        "overflow_probability_before_next_opportunity",
                        "pickup_avoided_loss_value_m_equivalent",
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
    st.subheader("Plans and mock dispatch records")
    st.caption(
        "Draft, accepted, completed, and cancelled plans are stored transactionally in "
        "data/routing_plans.sqlite3. Telemetry and citizen records remain separate."
    )
    store = PlanningStore(PLANNING_DB)
    plan_records = store.latest()
    records = store.latest_mock_dispatches()
    store.close()
    if not plan_records:
        st.info("No durable route proposals have been created yet.")
    else:
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "plan_id": record["plan_id"],
                        "decision_at": record["decision_at"],
                        "status": record["status"],
                        "source_mode": record["source_mode"],
                        "selected_bins": len(record["plan"]["selected_bin_indices"]),
                        "required_bins": len(record["plan"]["required_bin_indices"]),
                        "record_version": record["record_version"],
                    }
                    for record in plan_records
                ]
            ),
            hide_index=True,
            width="stretch",
        )
    if records:
        log_rows = [
            {
                "dispatch_id": record["dispatch_id"],
                "plan_id": record["plan_id"],
                "created_at_utc": record["created_at"],
                "truck": record["payload"].get("vehicle_id"),
                "bins": record["payload"].get("selected_bin_count"),
                "trips": record["payload"].get("trip_count"),
                "distance_km": record["payload"].get("route_distance_km"),
                "status": record["payload"].get("status"),
            }
            for record in records
        ]
        st.dataframe(pd.DataFrame(log_rows), hide_index=True, width="stretch")
        st.download_button(
            "Download latest dispatch JSON",
            json.dumps(records[0]["payload"], indent=2).encode("utf-8"),
            file_name=f"{records[0]['dispatch_id']}.json",
            mime="application/json",
        )
        with st.expander("View latest mock payload"):
            st.json(records[0]["payload"])
    legacy_records = load_mock_dispatches(DISPATCH_LOG)
    if legacy_records:
        with st.expander("Legacy JSONL dispatch records (read-only)"):
            st.caption(
                "Records created before the transactional plan lifecycle are preserved and are not rewritten."
            )
            st.dataframe(pd.DataFrame(legacy_records), hide_index=True, width="stretch")

st.caption("BinSight Focus Area C · OpenStreetMap/OSRM routing · prototype operator decision support")
