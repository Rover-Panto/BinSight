from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class PilotConfig:
    label: str
    center_lat: float
    center_lon: float
    depot_label: str
    depot_lat: float
    depot_lon: float
    radius_m: int
    network_type: str
    bin_count: int
    bins_per_controller: int
    physical_prototype_bin_count: int
    site_plan_file: str
    households: int
    commercial_units: int
    district_seed: int


@dataclass(frozen=True)
class WasteConfig:
    municipal_kg_per_capita_day: float
    household_size_persons: float
    commercial_kg_per_day: float
    bin_capacity_litres: float
    mixed_waste_density_kg_per_m3: float
    sizing_target_fill_pct: float
    sizing_reserve_factor: float
    sensor_interval_hours: int
    sensor_noise_sd_pct: float
    history_days: int
    event_days: tuple[int, ...]
    event_multiplier: float

    @property
    def bin_capacity_kg(self) -> float:
        return self.bin_capacity_litres / 1000.0 * self.mixed_waste_density_kg_per_m3

    @property
    def household_kg_per_day(self) -> float:
        return self.municipal_kg_per_capita_day * self.household_size_persons


@dataclass(frozen=True)
class OperationsConfig:
    horizon_days: int
    decision_hour: int
    smart_decision_hours: tuple[int, ...]
    fixed_interval_days: int
    smart_dispatch_current_trigger_pct: float
    smart_dispatch_predicted_trigger_pct: float
    smart_include_current_trigger_pct: float
    smart_include_predicted_trigger_pct: float
    smart_min_dispatch_gap_hours: int
    smart_max_dispatch_distance_km: float
    smart_dispatch_time_to_overflow_hours: float
    smart_emergency_current_trigger_pct: float
    smart_emergency_time_to_overflow_hours: float
    smart_sibling_include_current_pct: float
    smart_sibling_include_time_to_overflow_hours: float
    smart_optional_max_increment_km: float
    forecast_horizon_hours: int
    vehicle_archetype: str
    truck_body_volume_m3: float
    truck_compaction_ratio: float
    truck_capacity_kg: float
    crane_lift_limit_kg: float
    max_daily_trips: int
    service_minutes_per_bin: float
    fuel_l_per_km: float
    diesel_co2_kg_per_l: float
    wasted_pickup_threshold_pct: float
    replications: int
    base_seed: int
    route_solver_milliseconds: int


@dataclass(frozen=True)
class Config:
    project_name: str
    pilot: PilotConfig
    waste: WasteConfig
    operations: OperationsConfig

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def load_config(path: str | Path) -> Config:
    config_path = Path(path)
    payload = json.loads(config_path.read_text(encoding="utf-8"))
    waste_payload = dict(payload["waste"])
    waste_payload["event_days"] = tuple(waste_payload["event_days"])
    config = Config(
        project_name=payload["project_name"],
        pilot=PilotConfig(**payload["pilot"]),
        waste=WasteConfig(**waste_payload),
        operations=OperationsConfig(
            **(
                dict(payload["operations"])
                | {"smart_decision_hours": tuple(payload["operations"]["smart_decision_hours"])}
            )
        ),
    )
    validate_config(config)
    return config


