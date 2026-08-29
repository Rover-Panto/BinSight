from __future__ import annotations

import argparse
import json
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import replace
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from binsight.config import load_config, validate_config
from binsight.demand import generate_demand_realization
from binsight.district import build_district
from binsight.forecast import train_forecaster
from binsight.network import load_cached_service_network
from binsight.pipeline import experiment_scenarios, prepare_project
from binsight.simulation import run_policy


ROOT = Path(__file__).resolve().parents[1]

CANDIDATES: dict[str, dict[str, float | int]] = {
    "legacy_v2": {"route_post_optimization_enabled": False},
    "route_2opt_v3": {"route_post_optimization_enabled": True},
    "solver_500ms": {
        "route_post_optimization_enabled": False,
        "route_solver_milliseconds": 500,
    },
    "solver_1000ms": {
        "route_post_optimization_enabled": False,
        "route_solver_milliseconds": 1000,
    },
    "solver_2000ms": {
        "route_post_optimization_enabled": False,
        "route_solver_milliseconds": 2000,
    },
    "current_90": {},
    "emergency_fill_92": {
        "smart_emergency_current_trigger_pct": 92,
        "uncertain_service_trigger_pct": 92,
    },
    "emergency_fill_94": {
        "smart_emergency_current_trigger_pct": 94,
        "uncertain_service_trigger_pct": 94,
    },
    "emergency_fill_95": {
        "smart_emergency_current_trigger_pct": 95,
        "uncertain_service_trigger_pct": 95,
    },
    "emergency_fill_96": {
        "smart_emergency_current_trigger_pct": 96,
        "uncertain_service_trigger_pct": 96,
    },
    "fill_94_batch_96": {
        "smart_emergency_current_trigger_pct": 94,
        "uncertain_service_trigger_pct": 94,
        "smart_min_dispatch_gap_hours": 96,
        "smart_optional_min_central_fill_pct": 50,
        "route_fixed_cost_m_equivalent": 25_000,
        "minimum_route_value_m": 5_000,
    },
    "consolidate_40": {
        "smart_include_current_trigger_pct": 50,
        "smart_include_predicted_trigger_pct": 75,
        "smart_optional_min_central_fill_pct": 40,
        "smart_sibling_include_current_pct": 40,
        "smart_sibling_include_time_to_overflow_hours": 96,
    },
    "fill_92_consolidate_40": {
        "smart_emergency_current_trigger_pct": 92,
        "uncertain_service_trigger_pct": 92,
        "smart_include_current_trigger_pct": 50,
        "smart_include_predicted_trigger_pct": 75,
        "smart_optional_min_central_fill_pct": 40,
        "smart_sibling_include_current_pct": 40,
        "smart_sibling_include_time_to_overflow_hours": 96,
    },
    "fill_92_consolidate_35": {
        "smart_emergency_current_trigger_pct": 92,
        "uncertain_service_trigger_pct": 92,
        "smart_include_current_trigger_pct": 45,
        "smart_include_predicted_trigger_pct": 70,
        "smart_optional_min_central_fill_pct": 35,
        "smart_sibling_include_current_pct": 35,
        "smart_sibling_include_time_to_overflow_hours": 120,
    },
    "fill_93_consolidate_40": {
        "smart_emergency_current_trigger_pct": 93,
        "uncertain_service_trigger_pct": 93,
        "smart_include_current_trigger_pct": 50,
        "smart_include_predicted_trigger_pct": 75,
        "smart_optional_min_central_fill_pct": 40,
        "smart_sibling_include_current_pct": 40,
        "smart_sibling_include_time_to_overflow_hours": 96,
    },
    "strict_optional_120": {
        "smart_include_current_trigger_pct": 60,
        "smart_include_predicted_trigger_pct": 90,
        "smart_min_dispatch_gap_hours": 120,
        "smart_optional_min_central_fill_pct": 50,
        "smart_sibling_include_current_pct": 60,
        "smart_sibling_include_time_to_overflow_hours": 48,
        "route_fixed_cost_m_equivalent": 35_000,
        "minimum_route_value_m": 10_000,
    },
    "three_hour_fill_94": {
        "smart_emergency_current_trigger_pct": 94,
        "uncertain_service_trigger_pct": 94,
        "next_planning_opportunity_hours": 3.0,
    },
    "three_hour_fill_92": {
        "smart_emergency_current_trigger_pct": 92,
        "uncertain_service_trigger_pct": 92,
        "next_planning_opportunity_hours": 3.0,
    },
    "three_hour_fill_93": {
        "smart_emergency_current_trigger_pct": 93,
        "uncertain_service_trigger_pct": 93,
        "next_planning_opportunity_hours": 3.0,
    },
    "three_hour_fill_93_gap_96": {
        "smart_emergency_current_trigger_pct": 93,
        "uncertain_service_trigger_pct": 93,
        "next_planning_opportunity_hours": 3.0,
        "smart_min_dispatch_gap_hours": 96,
        "smart_optional_min_central_fill_pct": 50,
        "route_fixed_cost_m_equivalent": 25_000,
        "minimum_route_value_m": 5_000,
    },
    "three_hour_fill_93_strict": {
        "smart_emergency_current_trigger_pct": 93,
        "uncertain_service_trigger_pct": 93,
        "next_planning_opportunity_hours": 3.0,
        "smart_include_current_trigger_pct": 60,
        "smart_include_predicted_trigger_pct": 90,
        "smart_min_dispatch_gap_hours": 120,
        "smart_optional_min_central_fill_pct": 50,
        "smart_sibling_include_current_pct": 60,
        "smart_sibling_include_time_to_overflow_hours": 48,
        "route_fixed_cost_m_equivalent": 35_000,
        "minimum_route_value_m": 10_000,
    },
    "three_hour_fill_95": {
        "smart_emergency_current_trigger_pct": 95,
        "uncertain_service_trigger_pct": 95,
        "next_planning_opportunity_hours": 3.0,
    },
    "three_hour_fill_96": {
        "smart_emergency_current_trigger_pct": 96,
        "uncertain_service_trigger_pct": 96,
        "next_planning_opportunity_hours": 3.0,
    },
    "two_hour_fill_95": {
        "smart_emergency_current_trigger_pct": 95,
        "uncertain_service_trigger_pct": 95,
        "next_planning_opportunity_hours": 2.0,
    },
    "two_hour_fill_96": {
        "smart_emergency_current_trigger_pct": 96,
        "uncertain_service_trigger_pct": 96,
        "next_planning_opportunity_hours": 2.0,
    },
}

