from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from binsight.config import load_config
from binsight.observations import (
    assert_observation_only_columns,
    generate_sensor_noise_scenario,
    observe_sensors,
)


ROOT = Path(__file__).resolve().parents[1]


def test_sensor_noise_is_seeded_and_policy_independent():
    config = load_config(ROOT / "config.json")
    first = generate_sensor_noise_scenario(config, 88, 4, 3)
    second = generate_sensor_noise_scenario(config, 88, 4, 3)
    different = generate_sensor_noise_scenario(config, 89, 4, 3)
    np.testing.assert_allclose(first.fill_random_pct, second.fill_random_pct)
    np.testing.assert_allclose(first.weight_random_kg, second.weight_random_kg)
    assert not np.allclose(first.fill_random_pct, different.fill_random_pct)


def test_missing_and_disagreeing_sensors_produce_low_confidence_upper_estimates():
    config = load_config(ROOT / "config.json")
    failed_sensor = replace(config.sensor, missing_probability=1.0)
    failed_config = replace(config, sensor=failed_sensor)
    scenario = generate_sensor_noise_scenario(failed_config, 42, 1, 3)
    batch = observe_sensors(
        np.array([100.0, 200.0, 300.0]),
        np.array([540.0, 540.0, 540.0]),
        scenario,
        0,
        24,
        failed_config,
    )
    assert batch.missing_flag.tolist() == [True, True, True]
    assert batch.confidence_flag.tolist() == [False, False, False]
    assert batch.upper_fill_pct.tolist() == [100.0, 100.0, 100.0]
    assert all("low_confidence" in flags for flags in batch.quality_flags)


def test_feature_leakage_guard_rejects_hidden_and_future_state():
    assert_observation_only_columns(["fill_pct", "weight_kg", "confidence_flag"])
    with pytest.raises(ValueError, match="Hidden or future state"):
        assert_observation_only_columns(["fill_pct", "latent_fill_pct"])
    with pytest.raises(ValueError, match="Hidden or future state"):
        assert_observation_only_columns(["fill_pct", "future_growth"])


def test_over_capacity_weight_does_not_emit_invalid_fill_percentage():
    config = load_config(ROOT / "config.json")
    sensor = replace(
        config.sensor,
        fill_random_sd_pct=0.0,
        weight_random_sd_kg=0.0,
        fill_bias_sd_pct=0.0,
        weight_bias_sd_kg=0.0,
        fill_drift_sd_pct_per_day=0.0,
        weight_drift_sd_kg_per_day=0.0,
        outlier_probability=0.0,
        missing_probability=0.0,
    )
    bounded = replace(config, sensor=sensor)
    scenario = generate_sensor_noise_scenario(bounded, 91, 1, 1)
    batch = observe_sensors(
        np.array([700.0]),
        np.array([540.0]),
        scenario,
        0,
        0,
        bounded,
    )

    assert batch.fill_pct[0] == 100.0
    assert batch.weight_kg[0] == 700.0
