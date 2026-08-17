import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from binsight.config import load_config
from binsight.dispatch import (
    build_dispatch_plan,
    load_mock_dispatches,
    make_demo_snapshot,
    make_snapshot_template,
    mock_dispatch_payload,
    parse_snapshot_json,
    save_mock_dispatch,
    validate_snapshot,
)


ROOT = Path(__file__).resolve().parents[1]


def _project_inputs():
    config = load_config(ROOT / "config.json")
    bins = pd.read_csv(ROOT / "artifacts" / "district_bins.csv")
    matrix = np.load(ROOT / "artifacts" / "road_distance_matrix_m.npy")
    return config, bins, matrix


def test_demo_snapshot_builds_capacity_feasible_collection_route():
    config, bins, matrix = _project_inputs()
    snapshot = validate_snapshot(
        make_demo_snapshot(bins),
        bins["bin_id"],
        config.operations.crane_lift_limit_kg,
    )
    plan = build_dispatch_plan(snapshot, bins, matrix, config)

    selected_ids = {row["bin_id"] for row in plan.selection_rows}
    assert plan.collection_required is True
    assert {"UGB-004", "UGB-013", "UGB-025"}.issubset(selected_ids)
    assert "UGB-005" in selected_ids  # useful sibling at UGB-004's site
    assert plan.route_plan.distance_m > 0
    assert all(route[0] == -1 and route[-1] == -1 for route in plan.route_plan.routes)
    weights = snapshot["weight_kg"].to_numpy(dtype=float)
    for route in plan.route_plan.routes:
        route_load = sum(weights[index] for index in route if index != -1)
        assert route_load <= config.operations.truck_capacity_kg
    assert any("UGB-025" in warning for warning in plan.warnings)


def test_complete_low_risk_snapshot_requires_no_collection():
    config, bins, matrix = _project_inputs()
    snapshot = make_snapshot_template(bins["bin_id"])
    snapshot["fill_pct"] = 30
    snapshot["weight_kg"] = 162
    normalized = validate_snapshot(
        snapshot,
        bins["bin_id"],
        config.operations.crane_lift_limit_kg,
    )
    plan = build_dispatch_plan(normalized, bins, matrix, config)
    assert plan.collection_required is False
    assert plan.selected_count == 0
    assert plan.route_plan.routes == []


def test_snapshot_validation_requires_all_unique_bins_and_timezone():
    config, bins, _ = _project_inputs()
    snapshot = make_snapshot_template(bins["bin_id"])
    with pytest.raises(ValueError, match="exactly 33 rows"):
        validate_snapshot(
            snapshot.iloc[:-1],
            bins["bin_id"],
            config.operations.crane_lift_limit_kg,
        )

    duplicate = snapshot.copy()
    duplicate.loc[1, "bin_id"] = duplicate.loc[0, "bin_id"]
    with pytest.raises(ValueError, match="Duplicate bin_id"):
        validate_snapshot(
            duplicate,
            bins["bin_id"],
            config.operations.crane_lift_limit_kg,
        )

    naive_time = snapshot.copy()
    naive_time["timestamp"] = "2026-08-17T10:00:00"
    with pytest.raises(ValueError, match="must include a timezone"):
        validate_snapshot(
            naive_time,
            bins["bin_id"],
            config.operations.crane_lift_limit_kg,
        )


def test_json_object_parses_and_mock_dispatch_is_auditable(tmp_path):
    config, bins, matrix = _project_inputs()
    demo = make_demo_snapshot(bins)
    parsed = parse_snapshot_json(json.dumps({"bins": demo.to_dict(orient="records")}))
    snapshot = validate_snapshot(
        parsed,
        bins["bin_id"],
        config.operations.crane_lift_limit_kg,
    )
    plan = build_dispatch_plan(snapshot, bins, matrix, config)
    payload = mock_dispatch_payload(plan, snapshot, bins, config)
    output = tmp_path / "dispatches.jsonl"
    save_mock_dispatch(payload, output)

    records = load_mock_dispatches(output)
    assert len(records) == 1
    assert records[0]["mode"] == "MOCK"
    assert records[0]["status"] == "MOCK_SENT_TO_TRUCK"
    assert records[0]["routes"][0]["stops"][0] == "DEPOT"
    assert records[0]["routes"][0]["stops"][-1] == "DEPOT"
    assert "No message was sent to a real vehicle" in records[0]["disclaimer"]
