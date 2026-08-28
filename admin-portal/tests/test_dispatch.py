import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from binsight.config import load_config
from binsight.dispatch import (
    COLLECTION_REQUIRED,
    INSPECTION_REQUIRED,
    build_dispatch_plan as _build_dispatch_plan,
    load_mock_dispatches,
    make_demo_snapshot,
    make_snapshot_template,
    mock_dispatch_payload,
    parse_snapshot_json,
    route_loads_kg,
    save_mock_dispatch,
    load_last_valid_readings,
    update_last_valid_readings_file,
    validate_snapshot,
)


ROOT = Path(__file__).resolve().parents[1]


def build_dispatch_plan(snapshot, bins, matrix, config, *args, **kwargs):
    """Exercise production destination routing with the matching cached matrix."""
    district = pd.read_csv(ROOT / "artifacts" / "district_bins.csv")
    order = {str(value): index + 1 for index, value in enumerate(district["bin_id"])}
    locations = [0] + [order[str(value)] for value in bins["bin_id"]]
    recycling_distance = np.load(
        ROOT / "artifacts" / "recycling_road_distance_matrix_m.npy"
    )[np.ix_(locations, locations)]
    recycling_duration = np.load(
        ROOT / "artifacts" / "recycling_road_duration_matrix_s.npy"
    )[np.ix_(locations, locations)]
    kwargs.setdefault(
        "destination_matrices",
        {"recycling_facility": (recycling_distance, recycling_duration)},
    )
    return _build_dispatch_plan(snapshot, bins, matrix, config, *args, **kwargs)


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
    assert "UGB-004" in selected_ids
    assert 12 not in plan.required_bin_indices  # high risk remains value-tested, not mandatory
    assert "UGB-025" not in selected_ids  # low-confidence evidence stays an inspection
    assert "UGB-005" in selected_ids  # same-deadline early-departure demonstration
    equal_deadline_indices = [
        int(bins.index[bins["bin_id"] == bin_id][0])
        for bin_id in ("UGB-001", "UGB-005")
    ]
    arrivals = {
        index: arrival
        for route_arrivals in plan.route_plan.route_arrival_times_s
        for index, arrival in route_arrivals.items()
    }
    assert all(arrivals[index] <= 6.3 * 3600 for index in equal_deadline_indices)
    deadline_row = next(
        row for row in plan.audit_rows if row["bin_id"] == "UGB-005"
    )
    assert deadline_row["collection_state"] == "Required"
    assert "dispatch now" in deadline_row["reason"]
    assert plan.route_plan.distance_m > 0
    assert all(route[0] == -1 and route[-1] == -1 for route in plan.route_plan.routes)
    assert set(plan.route_plan.route_vehicle_ids) == {
        "GENERAL-01",
        "RECYCLING-01",
    }
    weights = snapshot["weight_kg"].to_numpy(dtype=float)
    for route in plan.route_plan.routes:
        route_load = sum(weights[index] for index in route if index != -1)
        assert route_load <= config.operations.truck_capacity_kg
    assert any("UGB-025" in warning for warning in plan.warnings)


def test_complete_low_risk_snapshot_requires_no_collection():
    config, bins, matrix = _project_inputs()
    snapshot = make_snapshot_template(bins["bin_id"])
    snapshot["fill_pct"] = 30
    snapshot["weight_kg"] = bins["capacity_kg"].to_numpy() * 0.30
    normalized = validate_snapshot(
        snapshot,
        bins["bin_id"],
        config.operations.crane_lift_limit_kg,
    )
    plan = build_dispatch_plan(normalized, bins, matrix, config)
    assert plan.collection_required is False
    assert plan.selected_count == 0
    assert plan.route_plan.routes == []


