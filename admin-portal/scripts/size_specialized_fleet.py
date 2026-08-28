from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from dataclasses import replace
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from binsight.config import load_config
from binsight.demand import generate_demand_realization
from binsight.district import build_district
from binsight.network import load_cached_service_network
from binsight.pipeline import experiment_scenarios
from binsight.simulation import run_policy


OUTPUT = ROOT / "artifacts" / "fleet-sizing"
FLEETS = {
    "one_general_one_recycling": {
        "general_waste_truck_count": 1,
        "recycling_truck_count": 1,
    },
}
SEEDS = {
    "screen": (3_110_000, 3_120_000),
    "confirm": (3_310_000, 3_320_000),
}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Bounded matched-seed sizing of the specialized BinSight fleet."
    )
    parser.add_argument("--phase", choices=tuple(SEEDS), default="screen")
    parser.add_argument("--replications", type=int, default=2)
    parser.add_argument(
        "--scenarios",
        nargs="+",
        default=["normal_patterned", "high_demand_seasonal"],
    )
    parser.add_argument(
        "--fleets",
        nargs="+",
        choices=tuple(FLEETS),
        default=list(FLEETS),
    )
    args = parser.parse_args()
    if not 2 <= args.replications <= 8:
        raise ValueError("replications must be in 2..8")

    base = load_config(ROOT / "config.json")
    network = load_cached_service_network(
        ROOT / "data" / "subang_jaya_osrm_network.json"
    )
    _, bins = build_district(base, network, ROOT / base.pilot.site_plan_file)
    distance = np.load(ROOT / "artifacts" / "road_distance_matrix_m.npy")
    duration = np.load(ROOT / "artifacts" / "road_duration_matrix_s.npy")
    recycling_distance = np.load(
        ROOT / "artifacts" / "recycling_road_distance_matrix_m.npy"
    )
    recycling_duration = np.load(
        ROOT / "artifacts" / "recycling_road_duration_matrix_s.npy"
    )
    destination_matrices = {
        "recycling_facility": (recycling_distance, recycling_duration)
    }
    forecaster = joblib.load(
        ROOT / "artifacts" / "dynamic_v2" / "fill_forecaster.joblib"
    )
    declared = {item.name: item for item in experiment_scenarios(base)}
    unknown = sorted(set(args.scenarios) - set(declared))
    if unknown:
        raise ValueError("Unknown scenarios: " + ", ".join(unknown))

    arrival_offset, sensor_offset = SEEDS[args.phase]
    rows = []
    seed_rows = []
    for scenario_name in args.scenarios:
        scenario = declared[scenario_name]
        for replication in range(args.replications):
            arrival_seed = base.operations.base_seed + arrival_offset + replication * 101
            sensor_seed = base.operations.base_seed + sensor_offset + replication * 103
            demand = generate_demand_realization(
                bins,
                base,
                seed=arrival_seed,
                horizon_hours=base.operations.horizon_days * 24,
                scenario=scenario.demand,
            )
            seed_rows.append(
                {
                    "scenario": scenario_name,
                    "replication": replication,
                    "arrival_seed": arrival_seed,
                    "sensor_seed": sensor_seed,
                }
            )
            for fleet_name in args.fleets:
                config = replace(
                    base,
                    operations=replace(base.operations, **FLEETS[fleet_name]),
                )
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
                    destination_matrices=destination_matrices,
                )
                destinations = Counter(
                    destination
                    for event in result.route_events
                    for destination in event.get("route_destinations", [])
                )
                rows.append(
                    {
                        "phase": args.phase,
                        "fleet": fleet_name,
                        "scenario": scenario_name,
                        "replication": replication,
                        "arrival_seed": arrival_seed,
                        "sensor_seed": sensor_seed,
                        "distance_km": result.metrics["distance_km"],
                        "collection_trips": result.metrics["collection_trips"],
                        "general_trips": destinations["waste_depot"],
                        "recycling_trips": destinations["recycling_facility"],
                        "overflow_incidents": result.metrics["overflow_incidents"],
                        "overflow_bin_hours": result.metrics["overflow_bin_hours"],
                        "overflow_spilled_kg": result.metrics["overflow_spilled_kg"],
                        "wasted_pickups": result.metrics["wasted_pickups"],
                        "unserved_required_bins": result.metrics["unserved_required_bins"],
                        "unfinished_trip_count": result.metrics["unfinished_trip_count"],
                        "fuel_l": result.metrics["fuel_l"],
                        "uncollected_kg_at_horizon": result.metrics[
                            "uncollected_kg_at_horizon"
                        ],
                    }
                )

    raw = pd.DataFrame(rows)
    metric_columns = [
        column
        for column in raw.columns
        if column
        not in {
            "phase",
            "fleet",
            "scenario",
            "replication",
            "arrival_seed",
            "sensor_seed",
        }
    ]
    summary = (
        raw.groupby(["scenario", "fleet"], as_index=False)[metric_columns]
        .mean()
        .sort_values(["scenario", "fleet"])
    )
    OUTPUT.mkdir(parents=True, exist_ok=True)
    raw.to_csv(OUTPUT / f"{args.phase}_raw.csv", index=False)
    summary.to_csv(OUTPUT / f"{args.phase}_summary.csv", index=False)
    manifest = {
        "phase": args.phase,
        "replications": args.replications,
        "scenarios": args.scenarios,
        "fleets": {name: FLEETS[name] for name in args.fleets},
        "seed_offsets": {"arrival": arrival_offset, "sensor": sensor_offset},
        "seeds": seed_rows,
        "horizon_days": base.operations.horizon_days,
        "model_path": "artifacts/dynamic_v2/fill_forecaster.joblib",
        "conceptual_model": {
            "general_base": "waste_depot",
            "recycling_base": base.pilot.recycling_facility_id,
            "recycling_materials": ["plastic_cups", "metal_cans", "glass_bottles"],
            "recycling_compartments": base.operations.recycling_compartment_count,
            "compartment_partitions": "sealed and movable; total mass/volume constrained",
            "max_daily_trips_is_per_truck": True,
            "rolling_planning_days": base.operations.multi_day_planning_horizon_days,
        },
        "inference_scope": "bounded matched-seed model contrast; not field causality",
    }
    (OUTPUT / f"{args.phase}_manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    print(summary.to_string(index=False))


if __name__ == "__main__":
    main()
