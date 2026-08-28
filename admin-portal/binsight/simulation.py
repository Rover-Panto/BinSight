from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timedelta, timezone
from typing import Any

import numpy as np
import pandas as pd
import simpy

from .config import Config
from .demand import DemandContext, DemandScenario
from .district import BinSpec
from .dispatch import build_dispatch_plan, validate_snapshot
from .forecast import ForecastBundle, make_feature_row
from .fuel import calculate_idle_fuel, calculate_leg_fuel, leg_travel_minutes
from .observations import generate_sensor_noise_scenario, observe_sensors
from .routing import (
    RoutePlan,
    greedy_proxy_distance_m,
    incremental_proxy_distance_m,
    select_capacity_feasible,
    solve_routes,
)


_greedy_proxy_distance_m = greedy_proxy_distance_m
_incremental_proxy_distance_m = incremental_proxy_distance_m


@dataclass(frozen=True)
class SimulationScenario:
    name: str = "normal_patterned"
    demand: DemandScenario = field(default_factory=DemandScenario)
    traffic_multiplier: float = 1.0
    sensor_missing_probability: float | None = None
    sensor_outlier_probability: float | None = None
    truck_capacity_multiplier: float = 1.0


@dataclass
class PolicyResult:
    policy: str
    replication: int
    metrics: dict[str, float | int | str]
    route_events: list[dict]
    final_fill_kg: np.ndarray
    regime_metrics: list[dict[str, float | int | str]] = field(default_factory=list)


def _time_to_overflow_hours(
    fill_pct: np.ndarray,
    predicted_growth_upper_pct: np.ndarray,
    forecast_horizon_hours: float,
) -> np.ndarray:
    current = np.asarray(fill_pct, dtype=float)
    growth = np.maximum(0.0, np.asarray(predicted_growth_upper_pct, dtype=float))
    remaining = np.maximum(0.0, 100.0 - current)
    rate_per_hour = growth / max(float(forecast_horizon_hours), 1e-9)
    result = np.full(current.shape, np.inf, dtype=float)
    result[current >= 100.0] = 0.0
    growing = (current < 100.0) & (rate_per_hour > 1e-9)
    result[growing] = remaining[growing] / rate_per_hour[growing]
    return result


def _risk_levels(
    fill_pct: np.ndarray,
    time_to_overflow_hours: np.ndarray,
    config: Config,
) -> np.ndarray:
    levels = np.full(len(fill_pct), "low", dtype=object)
    medium = (
        (fill_pct >= config.operations.smart_include_current_trigger_pct)
        | (time_to_overflow_hours <= config.operations.smart_sibling_include_time_to_overflow_hours)
    )
    high = (
        (fill_pct >= config.operations.smart_dispatch_current_trigger_pct)
        | (time_to_overflow_hours <= config.operations.smart_dispatch_time_to_overflow_hours)
    )
    critical = (
        (fill_pct >= config.operations.smart_emergency_current_trigger_pct)
        | (time_to_overflow_hours <= 0.0)
    )
    levels[medium] = "medium"
    levels[high] = "high"
    levels[critical] = "critical"
    return levels


def fixed_service_due(hour: int, config: Config) -> bool:
    first = config.operations.fixed_interval_days * 24 + config.operations.decision_hour
    interval = config.operations.fixed_interval_days * 24
    return hour >= first and (hour - first) % interval == 0


def _json_number(value: float) -> float | None:
    return float(value) if np.isfinite(value) else None