def validate_config(config: Config) -> None:
    p, w, o = config.pilot, config.waste, config.operations
    if not (-90 <= p.center_lat <= 90 and -180 <= p.center_lon <= 180):
        raise ValueError("Pilot centre must be valid WGS84 latitude/longitude")
    if not (-90 <= p.depot_lat <= 90 and -180 <= p.depot_lon <= 180):
        raise ValueError("Depot must be valid WGS84 latitude/longitude")
    if p.radius_m < 300 or p.radius_m > 20_000:
        raise ValueError("radius_m must be between 300 and 20,000 metres")
    if p.bin_count < 3:
        raise ValueError("At least three bins are required by the competition brief")
    if p.bins_per_controller != 3:
        raise ValueError("The physical design requires exactly three bins per controller")
    if p.physical_prototype_bin_count != 3:
        raise ValueError("The physical prototype must contain exactly three bins")
    if p.bin_count % p.bins_per_controller != 0:
        raise ValueError("Digital bin_count must be divisible into three-bin controller clusters")
    if not p.site_plan_file.lower().endswith(".json"):
        raise ValueError("site_plan_file must be a JSON file")
    if p.households != 500 or p.commercial_units != 20:
        raise ValueError("Digital district must model exactly 500 households and 20 commercial units")
    positive = {
        "municipal_kg_per_capita_day": w.municipal_kg_per_capita_day,
        "household_size_persons": w.household_size_persons,
        "household_kg_per_day": w.household_kg_per_day,
        "commercial_kg_per_day": w.commercial_kg_per_day,
        "bin_capacity_kg": w.bin_capacity_kg,
        "horizon_days": o.horizon_days,
        "truck_capacity_kg": o.truck_capacity_kg,
        "truck_body_volume_m3": o.truck_body_volume_m3,
        "truck_compaction_ratio": o.truck_compaction_ratio,
        "crane_lift_limit_kg": o.crane_lift_limit_kg,
        "replications": o.replications,
    }
    for name, value in positive.items():
        if value <= 0:
            raise ValueError(f"{name} must be positive")
    if not 50 <= w.sizing_target_fill_pct <= 95:
        raise ValueError("sizing_target_fill_pct must be in 50..95")
    if w.sizing_reserve_factor < 1 or w.sizing_reserve_factor > 2:
        raise ValueError("sizing_reserve_factor must be in 1..2")
    if p.bin_count != required_controller_sites(config) * p.bins_per_controller:
        raise ValueError("Digital bin_count does not match the documented capacity calculation")
    if o.horizon_days != 30:
        raise ValueError("The competition requires a 30-day digital simulation")
    if not 0 <= o.decision_hour <= 23:
        raise ValueError("decision_hour must be in 0..23")
    if o.decision_hour % w.sensor_interval_hours != 0:
        raise ValueError("decision_hour must coincide with a configured sensor observation")
    if not o.smart_decision_hours or any(
        hour < 0 or hour > 23 or hour % w.sensor_interval_hours != 0
        for hour in o.smart_decision_hours
    ):
        raise ValueError("smart_decision_hours must contain sensor-aligned hours in 0..23")
    if o.max_daily_trips < 1 or o.max_daily_trips > 20:
        raise ValueError("max_daily_trips must be in 1..20")
    if w.bin_capacity_kg > o.crane_lift_limit_kg:
        raise ValueError("A full underground bin must not exceed the truck's crane lift limit")
    if not (
        o.smart_include_current_trigger_pct <= o.smart_dispatch_current_trigger_pct
        and o.smart_include_predicted_trigger_pct <= o.smart_dispatch_predicted_trigger_pct
    ):
        raise ValueError("Smart inclusion thresholds must not exceed dispatch thresholds")
    if o.smart_min_dispatch_gap_hours < 0 or o.smart_min_dispatch_gap_hours > 7 * 24:
        raise ValueError("smart_min_dispatch_gap_hours must be in 0..168")
    if o.smart_max_dispatch_distance_km <= 0 or o.smart_max_dispatch_distance_km > 500:
        raise ValueError("smart_max_dispatch_distance_km must be in (0, 500]")
    if not 0 < o.smart_emergency_time_to_overflow_hours <= o.smart_dispatch_time_to_overflow_hours:
        raise ValueError(
            "Emergency overflow horizon must be positive and no greater than the dispatch horizon"
        )
    if not (
        o.smart_dispatch_current_trigger_pct
        <= o.smart_emergency_current_trigger_pct
        <= 100
    ):
        raise ValueError(
            "Emergency fill threshold must be between the normal dispatch threshold and 100"
        )
    if not 0 <= o.smart_sibling_include_current_pct <= 100:
        raise ValueError("smart_sibling_include_current_pct must be in 0..100")
    if o.smart_sibling_include_time_to_overflow_hours < o.smart_dispatch_time_to_overflow_hours:
        raise ValueError(
            "Sibling overflow horizon must be at least the normal dispatch horizon"
        )
    if o.smart_optional_max_increment_km < 0 or o.smart_optional_max_increment_km > 100:
        raise ValueError("smart_optional_max_increment_km must be in 0..100")
    if o.route_solver_milliseconds < 25 or o.route_solver_milliseconds > 10_000:
        raise ValueError("route_solver_milliseconds must be in 25..10,000")


def required_controller_sites(config: Config) -> int:
    daily_demand_kg = (
        config.pilot.households * config.waste.household_kg_per_day
        + config.pilot.commercial_units * config.waste.commercial_kg_per_day
    )
    design_demand_kg = (
        daily_demand_kg
        * config.operations.fixed_interval_days
        * config.waste.sizing_reserve_factor
    )
    usable_capacity_per_site_kg = (
        config.pilot.bins_per_controller
        * config.waste.bin_capacity_kg
        * config.waste.sizing_target_fill_pct
        / 100.0
    )
    return math.ceil(design_demand_kg / usable_capacity_per_site_kg)
