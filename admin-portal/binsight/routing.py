from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
from ortools.constraint_solver import pywrapcp, routing_enums_pb2


@dataclass(frozen=True)
class RoutePlan:
    routes: list[list[int]]
    distance_m: int
    served_bin_indices: list[int]
    solver_method: str
    dropped_bin_indices: list[int] = field(default_factory=list)
    route_duration_s: list[float] = field(default_factory=list)
    route_loads_kg: list[float] = field(default_factory=list)
    route_volumes_m3: list[float] = field(default_factory=list)
    objective_cost_m_equivalent: float = 0.0
    operating_cost_m_equivalent: float = 0.0
    avoided_loss_value_m_equivalent: float = 0.0
    net_value_m_equivalent: float = 0.0
    dispatch_reason: str = "no_candidate"


def _routing_demand_kg(value: float) -> int:
    """Match the integer, upward-rounded demand consumed by OR-Tools."""
    return max(0, int(math.ceil(float(value))))


def select_capacity_feasible(
    candidates: list[int],
    demands_kg: np.ndarray,
    truck_capacity_kg: float,
    max_trips: int,
) -> tuple[list[int], list[int]]:
    """Preserve candidate priority while guaranteeing an explicit trip packing."""
    if truck_capacity_kg <= 0 or max_trips < 1:
        raise ValueError("Truck capacity and trip count must be positive")
    integer_capacity = int(math.floor(truck_capacity_kg))
    loads = [0] * max_trips
    selected: list[int] = []
    unserved: list[int] = []
    for index in dict.fromkeys(int(value) for value in candidates):
        demand = _routing_demand_kg(demands_kg[index])
        feasible = [
            vehicle
            for vehicle in range(max_trips)
            if loads[vehicle] + demand <= integer_capacity
        ]
        if not feasible:
            unserved.append(index)
            continue
        vehicle = min(
            feasible,
            key=lambda item: (integer_capacity - loads[item] - demand, item),
        )
        loads[vehicle] += demand
        selected.append(index)
    return selected, unserved


def select_dual_capacity_feasible(
    candidates: list[int],
    demands_kg: np.ndarray,
    demands_m3: np.ndarray,
    truck_capacity_kg: float,
    truck_capacity_m3: float,
    max_trips: int,
) -> tuple[list[int], list[int]]:
    """Priority-preserving packing across both mass and compacted volume."""
    if truck_capacity_kg <= 0 or truck_capacity_m3 <= 0 or max_trips < 1:
        raise ValueError("Truck mass, volume and trip count must be positive")
    mass_capacity = int(math.floor(truck_capacity_kg))
    volume_capacity = int(math.floor(truck_capacity_m3 * 1000))
    mass_loads = [0] * max_trips
    volume_loads = [0] * max_trips
    selected: list[int] = []
    unserved: list[int] = []
    for index in dict.fromkeys(int(value) for value in candidates):
        mass = _routing_demand_kg(demands_kg[index])
        volume = max(0, int(math.ceil(float(demands_m3[index]) * 1000)))
        feasible = [
            vehicle
            for vehicle in range(max_trips)
            if mass_loads[vehicle] + mass <= mass_capacity
            and volume_loads[vehicle] + volume <= volume_capacity
        ]
        if not feasible:
            unserved.append(index)
            continue
        vehicle = min(
            feasible,
            key=lambda item: (
                (mass_capacity - mass_loads[item] - mass) / max(mass_capacity, 1)
                + (volume_capacity - volume_loads[item] - volume) / max(volume_capacity, 1),
                item,
            ),
        )
        mass_loads[vehicle] += mass
        volume_loads[vehicle] += volume
        selected.append(index)
    return selected, unserved


