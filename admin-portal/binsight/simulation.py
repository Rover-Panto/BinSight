from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
import simpy

from .config import Config
from .district import BinSpec
from .forecast import ForecastBundle, make_feature_row
from .routing import RoutePlan, solve_routes


@dataclass
class PolicyResult:
    policy: str
    replication: int
    metrics: dict[str, float | int | str]
    route_events: list[dict]
    final_fill_kg: np.ndarray


def _greedy_proxy_distance_m(
    selected: list[int],
    demands_kg: np.ndarray,
    distance_matrix_m: np.ndarray,
    truck_capacity_kg: float,
    max_trips: int,
) -> float:
    """Fast deterministic distance proxy used only for optional-stop preselection."""
    unvisited = set(selected)
    total_distance = 0.0
    trips = 0
    while unvisited and trips < max_trips:
        current_location = 0
        load = 0.0
        served_this_trip = 0
        while True:
            feasible = [
                index
                for index in unvisited
                if load + float(demands_kg[index]) <= truck_capacity_kg + 1e-9
            ]
            if not feasible:
                break
            next_bin = min(
                feasible,
                key=lambda index: (
                    distance_matrix_m[current_location, index + 1],
                    index,
                ),
            )
            total_distance += float(distance_matrix_m[current_location, next_bin + 1])
            load += float(demands_kg[next_bin])
            current_location = next_bin + 1
            unvisited.remove(next_bin)
            served_this_trip += 1
        if served_this_trip == 0:
            return float("inf")
        total_distance += float(distance_matrix_m[current_location, 0])
        trips += 1
    return total_distance if not unvisited else float("inf")


def _time_to_overflow_hours(
    fill_pct: np.ndarray,
    predicted_growth_upper_pct: np.ndarray,
    forecast_horizon_hours: float,
) -> np.ndarray:
    """Convert a conservative horizon-growth forecast into an overflow deadline."""
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
    """Map sensor state and predicted deadline to the confirmed AI risk vocabulary."""
    levels = np.full(len(fill_pct), "low", dtype=object)
    medium = (
        (fill_pct >= config.operations.smart_include_current_trigger_pct)
        | (
            time_to_overflow_hours
            <= config.operations.smart_sibling_include_time_to_overflow_hours
        )
    )
    high = (
        (fill_pct >= config.operations.smart_dispatch_current_trigger_pct)
        | (
            time_to_overflow_hours
            <= config.operations.smart_dispatch_time_to_overflow_hours
        )
    )
    critical = (
        (fill_pct >= config.operations.smart_emergency_current_trigger_pct)
        | (
            time_to_overflow_hours
            <= config.operations.smart_emergency_time_to_overflow_hours
        )
    )
    levels[medium] = "medium"
    levels[high] = "high"
    levels[critical] = "critical"
    return levels


def _incremental_proxy_distance_m(
    selected: list[int],
    candidate: int,
    demands_kg: np.ndarray,
    distance_matrix_m: np.ndarray,
    truck_capacity_kg: float,
    max_trips: int,
) -> tuple[float, float]:
    """Return proposal distance and added distance for one optional collection."""
    base = _greedy_proxy_distance_m(
        selected,
        demands_kg,
        distance_matrix_m,
        truck_capacity_kg,
        max_trips,
    )
    proposal = _greedy_proxy_distance_m(
        selected + [candidate],
        demands_kg,
        distance_matrix_m,
        truck_capacity_kg,
        max_trips,
    )
    return proposal, max(0.0, proposal - base)


