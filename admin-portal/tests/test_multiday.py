from pathlib import Path

import numpy as np
import pandas as pd

from binsight.config import load_config
from binsight.dispatch import make_snapshot_template, validate_snapshot
from binsight.multiday import optimize_multiday_pickups


ROOT = Path(__file__).resolve().parents[1]


def _inputs():
    config = load_config(ROOT / "config.json")
    bins = pd.read_csv(ROOT / "artifacts" / "district_bins.csv")
    waste_distance = np.load(ROOT / "artifacts" / "road_distance_matrix_m.npy")
    waste_duration = np.load(ROOT / "artifacts" / "road_duration_matrix_s.npy")
    recycling_distance = np.load(
        ROOT / "artifacts" / "recycling_road_distance_matrix_m.npy"
    )
    recycling_duration = np.load(
        ROOT / "artifacts" / "recycling_road_duration_matrix_s.npy"
    )
    return config, bins, {
        "waste_depot": (waste_distance, waste_duration),
        "recycling_facility": (recycling_distance, recycling_duration),
    }


def test_multiday_plan_assigns_forecast_due_bins_before_their_deadlines():
    config, bins, matrices = _inputs()
    snapshot = make_snapshot_template(bins["bin_id"])
    snapshot["fill_pct"] = 20.0
    snapshot["weight_kg"] = bins["capacity_kg"].to_numpy(float) * 0.20
    snapshot["time_to_overflow_hours"] = 999.0
    snapshot["risk_level"] = "low"
    snapshot["confidence_flag"] = True
    snapshot.loc[0, ["fill_pct", "weight_kg", "time_to_overflow_hours", "risk_level"]] = [
        80.0,
        float(bins.iloc[0]["capacity_kg"]) * 0.80,
        18.0,
        "high",
    ]
    snapshot.loc[1, ["fill_pct", "weight_kg", "time_to_overflow_hours", "risk_level"]] = [
        65.0,
        float(bins.iloc[1]["capacity_kg"]) * 0.65,
        42.0,
        "medium",
    ]
    normalized = validate_snapshot(
        snapshot,
        bins["bin_id"],
        config.operations.crane_lift_limit_kg,
    )

    plan = optimize_multiday_pickups(normalized, bins, config, matrices)

    by_index = {item.bin_index: item for item in plan.assignments}
    assert plan.status in {"OPTIMAL", "FEASIBLE"}
    assert {0, 1} <= set(by_index)
    assert by_index[0].service_day <= by_index[0].deadline_day == 0
    assert by_index[1].service_day <= by_index[1].deadline_day == 1
    assert not plan.unscheduled_required_bin_indices


def test_multiday_plan_does_not_create_work_from_low_empty_bins():
    config, bins, matrices = _inputs()
    snapshot = make_snapshot_template(bins["bin_id"])
    snapshot["fill_pct"] = 10.0
    snapshot["weight_kg"] = bins["capacity_kg"].to_numpy(float) * 0.10
    snapshot["time_to_overflow_hours"] = 999.0
    snapshot["risk_level"] = "low"
    snapshot["confidence_flag"] = True
    normalized = validate_snapshot(
        snapshot,
        bins["bin_id"],
        config.operations.crane_lift_limit_kg,
    )

    plan = optimize_multiday_pickups(normalized, bins, config, matrices)

    assert plan.status == "NO_CANDIDATE"
    assert not plan.assignments