def run_policy(
    policy: str,
    replication: int,
    bins: list[BinSpec],
    config: Config,
    distance_matrix_m: np.ndarray,
    duration_matrix_s: np.ndarray,
    arrivals_kg: np.ndarray,
    sensor_seed: int,
    forecaster: ForecastBundle | None = None,
    scenario: SimulationScenario | None = None,
    demand_context: DemandContext | None = None,
) -> PolicyResult:
    if policy not in {"fixed", "smart"}:
        raise ValueError("policy must be 'fixed' or 'smart'")
    if policy == "smart" and forecaster is None:
        raise ValueError("smart policy requires a trained forecaster")
    active_scenario = scenario or SimulationScenario()
    horizon_hours = config.operations.horizon_days * 24
    horizon_minutes = horizon_hours * 60
    if arrivals_kg.shape != (horizon_hours, len(bins)):
        raise ValueError("arrivals_kg has the wrong shape")
    if demand_context is not None and (
        demand_context.current_event_intensity.shape != arrivals_kg.shape
        or demand_context.known_event_intensity_48h.shape != arrivals_kg.shape
        or demand_context.known_event_intensity_168h.shape != arrivals_kg.shape
        or len(demand_context.regime_labels) != horizon_hours
    ):
        raise ValueError("Demand context must align with the arrival matrix")
    expected_shape = (len(bins) + 1, len(bins) + 1)
    if distance_matrix_m.shape != expected_shape or duration_matrix_s.shape != expected_shape:
        raise ValueError("Road distance and duration matrices must contain depot plus every bin")

    env = simpy.Environment()
    capacities = np.array([item.capacity_kg for item in bins], dtype=float)
    bins_table = pd.DataFrame([asdict(item) for item in bins])
    reference_epoch = datetime.fromisoformat(config.demand.reference_start_utc).astimezone(
        timezone.utc
    )
    start_absolute_hour = (
        int(demand_context.absolute_hours[0]) if demand_context is not None else 0
    )
    simulation_epoch = reference_epoch + timedelta(hours=start_absolute_hour)
    hidden_mass = np.zeros(len(bins), dtype=float)
    observed_history: list[list[tuple[float, float]]] = [[] for _ in bins]
    last_valid_fill = np.full(len(bins), np.nan, dtype=float)
    last_valid_weight = np.full(len(bins), np.nan, dtype=float)
    last_valid_hour = np.full(len(bins), np.nan, dtype=float)
    last_collection_feature_hour = np.full(len(bins), np.nan, dtype=float)
    observation_count = horizon_hours // config.waste.sensor_interval_hours + 1
    sensor_scenario = generate_sensor_noise_scenario(
        config,
        sensor_seed,
        observation_count,
        len(bins),
        missing_probability=active_scenario.sensor_missing_probability,
        outlier_probability=active_scenario.sensor_outlier_probability,
    )
    route_events: list[dict[str, Any]] = []
    # Both policies start from the same empty district. Optional dynamic work
    # must accrue a full consolidation interval before its first departure;
    # emergency/service constraints can still override this clock.
    last_optional_dispatch_hour = 0.0
    truck_active = False
    trips_by_day: dict[int, int] = {}
    warmup_minute = config.operations.analysis_warmup_days * 24 * 60
    effective_truck_capacity = (
        config.operations.truck_capacity_kg * active_scenario.truck_capacity_multiplier
    )

    metric_names = (
        "overflow_incidents",
        "overflow_bin_hours",
        "overflow_spilled_kg",
        "distance_km",
        "travel_time_hours",
        "service_time_hours",
        "depot_unloading_time_hours",
        "turnaround_time_hours",
        "collection_trips",
        "collection_stops",
        "wasted_pickups",
        "collected_kg",
        "sum_collection_fill_pct",
        "unserved_required_bins",
        "inspection_events",
        "base_driving_fuel_l",
        "traffic_fuel_penalty_l",
        "payload_fuel_penalty_l",
        "collection_idle_fuel_l",
        "depot_idle_fuel_l",
        "routing_fallbacks",
        "forecast_driven_dispatches",
        "capacity_constrained_decisions",
        "dispatch_limit_blocks",
        "sensor_uncertainty_decisions",
    )
    totals = {name: 0.0 for name in metric_names}
    post_warmup = {name: 0.0 for name in metric_names}
    regime_totals = {
        label: {name: 0.0 for name in metric_names}
        for label in ("quiet", "normal", "surge")
    }

    def record(name: str, value: float, at_minute: float | None = None) -> None:
        moment = env.now if at_minute is None else at_minute
        totals[name] += float(value)
        regime_hour = min(horizon_hours - 1, max(0, int(float(moment) // 60)))
        regime_label = (
            demand_context.regime_labels[regime_hour]
            if demand_context is not None
            else "normal"
        )
        regime_totals[regime_label][name] += float(value)
        if moment >= warmup_minute:
            post_warmup[name] += float(value)

    def timeline_event(event: dict[str, Any], status: str, **details: Any) -> None:
        event["timeline"].append(
            {
                "status": status,
                "simulation_minute": round(float(env.now), 3),
                "simulation_hour": round(float(env.now) / 60.0, 4),
                "day": int(env.now // 1440) + 1,
            }
            | details
        )

    def conservative_observations(batch, hour: float) -> tuple[np.ndarray, np.ndarray, list[list[str]]]:
        upper_fill = batch.upper_fill_pct.copy()
        upper_weight = batch.upper_weight_kg.copy()
        review_reasons: list[list[str]] = [[] for _ in bins]
        for index in range(len(bins)):
            review_reasons[index].extend(batch.quality_flags[index])
            fused_missing = not np.isfinite(batch.fill_pct[index])
            has_last_valid = np.isfinite(last_valid_fill[index])
            if not batch.confidence_flag[index] and has_last_valid:
                age = max(0.0, hour - last_valid_hour[index])
                retained_margin = (
                    config.sensor.low_confidence_margin_pct
                    if fused_missing
                    else config.sensor.single_sensor_margin_pct
                )
                aged_fill = min(
                    150.0,
                    last_valid_fill[index]
                    + age * config.sensor.conservative_growth_pct_per_hour
                    + retained_margin,
                )
                if fused_missing:
                    upper_fill[index] = aged_fill
                    derived_weight = aged_fill / 100.0 * capacities[index]
                    upper_weight[index] = (
                        max(last_valid_weight[index], derived_weight)
                        if np.isfinite(last_valid_weight[index])
                        else derived_weight
                    )
                else:
                    upper_fill[index] = max(upper_fill[index], aged_fill)
                    if np.isfinite(last_valid_weight[index]):
                        upper_weight[index] = (
                            max(upper_weight[index], last_valid_weight[index])
                            if np.isfinite(upper_weight[index])
                            else last_valid_weight[index]
                        )
                review_reasons[index].append("last valid reading retained conservatively")
            elif fused_missing:
                # No reading is not evidence of a full bin. Preserve the unsafe state
                # as an inspection requirement without fabricating a collection load.
                upper_fill[index] = np.nan
                upper_weight[index] = np.nan
                review_reasons[index].append("no valid reading available; inspection required")
        return (
            np.clip(upper_fill, 0.0, 150.0),
            np.clip(upper_weight, 0.0, config.operations.crane_lift_limit_kg),
            review_reasons,
        )

    def predict_smart_state(
        hour: int,
        batch,
        upper_fill: np.ndarray,
    ):
        model_fill = batch.fill_pct.copy()
        model_weight = batch.weight_kg.copy()
        for index in range(len(bins)):
            if not np.isfinite(model_fill[index]):
                model_fill[index] = (
                    observed_history[index][-1][1] if observed_history[index] else upper_fill[index]
                )
            if not np.isfinite(model_weight[index]):
                model_weight[index] = model_fill[index] / 100.0 * capacities[index]
        feature_hour = (
            int(demand_context.absolute_hours[hour])
            if demand_context is not None
            else hour
        )
        feature_rows = []
        for index, item in enumerate(bins):
            feature_rows.append(
                make_feature_row(
                    item,
                    float(model_fill[index]),
                    float(model_weight[index]),
                    bool(batch.confidence_flag[index]),
                    observed_history[index],
                    feature_hour,
                    last_collection_hour=(
                        float(last_collection_feature_hour[index])
                        if np.isfinite(last_collection_feature_hour[index])
                        else None
                    ),
                    current_event_intensity=(
                        float(demand_context.current_event_intensity[hour, index])
                        if demand_context is not None
                        else 0.0
                    ),
                    known_event_intensity_48h=(
                        float(demand_context.known_event_intensity_48h[hour, index])
                        if demand_context is not None
                        else 0.0
                    ),
                    known_event_intensity_168h=(
                        float(demand_context.known_event_intensity_168h[hour, index])
                        if demand_context is not None
                        else 0.0
                    ),
                    calendar_timestamp=reference_epoch + timedelta(hours=feature_hour),
                )
            )
        predicted_mean, predicted_upper = forecaster.predict(pd.DataFrame(feature_rows))
        overflow_probability_6h = (
            forecaster.predict_overflow_probability_6h(pd.DataFrame(feature_rows))
            if hasattr(forecaster, "predict_overflow_probability_6h")
            else np.full(len(feature_rows), np.nan, dtype=float)
        )
        overflow_probability_48h = (
            forecaster.predict_overflow_probability_48h(pd.DataFrame(feature_rows))
            if hasattr(forecaster, "predict_overflow_probability_48h")
            else np.full(len(feature_rows), np.nan, dtype=float)
        )
        time_to_overflow = _time_to_overflow_hours(
            upper_fill,
            predicted_upper,
            config.operations.forecast_horizon_hours,
        )
        risk = _risk_levels(upper_fill, time_to_overflow, config)
        return (
            np.asarray(predicted_mean),
            np.asarray(predicted_upper),
            time_to_overflow,
            risk,
            overflow_probability_6h,
            overflow_probability_48h,
        )

    def execute_plan(plan: RoutePlan, route_event: dict[str, Any]):
        nonlocal truck_active
        completed_bins: list[int] = []
        for trip_number, route in enumerate(plan.routes, start=1):
            start_day = int(env.now // 1440)
            if trips_by_day.get(start_day, 0) >= config.operations.max_daily_trips:
                next_day = (start_day + 1) * 1440
                timeline_event(
                    route_event,
                    "WAITING_DAILY_TRIP_LIMIT",
                    trip_number=trip_number,
                    resume_minute=next_day,
                )
                yield env.timeout(next_day - env.now)
                start_day += 1
            trips_by_day[start_day] = trips_by_day.get(start_day, 0) + 1
            record("collection_trips", 1)
            payload_kg = 0.0
            timeline_event(
                route_event,
                "DISPATCHED",
                trip_number=trip_number,
                payload_kg=0.0,
                payload_capacity_kg=effective_truck_capacity,
            )
            for origin, destination in zip(route[:-1], route[1:]):
                origin_location = 0 if origin == -1 else origin + 1
                destination_location = 0 if destination == -1 else destination + 1
                distance_m = float(distance_matrix_m[origin_location, destination_location])
                osrm_duration = float(duration_matrix_s[origin_location, destination_location])
                travel_minutes, traffic, duration_source = leg_travel_minutes(
                    distance_m,
                    osrm_duration,
                    config,
                    env.now,
                    active_scenario.traffic_multiplier,
                )
                destination_id = "DEPOT" if destination == -1 else bins[destination].bin_id
                status = "RETURNING_TO_DEPOT" if destination == -1 else "EN_ROUTE"
                timeline_event(
                    route_event,
                    status,
                    trip_number=trip_number,
                    origin="DEPOT" if origin == -1 else bins[origin].bin_id,
                    destination=destination_id,
                    next_stop=destination_id,
                    travel_minutes=round(travel_minutes, 3),
                    distance_km=round(distance_m / 1000.0, 4),
                    traffic=traffic.label,
                    duration_source=duration_source,
                    payload_kg=round(payload_kg, 3),
                )
                leg_fuel = calculate_leg_fuel(
                    distance_m / 1000.0,
                    payload_kg,
                    effective_truck_capacity,
                    traffic.fuel_multiplier,
                    config,
                )
                yield env.timeout(travel_minutes)
                record("distance_km", distance_m / 1000.0)
                record("travel_time_hours", travel_minutes / 60.0)
                record("base_driving_fuel_l", leg_fuel.base_driving_l)
                record("traffic_fuel_penalty_l", leg_fuel.traffic_penalty_l)
                record("payload_fuel_penalty_l", leg_fuel.payload_penalty_l)

                if destination == -1:
                    timeline_event(
                        route_event,
                        "UNLOADING",
                        trip_number=trip_number,
                        payload_kg=round(payload_kg, 3),
                        duration_minutes=config.operations.depot_unload_minutes,
                    )
                    unload_fuel = calculate_idle_fuel(
                        config.operations.depot_unload_minutes,
                        config.operations.depot_idle_l_per_hour,
                    )
                    yield env.timeout(config.operations.depot_unload_minutes)
                    record(
                        "depot_unloading_time_hours",
                        config.operations.depot_unload_minutes / 60.0,
                    )
                    record("depot_idle_fuel_l", unload_fuel)
                    payload_kg = 0.0
                    if (
                        trip_number < len(plan.routes)
                        and config.operations.turnaround_minutes > 0
                    ):
                        timeline_event(
                            route_event,
                            "TURNAROUND",
                            trip_number=trip_number,
                            duration_minutes=config.operations.turnaround_minutes,
                        )
                        yield env.timeout(config.operations.turnaround_minutes)
                        record(
                            "turnaround_time_hours",
                            config.operations.turnaround_minutes / 60.0,
                        )
                    timeline_event(
                        route_event,
                        "TRIP_COMPLETE",
                        trip_number=trip_number,
                        bins_completed=len(completed_bins),
                    )
                    continue

                timeline_event(
                    route_event,
                    "ARRIVED",
                    trip_number=trip_number,
                    bin_id=bins[destination].bin_id,
                    payload_kg=round(payload_kg, 3),
                )
                timeline_event(
                    route_event,
                    "COLLECTING",
                    trip_number=trip_number,
                    bin_id=bins[destination].bin_id,
                    duration_minutes=config.operations.service_minutes_per_bin,
                )
                service_fuel = calculate_idle_fuel(
                    config.operations.service_minutes_per_bin,
                    config.operations.service_idle_l_per_hour,
                )
                yield env.timeout(config.operations.service_minutes_per_bin)
                record("service_time_hours", config.operations.service_minutes_per_bin / 60.0)
                record("collection_idle_fuel_l", service_fuel)
                actual_mass = float(hidden_mass[destination])
                if payload_kg + actual_mass > effective_truck_capacity + 1e-9:
                    record("unserved_required_bins", 1)
                    timeline_event(
                        route_event,
                        "COLLECTION_BLOCKED_CAPACITY",
                        trip_number=trip_number,
                        bin_id=bins[destination].bin_id,
                        payload_kg=round(payload_kg, 3),
                        bin_mass_kg=round(actual_mass, 3),
                    )
                    continue
                fill_at_completion_pct = 100.0 * actual_mass / capacities[destination]
                hidden_mass[destination] = 0.0
                # A completed collection is stronger evidence than delayed or
                # missing pre-collection telemetry. Reset the digital service
                # state so the same old reading cannot trigger another truck.
                completed_hour = float(env.now) / 60.0
                completed_feature_hour = start_absolute_hour + completed_hour
                last_valid_fill[destination] = 0.0
                last_valid_weight[destination] = 0.0
                last_valid_hour[destination] = completed_hour
                observed_history[destination].clear()
                observed_history[destination].append((completed_hour, 0.0))
                observed_history[destination][-1] = (completed_feature_hour, 0.0)
                last_collection_feature_hour[destination] = completed_feature_hour
                payload_kg += actual_mass
                completed_bins.append(destination)
                record("collection_stops", 1)
                record("collected_kg", actual_mass)
                record("sum_collection_fill_pct", fill_at_completion_pct)
                record(
                    "wasted_pickups",
                    float(fill_at_completion_pct < config.operations.wasted_pickup_threshold_pct),
                )
                timeline_event(
                    route_event,
                    "COLLECTION_COMPLETE",
                    trip_number=trip_number,
                    bin_id=bins[destination].bin_id,
                    collected_kg=round(actual_mass, 3),
                    payload_kg=round(payload_kg, 3),
                    bins_completed=len(completed_bins),
                )
        truck_active = False
        route_event["completed"] = True
        route_event["completed_minute"] = round(float(env.now), 3)

    def dispatch(hour: int, batch) -> None:
        nonlocal last_optional_dispatch_hour, truck_active
        decision_day = int(env.now // 1440)
        remaining_trips = config.operations.max_daily_trips - trips_by_day.get(decision_day, 0)
        if remaining_trips <= 0:
            record("dispatch_limit_blocks", 1)
            return
        if truck_active:
            return
        if policy == "fixed" and not fixed_service_due(hour, config):
            return
        upper_fill, upper_weight, review_reasons = conservative_observations(batch, hour)
        route_weights = np.where(
            np.isfinite(upper_weight), np.minimum(upper_weight, capacities), capacities
        )
        predicted_mean = np.zeros(len(bins), dtype=float)
        predicted_upper = np.zeros(len(bins), dtype=float)
        time_to_overflow = np.full(len(bins), np.inf, dtype=float)
        risk = np.full(len(bins), "fixed", dtype=object)
        required_set: set[int]
        unserved_required: list[int]
        snapshot_rows: list[dict[str, Any]]

        if policy == "fixed":
            review_indices = [index for index, reasons in enumerate(review_reasons) if reasons]
            record("inspection_events", len(review_indices))
            record("sensor_uncertainty_decisions", float(bool(review_indices)))
            selected = list(range(len(bins)))
            stream_groups: dict[str, list[int]] = {}
            for index, item in enumerate(bins):
                stream_groups.setdefault(item.waste_stream, []).append(index)
            stream_plans: list[RoutePlan] = []
            fixed_unserved: set[int] = set()
            remaining_stream_trips = remaining_trips
            for stream in sorted(stream_groups):
                stream_selected = stream_groups[stream]
                if remaining_stream_trips <= 0:
                    fixed_unserved.update(stream_selected)
                    continue
                capacity_selected, rejected = select_capacity_feasible(
                    stream_selected,
                    route_weights,
                    effective_truck_capacity,
                    remaining_stream_trips,
                )
                fixed_unserved.update(rejected)
                if not capacity_selected:
                    continue
                stream_plan = solve_routes(
                    capacity_selected,
                    route_weights,
                    distance_matrix_m,
                    effective_truck_capacity,
                    remaining_stream_trips,
                    config.operations.route_solver_milliseconds,
                )
                stream_plans.append(stream_plan)
                served_in_stream = set(stream_plan.served_bin_indices)
                fixed_unserved.update(set(capacity_selected) - served_in_stream)
                remaining_stream_trips -= len(stream_plan.routes)
            plan = RoutePlan(
                routes=[route for item in stream_plans for route in item.routes],
                distance_m=sum(item.distance_m for item in stream_plans),
                served_bin_indices=[
                    index for item in stream_plans for index in item.served_bin_indices
                ],
                solver_method="stream_separated_fixed:" + "+".join(
                    sorted({item.solver_method for item in stream_plans})
                ),
                dropped_bin_indices=sorted(fixed_unserved),
                dispatch_reason="fixed_due_service",
            )
            capacity_selected = list(plan.served_bin_indices)
            required_set = set(capacity_selected)
            unserved_required = sorted(set(selected) - required_set | fixed_unserved)
            record("unserved_required_bins", len(unserved_required))
            record(
                "capacity_constrained_decisions", float(bool(unserved_required))
            )
            if not capacity_selected:
                return
            served = set(plan.served_bin_indices)
            snapshot_rows = []
            for index, item in enumerate(bins):
                selection = "Required" if index in served else "Unserved required"
                snapshot_rows.append(
                    {
                        "bin_id": item.bin_id,
                        "site_id": item.site_id,
                        "fill_pct": _json_number(batch.fill_pct[index]),
                        "weight_kg": _json_number(batch.weight_kg[index]),
                        "time_to_overflow_hours": None,
                        "risk_level": "fixed",
                        "confidence_flag": bool(batch.confidence_flag[index]),
                        "conservative_upper_fill_pct": _json_number(upper_fill[index]),
                        "selection": selection,
                        "selection_reason": selection.lower(),
                        "collection_state": selection,
                    }
                )
        else:
            (
                predicted_mean,
                predicted_upper,
                time_to_overflow,
                risk,
                overflow_probability_6h,
                overflow_probability_48h,
            ) = predict_smart_state(hour, batch, upper_fill)
            # An upper forecast based on a failed/outlier observation is not an
            # independent critical signal. Keep it explicit as unavailable and
            # request inspection; a later valid observation or an upstream
            # explicitly critical event can still require collection.
            unreliable = ~np.asarray(batch.confidence_flag, dtype=bool)
            time_to_overflow[unreliable] = np.nan
            risk[unreliable] = "unknown"
            overflow_probability_6h[unreliable] = np.nan
            overflow_probability_48h[unreliable] = np.nan
            decision_time = simulation_epoch + timedelta(hours=hour)
            forecast_status = [
                (
                    "unavailable"
                    if unreliable[index]
                    else ("available" if np.isfinite(value) else "stable_no_overflow")
                )
                for index, value in enumerate(time_to_overflow)
            ]
            snapshot = pd.DataFrame(
                {
                    "schema_version": "2.0",
                    "timestamp": decision_time.isoformat(),
                    "observed_at": decision_time.isoformat(),
                    "decision_at": decision_time.isoformat(),
                    "snapshot_id": f"SIM-{active_scenario.name}-{replication}-{hour}",
                    "event_id": [
                        f"SIM:{active_scenario.name}:{replication}:{hour}:{item.bin_id}"
                        for item in bins
                    ],
                    "clock_status": "synchronized",
                    "source_mode": "synthetic",
                    "bin_id": [item.bin_id for item in bins],
                    "fill_pct": batch.fill_pct,
                    "weight_kg": batch.weight_kg,
                    "time_to_overflow_hours": [
                        _json_number(value) for value in time_to_overflow
                    ],
                    "risk_level": risk,
                    "overflow_probability_next_opportunity": overflow_probability_6h,
                    "overflow_probability_48h": overflow_probability_48h,
                    "confidence_flag": batch.confidence_flag,
                    "forecast_status": forecast_status,
                    "forecast_method": "growth-q90-v2",
                    "model_version": "simulation-forecast-bundle",
                    "quality_flags": [tuple(flags) for flags in batch.quality_flags],
                }
            )
            normalized = validate_snapshot(
                snapshot,
                [item.bin_id for item in bins],
                config.operations.crane_lift_limit_kg,
                now_utc=decision_time,
                stale_after_hours=config.sensor.stale_after_hours,
                future_tolerance_minutes=config.sensor.future_tolerance_minutes,
            )
            history: dict[str, dict[str, Any]] = {}
            for index, item in enumerate(bins):
                row: dict[str, Any] = {}
                if np.isfinite(last_valid_fill[index]):
                    observed_at = (
                        simulation_epoch + timedelta(hours=float(last_valid_hour[index]))
                    ).isoformat()
                    row["fill"] = {
                        "value": float(last_valid_fill[index]),
                        "observed_at": observed_at,
                    }
                if np.isfinite(last_valid_weight[index]):
                    observed_at = (
                        simulation_epoch + timedelta(hours=float(last_valid_hour[index]))
                    ).isoformat()
                    row["weight"] = {
                        "value": float(last_valid_weight[index]),
                        "observed_at": observed_at,
                    }
                if row:
                    history[item.bin_id] = row
            decision_config = replace(
                config,
                operations=replace(
                    config.operations,
                    truck_capacity_kg=effective_truck_capacity,
                    max_daily_trips=remaining_trips,
                ),
            )
            optional_window_open = (
                hour - last_optional_dispatch_hour
                >= config.operations.smart_min_dispatch_gap_hours
            )
            dispatch_plan = build_dispatch_plan(
                normalized,
                bins_table,
                distance_matrix_m,
                decision_config,
                history,
                duration_matrix_s,
                optional_dispatch_allowed=optional_window_open,
            )
            record("inspection_events", len(dispatch_plan.review_bin_indices))
            record(
                "sensor_uncertainty_decisions",
                float(bool(dispatch_plan.review_bin_indices)),
            )
            record("unserved_required_bins", len(dispatch_plan.unserved_required_bin_indices))
            record(
                "capacity_constrained_decisions",
                float(bool(dispatch_plan.unserved_required_bin_indices)),
            )
            if not dispatch_plan.route_plan.routes:
                return
            plan = dispatch_plan.route_plan
            capacity_selected = list(plan.served_bin_indices)
            required_set = set(dispatch_plan.required_bin_indices)
            unserved_required = list(dispatch_plan.unserved_required_bin_indices)
            snapshot_rows = [
                row | {"selection_reason": row["reason"]}
                for row in dispatch_plan.audit_rows
            ]
            if plan.routes and any(
                np.isfinite(time_to_overflow[index])
                for index in plan.served_bin_indices
            ):
                record("forecast_driven_dispatches", 1)
            if optional_window_open:
                last_optional_dispatch_hour = hour

        record(
            "routing_fallbacks",
            float(
                "deterministic_fallback" in plan.solver_method
                or "value_infeasible" in plan.solver_method
            ),
        )
        route_event = {
            "hour": hour,
            "dispatch_minute": round(float(env.now), 3),
            "day": int(env.now // 1440) + 1,
            "policy": policy,
            "scenario": active_scenario.name,
            "distance_km": plan.distance_m / 1000.0,
            "trip_count": len(plan.routes),
            "route_solver_method": plan.solver_method,
            "routes": [
                ["DEPOT" if index == -1 else bins[index].bin_id for index in route]
                for route in plan.routes
            ],
            "route_bin_indices": plan.routes,
            "served_bins": [bins[index].bin_id for index in plan.served_bin_indices],
            "required_bins": [bins[index].bin_id for index in required_set],
            "unserved_required_bins": [bins[index].bin_id for index in unserved_required],
            "snapshot_rows": snapshot_rows,
            "predicted_growth_mean_pct": {
                bins[index].bin_id: float(predicted_mean[index]) for index in capacity_selected
            },
            "predicted_growth_upper_pct": {
                bins[index].bin_id: float(predicted_upper[index]) for index in capacity_selected
            },
            "timeline": [],
            "completed": False,
            "decision_drivers": {
                "forecast": bool(
                    policy == "smart"
                    and any(
                        np.isfinite(time_to_overflow[index])
                        for index in plan.served_bin_indices
                    )
                ),
                "route_capacity": bool(unserved_required),
                "sensor_uncertainty": bool(
                    policy == "smart"
                    and any(
                        row.get("collection_state") == "Inspection/data review required"
                        or "review" in str(row.get("reason", "")).lower()
                        for row in snapshot_rows
                    )
                ),
            },
        }
        route_events.append(route_event)
        truck_active = True
        env.process(execute_plan(plan, route_event))

    def waste_process():
        for hour in range(horizon_hours):
            unconstrained = hidden_mass + arrivals_kg[hour]
            crossed = (hidden_mass < capacities) & (unconstrained > capacities)
            spilled = np.maximum(unconstrained - capacities, 0)
            record("overflow_incidents", float(crossed.sum()))
            record("overflow_spilled_kg", float(spilled.sum()))
            if truck_active and route_events and np.any(spilled > 0):
                latest = route_events[-1]
                current_status = (
                    latest["timeline"][-1]["status"] if latest["timeline"] else "DISPATCHED"
                )
                timeline_event(
                    latest,
                    "OVERFLOW_DETECTED",
                    truck_status=current_status,
                    affected_bins=[
                        bins[index].bin_id
                        for index in np.flatnonzero(spilled > 0)
                    ],
                    spilled_kg=round(float(spilled.sum()), 3),
                )
            hidden_mass[:] = np.minimum(unconstrained, capacities)
            record("overflow_bin_hours", float(np.count_nonzero(hidden_mass >= capacities)))
            yield env.timeout(60)

    def observation_process():
        interval = config.waste.sensor_interval_hours
        sensor_index = 0
        for hour in range(0, horizon_hours, interval):
            target_minute = hour * 60
            if env.now < target_minute:
                yield env.timeout(target_minute - env.now)
            # Waste and observations can share an hour boundary. A zero-duration
            # event lets the already-scheduled hourly arrival run first without
            # advancing simulation time, so decisions see all data available at
            # that timestamp and never peek ahead.
            yield env.timeout(0)
            batch = observe_sensors(
                hidden_mass,
                capacities,
                sensor_scenario,
                sensor_index,
                hour,
                config,
            )
            should_decide = (
                policy == "fixed" and hour % 24 == config.operations.decision_hour
            ) or (
                policy == "smart"
            )
            if should_decide:
                dispatch(hour, batch)
            for index in range(len(bins)):
                observed = batch.fill_pct[index]
                if np.isfinite(observed):
                    feature_hour = (
                        float(demand_context.absolute_hours[hour])
                        if demand_context is not None
                        else float(hour)
                    )
                    observed_history[index].append((feature_hour, float(observed)))
                if (
                    batch.confidence_flag[index]
                    and np.isfinite(batch.fill_pct[index])
                ):
                    last_valid_fill[index] = batch.fill_pct[index]
                    last_valid_hour[index] = hour
                if batch.confidence_flag[index] and np.isfinite(batch.weight_kg[index]):
                    last_valid_weight[index] = batch.weight_kg[index]
                    if not np.isfinite(last_valid_hour[index]):
                        last_valid_hour[index] = hour
            sensor_index += 1

    env.process(waste_process())
    env.process(observation_process())
    env.run(until=horizon_minutes)

    def assembled(source: dict[str, float], suffix: str = "") -> dict[str, float]:
        stops = source["collection_stops"]
        trips = source["collection_trips"]
        driving = (
            source["base_driving_fuel_l"]
            + source["traffic_fuel_penalty_l"]
            + source["payload_fuel_penalty_l"]
        )
        total_fuel = driving + source["collection_idle_fuel_l"] + source["depot_idle_fuel_l"]
        return {
            f"overflow_incidents{suffix}": source["overflow_incidents"],
            f"overflow_bin_hours{suffix}": source["overflow_bin_hours"],
            f"overflow_spilled_kg{suffix}": source["overflow_spilled_kg"],
            f"distance_km{suffix}": source["distance_km"],
            f"travel_time_hours{suffix}": source["travel_time_hours"],
            f"service_time_hours{suffix}": source["service_time_hours"],
            f"depot_unloading_time_hours{suffix}": source["depot_unloading_time_hours"],
            f"turnaround_time_hours{suffix}": source["turnaround_time_hours"],
            f"idling_time_hours{suffix}": source["service_time_hours"] + source["depot_unloading_time_hours"],
            f"collection_trips{suffix}": trips,
            f"collection_stops{suffix}": stops,
            f"wasted_pickups{suffix}": source["wasted_pickups"],
            f"collected_kg{suffix}": source["collected_kg"],
            f"mean_fill_at_collection_pct{suffix}": source["sum_collection_fill_pct"] / stops if stops else 0.0,
            f"truck_utilization_pct{suffix}": 100.0 * source["collected_kg"] / (trips * effective_truck_capacity) if trips else 0.0,
            f"unserved_required_bins{suffix}": source["unserved_required_bins"],
            f"inspection_events{suffix}": source["inspection_events"],
            f"base_driving_fuel_l{suffix}": source["base_driving_fuel_l"],
            f"traffic_fuel_penalty_l{suffix}": source["traffic_fuel_penalty_l"],
            f"payload_fuel_penalty_l{suffix}": source["payload_fuel_penalty_l"],
            f"driving_fuel_l{suffix}": driving,
            f"collection_idle_fuel_l{suffix}": source["collection_idle_fuel_l"],
            f"depot_idle_fuel_l{suffix}": source["depot_idle_fuel_l"],
            f"fuel_l{suffix}": total_fuel,
            f"co2_kg{suffix}": total_fuel * config.operations.diesel_co2_kg_per_l,
            f"routing_fallbacks{suffix}": source["routing_fallbacks"],
            f"forecast_driven_dispatches{suffix}": source[
                "forecast_driven_dispatches"
            ],
            f"capacity_constrained_decisions{suffix}": source[
                "capacity_constrained_decisions"
            ],
            f"dispatch_limit_blocks{suffix}": source["dispatch_limit_blocks"],
            f"sensor_uncertainty_decisions{suffix}": source[
                "sensor_uncertainty_decisions"
            ],
        }

    metrics: dict[str, float | int | str] = {
        "policy": policy,
        "scenario": active_scenario.name,
        "replication": replication,
        **assembled(totals),
        **assembled(post_warmup, "_post_warmup"),
        "uncollected_kg_at_horizon": float(hidden_mass.sum()),
        "unfinished_trip_count": int(truck_active),
        "analysis_warmup_days": config.operations.analysis_warmup_days,
    }
    regime_rows = []
    for regime, values in regime_totals.items():
        assembled_values = assembled(values)
        regime_rows.append(
            {
                "scenario": active_scenario.name,
                "policy": policy,
                "replication": replication,
                "demand_regime": regime,
                **assembled_values,
            }
        )
    return PolicyResult(
        policy,
        replication,
        metrics,
        route_events,
        hidden_mass.copy(),
        regime_rows,
    )
