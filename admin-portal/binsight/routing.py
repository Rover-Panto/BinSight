from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from ortools.constraint_solver import pywrapcp, routing_enums_pb2


@dataclass(frozen=True)
class RoutePlan:
    routes: list[list[int]]
    distance_m: int
    served_bin_indices: list[int]
    solver_method: str


def _fallback_routes(
    selected: list[int],
    demands_kg: np.ndarray,
    full_matrix_m: np.ndarray,
    truck_capacity_kg: float,
    max_trips: int,
) -> RoutePlan:
    """Deterministic capacity-feasible construction for OR-Tools timeouts."""
    buckets: list[list[int]] = [[] for _ in range(max_trips)]
    loads = [0.0] * max_trips
    for bin_index in sorted(selected, key=lambda index: (-float(demands_kg[index]), index)):
        demand = max(0.0, float(demands_kg[bin_index]))
        feasible = [
            vehicle
            for vehicle in range(max_trips)
            if loads[vehicle] + demand <= truck_capacity_kg + 1e-9
        ]
        if not feasible:
            raise RuntimeError("Deterministic fallback could not pack the selected waste")
        vehicle = min(
            feasible,
            key=lambda item: (truck_capacity_kg - loads[item] - demand, item),
        )
        buckets[vehicle].append(bin_index)
        loads[vehicle] += demand

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
    demand_values = [0] + [max(0, int(math.ceil(float(demands_kg[index])))) for index in selected]
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