def test_optional_consolidation_gap_defers_value_route_but_not_emergency():
    config, bins, matrix = _project_inputs()
    snapshot = make_snapshot_template(bins["bin_id"])
    snapshot["fill_pct"] = 60.0
    snapshot["weight_kg"] = bins["capacity_kg"].to_numpy() * 0.60
    snapshot["time_to_overflow_hours"] = 48.0
    snapshot["risk_level"] = "medium"
    normalized = validate_snapshot(
        snapshot,
        bins["bin_id"],
        config.operations.crane_lift_limit_kg,
    )
    normalized["overflow_probability_next_opportunity"] = 0.01
    normalized["overflow_probability_48h"] = 0.95

    allowed = build_dispatch_plan(normalized, bins, matrix, config)
    deferred = build_dispatch_plan(
        normalized,
        bins,
        matrix,
        config,
        optional_dispatch_allowed=False,
    )
    assert allowed.route_plan.routes
    assert not allowed.required_bin_indices
    assert deferred.route_plan.routes == []
    assert deferred.route_plan.dispatch_reason == "optional_consolidation_gap"

    low_fill = normalized.copy()
    low_fill["fill_pct"] = 40.0
    low_fill["weight_kg"] = bins["capacity_kg"].to_numpy() * 0.40
    low_fill["time_to_overflow_hours"] = 120.0
    low_fill_plan = build_dispatch_plan(low_fill, bins, matrix, config)
    assert low_fill_plan.route_plan.routes == []
    assert low_fill_plan.required_bin_indices == []

    emergency = normalized.copy()
    emergency.loc[0, "risk_level"] = "critical"
    emergency_plan = build_dispatch_plan(
        emergency,
        bins,
        matrix,
        config,
        optional_dispatch_allowed=False,
    )
    assert emergency_plan.route_plan.routes
    assert 0 in emergency_plan.required_bin_indices


def test_dispatches_before_wait_plus_travel_would_miss_overflow_deadline():
    config, all_bins, full_matrix = _project_inputs()
    bins = all_bins.iloc[[0]].reset_index(drop=True)
    matrix = full_matrix[np.ix_([0, 1], [0, 1])]
    duration = np.array([[0.0, 3600.0], [3600.0, 0.0]])
    now = datetime.now(timezone.utc).replace(microsecond=0)
    snapshot = _safe_snapshot(bins, now)
    snapshot.loc[0, ["fill_pct", "weight_kg", "time_to_overflow_hours", "risk_level"]] = [
        60.0,
        float(bins.iloc[0]["capacity_kg"]) * 0.60,
        6.5,
        "medium",
    ]
    normalized = validate_snapshot(
        snapshot,
        bins["bin_id"],
        config.operations.crane_lift_limit_kg,
        now_utc=now,
    )

    plan = build_dispatch_plan(
        normalized,
        bins,
        matrix,
        config,
        duration_matrix_s=duration,
    )

    assert plan.required_bin_indices == [0]
    assert plan.route_plan.route_arrival_times_s[0][0] <= 6.5 * 3600
    assert "dispatch now" in plan.audit_rows[0]["reason"]


def test_equal_overflow_times_include_service_delay_at_the_first_bin():
    config, all_bins, full_matrix = _project_inputs()
    bins = all_bins.iloc[[0, 4]].reset_index(drop=True)
    matrix = full_matrix[np.ix_([0, 1, 5], [0, 1, 5])]
    duration = np.array(
        [
            [0.0, 3600.0, 3600.0],
            [3600.0, 0.0, 1800.0],
            [3600.0, 1800.0, 0.0],
        ]
    )
    now = datetime.now(timezone.utc).replace(microsecond=0)
    snapshot = _safe_snapshot(bins, now)
    snapshot["fill_pct"] = 80.0
    snapshot["weight_kg"] = bins["capacity_kg"].to_numpy(float) * 0.80
    snapshot["time_to_overflow_hours"] = 7.2
    snapshot["risk_level"] = "high"
    normalized = validate_snapshot(
        snapshot,
        bins["bin_id"],
        config.operations.crane_lift_limit_kg,
        now_utc=now,
    )

    plan = build_dispatch_plan(
        normalized,
        bins,
        matrix,
        config,
        duration_matrix_s=duration,
    )

    assert set(plan.required_bin_indices) == {0, 1}
    assert len(plan.route_plan.routes) == 1
    assert set(plan.route_plan.served_bin_indices) == {0, 1}
    arrivals = plan.route_plan.route_arrival_times_s[0]
    assert max(arrivals.values()) <= 7.2 * 3600


