from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pandas as pd

from binsight.district import generate_hourly_waste
from binsight.forecast import train_forecaster
from binsight.pipeline import prepare_project
from binsight.simulation import run_policy


ROOT = Path(__file__).resolve().parents[1]
VARIANTS = {
    "balanced_64_102": {
        "smart_dispatch_current_trigger_pct": 64,
        "smart_dispatch_predicted_trigger_pct": 102,
        "smart_include_current_trigger_pct": 54,
        "smart_include_predicted_trigger_pct": 100,
        "smart_min_dispatch_gap_hours": 48,
        "smart_max_dispatch_distance_km": 30,
    },
    "balanced_63_101": {
        "smart_dispatch_current_trigger_pct": 63,
        "smart_dispatch_predicted_trigger_pct": 101,
        "smart_include_current_trigger_pct": 54,
        "smart_include_predicted_trigger_pct": 99,
        "smart_min_dispatch_gap_hours": 48,
        "smart_max_dispatch_distance_km": 30,
    },
    "balanced_62_100": {
        "smart_dispatch_current_trigger_pct": 62,
        "smart_dispatch_predicted_trigger_pct": 100,
        "smart_include_current_trigger_pct": 54,
        "smart_include_predicted_trigger_pct": 98,
        "smart_min_dispatch_gap_hours": 48,
        "smart_max_dispatch_distance_km": 30,
    },
}


def main() -> None:
    config, _, _, bins, matrix = prepare_project(ROOT)
    forecaster, _ = train_forecaster(bins, config, seed=config.operations.base_seed + 90_000)
    horizon = config.operations.horizon_days * 24
    rows = []
    for replication in range(4):
        arrival_seed = config.operations.base_seed + 510_000 + replication * 101
        sensor_seed = config.operations.base_seed + 520_000 + replication * 103
        arrivals = generate_hourly_waste(bins, config, arrival_seed, horizon)
        fixed = run_policy(
            "fixed", replication, bins, config, matrix, arrivals, sensor_seed, forecaster=None
        )
        rows.append({"variant": "fixed", **fixed.metrics})
        for name, changes in VARIANTS.items():
            variant_config = replace(config, operations=replace(config.operations, **changes))
            smart = run_policy(
                "smart",
                replication,
                bins,
                variant_config,
                matrix,
                arrivals,
                sensor_seed,
                forecaster=forecaster,
            )
            rows.append({"variant": name, **smart.metrics})
    frame = pd.DataFrame(rows)
    metrics = [
        "overflow_incidents",
        "overflow_bin_hours",
        "overflow_spilled_kg",
        "distance_km",
        "collection_trips",
        "collection_stops",
        "wasted_pickups",
        "truck_utilization_pct",
    ]
    summary = frame.groupby("variant", as_index=False)[metrics].mean()
    summary.to_csv(ROOT / "artifacts" / "subang_policy_sensitivity_refinement.csv", index=False)
    print(summary.to_string(index=False))


if __name__ == "__main__":
    main()
