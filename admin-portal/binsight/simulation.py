from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
import simpy

from .config import Config
from .district import BinSpec
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
    name: str = "base"
    demand_multiplier: float = 1.0
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
        | (time_to_overflow_hours <= config.operations.smart_emergency_time_to_overflow_hours)
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
    expected_shape = (len(bins) + 1, len(bins) + 1)
    if distance_matrix_m.shape != expected_shape or duration_matrix_s.shape != expected_shape:
        raise ValueError("Road distance and duration matrices must contain depot plus every bin")

    env = simpy.Environment()
    capacities = np.array([item.capacity_kg for item in bins], dtype=float)
    hidden_mass = np.zeros(len(bins), dtype=float)
    observed_history: list[list[float]] = [[] for _ in bins]
    last_valid_fill = np.full(len(bins), np.nan, dtype=float)
    last_valid_weight = np.full(len(bins), np.nan, dtype=float)
    last_valid_hour = np.full(len(bins), np.nan, dtype=float)
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
    last_dispatch_hour = -10_000.0
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
    )
    totals = {name: 0.0 for name in metric_names}
    post_warmup = {name: 0.0 for name in metric_names}

    def record(name: str, value: float, at_minute: float | None = None) -> None:
        moment = env.now if at_minute is None else at_minute
        totals[name] += float(value)
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
                    upper_weight[index] = max(
                        last_valid_weight[index], aged_fill / 100.0 * capacities[index]
                    )
                else:
                    upper_fill[index] = max(upper_fill[index], aged_fill)
                    upper_weight[index] = max(upper_weight[index], last_valid_weight[index])
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

    def choose_smart_bins(
        hour: int,
        batch,
        upper_fill: np.ndarray,
        route_weights: np.ndarray,
        remaining_trips: int,
    ):
        model_fill = batch.fill_pct.copy()
        model_weight = batch.weight_kg.copy()
        for index in range(len(bins)):
            if not np.isfinite(model_fill[index]):
                model_fill[index] = (
                    observed_history[index][-1] if observed_history[index] else upper_fill[index]
                )
            if not np.isfinite(model_weight[index]):
                model_weight[index] = model_fill[index] / 100.0 * capacities[index]
        feature_rows = [
            make_feature_row(
                item,
                float(model_fill[index]),
                float(model_weight[index]),
                bool(batch.confidence_flag[index]),
                observed_history[index],
                hour,
            )
            for index, item in enumerate(bins)
        ]
        predicted_mean, predicted_upper = forecaster.predict(pd.DataFrame(feature_rows))
        time_to_overflow = _time_to_overflow_hours(
            upper_fill,
            predicted_upper,
            config.operations.forecast_horizon_hours,
        )
        risk = _risk_levels(upper_fill, time_to_overflow, config)
        # A low-confidence forecast cannot by itself command a truck. Preserve
        # only the conservative emergency current/aged-fill trigger; route the
        # remaining uncertainty to inspection rather than fabricating urgency.
        for index in range(len(bins)):
            if batch.confidence_flag[index]:
                continue
            if (
                upper_fill[index]
                >= config.operations.smart_emergency_current_trigger_pct
            ):
                risk[index] = "critical"
            else:
                risk[index] = "low"
        required = [index for index in range(len(bins)) if risk[index] in {"high", "critical"}]
        required.sort(
            key=lambda index: (
                risk[index] != "critical",
                time_to_overflow[index],
                -upper_fill[index],
                bins[index].bin_id,
            )
        )
        selected, _ = select_capacity_feasible(
            required,
            route_weights,
            effective_truck_capacity,
            remaining_trips,
        )

        selected_sites = {bins[index].service_index for index in selected}
        siblings = sorted(
            (
                index
                for index in range(len(bins))
                if index not in selected
                and bins[index].service_index in selected_sites
                and (
                    (
                        batch.confidence_flag[index]
                        and (
                            upper_fill[index]
                            >= config.operations.smart_sibling_include_current_pct
                            or time_to_overflow[index]
                            <= config.operations.smart_sibling_include_time_to_overflow_hours
                        )
                    )
                    or (
                        not batch.confidence_flag[index]
                        and risk[index] == "critical"
                    )
                )
            ),
            key=lambda index: (time_to_overflow[index], -upper_fill[index], bins[index].bin_id),
        )
        selected_siblings: list[int] = []
        for index in siblings:
            proposal, rejected = select_capacity_feasible(
                selected + [index],
                route_weights,
                effective_truck_capacity,
                remaining_trips,
            )
            if not rejected:
                selected = proposal
                selected_siblings.append(index)

        optional_candidates = sorted(
            (
                index
                for index in range(len(bins))
                if index not in selected
                and batch.confidence_flag[index]
                and risk[index] == "medium"
            ),
            key=lambda index: (time_to_overflow[index], -upper_fill[index], bins[index].bin_id),
        )
        selected_optional: list[int] = []
        budget_m = config.operations.smart_max_dispatch_distance_km * 1000.0
        increment_limit_m = config.operations.smart_optional_max_increment_km * 1000.0
        if required:
            for index in optional_candidates:
                capacity_proposal, rejected = select_capacity_feasible(
                    selected + [index],
                    route_weights,
                    effective_truck_capacity,
                    remaining_trips,
                )
                if rejected:
                    continue
                proposal, added = incremental_proxy_distance_m(
                    selected,
                    index,
                    route_weights,
                    distance_matrix_m,
                    effective_truck_capacity,
                    remaining_trips,
                )
                if proposal <= budget_m and added <= increment_limit_m:
                    selected = capacity_proposal
                    selected_optional.append(index)
        return (
            selected,
            required,
            selected_siblings,
            selected_optional,
            np.asarray(predicted_mean),
            np.asarray(predicted_upper),
            time_to_overflow,
            risk,
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
        nonlocal last_dispatch_hour, truck_active
        decision_day = int(env.now // 1440)
        remaining_trips = config.operations.max_daily_trips - trips_by_day.get(decision_day, 0)
        if truck_active or remaining_trips <= 0:
            return
        if policy == "fixed" and not fixed_service_due(hour, config):
            return
        upper_fill, upper_weight, review_reasons = conservative_observations(batch, hour)
        review_indices = [index for index, reasons in enumerate(review_reasons) if reasons]
        record("inspection_events", len(review_indices))
        route_weights = np.where(
            np.isfinite(upper_weight), np.minimum(upper_weight, capacities), 0.0
        )

        predicted_mean = np.zeros(len(bins), dtype=float)
        predicted_upper = np.zeros(len(bins), dtype=float)
        time_to_overflow = np.full(len(bins), np.inf, dtype=float)
        risk = np.full(len(bins), "fixed", dtype=object)
        required: list[int] = []
        siblings: list[int] = []
        optional: list[int] = []
        if policy == "fixed":
            selected = list(range(len(bins)))
        else:
            (
                selected,
                required,
                siblings,
                optional,
                predicted_mean,
                predicted_upper,
                time_to_overflow,
                risk,
            ) = choose_smart_bins(hour, batch, upper_fill, route_weights, remaining_trips)
            emergency = [
                index
                for index in required
                if risk[index] == "critical"
            ]
            if not required:
                return
            if (
                hour - last_dispatch_hour < config.operations.smart_min_dispatch_gap_hours
                and not emergency
            ):
                return

        required_set = set(required if policy == "smart" else selected)
        capacity_selected, rejected = select_capacity_feasible(
            selected,
            route_weights,
            effective_truck_capacity,
            remaining_trips,
        )
        unserved_required = sorted(
            index
            for index in required_set
            if index not in capacity_selected or index in rejected
        )
        record("unserved_required_bins", len(unserved_required))
        if not capacity_selected:
            return
        plan = solve_routes(
            capacity_selected,
            route_weights,
            distance_matrix_m,
            effective_truck_capacity,
            remaining_trips,
            config.operations.route_solver_milliseconds,
        )
        record("routing_fallbacks", float(plan.solver_method == "deterministic_fallback"))
        served = set(plan.served_bin_indices)
        required_set = set(required if policy == "smart" else capacity_selected)
        sibling_set = set(siblings)
        optional_set = set(optional)
        snapshot_rows = []
        for index, item in enumerate(bins):
            if index in required_set and index in served:
                selection = "Required"
            elif index in unserved_required:
                selection = "Unserved required"
            elif review_reasons[index] and index not in served:
                selection = "Inspection required"
            elif index in sibling_set and index in served:
                selection = "Co-located sibling"
            elif index in optional_set and index in served:
                selection = "Efficient nearby pickup"
            else:
                selection = "Wait"
            reasons = list(review_reasons[index])
            if risk[index] in {"high", "critical"}:
                reasons.append(f"{risk[index]} risk")
            if (
                np.isfinite(time_to_overflow[index])
                and time_to_overflow[index]
                <= config.operations.smart_dispatch_time_to_overflow_hours
            ):
                reasons.append(f"overflow in {time_to_overflow[index]:.1f}h")
            if upper_fill[index] >= config.operations.smart_dispatch_current_trigger_pct:
                reasons.append(f"upper fill {upper_fill[index]:.1f}%")
            if not reasons:
                reasons.append(selection.lower())
            snapshot_rows.append(
                {
                    "bin_id": item.bin_id,
                    "site_id": item.site_id,
                    "fill_pct": _json_number(batch.fill_pct[index]),
                    "weight_kg": _json_number(batch.weight_kg[index]),
                    "time_to_overflow_hours": _json_number(time_to_overflow[index]),
                    "risk_level": str(risk[index]),
                    "confidence_flag": bool(batch.confidence_flag[index]),
                    "conservative_upper_fill_pct": float(upper_fill[index]),
                    "selection": selection,
                    "selection_reason": ", ".join(reasons),
                    "collection_state": selection,
                }
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
        }
        route_events.append(route_event)
        truck_active = True
        last_dispatch_hour = hour
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
                policy == "smart" and hour % 24 in config.operations.smart_decision_hours
            )
            if should_decide:
                dispatch(hour, batch)
            for index in range(len(bins)):
                observed = batch.fill_pct[index]
                if np.isfinite(observed):
                    observed_history[index].append(float(observed))
                if (
                    batch.confidence_flag[index]
                    and np.isfinite(batch.fill_pct[index])
                    and np.isfinite(batch.weight_kg[index])
                ):
                    last_valid_fill[index] = batch.fill_pct[index]
                    last_valid_weight[index] = batch.weight_kg[index]
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
    return PolicyResult(policy, replication, metrics, route_events, hidden_mass.copy())
