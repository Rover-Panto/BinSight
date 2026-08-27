import shutil
from pathlib import Path

import numpy as np

from binsight.config import load_config
from binsight.pipeline import (
    build_fixed_baseline_route_audit,
    experiment_scenarios,
    prepare_project,
)


ROOT = Path(__file__).resolve().parents[1]


def test_prepare_project_persists_matching_osrm_distance_and_duration_matrices(tmp_path):
    (tmp_path / "data").mkdir()
    shutil.copy2(ROOT / "config.json", tmp_path / "config.json")
    for filename in ("subang_jaya_sites.json", "subang_jaya_osrm_network.json"):
        shutil.copy2(ROOT / "data" / filename, tmp_path / "data" / filename)

    config, network, depot, bins, distance, duration = prepare_project(tmp_path)

    assert config.pilot.bin_count == 33
    assert network.service_count == 12
    assert depot == 0
    assert len(bins) == 33
    assert distance.shape == duration.shape == (34, 34)
    np.testing.assert_array_equal(
        np.load(tmp_path / "artifacts" / "road_distance_matrix_m.npy"), distance
    )
    np.testing.assert_array_equal(
        np.load(tmp_path / "artifacts" / "road_duration_matrix_s.npy"), duration
    )


def test_declared_stress_scenarios_change_one_primary_condition_at_a_time():
    config = load_config(ROOT / "config.json")
    scenarios = {scenario.name: scenario for scenario in experiment_scenarios(config)}

    assert set(scenarios) == {
        "normal_patterned",
        "high_demand_seasonal",
        "event_heavy",
        "persistent_multi_day_surge",
        "localized_surge",
        "gradual_upward_trend",
        "abrupt_behavior_change",
        "traffic_disruption",
        "sensor_failure",
        "reduced_truck_capacity",
        "combined_demand_operational_stress",
    }
    assert (
        scenarios["high_demand_seasonal"].demand.demand_multiplier
        == config.stress.high_demand_multiplier
    )
    assert (
        scenarios["traffic_disruption"].traffic_multiplier
        == config.stress.traffic_multiplier
    )
    assert (
        scenarios["sensor_failure"].sensor_missing_probability
        == config.stress.sensor_failure_probability
    )
    assert (
        scenarios["sensor_failure"].sensor_outlier_probability
        == config.stress.sensor_outlier_probability
    )
    assert (
        scenarios["reduced_truck_capacity"].truck_capacity_multiplier
        == config.stress.truck_capacity_multiplier
    )
    assert scenarios["event_heavy"].demand.add_unannounced_event
    assert scenarios["persistent_multi_day_surge"].demand.shared_surge_windows
    assert scenarios["localized_surge"].demand.local_surge_bin_ids
    assert scenarios["gradual_upward_trend"].demand.trend_per_year > 0
    assert scenarios["abrupt_behavior_change"].demand.change_point_day == 12


def test_fixed_baseline_audit_is_explicit_about_reoptimization_and_limits():
    config = load_config(ROOT / "config.json")
    distance = np.load(ROOT / "artifacts" / "road_distance_matrix_m.npy")
    duration = np.load(ROOT / "artifacts" / "road_duration_matrix_s.npy")
    representative = {
        "base": {
            "fixed": [
                {
                    "hour": config.operations.fixed_interval_days * 24
                    + config.operations.decision_hour,
                    "route_solver_method": "ortools",
                    "route_bin_indices": [[-1, 0, 1, -1]],
                    "served_bins": ["UGB-001", "UGB-002"],
                    "unserved_required_bins": [],
                    "timeline": [],
                }
            ],
            "smart": [],
        }
    }

    audit = build_fixed_baseline_route_audit(
        config, distance, duration, representative
    )

    assert audit["fairness"]["fixed_has_reoptimized_path_each_dispatch"]
    assert "not an exact global-optimality certificate" in audit["limitations"][0]
    assert audit["representative_replication_checks"]["base"][
        "all_dispatches_on_fixed_schedule"
    ]
    assert audit["representative_replication_checks"]["base"][
        "all_routes_start_and_end_at_depot"
    ]
