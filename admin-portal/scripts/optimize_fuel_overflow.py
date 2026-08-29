from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import replace
from pathlib import Path

import joblib
import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from binsight.config import load_config, validate_config
from binsight.demand import generate_demand_realization
from binsight.district import build_district
from binsight.network import load_cached_service_network
from binsight.pipeline import experiment_scenarios
from binsight.simulation import run_policy


OUTPUT = ROOT / "artifacts" / "fuel-overflow-optimization"

# `next_planning_opportunity_hours` is the time the route must safely bridge.
# The 12-hour candidate corrects the production mismatch between twice-daily
# decisions (06:00/18:00) and the old six-hour value. Longer values deliberately
# test anticipatory batching: collect all forecast-due stops early enough that a
# stream can avoid another departure inside the batching horizon.
POLICIES: dict[str, dict[str, object]] = {
    "fixed_baseline": {},
    "current_6h": {},
    "decision_aligned_12h": {"next_planning_opportunity_hours": 12.0},
    "anticipatory_24h": {"next_planning_opportunity_hours": 24.0},
    "anticipatory_36h": {"next_planning_opportunity_hours": 36.0},
    "anticipatory_48h": {"next_planning_opportunity_hours": 48.0},
    "anticipatory_24h_selective": {
        "next_planning_opportunity_hours": 24.0,
        "smart_optional_min_central_fill_pct": 50.0,
        "route_fixed_cost_m_equivalent": 25_000,
        "minimum_route_value_m": 5_000.0,
    },
    "anticipatory_36h_selective": {
        "next_planning_opportunity_hours": 36.0,
        "smart_optional_min_central_fill_pct": 50.0,
        "route_fixed_cost_m_equivalent": 25_000,
        "minimum_route_value_m": 5_000.0,
    },
    "daily_24h": {
        "smart_decision_hours": (6,),
        "next_planning_opportunity_hours": 24.0,
    },
    "daily_24h_selective": {
        "smart_decision_hours": (6,),
        "next_planning_opportunity_hours": 24.0,
        "smart_optional_min_central_fill_pct": 50.0,
        "route_fixed_cost_m_equivalent": 25_000,
        "minimum_route_value_m": 5_000.0,
    },
    "emergency_fill_94": {
        "smart_emergency_current_trigger_pct": 94.0,
        "uncertain_service_trigger_pct": 94.0,
    },
    "selective_current": {
        "smart_optional_min_central_fill_pct": 50.0,
        "route_fixed_cost_m_equivalent": 25_000,
        "minimum_route_value_m": 5_000.0,
    },
    "emergency_fill_94_selective": {
        "smart_emergency_current_trigger_pct": 94.0,
        "uncertain_service_trigger_pct": 94.0,
        "smart_optional_min_central_fill_pct": 50.0,
        "route_fixed_cost_m_equivalent": 25_000,
        "minimum_route_value_m": 5_000.0,
    },
    "strict_optional_120h": {
        "smart_include_current_trigger_pct": 60.0,
        "smart_include_predicted_trigger_pct": 90.0,
        "smart_min_dispatch_gap_hours": 120,
        "smart_optional_min_central_fill_pct": 50.0,
        "smart_sibling_include_current_pct": 60.0,
        "smart_sibling_include_time_to_overflow_hours": 48.0,
        "route_fixed_cost_m_equivalent": 35_000,
        "minimum_route_value_m": 10_000.0,
    },
    "emergency_fill_92_selective": {
        "smart_emergency_current_trigger_pct": 92.0,
        "uncertain_service_trigger_pct": 92.0,
        "smart_optional_min_central_fill_pct": 50.0,
        "route_fixed_cost_m_equivalent": 25_000,
        "minimum_route_value_m": 5_000.0,
    },
    "emergency_fill_88_selective": {
        "smart_emergency_current_trigger_pct": 88.0,
        "uncertain_service_trigger_pct": 88.0,
        "smart_optional_min_central_fill_pct": 50.0,
        "route_fixed_cost_m_equivalent": 25_000,
        "minimum_route_value_m": 5_000.0,
    },
    "emergency_fill_86_selective": {
        "smart_emergency_current_trigger_pct": 86.0,
        "uncertain_service_trigger_pct": 86.0,
        "smart_optional_min_central_fill_pct": 50.0,
        "route_fixed_cost_m_equivalent": 25_000,
        "minimum_route_value_m": 5_000.0,
    },
    "plastic_90_fill_94_selective": {
        "smart_emergency_current_trigger_pct": 94.0,
        "smart_plastic_required_trigger_pct": 90.0,
        "uncertain_service_trigger_pct": 94.0,
        "smart_optional_min_central_fill_pct": 50.0,
        "route_fixed_cost_m_equivalent": 25_000,
        "minimum_route_value_m": 5_000.0,
    },
    "adaptive_material_guard_selective": {
        "smart_emergency_current_trigger_pct": 94.0,
        "smart_plastic_required_trigger_pct": 90.0,
        "uncertain_service_trigger_pct": 90.0,
        "smart_optional_min_central_fill_pct": 50.0,
        "route_fixed_cost_m_equivalent": 25_000,
        "minimum_route_value_m": 5_000.0,
    },
    "uncertain_guard_selective": {
        "smart_emergency_current_trigger_pct": 94.0,
        "uncertain_service_trigger_pct": 90.0,
        "smart_optional_min_central_fill_pct": 50.0,
        "route_fixed_cost_m_equivalent": 25_000,
        "minimum_route_value_m": 5_000.0,
    },
    "plastic_85_fill_94_selective": {
        "smart_emergency_current_trigger_pct": 94.0,
        "smart_plastic_required_trigger_pct": 85.0,
        "uncertain_service_trigger_pct": 94.0,
        "smart_optional_min_central_fill_pct": 50.0,
        "route_fixed_cost_m_equivalent": 25_000,
        "minimum_route_value_m": 5_000.0,
    },
    "plastic_85_fill_92_selective": {
        "smart_emergency_current_trigger_pct": 92.0,
        "smart_plastic_required_trigger_pct": 85.0,
        "uncertain_service_trigger_pct": 92.0,
        "smart_optional_min_central_fill_pct": 50.0,
        "route_fixed_cost_m_equivalent": 25_000,
        "minimum_route_value_m": 5_000.0,
    },
    "plastic_88_fill_92_selective": {
        "smart_emergency_current_trigger_pct": 92.0,
        "smart_plastic_required_trigger_pct": 88.0,
        "uncertain_service_trigger_pct": 92.0,
        "smart_optional_min_central_fill_pct": 50.0,
        "route_fixed_cost_m_equivalent": 25_000,
        "minimum_route_value_m": 5_000.0,
    },
    "plastic_90_fill_92_selective": {
        "smart_emergency_current_trigger_pct": 92.0,
        "smart_plastic_required_trigger_pct": 90.0,
        "uncertain_service_trigger_pct": 92.0,
        "smart_optional_min_central_fill_pct": 50.0,
        "route_fixed_cost_m_equivalent": 25_000,
        "minimum_route_value_m": 5_000.0,
    },
    "plastic_80_fill_94_selective": {
        "smart_emergency_current_trigger_pct": 94.0,
        "smart_plastic_required_trigger_pct": 80.0,
        "uncertain_service_trigger_pct": 94.0,
        "smart_optional_min_central_fill_pct": 50.0,
        "route_fixed_cost_m_equivalent": 25_000,
        "minimum_route_value_m": 5_000.0,
    },
    "plastic_80_fill_92_selective": {
        "smart_emergency_current_trigger_pct": 92.0,
        "smart_plastic_required_trigger_pct": 80.0,
        "uncertain_service_trigger_pct": 92.0,
        "smart_optional_min_central_fill_pct": 50.0,
        "route_fixed_cost_m_equivalent": 25_000,
        "minimum_route_value_m": 5_000.0,
    },
    "emergency_fill_94_selective_tto12": {
        "smart_emergency_current_trigger_pct": 94.0,
        "uncertain_service_trigger_pct": 94.0,
        "smart_emergency_time_to_overflow_hours": 12.0,
        "smart_optional_min_central_fill_pct": 50.0,
        "route_fixed_cost_m_equivalent": 25_000,
        "minimum_route_value_m": 5_000.0,
    },
    "emergency_fill_94_selective_tto18": {
        "smart_emergency_current_trigger_pct": 94.0,
        "uncertain_service_trigger_pct": 94.0,
        "smart_emergency_time_to_overflow_hours": 18.0,
        "smart_optional_min_central_fill_pct": 50.0,
        "route_fixed_cost_m_equivalent": 25_000,
        "minimum_route_value_m": 5_000.0,
    },
}

