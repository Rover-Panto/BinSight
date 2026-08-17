import shutil
from pathlib import Path

import numpy as np

from binsight.config import load_config
from binsight.pipeline import experiment_scenarios, prepare_project


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
        "base",
        "high_demand",
        "traffic",
        "sensor_failure",
        "truck_capacity",
    }
    assert scenarios["high_demand"].demand_multiplier == config.stress.high_demand_multiplier
    assert scenarios["traffic"].traffic_multiplier == config.stress.traffic_multiplier
    assert (
        scenarios["sensor_failure"].sensor_missing_probability
        == config.stress.sensor_failure_probability
    )
    assert (
        scenarios["sensor_failure"].sensor_outlier_probability
        == config.stress.sensor_outlier_probability
    )
    assert (
        scenarios["truck_capacity"].truck_capacity_multiplier
        == config.stress.truck_capacity_multiplier
    )
