from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from binsight.config import load_config
from binsight.dispatch import make_demo_snapshot, make_snapshot_template
from binsight.planner import ControlledPlanningRunner, PlanningService
from binsight.planning_store import PlanningStore


ROOT = Path(__file__).resolve().parents[1]


def _service(tmp_path):
    config = load_config(ROOT / "config.json")
    bins = pd.read_csv(ROOT / "artifacts" / "district_bins.csv")
    distance = np.load(ROOT / "artifacts" / "road_distance_matrix_m.npy")
    duration = np.load(ROOT / "artifacts" / "road_duration_matrix_s.npy")
    recycling_distance = np.load(
        ROOT / "artifacts" / "recycling_road_distance_matrix_m.npy"
    )
    recycling_duration = np.load(
        ROOT / "artifacts" / "recycling_road_duration_matrix_s.npy"
    )
    store = PlanningStore(tmp_path / "plans.sqlite3")
    return PlanningService(
        config,
        bins,
        distance,
        duration,
        store,
        network_version="test-network",
        model_version="test-model",
        destination_matrices={
            "recycling_facility": (recycling_distance, recycling_duration)
        },
    ), store, bins


def test_plan_lifecycle_is_idempotent_and_new_drafts_do_not_replace_acceptance(tmp_path):
    service, store, bins = _service(tmp_path)
    clock = datetime(2026, 8, 27, 8, tzinfo=timezone.utc)
    snapshot = make_demo_snapshot(bins, clock)
    first = service.evaluate(snapshot, decision_at=clock)
    duplicate = service.evaluate(snapshot, decision_at=clock + timedelta(minutes=5))
    assert first.created
    assert not duplicate.created
    assert first.plan.plan_id == duplicate.plan.plan_id
    assert duplicate.plan.decision_at == first.plan.decision_at
    assert duplicate.snapshot.iloc[0]["decision_at"] == first.snapshot.iloc[0]["decision_at"]

    accepted = store.accept(first.plan.plan_id, "test-operator")
    later = service.evaluate(snapshot, decision_at=clock + timedelta(minutes=16))
    assert later.created
    assert later.plan.plan_id != first.plan.plan_id
    assert store.get_plan(first.plan.plan_id)["status"] == "ACCEPTED"
    assert store.get_plan(later.plan.plan_id)["status"] == "DRAFT"

    payload = {"dispatch_id": "MOCK-ONE", "plan_id": first.plan.plan_id}
    saved, created = store.record_mock_dispatch(first.plan.plan_id, payload)
    replayed, created_again = store.record_mock_dispatch(
        first.plan.plan_id, {"dispatch_id": "MOCK-TWO"}
    )
    assert created and not created_again
    assert saved == replayed
    with pytest.raises(ValueError, match="cannot move"):
        store.accept(first.plan.plan_id, "test-operator")
    store.close()


def test_runner_is_single_instance_and_cleans_its_lock(tmp_path):
    runner = ControlledPlanningRunner(tmp_path, 1)
    result = SimpleNamespace(plan=SimpleNamespace(plan_id="PLAN-TEST"), created=True)
    assert runner.serve(lambda: result, max_iterations=1) == 1
    assert runner.status()["state"] == "STOPPED"
    assert not runner.lock_path.exists()
    first = ControlledPlanningRunner(tmp_path, 1)
    second = ControlledPlanningRunner(tmp_path, 1)
    first.acquire()
    try:
        with pytest.raises(RuntimeError, match="already owns"):
            second.acquire()
    finally:
        if first._lock_fd is not None:
            import os

            os.close(first._lock_fd)
        first.lock_path.unlink(missing_ok=True)


def test_active_trip_revision_freezes_leg_and_preserves_accepted_plan(tmp_path):
    service, store, bins = _service(tmp_path)
    clock = datetime(2026, 8, 27, 8, tzinfo=timezone.utc)
    snapshot = make_demo_snapshot(bins, clock)
    active = service.evaluate(snapshot, decision_at=clock)
    store.accept(active.plan.plan_id, "test-operator")
    first_route = active.plan.route_plan.routes[0]
    destination_index = next(index for index in first_route if index != -1)
    destination = str(bins.iloc[destination_index]["bin_id"])

    revision = service.replan_remaining_after_event(
        snapshot,
        active_plan_id=active.plan.plan_id,
        frozen_leg_origin="DEPOT",
        frozen_leg_destination=destination,
        completed_bin_ids=set(),
        decision_at=clock + timedelta(minutes=1),
    )

    assert store.get_plan(active.plan.plan_id)["status"] == "ACCEPTED"
    assert revision.remaining.stored_record["status"] == "DRAFT"
    assert revision.remaining.plan.plan_id != active.plan.plan_id
    assert revision.frozen_leg_destination == destination
    assert destination not in {
        str(bins.iloc[index]["bin_id"])
        for index in revision.remaining.plan.selected_bin_indices
    }
    store.close()


def test_network_or_model_version_change_creates_a_distinct_plan_identity(tmp_path):
    service, store, bins = _service(tmp_path)
    clock = datetime(2026, 8, 27, 8, tzinfo=timezone.utc)
    snapshot = make_demo_snapshot(bins, clock)
    first = service.evaluate(snapshot, decision_at=clock)
    changed = PlanningService(
        service.config,
        service.bins,
        service.distance_matrix_m,
        service.duration_matrix_s,
        store,
        network_version="changed-network",
        model_version="changed-model",
        destination_matrices=service.destination_matrices,
    ).evaluate(snapshot, decision_at=clock)

    assert changed.created
    assert changed.plan.plan_id != first.plan.plan_id
    assert changed.stored_record["assumptions"]["network_version"] == "changed-network"
    assert changed.stored_record["assumptions"]["model_version"] == "changed-model"
    store.close()


