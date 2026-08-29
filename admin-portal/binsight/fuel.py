from __future__ import annotations

from dataclasses import dataclass

from .config import Config


@dataclass(frozen=True)
class TrafficCondition:
    label: str
    duration_multiplier: float
    fuel_multiplier: float


@dataclass(frozen=True)
class LegFuel:
    base_driving_l: float
    traffic_penalty_l: float
    payload_penalty_l: float
    total_driving_l: float
    traffic_multiplier: float
    payload_multiplier: float


def traffic_condition(
    config: Config,
    absolute_minute: float,
    scenario_multiplier: float = 1.0,
) -> TrafficCondition:
    hour = int(absolute_minute // 60) % 24
    operations = config.operations
    if hour in operations.traffic_peak_hours:
        label = "peak"
        duration = operations.traffic_peak_duration_multiplier
        fuel = operations.traffic_peak_fuel_multiplier
    elif hour in operations.traffic_shoulder_hours:
        label = "shoulder"
        duration = operations.traffic_shoulder_duration_multiplier
        fuel = operations.traffic_shoulder_fuel_multiplier
    else:
        label = "off-peak"
        duration = operations.traffic_offpeak_duration_multiplier
        fuel = operations.traffic_offpeak_fuel_multiplier
    return TrafficCondition(
        label=label,
        duration_multiplier=duration * scenario_multiplier,
        fuel_multiplier=fuel * scenario_multiplier,
    )


def leg_travel_minutes(
    distance_m: float,
    osrm_duration_s: float | None,
    config: Config,
    absolute_minute: float,
    scenario_multiplier: float = 1.0,
) -> tuple[float, TrafficCondition, str]:
    traffic = traffic_condition(config, absolute_minute, scenario_multiplier)
    if osrm_duration_s is not None and osrm_duration_s > 0:
        base_minutes = osrm_duration_s / 60.0
        source = "OSRM duration"
    else:
        base_minutes = distance_m / 1000.0 / config.operations.fallback_road_speed_kph * 60.0
        source = f"{config.operations.fallback_road_speed_kph:g} km/h fallback"
    return base_minutes * traffic.duration_multiplier, traffic, source


def calculate_leg_fuel(
    distance_km: float,
    payload_kg: float,
    payload_capacity_kg: float,
    traffic_fuel_multiplier: float,
    config: Config,
) -> LegFuel:
    if distance_km < 0 or payload_kg < 0 or payload_capacity_kg <= 0:
        raise ValueError("Fuel inputs must use non-negative distance/payload and positive capacity")
    payload_fraction = min(1.0, payload_kg / payload_capacity_kg)
    payload_multiplier = 1.0 + (
        config.operations.payload_full_penalty_pct / 100.0 * payload_fraction
    )
    base = distance_km * config.operations.base_fuel_l_per_km
    after_traffic = base * traffic_fuel_multiplier
    traffic_penalty = after_traffic - base
    total = after_traffic * payload_multiplier
    payload_penalty = total - after_traffic
    return LegFuel(
        base_driving_l=base,
        traffic_penalty_l=traffic_penalty,
        payload_penalty_l=payload_penalty,
        total_driving_l=total,
        traffic_multiplier=traffic_fuel_multiplier,
        payload_multiplier=payload_multiplier,
    )


def calculate_idle_fuel(duration_minutes: float, litres_per_hour: float) -> float:
    if duration_minutes < 0 or litres_per_hour < 0:
        raise ValueError("Idle duration and rate must be non-negative")
    return duration_minutes / 60.0 * litres_per_hour