def test_snapshot_validation_requires_all_unique_bins_and_timezone():
    config, bins, _ = _project_inputs()
    snapshot = make_snapshot_template(bins["bin_id"])
    with pytest.raises(ValueError, match="exactly 44 rows"):
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
    for route in records[0]["routes"]:
        expected_base = (
            config.pilot.recycling_facility_id
            if route["vehicle_type"] == "recycling"
            else "DEPOT"
        )
        assert route["stops"][0] == expected_base
        assert route["stops"][-1] == expected_base
        assert route["planned_arrivals"]
    assert "No message was sent to a real vehicle" in records[0]["disclaimer"]


def _safe_snapshot(bins, timestamp):
    snapshot = make_snapshot_template(bins["bin_id"], timestamp)
    snapshot["fill_pct"] = 20.0
    snapshot["weight_kg"] = bins["capacity_kg"].to_numpy(dtype=float) * 0.20
    snapshot["time_to_overflow_hours"] = 120.0
    snapshot["risk_level"] = "low"
    snapshot["confidence_flag"] = True
    return snapshot


def test_stale_snapshot_requires_inspection_not_no_collection():
    config, bins, matrix = _project_inputs()
    now = datetime(2026, 8, 17, 12, tzinfo=timezone.utc)
    snapshot = _safe_snapshot(bins, now - timedelta(hours=13))
    normalized = validate_snapshot(
        snapshot,
        bins["bin_id"],
        config.operations.crane_lift_limit_kg,
        now_utc=now,
        stale_after_hours=config.sensor.stale_after_hours,
    )
    plan = build_dispatch_plan(normalized, bins, matrix, config)

    assert plan.decision_state == INSPECTION_REQUIRED
    assert plan.collection_required is False
    assert plan.inspection_required is True
    assert len(plan.review_bin_indices) == config.pilot.bin_count
    assert all("stale reading" in row["reason"] for row in plan.audit_rows)


def test_low_confidence_critical_reading_remains_collection_relevant():
    config, bins, matrix = _project_inputs()
    now = datetime.now(timezone.utc).replace(microsecond=0)
    snapshot = _safe_snapshot(bins, now)
    snapshot.loc[0, ["risk_level", "confidence_flag"]] = ["critical", False]
    normalized = validate_snapshot(
        snapshot,
        bins["bin_id"],
        config.operations.crane_lift_limit_kg,
        now_utc=now,
    )
    plan = build_dispatch_plan(normalized, bins, matrix, config)

    assert plan.decision_state == COLLECTION_REQUIRED
    assert 0 in plan.required_bin_indices
    assert 0 in plan.review_bin_indices
    assert "critical risk" in plan.audit_rows[0]["reason"]
    assert "low confidence" in plan.audit_rows[0]["reason"]


def test_sensor_disagreement_requires_review_even_when_fill_is_low():
    config, bins, matrix = _project_inputs()
    now = datetime.now(timezone.utc).replace(microsecond=0)
    snapshot = _safe_snapshot(bins, now)
    snapshot.loc[0, ["fill_pct", "weight_kg"]] = [10.0, 170.0]
    normalized = validate_snapshot(
        snapshot,
        bins["bin_id"],
        config.operations.crane_lift_limit_kg,
        now_utc=now,
    )
    plan = build_dispatch_plan(normalized, bins, matrix, config)

    assert plan.decision_state == INSPECTION_REQUIRED
    assert plan.collection_required is False
    assert plan.review_bin_indices == [0]
    assert "sensors disagree" in plan.audit_rows[0]["reason"]


