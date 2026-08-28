from __future__ import annotations

from dataclasses import replace

from .config import OperationsConfig
from .routing import RoutePlan


GENERAL_STREAM = "mixed_general_waste"
RECYCLING_STREAM = "dry_recycling"
WASTE_DEPOT = "waste_depot"
RECYCLING_FACILITY = "recycling_facility"


def vehicle_type_for_destination(destination_id: str) -> str:
    if destination_id == RECYCLING_FACILITY:
        return "recycling"
    if destination_id == WASTE_DEPOT:
        return "general_waste"
    raise ValueError(f"No specialized vehicle type is configured for {destination_id}")


def trip_limit_for_stream(stream: str, operations: OperationsConfig) -> int:
    """Maximum bounded daily trips for the dedicated fleet serving a stream."""
    if stream == RECYCLING_STREAM:
        trucks = operations.recycling_truck_count
    elif stream == GENERAL_STREAM:
        trucks = operations.general_waste_truck_count
    else:
        raise ValueError(f"No specialized fleet is configured for waste stream {stream}")
    return trucks * operations.max_daily_trips


def vehicle_limit_for_stream(stream: str, operations: OperationsConfig) -> int:
    """Concurrent departures available to one dispatch decision."""
    if stream == RECYCLING_STREAM:
        return operations.recycling_truck_count
    if stream == GENERAL_STREAM:
        return operations.general_waste_truck_count
    raise ValueError(f"No specialized fleet is configured for waste stream {stream}")


def assign_route_vehicles(plan: RoutePlan, operations: OperationsConfig) -> RoutePlan:
    """Attach deterministic dedicated-vehicle identities to every planned route.

    Routes are shared round-robin only across the configured permanent trucks;
    the planner never invents extra surge vehicles.
    """
    vehicle_types: list[str] = []
    vehicle_ids: list[str] = []
    counters = {WASTE_DEPOT: 0, RECYCLING_FACILITY: 0}
    for route_position, _ in enumerate(plan.routes):
        destination = (
            plan.route_destinations[route_position]
            if route_position < len(plan.route_destinations)
            else WASTE_DEPOT
        )
        vehicle_type = vehicle_type_for_destination(destination)
        route_number = counters[destination]
        counters[destination] += 1
        if destination == RECYCLING_FACILITY:
            vehicle_slot = route_number % operations.recycling_truck_count
            vehicle_id = f"RECYCLING-{vehicle_slot + 1:02d}"
        else:
            vehicle_slot = route_number % operations.general_waste_truck_count
            vehicle_id = f"GENERAL-{vehicle_slot + 1:02d}"
        vehicle_types.append(vehicle_type)
        vehicle_ids.append(vehicle_id)
    return replace(
        plan,
        route_vehicle_types=vehicle_types,
        route_vehicle_ids=vehicle_ids,
    )