FLEETS = {
    "g1_r1": {"general_waste_truck_count": 1, "recycling_truck_count": 1},
    "g2_r1": {"general_waste_truck_count": 2, "recycling_truck_count": 1},
    "g1_r2": {"general_waste_truck_count": 1, "recycling_truck_count": 2},
    "g2_r2": {"general_waste_truck_count": 2, "recycling_truck_count": 2},
}

SEED_OFFSETS = {
    "screen": (4_110_000, 4_120_000),
    "cadence": (4_210_000, 4_220_000),
    "fleet": (4_310_000, 4_320_000),
    "batch": (4_410_000, 4_420_000),
    "guard": (4_460_000, 4_470_000),
    "selective": (4_480_000, 4_490_000),
    "safety": (4_500_000, 4_505_000),
    "material": (4_507_000, 4_509_000),
    "plastic": (4_511_000, 4_512_000),
    "confirm": (4_510_000, 4_520_000),
    "reserve_confirm": (4_510_000, 4_520_000),
    "reserve_adaptive": (4_610_000, 4_620_000),
    "hybrid_screen": (4_710_000, 4_720_000),
    "hybrid_refine": (4_730_000, 4_740_000),
    "adaptive_guard": (4_750_000, 4_760_000),
    "same_site": (4_770_000, 4_780_000),
    "uncertain_guard": (4_790_000, 4_800_000),
    "load_adaptive": (4_805_000, 4_808_000),
    "final_confirm": (4_810_000, 4_820_000),
    "final_safety": (4_810_000, 4_820_000),
    "final_plastic": (4_810_000, 4_820_000),
    "pipeline_recheck": (1_610_000, 1_620_000),
    "final_exact": (5_110_000, 5_120_000),
    "determinism_a": (5_110_000, 5_120_000),
    "determinism_b": (5_110_000, 5_120_000),
    "sensor_fallback": (5_110_000, 5_120_000),
    "degraded_refine": (5_110_000, 5_120_000),
}

