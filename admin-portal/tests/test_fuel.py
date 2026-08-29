from pathlib import Path

import pytest

from binsight.config import load_config
from binsight.fuel import calculate_idle_fuel, calculate_leg_fuel


ROOT = Path(__file__).resolve().parents[1]


def test_payload_increases_leg_fuel_and_components_reconcile():
    config = load_config(ROOT / "config.json")
    empty = calculate_leg_fuel(10.0, 0.0, 9_000.0, 1.25, config)
    loaded = calculate_leg_fuel(10.0, 9_000.0, 9_000.0, 1.25, config)

    assert empty.base_driving_l == pytest.approx(4.5)
    assert empty.traffic_penalty_l == pytest.approx(1.125)
    assert empty.payload_penalty_l == pytest.approx(0.0)
    assert loaded.payload_penalty_l > 0
    assert loaded.total_driving_l > empty.total_driving_l
    assert loaded.total_driving_l == pytest.approx(
        loaded.base_driving_l + loaded.traffic_penalty_l + loaded.payload_penalty_l
    )


def test_idling_fuel_uses_duration_and_rate():
    assert calculate_idle_fuel(30.0, 3.0) == pytest.approx(1.5)
    assert calculate_idle_fuel(0.0, 3.0) == 0.0
    with pytest.raises(ValueError, match="non-negative"):
        calculate_idle_fuel(-1.0, 3.0)
