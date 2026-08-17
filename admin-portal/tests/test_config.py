from pathlib import Path

from binsight.config import load_config, required_controller_sites


ROOT = Path(__file__).resolve().parents[1]


def test_competition_scale_is_locked():
    config = load_config(ROOT / "config.json")
    assert config.pilot.households == 500
    assert config.pilot.commercial_units == 20
    assert config.operations.horizon_days == 30
    assert config.pilot.physical_prototype_bin_count == 3
    assert config.pilot.bins_per_controller == 3
    assert config.pilot.bin_count == 33
    assert config.waste.household_kg_per_day == 7.03
    assert config.waste.bin_capacity_kg == 540.0
    assert config.operations.crane_lift_limit_kg == 1500
    assert required_controller_sites(config) == 11
