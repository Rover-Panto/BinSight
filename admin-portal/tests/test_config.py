from pathlib import Path

from binsight.config import load_config, required_controller_sites


ROOT = Path(__file__).resolve().parents[1]


def test_competition_scale_is_locked():
    config = load_config(ROOT / "config.json")
    assert config.pilot.households == 500
    assert config.pilot.commercial_units == 20
    assert config.operations.horizon_days == 30
    assert config.pilot.physical_prototype_bin_count == 3
    assert config.pilot.bins_per_service_site == 4
    assert config.pilot.physical_controller_bin_count == 3
    assert config.pilot.bin_count == 44
    assert config.pilot.recycling_facility_id == "USJ9-RECYCLING-CENTRE"
    assert config.waste.household_kg_per_day == 7.03
    assert config.waste.bin_capacity_kg == 540.0
    assert config.operations.crane_lift_limit_kg == 1500
    assert config.operations.smart_emergency_current_trigger_pct == 92
    assert config.operations.smart_plastic_required_trigger_pct == 95
    assert config.operations.uncertain_service_trigger_pct == 92
    assert config.operations.sensor_degraded_fraction_threshold == 0.15
    assert config.operations.sensor_degraded_fixed_interval_days == 2
    assert config.operations.smart_optional_min_central_fill_pct == 50
    assert config.operations.route_fixed_cost_m_equivalent == 25_000
    assert config.operations.minimum_route_value_m == 5_000
    assert config.operations.route_solver_milliseconds == 1_000
    assert config.operations.smart_emergency_time_to_overflow_hours == 6
    assert config.operations.next_planning_opportunity_hours == 6
    assert required_controller_sites(config) == 11