def run_policy(
    policy: str,
    replication: int,
    bins: list[BinSpec],
    config: Config,
    distance_matrix_m: np.ndarray,
    arrivals_kg: np.ndarray,
    sensor_seed: int,
    forecaster: ForecastBundle | None = None,
) -> PolicyResult:
    if policy not in {"fixed", "smart"}:
        raise ValueError("policy must be 'fixed' or 'smart'")
    if policy == "smart" and forecaster is None:
        raise ValueError("smart policy requires a trained forecaster")
    horizon_hours = config.operations.horizon_days * 24
    if arrivals_kg.shape != (horizon_hours, len(bins)):
        raise ValueError("arrivals_kg has the wrong shape")

    env = simpy.Environment()
    capacities = np.array([item.capacity_kg for item in bins], dtype=float)
    fill = np.zeros(len(bins), dtype=float)
    previous_fill = fill.copy()
    observed_history: list[list[float]] = [[] for _ in bins]
    rng = np.random.default_rng(sensor_seed)
    # Common sensor noise is generated in advance, independent of policy event ordering.
    sensor_noise = rng.normal(
        0,
        config.waste.sensor_noise_sd_pct,
        size=(horizon_hours // config.waste.sensor_interval_hours + 1, len(bins)),
    )
    route_events: list[dict] = []
    last_dispatch_hour = -10_000
    totals = {
        "overflow_incidents": 0,
        "overflow_bin_hours": 0.0,
        "overflow_spilled_kg": 0.0,
        "distance_km": 0.0,
        "collection_trips": 0,
        "collection_stops": 0,
        "wasted_pickups": 0,
        "collected_kg": 0.0,
        "sum_collection_fill_pct": 0.0,
        "routing_fallbacks": 0,
    }

    def dispatch(hour: int, current_observed: np.ndarray) -> None:
        nonlocal last_dispatch_hour
        fill_pct = 100.0 * fill / capacities
        if policy == "fixed":
            day = hour // 24
            if day % config.operations.fixed_interval_days != 0:
                return
            selected = list(range(len(bins)))
            priority_scores = np.ones(len(bins), dtype=float)
            predicted_mean = np.zeros(len(bins), dtype=float)
            predicted_upper = np.zeros(len(bins), dtype=float)
            time_to_overflow = np.full(len(bins), np.inf, dtype=float)
            risk_levels = np.full(len(bins), "fixed", dtype=object)
            emergency: list[int] = []
        else:
            feature_rows = [
                make_feature_row(item, current_observed[index], observed_history[index], hour)
                for index, item in enumerate(bins)
            ]
            predicted_mean, predicted_upper = forecaster.predict(pd.DataFrame(feature_rows))
            predicted_fill_upper = fill_pct + predicted_upper
            time_to_overflow = _time_to_overflow_hours(
                fill_pct,
                predicted_upper,
                config.operations.forecast_horizon_hours,
            )
            risk_levels = _risk_levels(fill_pct, time_to_overflow, config)
            priority_scores = (
                0.55 * np.clip(predicted_fill_upper / 100.0, 0, 2)
                + 0.35 * np.clip(fill_pct / 100.0, 0, 2)
                + 0.10 * np.clip(predicted_mean / 100.0, 0, 1)
            )
            critical = [
                index
                for index in range(len(bins))
                if risk_levels[index] in {"high", "critical"}
            ]
            if not critical:
                return
            emergency = [
                index for index in critical if risk_levels[index] == "critical"
            ]
            if (
                hour - last_dispatch_hour < config.operations.smart_min_dispatch_gap_hours
                and not emergency
            ):
                return
            candidates = [
                index
                for index in range(len(bins))
                if risk_levels[index] == "medium"
            ]
            candidates = sorted(set(candidates) | set(critical))
            daily_capacity = config.operations.truck_capacity_kg * config.operations.max_daily_trips
            critical_ranked = sorted(
                critical,
                key=lambda index: (
                    risk_levels[index] != "critical",
                    time_to_overflow[index],
                    -fill_pct[index],
                    bins[index].bin_id,
                ),
            )
            selected = []
            load = 0.0
            for index in critical_ranked:
                demand = max(0.0, fill[index])
                if load + demand <= daily_capacity + 1e-9:
                    selected.append(index)
                    load += demand

            # A truck already visiting a site can collect useful sibling bins with
            # no extra road travel. Add those before considering other optional sites.
            selected_sites = {bins[index].service_index for index in selected}
            sibling_ranked = sorted(
                (
                    index
                    for index in range(len(bins))
                    if index not in selected
                    and bins[index].service_index in selected_sites
                    and (
                        fill_pct[index]
                        >= config.operations.smart_sibling_include_current_pct
                        or time_to_overflow[index]
                        <= config.operations.smart_sibling_include_time_to_overflow_hours
                    )
                ),
                key=lambda index: (
                    time_to_overflow[index],
                    -fill_pct[index],
                    bins[index].bin_id,
                ),
            )
            for index in sibling_ranked:
                demand = max(0.0, fill[index])
                if load + demand <= daily_capacity + 1e-9:
                    selected.append(index)
                    load += demand

            optional = set(candidates) - set(selected)
            optional_ranked = sorted(
                optional,
                key=lambda index: (
                    time_to_overflow[index],
                    -priority_scores[index],
                    bins[index].bin_id,
                ),
            )
            budget_m = config.operations.smart_max_dispatch_distance_km * 1000.0
            increment_limit_m = config.operations.smart_optional_max_increment_km * 1000.0
            for index in optional_ranked:
                demand = max(0.0, fill[index])
                if load + demand > daily_capacity + 1e-9:
                    continue
                proxy_distance, added_distance = _incremental_proxy_distance_m(
                    selected,
                    index,
                    fill,
                    distance_matrix_m,
                    config.operations.truck_capacity_kg,
                    config.operations.max_daily_trips,
                )
                if proxy_distance <= budget_m and added_distance <= increment_limit_m:
                    selected.append(index)
                    load += demand
        if not selected:
            return

        plan: RoutePlan = solve_routes(
            selected,
            fill,
            distance_matrix_m,
            config.operations.truck_capacity_kg,
            config.operations.max_daily_trips,
            config.operations.route_solver_milliseconds,
        )
        totals["routing_fallbacks"] += int(plan.solver_method == "deterministic_fallback")
        before_pct = 100.0 * fill / capacities
        served = plan.served_bin_indices
        collected = float(fill[served].sum()) if served else 0.0
        wasted = int(
            sum(before_pct[index] < config.operations.wasted_pickup_threshold_pct for index in served)
        )
        totals["distance_km"] += plan.distance_m / 1000.0
        totals["collection_trips"] += len(plan.routes)
        totals["collection_stops"] += len(served)
        totals["wasted_pickups"] += wasted
        totals["collected_kg"] += collected
        totals["sum_collection_fill_pct"] += float(before_pct[served].sum()) if served else 0.0
        fill[served] = 0.0
        route_events.append(
            {
                "hour": hour,
                "day": hour // 24 + 1,
                "policy": policy,
                "distance_km": plan.distance_m / 1000.0,
                "trip_count": len(plan.routes),
                "route_solver_method": plan.solver_method,
                "distance_budget_km": (
                    config.operations.smart_max_dispatch_distance_km
                    if policy == "smart"
                    else None
                ),
                "distance_budget_exceeded_by_critical_route": (
                    bool(
                        policy == "smart"
                        and plan.distance_m
                        > config.operations.smart_max_dispatch_distance_km * 1000
                    )
                ),
                "routes": [
                    ["DEPOT" if index == -1 else bins[index].bin_id for index in route]
                    for route in plan.routes
                ],
                "route_bin_indices": plan.routes,
                "served_bins": [bins[index].bin_id for index in served],
                "collected_kg": collected,
                "mean_fill_at_collection_pct": (
                    float(before_pct[served].mean()) if served else 0.0
                ),
                "priority_scores": {
                    bins[index].bin_id: float(priority_scores[index]) for index in selected
                },
                "predicted_growth_mean_pct": {
                    bins[index].bin_id: float(predicted_mean[index]) for index in selected
                },
                "predicted_growth_upper_pct": {
                    bins[index].bin_id: float(predicted_upper[index]) for index in selected
                },
                "time_to_overflow_hours": {
                    bins[index].bin_id: (
                        float(time_to_overflow[index])
                        if np.isfinite(time_to_overflow[index])
                        else None
                    )
                    for index in selected
                },
                "risk_level": {
                    bins[index].bin_id: str(risk_levels[index]) for index in selected
                },
                "emergency_gap_override": bool(
                    policy == "smart"
                    and emergency
                    and hour - last_dispatch_hour
                    < config.operations.smart_min_dispatch_gap_hours
                ),
            }
        )
        last_dispatch_hour = hour

    def clock():
        nonlocal previous_fill
        sensor_index = 0
        for hour in range(horizon_hours):
            previous_fill = fill.copy()
            unconstrained_fill = fill + arrivals_kg[hour]
            crossed = (previous_fill < capacities) & (unconstrained_fill > capacities)
            totals["overflow_incidents"] += int(crossed.sum())
            totals["overflow_spilled_kg"] += float(
                np.maximum(unconstrained_fill - capacities, 0).sum()
            )
            fill[:] = np.minimum(unconstrained_fill, capacities)
            if hour % config.waste.sensor_interval_hours == 0:
                observed = np.maximum(0.0, 100.0 * fill / capacities + sensor_noise[sensor_index])
                should_decide = (
                    policy == "fixed" and hour % 24 == config.operations.decision_hour
                ) or (
                    policy == "smart" and hour % 24 in config.operations.smart_decision_hours
                )
                if should_decide:
                    dispatch(hour, observed)
                for index in range(len(bins)):
                    observed_history[index].append(float(observed[index]))
                sensor_index += 1
            totals["overflow_bin_hours"] += float(np.count_nonzero(fill >= capacities))
            yield env.timeout(1)

    env.process(clock())
    env.run(until=horizon_hours)
    distance_km = float(totals["distance_km"])
    trips = int(totals["collection_trips"])
    stops = int(totals["collection_stops"])
    fuel_l = distance_km * config.operations.fuel_l_per_km
    collected_kg = float(totals["collected_kg"])
    metrics: dict[str, float | int | str] = {
        "policy": policy,
        "replication": replication,
        "overflow_incidents": int(totals["overflow_incidents"]),
        "overflow_bin_hours": float(totals["overflow_bin_hours"]),
        "overflow_spilled_kg": float(totals["overflow_spilled_kg"]),
        "distance_km": distance_km,
        "collection_trips": trips,
        "collection_stops": stops,
        "wasted_pickups": int(totals["wasted_pickups"]),
        "collected_kg": collected_kg,
        "mean_fill_at_collection_pct": (
            float(totals["sum_collection_fill_pct"]) / stops if stops else 0.0
        ),
        "truck_utilization_pct": (
            100.0 * collected_kg / (trips * config.operations.truck_capacity_kg) if trips else 0.0
        ),
        "fuel_l": fuel_l,
        "co2_kg": fuel_l * config.operations.diesel_co2_kg_per_l,
        "uncollected_kg_at_horizon": float(fill.sum()),
        "routing_fallbacks": int(totals["routing_fallbacks"]),
    }
    return PolicyResult(policy, replication, metrics, route_events, fill.copy())