def test_missing_sensors_request_inspection_without_fabricating_collection():
    config, bins, matrix = _project_inputs()
    now = datetime.now(timezone.utc).replace(microsecond=0)
    snapshot = _safe_snapshot(bins, now)
    snapshot.loc[0, ["fill_pct", "weight_kg", "confidence_flag"]] = [np.nan, np.nan, False]
    normalized = validate_snapshot(
        snapshot,
        bins["bin_id"],
        config.operations.crane_lift_limit_kg,
        now_utc=now,
    )
    plan = build_dispatch_plan(normalized, bins, matrix, config)

    assert plan.decision_state == INSPECTION_REQUIRED
    assert plan.collection_required is False
    assert 0 not in plan.required_bin_indices
    assert 0 in plan.review_bin_indices
    assert all(np.isfinite(route_loads_kg(plan, normalized)))


def test_missing_sensors_keep_ai_critical_bin_collection_relevant_with_safe_load():
    config, bins, matrix = _project_inputs()
    now = datetime.now(timezone.utc).replace(microsecond=0)
    snapshot = _safe_snapshot(bins, now)
    snapshot.loc[0, ["fill_pct", "weight_kg", "risk_level", "confidence_flag"]] = [
        np.nan,
        np.nan,
        "critical",
        False,
    ]
    normalized = validate_snapshot(
        snapshot,
        bins["bin_id"],
        config.operations.crane_lift_limit_kg,
        now_utc=now,
    )
    plan = build_dispatch_plan(normalized, bins, matrix, config)

    assert plan.decision_state == COLLECTION_REQUIRED
    assert 0 in plan.required_bin_indices
    assert route_loads_kg(plan, normalized)[0] == bins.iloc[0]["capacity_kg"]


def test_medium_long_horizon_bins_wait_instead_of_aggregating_false_trip_value():
    config, bins, matrix = _project_inputs()
    now = datetime.now(timezone.utc).replace(microsecond=0)
    snapshot = _safe_snapshot(bins, now)
    snapshot.loc[:10, "fill_pct"] = 30.0
    snapshot.loc[:10, "weight_kg"] = bins.loc[:10, "capacity_kg"].to_numpy() * 0.30
    snapshot.loc[:10, "time_to_overflow_hours"] = 69.0
    snapshot.loc[:10, "risk_level"] = "medium"
    normalized = validate_snapshot(
        snapshot,
        bins["bin_id"],
        config.operations.crane_lift_limit_kg,
        now_utc=now,
    )
    plan = build_dispatch_plan(normalized, bins, matrix, config)

    assert not plan.required_bin_indices
    assert not plan.route_plan.routes
    assert plan.route_plan.dispatch_reason in {
        "wait_has_lower_expected_cost",
        "no_positive_value_route",
        "no_candidate",
    }


def test_last_valid_reading_is_aged_conservatively_without_forcing_a_wasteful_trip():
    config, bins, matrix = _project_inputs()
    now = datetime.now(timezone.utc).replace(microsecond=0)
    snapshot = _safe_snapshot(bins, now)
    snapshot.loc[0, ["fill_pct", "weight_kg", "confidence_flag"]] = [10.0, 54.0, False]
    normalized = validate_snapshot(
        snapshot,
        bins["bin_id"],
        config.operations.crane_lift_limit_kg,
        now_utc=now,
    )
    history = {
        str(bins.iloc[0]["bin_id"]): {
            "timestamp": (now - timedelta(hours=2)).isoformat(),
            "fill_pct": 79.0,
            "weight_kg": float(bins.iloc[0]["capacity_kg"]) * 0.79,
        }
    }
    plan = build_dispatch_plan(normalized, bins, matrix, config, history)

    assert 0 not in plan.required_bin_indices
    assert 0 in plan.review_bin_indices
    assert plan.inspection_required
    assert plan.audit_rows[0]["conservative_upper_fill_pct"] >= 80.5


def test_uncertain_high_margin_requests_inspection_without_forcing_a_truck():
    config, bins, matrix = _project_inputs()
    now = datetime.now(timezone.utc).replace(microsecond=0)
    snapshot = _safe_snapshot(bins, now)
    snapshot.loc[0, ["fill_pct", "weight_kg", "confidence_flag", "risk_level"]] = [
        80.0,
        float(bins.iloc[0]["capacity_kg"]) * 0.80,
        False,
        "low",
    ]
    normalized = validate_snapshot(
        snapshot,
        bins["bin_id"],
        config.operations.crane_lift_limit_kg,
        now_utc=now,
    )
    plan = build_dispatch_plan(normalized, bins, matrix, config)

    assert plan.audit_rows[0]["conservative_upper_fill_pct"] >= 90.0
    assert 0 in plan.review_bin_indices
    assert 0 not in plan.required_bin_indices
    assert plan.collection_required is False