CANDIDATE_WASTE_OVERRIDES: dict[str, dict[str, float | int]] = {
    "three_hour_fill_92": {"sensor_interval_hours": 3},
    "three_hour_fill_93": {"sensor_interval_hours": 3},
    "three_hour_fill_93_gap_96": {"sensor_interval_hours": 3},
    "three_hour_fill_93_strict": {"sensor_interval_hours": 3},
    "three_hour_fill_94": {"sensor_interval_hours": 3},
    "three_hour_fill_95": {"sensor_interval_hours": 3},
    "three_hour_fill_96": {"sensor_interval_hours": 3},
    "two_hour_fill_95": {"sensor_interval_hours": 2},
    "two_hour_fill_96": {"sensor_interval_hours": 2},
}

PHASE_SEEDS = {
    "screen": (2_110_000, 2_120_000),
    "confirm": (2_310_000, 2_320_000),
    "adaptive_screen": (2_510_000, 2_520_000),
    "adaptive_confirm": (2_710_000, 2_720_000),
}

METRICS = (
    "overflow_incidents",
    "overflow_bin_hours",
    "overflow_spilled_kg",
    "distance_km",
    "collection_trips",
    "collection_stops",
    "wasted_pickups",
    "fuel_l",
    "unserved_required_bins",
    "uncollected_kg_at_horizon",
    "unfinished_trip_count",
    "routing_fallbacks",
    "mean_candidate_bins_per_dispatch",
    "max_candidate_bins_per_dispatch",
    "mean_required_bins_per_dispatch",
    "optional_only_dispatches",
    "mean_forecast_growth_pct_per_hour",
    "mean_overflow_probability_48h",
)