METRICS = (
    "distance_km",
    "collection_trips",
    "collection_stops",
    "wasted_pickups",
    "overflow_incidents",
    "overflow_bin_hours",
    "overflow_spilled_kg",
    "overflow_bin_hours_mixed_general_waste",
    "overflow_bin_hours_plastic_cups",
    "overflow_bin_hours_metal_cans",
    "overflow_bin_hours_glass_bottles",
    "base_driving_fuel_l",
    "traffic_fuel_penalty_l",
    "payload_fuel_penalty_l",
    "collection_idle_fuel_l",
    "depot_idle_fuel_l",
    "fuel_l",
    "unserved_required_bins",
    "unfinished_trip_count",
    "uncollected_kg_at_horizon",
)


def _run(task: dict[str, object]) -> dict[str, object]:
    base = load_config(ROOT / "config.json")
    policy_name = str(task["policy"])
    fleet_name = str(task["fleet"])
    operations = replace(
        base.operations,
        **POLICIES[policy_name],
        **FLEETS[fleet_name],
    )
    config = replace(base, operations=operations)
    validate_config(config)

    network = load_cached_service_network(
        ROOT / "data" / "subang_jaya_osrm_network.json"
    )
    _, bins = build_district(config, network, ROOT / config.pilot.site_plan_file)
    distance = np.load(ROOT / "artifacts" / "road_distance_matrix_m.npy")
    duration = np.load(ROOT / "artifacts" / "road_duration_matrix_s.npy")
    recycling_distance = np.load(
        ROOT / "artifacts" / "recycling_road_distance_matrix_m.npy"
    )
    recycling_duration = np.load(
        ROOT / "artifacts" / "recycling_road_duration_matrix_s.npy"
    )
    scenario_name = str(task["scenario"])
    scenario = {
        item.name: item for item in experiment_scenarios(config)
    }[scenario_name]
    demand = generate_demand_realization(
        bins,
        config,
        seed=int(task["arrival_seed"]),
        horizon_hours=config.operations.horizon_days * 24,
        scenario=scenario.demand,
    )
    result = run_policy(
        "fixed" if policy_name == "fixed_baseline" else "smart",
        int(task["replication"]),
        bins,
        config,
        distance,
        duration,
        demand.arrivals_kg,
        int(task["sensor_seed"]),
        forecaster=joblib.load(Path(str(task["model_path"]))),
        scenario=scenario,
        demand_context=demand.context,
        destination_matrices={
            "recycling_facility": (recycling_distance, recycling_duration)
        },
    )
    destinations = Counter(
        destination
        for event in result.route_events
        for destination in event.get("route_destinations", ())
    )
    row: dict[str, object] = {
        "phase": str(task["phase"]),
        "policy": policy_name,
        "fleet": fleet_name,
        "scenario": scenario_name,
        "replication": int(task["replication"]),
        "arrival_seed": int(task["arrival_seed"]),
        "sensor_seed": int(task["sensor_seed"]),
        "general_trips": destinations["waste_depot"],
        "recycling_trips": destinations["recycling_facility"],
    }
    row.update({metric: result.metrics[metric] for metric in METRICS})
    return row


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Matched-seed fuel/overflow policy and specialized-fleet search."
    )
    parser.add_argument("--phase", choices=tuple(SEED_OFFSETS), default="screen")
    parser.add_argument("--replications", type=int, default=2)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument(
        "--scenarios", nargs="+", default=["normal_patterned", "high_demand_seasonal"]
    )
    parser.add_argument(
        "--policies", nargs="+", choices=tuple(POLICIES), default=list(POLICIES)
    )
    parser.add_argument(
        "--fleets", nargs="+", choices=tuple(FLEETS), default=["g1_r1"]
    )
    parser.add_argument(
        "--model-path",
        type=Path,
        default=ROOT / "artifacts" / "dynamic_v4" / "fill_forecaster.joblib",
    )
    args = parser.parse_args()
    if not 2 <= args.replications <= 20:
        raise ValueError("replications must be in 2..20")
    if not 1 <= args.workers <= 4:
        raise ValueError("workers must be in 1..4")
    model_path = args.model_path.resolve()
    if not model_path.is_file():
        raise FileNotFoundError(model_path)
    try:
        recorded_model_path = model_path.relative_to(ROOT).as_posix()
    except ValueError:
        recorded_model_path = str(model_path)
    model_sha256 = hashlib.sha256(model_path.read_bytes()).hexdigest()

    base = load_config(ROOT / "config.json")
    declared = {item.name for item in experiment_scenarios(base)}
    unknown = sorted(set(args.scenarios) - declared)
    if unknown:
        raise ValueError("Unknown scenarios: " + ", ".join(unknown))

    arrival_offset, sensor_offset = SEED_OFFSETS[args.phase]
    tasks = []
    for policy in args.policies:
        for fleet in args.fleets:
            for scenario in args.scenarios:
                for replication in range(args.replications):
                    tasks.append(
                        {
                            "phase": args.phase,
                            "policy": policy,
                            "fleet": fleet,
                            "scenario": scenario,
                            "replication": replication,
                            "arrival_seed": base.operations.base_seed
                            + arrival_offset
                            + replication * 101,
                            "sensor_seed": base.operations.base_seed
                            + sensor_offset
                            + replication * 103,
                            "model_path": str(model_path),
                        }
                    )

    rows: list[dict[str, object]] = []
    with ProcessPoolExecutor(max_workers=args.workers) as executor:
        futures = {executor.submit(_run, task): task for task in tasks}
        for count, future in enumerate(as_completed(futures), 1):
            row = future.result()
            rows.append(row)
            print(
                f"[{count}/{len(tasks)}] {row['policy']} {row['fleet']} "
                f"{row['scenario']} rep={row['replication']} "
                f"fuel={float(row['fuel_l']):.1f}L "
                f"overflow={float(row['overflow_bin_hours']):.1f} bin-h",
                flush=True,
            )

    raw = pd.DataFrame(rows).sort_values(
        ["scenario", "policy", "fleet", "replication"]
    )
    grouping = ["scenario", "policy", "fleet"]
    numeric = [
        column
        for column in raw.columns
        if column not in {"phase", "policy", "fleet", "scenario"}
        and column not in {"replication", "arrival_seed", "sensor_seed"}
    ]
    summary = raw.groupby(grouping, as_index=False)[numeric].mean()
    worst = (
        raw.groupby(grouping, as_index=False)[
            ["fuel_l", "overflow_bin_hours", "overflow_spilled_kg"]
        ]
        .max()
        .rename(
            columns={
                "fuel_l": "worst_fuel_l",
                "overflow_bin_hours": "worst_overflow_bin_hours",
                "overflow_spilled_kg": "worst_overflow_spilled_kg",
            }
        )
    )
    summary = summary.merge(worst, on=grouping).sort_values(
        ["scenario", "overflow_bin_hours", "fuel_l"]
    )

    OUTPUT.mkdir(parents=True, exist_ok=True)
    raw_path = OUTPUT / f"{args.phase}_raw.csv"
    summary_path = OUTPUT / f"{args.phase}_summary.csv"
    manifest_path = OUTPUT / f"{args.phase}_manifest.json"
    raw.to_csv(raw_path, index=False)
    summary.to_csv(summary_path, index=False)
    manifest_path.write_text(
        json.dumps(
            {
                "phase": args.phase,
                "replications": args.replications,
                "scenarios": args.scenarios,
                "policies": {name: POLICIES[name] for name in args.policies},
                "fleets": {name: FLEETS[name] for name in args.fleets},
                "seed_offsets": {"arrival": arrival_offset, "sensor": sensor_offset},
                "model_path": recorded_model_path,
                "model_sha256": model_sha256,
                "horizon_days": base.operations.horizon_days,
                "metric_definition": (
                    "overflow_bin_hours is aggregate overflow exposure; two bins "
                    "overflowing for 30 minutes equal one bin-hour"
                ),
                "inference_scope": (
                    "bounded matched-seed simulation search; field validation remains required"
                ),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(summary.to_string(index=False))
    print(f"Wrote {raw_path}")


if __name__ == "__main__":
    main()