def test_incompatible_physical_waste_streams_use_separate_trips():
    config, all_bins, full_matrix = _project_inputs()
    bins = all_bins.iloc[:3].reset_index(drop=True).copy()
    bins["waste_stream"] = [
        "mixed_general_waste",
        "dry_recycling",
        "dry_recycling",
    ]
    matrix = full_matrix[np.ix_([0, 1, 2, 3], [0, 1, 2, 3])]
    snapshot = _safe_snapshot(bins, datetime.now(timezone.utc).replace(microsecond=0))
    snapshot["fill_pct"] = 95.0
    snapshot["weight_kg"] = bins["capacity_kg"].to_numpy(dtype=float) * 0.95
    snapshot["risk_level"] = "critical"
    normalized = validate_snapshot(
        snapshot,
        bins["bin_id"],
        config.operations.crane_lift_limit_kg,
    )

    plan = build_dispatch_plan(normalized, bins, matrix, config)

    assert len(plan.route_plan.routes) == 2
    for route in plan.route_plan.routes:
        streams = {bins.iloc[index]["waste_stream"] for index in route if index != -1}
        assert len(streams) == 1
    assert plan.route_plan.solver_method.startswith("stream_separated:")
    assert set(plan.route_plan.route_vehicle_types) == {"general_waste", "recycling"}
    assert set(plan.route_plan.route_vehicle_ids) == {"GENERAL-01", "RECYCLING-01"}


def test_stream_trip_limit_reports_mandatory_bin_as_unserved():
    config, all_bins, full_matrix = _project_inputs()
    config = replace(
        config,
        operations=replace(
            config.operations,
            max_daily_trips=1,
            truck_capacity_kg=600.0,
        ),
    )
    bins = all_bins.iloc[[0, 4]].reset_index(drop=True).copy()
    matrix = full_matrix[np.ix_([0, 1, 5], [0, 1, 5])]
    snapshot = _safe_snapshot(bins, datetime.now(timezone.utc).replace(microsecond=0))
    snapshot["fill_pct"] = 95.0
    snapshot["weight_kg"] = bins["capacity_kg"].to_numpy(dtype=float) * 0.95
    snapshot["risk_level"] = "critical"
    normalized = validate_snapshot(
        snapshot,
        bins["bin_id"],
        config.operations.crane_lift_limit_kg,
    )

    plan = build_dispatch_plan(normalized, bins, matrix, config)

    assert len(plan.required_bin_indices) == 2
    assert len(plan.route_plan.routes) == 1
    assert len(plan.unserved_required_bin_indices) == 1
    assert set(plan.required_bin_indices) == (
        set(plan.selected_bin_indices) | set(plan.unserved_required_bin_indices)
    )
    assert any("Daily truck capacity could not cover" in item for item in plan.warnings)


def test_history_read_merge_write_serializes_portal_and_runner_writers(tmp_path):
    config, bins, _ = _project_inputs()
    now = datetime.now(timezone.utc).replace(microsecond=0)
    first = _safe_snapshot(bins, now)
    second = _safe_snapshot(bins, now)
    first["confidence_flag"] = False
    second["confidence_flag"] = False
    first.loc[0, "confidence_flag"] = True
    second.loc[1, "confidence_flag"] = True
    history_path = tmp_path / "last-valid.json"

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [
            pool.submit(update_last_valid_readings_file, frame, bins, config, history_path)
            for frame in (first, second)
        ]
        for future in futures:
            future.result()

    saved = load_last_valid_readings(history_path)
    assert {str(bins.iloc[0]["bin_id"]), str(bins.iloc[1]["bin_id"])} <= set(saved)