def test_completed_service_supersedes_delayed_pre_collection_telemetry(tmp_path):
    service, store, bins = _service(tmp_path)
    clock = datetime.now(timezone.utc).replace(microsecond=0)
    snapshot = make_demo_snapshot(bins, clock)
    first = service.evaluate(snapshot, decision_at=clock)
    served_ids = {
        str(bins.iloc[index]["bin_id"])
        for index in first.plan.route_plan.served_bin_indices
    }
    assert served_ids
    store.accept(first.plan.plan_id, "test-operator")
    store.complete(first.plan.plan_id, "test-operator", "route finished")

    delayed = service.evaluate(snapshot, decision_at=clock + timedelta(minutes=16))
    serviced_rows = delayed.snapshot[
        delayed.snapshot["bin_id"].astype(str).isin(served_ids)
    ]
    assert (serviced_rows["fill_pct"] == 0.0).all()
    assert (serviced_rows["weight_kg"] == 0.0).all()
    assert (serviced_rows["forecast_status"] == "stable_no_overflow").all()
    assert serviced_rows["service_plan_id"].eq(first.plan.plan_id).all()
    assert served_ids.isdisjoint(
        {
            str(bins.iloc[index]["bin_id"])
            for index in delayed.plan.selected_bin_indices
        }
    )
    assert set(store.latest_services()) == served_ids
    store.close()


def test_completed_service_empty_override_expires_to_inspection(tmp_path):
    service, store, bins = _service(tmp_path)
    clock = datetime.now(timezone.utc).replace(microsecond=0)
    snapshot = make_demo_snapshot(bins, clock)
    first = service.evaluate(snapshot, decision_at=clock)
    served_indices = list(first.plan.route_plan.served_bin_indices)
    served_ids = {str(bins.iloc[index]["bin_id"]) for index in served_indices}
    store.accept(first.plan.plan_id, "test-operator")
    store.complete(first.plan.plan_id, "test-operator", "route finished")

    after_grace = service.evaluate(
        snapshot,
        decision_at=clock
        + timedelta(hours=service.config.operations.post_service_empty_state_hours + 1),
    )
    rows = after_grace.snapshot[
        after_grace.snapshot["bin_id"].astype(str).isin(served_ids)
    ]
    assert rows["fill_pct"].isna().all()
    assert rows["weight_kg"].isna().all()
    assert (rows["forecast_status"] == "unavailable").all()
    assert (rows["service_confirmation_state"] == "telemetry_confirmation_required").all()
    assert not rows["confidence_flag"].any()
    assert all("post_service_telemetry_missing" in flags for flags in rows["quality_flags"])
    assert set(served_indices).issubset(after_grace.plan.review_bin_indices)
    store.close()


def test_recent_mock_dispatch_defers_optional_live_plan_but_not_evaluation(tmp_path):
    service, store, bins = _service(tmp_path)
    clock = datetime.now(timezone.utc).replace(microsecond=0)
    snapshot = make_snapshot_template(bins["bin_id"], clock)
    snapshot["schema_version"] = "2.0"
    snapshot["observed_at"] = snapshot["timestamp"]
    snapshot["decision_at"] = clock.isoformat()
    snapshot["snapshot_id"] = "OPTIONAL-GAP-SNAPSHOT"
    snapshot["event_id"] = [f"OPTIONAL-{index}" for index in range(len(snapshot))]
    snapshot["clock_status"] = "synchronized"
    snapshot["source_mode"] = "synthetic"
    snapshot["forecast_status"] = "available"
    snapshot["forecast_method"] = "test"
    snapshot["quality_flags"] = [tuple() for _ in range(len(snapshot))]
    snapshot["fill_pct"] = 60.0
    snapshot["weight_kg"] = bins["capacity_kg"].to_numpy() * 0.60
    snapshot["time_to_overflow_hours"] = 48.0
    snapshot["risk_level"] = "medium"
    snapshot["overflow_probability_next_opportunity"] = 0.01
    snapshot["overflow_probability_48h"] = 0.95

    first = service.evaluate(snapshot, decision_at=clock)
    assert first.plan.route_plan.routes
    assert not first.plan.required_bin_indices
    store.accept(first.plan.plan_id, "test-operator")
    store.record_mock_dispatch(
        first.plan.plan_id,
        {"dispatch_id": "OPTIONAL-GAP-DISPATCH", "plan_id": first.plan.plan_id},
    )

    later_snapshot = snapshot.copy()
    later_snapshot["observed_at"] = (clock + timedelta(hours=1)).isoformat()
    later_snapshot["timestamp"] = later_snapshot["observed_at"]
    later_snapshot["decision_at"] = later_snapshot["observed_at"]
    later = service.evaluate(later_snapshot, decision_at=clock + timedelta(hours=1))
    assert later.created
    assert later.plan.route_plan.routes == []
    assert later.plan.route_plan.dispatch_reason == "optional_consolidation_gap"
    store.close()