def _exact_capacity_buckets(
    selected: list[int],
    demands_kg: np.ndarray,
    truck_capacity_kg: float,
    max_trips: int,
) -> list[list[int]] | None:
    ordered = sorted(selected, key=lambda index: (-float(demands_kg[index]), index))
    buckets: list[list[int]] = [[] for _ in range(max_trips)]
    integer_capacity = int(math.floor(truck_capacity_kg))
    loads = [0] * max_trips

    def assign(position: int) -> bool:
        if position >= len(ordered):
            return True
        index = ordered[position]
        demand = _routing_demand_kg(demands_kg[index])
        tried_loads: set[int] = set()
        vehicles = sorted(
            range(max_trips),
            key=lambda vehicle: (integer_capacity - loads[vehicle] - demand, vehicle),
        )
        for vehicle in vehicles:
            if loads[vehicle] in tried_loads:
                continue
            tried_loads.add(loads[vehicle])
            if loads[vehicle] + demand > integer_capacity:
                continue
            buckets[vehicle].append(index)
            loads[vehicle] += demand
            if assign(position + 1):
                return True
            loads[vehicle] -= demand
            buckets[vehicle].pop()
        return False

    return buckets if assign(0) else None


def greedy_proxy_distance_m(
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
        load = 0
        served_this_trip = 0
        while True:
            feasible = [
                index
                for index in unvisited
                if load + _routing_demand_kg(demands_kg[index])
                <= int(math.floor(truck_capacity_kg))
            ]
            if not feasible:
                break
            next_bin = min(
                feasible,
                key=lambda index: (distance_matrix_m[current_location, index + 1], index),
            )
            total_distance += float(distance_matrix_m[current_location, next_bin + 1])
            load += _routing_demand_kg(demands_kg[next_bin])
            current_location = next_bin + 1
            unvisited.remove(next_bin)
            served_this_trip += 1
        if served_this_trip == 0:
            return float("inf")
        total_distance += float(distance_matrix_m[current_location, 0])
        trips += 1
    return total_distance if not unvisited else float("inf")


def incremental_proxy_distance_m(
    selected: list[int],
    candidate: int,
    demands_kg: np.ndarray,
    distance_matrix_m: np.ndarray,
    truck_capacity_kg: float,
    max_trips: int,
) -> tuple[float, float]:
    """Return proposal distance and added distance for one optional collection."""
    base = greedy_proxy_distance_m(
        selected, demands_kg, distance_matrix_m, truck_capacity_kg, max_trips
    )
    proposal = greedy_proxy_distance_m(
        selected + [candidate],
        demands_kg,
        distance_matrix_m,
        truck_capacity_kg,
        max_trips,
    )
    return proposal, max(0.0, proposal - base)


def _fallback_routes(
    selected: list[int],
    demands_kg: np.ndarray,
    full_matrix_m: np.ndarray,
    truck_capacity_kg: float,
    max_trips: int,
) -> RoutePlan:
    """Deterministic capacity-feasible construction for OR-Tools timeouts."""
    buckets = _exact_capacity_buckets(
        selected, demands_kg, truck_capacity_kg, max_trips
    )
    if buckets is None:
        raise RuntimeError("Deterministic fallback could not pack the selected waste")

    routes: list[list[int]] = []
    served: list[int] = []
    total_distance = 0
    for bucket in buckets:
        if not bucket:
            continue
        unvisited = set(bucket)
        current_location = 0
        route = [-1]
        while unvisited:
            next_bin = min(
                unvisited,
                key=lambda index: (full_matrix_m[current_location, index + 1], index),
            )
            total_distance += int(full_matrix_m[current_location, next_bin + 1])
            route.append(next_bin)
            served.append(next_bin)
            current_location = next_bin + 1
            unvisited.remove(next_bin)
        total_distance += int(full_matrix_m[current_location, 0])
        route.append(-1)
        routes.append(route)
    return RoutePlan(routes, total_distance, served, "deterministic_fallback")


def solve_routes(
    selected_bin_indices: list[int],
    demands_kg: np.ndarray,
    full_matrix_m: np.ndarray,
    truck_capacity_kg: float,
    max_trips: int,
    solver_milliseconds: int,
) -> RoutePlan:
    """Solve capacity-constrained tours. Full matrix order is depot, BIN-01, BIN-02, ..."""
    selected = list(dict.fromkeys(int(index) for index in selected_bin_indices))
    if not selected:
        return RoutePlan(routes=[], distance_m=0, served_bin_indices=[], solver_method="none")
    locations = [0] + [index + 1 for index in selected]
    matrix = full_matrix_m[np.ix_(locations, locations)].astype(np.int64)
    demand_values = [0] + [_routing_demand_kg(demands_kg[index]) for index in selected]
    vehicle_count = max_trips
    if sum(demand_values) > vehicle_count * truck_capacity_kg:
        raise ValueError("Selected waste exceeds configured daily trip capacity")

    manager = pywrapcp.RoutingIndexManager(len(locations), vehicle_count, 0)
    routing = pywrapcp.RoutingModel(manager)

    def distance_callback(from_index: int, to_index: int) -> int:
        return int(matrix[manager.IndexToNode(from_index), manager.IndexToNode(to_index)])

    transit_index = routing.RegisterTransitCallback(distance_callback)
    routing.SetArcCostEvaluatorOfAllVehicles(transit_index)
    # Expose every allowed tour for feasibility, but penalize depot departures so
    # the solution consolidates loads and normally uses the minimum practical count.
    routing.SetFixedCostOfAllVehicles(15_000)

    def demand_callback(from_index: int) -> int:
        return int(demand_values[manager.IndexToNode(from_index)])

    demand_index = routing.RegisterUnaryTransitCallback(demand_callback)
    routing.AddDimensionWithVehicleCapacity(
        demand_index,
        0,
        [int(truck_capacity_kg)] * vehicle_count,
        True,
        "Capacity",
    )
    search = pywrapcp.DefaultRoutingSearchParameters()
    search.first_solution_strategy = (
        routing_enums_pb2.FirstSolutionStrategy.PARALLEL_CHEAPEST_INSERTION
    )
    search.local_search_metaheuristic = routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
    search.time_limit.FromMilliseconds(max(25, int(solver_milliseconds)))
    search.solution_limit = 50
    solution = routing.SolveWithParameters(search)
    if solution is None:
        return _fallback_routes(
            selected,
            demands_kg,
            full_matrix_m,
            truck_capacity_kg,
            max_trips,
        )

    routes: list[list[int]] = []
    total_distance = 0
    served: list[int] = []
    for vehicle in range(vehicle_count):
        index = routing.Start(vehicle)
        route = [-1]  # -1 denotes the depot.
        distance = 0
        while not routing.IsEnd(index):
            next_index = solution.Value(routing.NextVar(index))
            next_location = manager.IndexToNode(next_index)
            distance += distance_callback(index, next_index)
            if next_location != 0:
                bin_index = selected[next_location - 1]
                route.append(bin_index)
                served.append(bin_index)
            index = next_index
        route.append(-1)
        if len(route) > 2:
            routes.append(route)
            total_distance += distance
    return RoutePlan(
        routes=routes,
        distance_m=total_distance,
        served_bin_indices=served,
        solver_method="ortools",
    )


def solve_value_routes(
    candidate_bin_indices: list[int],
    mandatory_bin_indices: list[int],
    demands_kg: np.ndarray,
    demands_m3: np.ndarray,
    full_distance_matrix_m: np.ndarray,
    full_duration_matrix_s: np.ndarray,
    skip_penalties_m_equivalent: np.ndarray,
    truck_capacity_kg: float,
    truck_capacity_m3: float,
    max_trips: int,
    service_seconds_per_bin: float,
    max_route_duration_seconds: float,
    fixed_trip_cost_m_equivalent: int,
    travel_time_cost_m_per_minute: float,
    service_cost_m_per_minute: float,
    additional_service_cost_m_equivalent: np.ndarray,
    solver_milliseconds: int,
    *,
    minimum_net_value_m_equivalent: float = 0.0,
) -> RoutePlan:
    """Jointly choose optional pickups and route mandatory safety stops.

    Optional-node skip penalties represent the expected loss avoided by serving
    the bin now. The solver therefore compares that benefit with fixed trip,
    road-distance, travel-time and per-bin service costs instead of forcing every
    threshold candidate onto a route.
    """
    candidates = list(dict.fromkeys(int(value) for value in candidate_bin_indices))
    mandatory = set(int(value) for value in mandatory_bin_indices)
    if not mandatory.issubset(candidates):
        raise ValueError("Every mandatory bin must also be a route candidate")
    if not candidates:
        return RoutePlan([], 0, [], "value_none", dispatch_reason="no_candidate")
    if max_trips < 1 or truck_capacity_kg <= 0 or truck_capacity_m3 <= 0:
        raise ValueError("Trip count and truck capacities must be positive")
    node_count = len(demands_kg)
    expected_shape = (node_count + 1, node_count + 1)
    if full_distance_matrix_m.shape != expected_shape:
        raise ValueError("Distance matrix must contain depot plus every bin")
    if full_duration_matrix_s.shape != expected_shape:
        raise ValueError("Duration matrix must contain depot plus every bin")
    if (
        len(demands_m3) != node_count
        or len(skip_penalties_m_equivalent) != node_count
        or len(additional_service_cost_m_equivalent) != node_count
    ):
        raise ValueError("Demand and penalty arrays must match the bin count")
    if any(_routing_demand_kg(demands_kg[index]) > int(math.floor(truck_capacity_kg)) for index in mandatory):
        raise ValueError("A mandatory pickup exceeds the truck mass capacity")
    if any(float(demands_m3[index]) > truck_capacity_m3 + 1e-9 for index in mandatory):
        raise ValueError("A mandatory pickup exceeds the truck compacted-volume capacity")

    locations = [0] + [index + 1 for index in candidates]
    distance = full_distance_matrix_m[np.ix_(locations, locations)].astype(np.int64)
    duration = full_duration_matrix_s[np.ix_(locations, locations)].astype(float)
    mass = [0] + [_routing_demand_kg(demands_kg[index]) for index in candidates]
    volume_litres = [0] + [max(0, int(math.ceil(float(demands_m3[index]) * 1000))) for index in candidates]

    manager = pywrapcp.RoutingIndexManager(len(locations), max_trips, 0)
    routing = pywrapcp.RoutingModel(manager)

    def operating_cost_callback(from_index: int, to_index: int) -> int:
        from_node = manager.IndexToNode(from_index)
        to_node = manager.IndexToNode(to_index)
        travel_distance = int(distance[from_node, to_node])
        travel_time_cost = duration[from_node, to_node] / 60.0 * travel_time_cost_m_per_minute
        service_cost = 0.0
        if from_node != 0:
            bin_index = candidates[from_node - 1]
            service_cost = (
                service_seconds_per_bin / 60.0 * service_cost_m_per_minute
                + float(additional_service_cost_m_equivalent[bin_index])
            )
        return max(0, int(round(travel_distance + travel_time_cost + service_cost)))

    cost_index = routing.RegisterTransitCallback(operating_cost_callback)
    routing.SetArcCostEvaluatorOfAllVehicles(cost_index)
    routing.SetFixedCostOfAllVehicles(max(0, int(fixed_trip_cost_m_equivalent)))

    mass_index = routing.RegisterUnaryTransitCallback(
        lambda index: int(mass[manager.IndexToNode(index)])
    )
    routing.AddDimensionWithVehicleCapacity(
        mass_index,
        0,
        [int(math.floor(truck_capacity_kg))] * max_trips,
        True,
        "MassKg",
    )
    volume_index = routing.RegisterUnaryTransitCallback(
        lambda index: int(volume_litres[manager.IndexToNode(index)])
    )
    routing.AddDimensionWithVehicleCapacity(
        volume_index,
        0,
        [int(math.floor(truck_capacity_m3 * 1000))] * max_trips,
        True,
        "CompactedVolumeLitres",
    )

    def time_callback(from_index: int, to_index: int) -> int:
        from_node = manager.IndexToNode(from_index)
        to_node = manager.IndexToNode(to_index)
        service = service_seconds_per_bin if from_node != 0 else 0.0
        return max(0, int(math.ceil(duration[from_node, to_node] + service)))

    time_index = routing.RegisterTransitCallback(time_callback)
    routing.AddDimension(
        time_index,
        0,
        max(1, int(math.floor(max_route_duration_seconds))),
        True,
        "RouteTime",
    )

    for local_node, bin_index in enumerate(candidates, start=1):
        if bin_index in mandatory:
            continue
        penalty = max(0, int(round(float(skip_penalties_m_equivalent[bin_index]))))
        routing.AddDisjunction([manager.NodeToIndex(local_node)], penalty)

    search = pywrapcp.DefaultRoutingSearchParameters()
    search.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.PARALLEL_CHEAPEST_INSERTION
    search.local_search_metaheuristic = routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
    search.time_limit.FromMilliseconds(max(25, int(solver_milliseconds)))
    search.solution_limit = 100
    solution = routing.SolveWithParameters(search)
    if solution is None:
        return RoutePlan(
            routes=[],
            distance_m=0,
            served_bin_indices=[],
            solver_method="value_infeasible",
            dropped_bin_indices=candidates,
            dispatch_reason="mandatory_constraints_infeasible" if mandatory else "no_positive_value_route",
        )

    dropped: list[int] = []
    for local_node, bin_index in enumerate(candidates, start=1):
        route_index = manager.NodeToIndex(local_node)
        if solution.Value(routing.NextVar(route_index)) == route_index:
            dropped.append(bin_index)

    routes: list[list[int]] = []
    route_durations: list[float] = []
    route_loads: list[float] = []
    route_volumes: list[float] = []
    served: list[int] = []
    total_distance = 0
    operating_cost = 0.0
    for vehicle in range(max_trips):
        index = routing.Start(vehicle)
        route = [-1]
        route_distance = 0
        route_duration = 0.0
        route_load = 0.0
        route_volume = 0.0
        route_cost = float(fixed_trip_cost_m_equivalent)
        while not routing.IsEnd(index):
            from_node = manager.IndexToNode(index)
            next_index = solution.Value(routing.NextVar(index))
            to_node = manager.IndexToNode(next_index)
            route_distance += int(distance[from_node, to_node])
            route_duration += float(duration[from_node, to_node])
            route_cost += float(operating_cost_callback(index, next_index))
            if from_node != 0:
                route_duration += service_seconds_per_bin
            if to_node != 0:
                bin_index = candidates[to_node - 1]
                route.append(bin_index)
                served.append(bin_index)
                route_load += float(demands_kg[bin_index])
                route_volume += float(demands_m3[bin_index])
            index = next_index
        route.append(-1)
        if len(route) > 2:
            routes.append(route)
            route_durations.append(route_duration)
            route_loads.append(route_load)
            route_volumes.append(route_volume)
            total_distance += route_distance
            operating_cost += route_cost

    avoided_loss = float(sum(skip_penalties_m_equivalent[index] for index in served))
    net_value = avoided_loss - operating_cost
    if not routes:
        return RoutePlan(
            routes=[],
            distance_m=0,
            served_bin_indices=[],
            solver_method="ortools_prize_collecting",
            dropped_bin_indices=candidates,
            objective_cost_m_equivalent=float(solution.ObjectiveValue()),
            avoided_loss_value_m_equivalent=0.0,
            net_value_m_equivalent=0.0,
            dispatch_reason="no_positive_value_route",
        )
    if not mandatory and routes and net_value <= minimum_net_value_m_equivalent:
        return RoutePlan(
            routes=[],
            distance_m=0,
            served_bin_indices=[],
            solver_method="value_gate",
            dropped_bin_indices=candidates,
            objective_cost_m_equivalent=float(solution.ObjectiveValue()),
            avoided_loss_value_m_equivalent=0.0,
            net_value_m_equivalent=net_value,
            dispatch_reason="wait_has_lower_expected_cost",
        )
    reason = "emergency_service_constraint" if mandatory else "positive_net_trip_value"
    return RoutePlan(
        routes=routes,
        distance_m=total_distance,
        served_bin_indices=served,
        solver_method="ortools_prize_collecting",
        dropped_bin_indices=dropped,
        route_duration_s=route_durations,
        route_loads_kg=route_loads,
        route_volumes_m3=route_volumes,
        objective_cost_m_equivalent=float(solution.ObjectiveValue()),
        operating_cost_m_equivalent=operating_cost,
        avoided_loss_value_m_equivalent=avoided_loss,
        net_value_m_equivalent=net_value,
        dispatch_reason=reason,
    )