def candidate_config(candidate: str):
    config = load_config(ROOT / "config.json")
    overrides = CANDIDATES[candidate]
    tuned = replace(
        config,
        operations=replace(config.operations, **overrides),
        waste=replace(
            config.waste,
            **CANDIDATE_WASTE_OVERRIDES.get(candidate, {}),
        ),
    )
    validate_config(tuned)
    return tuned


def _model_path() -> Path:
    smoke_model = ROOT / "artifacts" / "four-bin-smoke" / "fill_forecaster.joblib"
    if smoke_model.exists():
        return smoke_model
    output = ROOT / "artifacts" / "distance-tuning" / "tuning_forecaster.joblib"
    output.parent.mkdir(parents=True, exist_ok=True)
    if not output.exists():
        config, _, _, bins, _, _ = prepare_project(ROOT)
        forecaster, _ = train_forecaster(
            bins, config, seed=config.operations.base_seed + 90_000
        )
        joblib.dump(forecaster, output)
    return output


def _run_task(task: dict) -> dict:
    candidate = str(task["candidate"])
    scenario_name = str(task["scenario"])
    replication = int(task["replication"])
    arrival_seed = int(task["arrival_seed"])
    sensor_seed = int(task["sensor_seed"])
    model_path = Path(task["model_path"])

    config = candidate_config(candidate)
    service_network = load_cached_service_network(
        ROOT / "data" / "subang_jaya_osrm_network.json"
    )
    _, bins = build_district(
        config,
        service_network,
        ROOT / config.pilot.site_plan_file,
    )
    distance = np.load(ROOT / "artifacts" / "road_distance_matrix_m.npy")
    duration = np.load(ROOT / "artifacts" / "road_duration_matrix_s.npy")
    recycling_distance = np.load(
        ROOT / "artifacts" / "recycling_road_distance_matrix_m.npy"
    )
    recycling_duration = np.load(
        ROOT / "artifacts" / "recycling_road_duration_matrix_s.npy"
    )
    scenarios = {item.name: item for item in experiment_scenarios(config)}
    scenario = scenarios[scenario_name]
    demand = generate_demand_realization(
        bins,
        config,
        seed=arrival_seed,
        horizon_hours=config.operations.horizon_days * 24,
        scenario=scenario.demand,
    )
    forecaster = joblib.load(model_path)
    result = run_policy(
        "smart",
        replication,
        bins,
        config,
        distance,
        duration,
        demand.arrivals_kg,
        sensor_seed,
        forecaster=forecaster,
        scenario=scenario,
        demand_context=demand.context,
        destination_matrices={
            "recycling_facility": (recycling_distance, recycling_duration)
        },
    )
    row = {
        "candidate": candidate,
        "scenario": scenario_name,
        "replication": replication,
        "arrival_seed": arrival_seed,
        "sensor_seed": sensor_seed,
    }
    row.update(
        {metric: result.metrics[metric] for metric in METRICS if metric in result.metrics}
    )
    candidate_counts = [
        float(event.get("candidate_bin_count", 0)) for event in result.route_events
    ]
    required_counts = [
        float(len(event.get("required_bins", []))) for event in result.route_events
    ]
    forecast_growth = []
    probability_48h = []
    for event in result.route_events:
        for audit in event.get("snapshot_rows", []):
            fill = audit.get("conservative_upper_fill_pct")
            horizon = audit.get("effective_time_to_overflow_hours")
            if fill is not None and horizon is not None and float(horizon) > 0:
                forecast_growth.append(max(0.0, 100.0 - float(fill)) / float(horizon))
            probability = audit.get("overflow_probability_48h")
            if probability is not None:
                probability_48h.append(float(probability))
    row.update(
        {
            "mean_candidate_bins_per_dispatch": (
                float(np.mean(candidate_counts)) if candidate_counts else 0.0
            ),
            "max_candidate_bins_per_dispatch": max(candidate_counts, default=0.0),
            "mean_required_bins_per_dispatch": (
                float(np.mean(required_counts)) if required_counts else 0.0
            ),
            "optional_only_dispatches": float(
                sum(count == 0 for count in required_counts)
            ),
            "mean_forecast_growth_pct_per_hour": (
                float(np.mean(forecast_growth)) if forecast_growth else 0.0
            ),
            "mean_overflow_probability_48h": (
                float(np.mean(probability_48h)) if probability_48h else 0.0
            ),
        }
    )
    return row


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Bounded matched-seed screen of distance-policy coefficients."
    )
    parser.add_argument("--phase", choices=tuple(PHASE_SEEDS), default="screen")
    parser.add_argument("--replications", type=int, default=2)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument(
        "--scenarios",
        nargs="+",
        default=["normal_patterned"],
    )
    parser.add_argument(
        "--candidates",
        nargs="+",
        choices=tuple(CANDIDATES),
        default=list(CANDIDATES),
    )
    args = parser.parse_args()
    if not 2 <= args.replications <= 10:
        raise ValueError("replications must be in 2..10")
    if not 1 <= args.workers <= 4:
        raise ValueError("workers must be in 1..4")

    config, _, _, _, _, _ = prepare_project(ROOT)
    declared = {item.name for item in experiment_scenarios(config)}
    unknown = set(args.scenarios) - declared
    if unknown:
        raise ValueError("Unknown scenarios: " + ", ".join(sorted(unknown)))
    model_path = _model_path()
    arrival_offset, sensor_offset = PHASE_SEEDS[args.phase]
    tasks = []
    for candidate in args.candidates:
        for scenario in args.scenarios:
            for replication in range(args.replications):
                tasks.append(
                    {
                        "candidate": candidate,
                        "scenario": scenario,
                        "replication": replication,
                        "arrival_seed": (
                            config.operations.base_seed
                            + arrival_offset
                            + replication * 101
                        ),
                        "sensor_seed": (
                            config.operations.base_seed
                            + sensor_offset
                            + replication * 103
                        ),
                        "model_path": str(model_path),
                    }
                )

    rows = []
    with ProcessPoolExecutor(max_workers=args.workers) as executor:
        futures = {executor.submit(_run_task, task): task for task in tasks}
        for completed, future in enumerate(as_completed(futures), start=1):
            row = future.result()
            rows.append(row)
            print(
                f"[{completed}/{len(tasks)}] {row['candidate']} "
                f"rep={row['replication']} scenario={row['scenario']} "
                f"km={float(row['distance_km']):.1f} "
                f"overflow={float(row['overflow_incidents']):.0f} "
                f"trips={float(row['collection_trips']):.0f}",
                flush=True,
            )

    raw = pd.DataFrame(rows).sort_values(
        ["scenario", "candidate", "replication"]
    )
    summary = (
        raw.groupby(["scenario", "candidate"], as_index=False)[list(METRICS)]
        .mean()
        .sort_values(["scenario", "distance_km", "overflow_incidents"])
    )
    output = ROOT / "artifacts" / "distance-tuning"
    output.mkdir(parents=True, exist_ok=True)
    raw_path = output / f"{args.phase}_raw.csv"
    summary_path = output / f"{args.phase}_summary.csv"
    manifest_path = output / f"{args.phase}_manifest.json"
    raw.to_csv(raw_path, index=False)
    summary.to_csv(summary_path, index=False)
    manifest_path.write_text(
        json.dumps(
            {
                "phase": args.phase,
                "replications": args.replications,
                "scenarios": args.scenarios,
                "candidates": {
                    name: {
                        "operations": CANDIDATES[name],
                        "waste": CANDIDATE_WASTE_OVERRIDES.get(name, {}),
                    }
                    for name in args.candidates
                },
                "seed_offsets": {
                    "arrival": arrival_offset,
                    "sensor": sensor_offset,
                },
                "model_path": str(model_path.relative_to(ROOT)),
                "purpose": (
                    "development screen"
                    if args.phase.endswith("screen")
                    else "untouched confirmation"
                ),
                "inference_scope": "bounded model-based matched-seed comparison; not field causality",
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(summary.to_string(index=False))
    print(f"Wrote {raw_path}")


if __name__ == "__main__":
    main()
