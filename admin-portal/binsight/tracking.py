from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .network import ServiceNetwork, haversine_m, route_coordinates


@dataclass(frozen=True)
class TrackingFrame:
    simulation_minute: float
    elapsed_simulation_minutes: float
    trip_number: int
    status: str
    latitude: float
    longitude: float
    next_stop: str
    estimated_arrival_minute: float | None
    payload_kg: float
    payload_capacity_kg: float
    bins_completed: int
    bins_remaining: int


def _geometry_distances(geometry: list[tuple[float, float]]) -> tuple[list[float], float]:
    cumulative = [0.0]
    for first, second in zip(geometry[:-1], geometry[1:]):
        cumulative.append(cumulative[-1] + haversine_m(*first, *second))
    return cumulative, cumulative[-1] if cumulative else 0.0


def _interpolate_geometry(
    geometry: list[list[float]], cumulative_m: list[float], fraction: float
) -> tuple[float, float]:
    if not geometry:
        raise ValueError("Tracking segment has no geometry")
    if len(geometry) == 1 or not cumulative_m or cumulative_m[-1] <= 0:
        return float(geometry[-1][0]), float(geometry[-1][1])
    target = min(1.0, max(0.0, float(fraction))) * cumulative_m[-1]
    index = int(np.searchsorted(np.asarray(cumulative_m), target, side="right") - 1)
    index = min(max(index, 0), len(geometry) - 2)
    start_distance = cumulative_m[index]
    end_distance = cumulative_m[index + 1]
    local = 0.0 if end_distance <= start_distance else (
        (target - start_distance) / (end_distance - start_distance)
    )
    first = geometry[index]
    second = geometry[index + 1]
    return (
        float(first[0] + (second[0] - first[0]) * local),
        float(first[1] + (second[1] - first[1]) * local),
    )


def build_tracking_manifest(
    route_event: dict[str, Any],
    bins: pd.DataFrame,
    service_network: ServiceNetwork,
    cache_path: str | Path,
    destination_service_indices: dict[str, int] | None = None,
    *,
    trip_number: int | None = None,
) -> dict[str, Any]:
    """Convert one completed simulated dispatch into browser-playable segments."""
    timeline = sorted(
        route_event.get("timeline", []), key=lambda row: float(row["simulation_minute"])
    )
    if trip_number is not None:
        timeline = [
            row
            for row in timeline
            if int(row.get("trip_number", -1)) == int(trip_number)
        ]
    if not timeline:
        raise ValueError("The route event has no timestamped execution timeline")
    by_id = {str(row.bin_id): row for row in bins.itertuples()}
    destination_service_indices = dict(destination_service_indices or {})
    def service_index(stop_id: str) -> int:
        if stop_id == "DEPOT":
            return 0
        if stop_id in destination_service_indices:
            index = int(destination_service_indices[stop_id])
            if index < 0 or index >= service_network.service_count:
                raise ValueError(f"Destination {stop_id} has an invalid service index")
            return index
        if stop_id not in by_id:
            raise ValueError(f"Tracking timeline contains unknown stop {stop_id}")
        return int(by_id[stop_id].service_index)
    route_position = max(0, int(trip_number or 1) - 1)
    route_bin_indices = route_event.get("route_bin_indices", [])
    if trip_number is not None and route_position < len(route_bin_indices):
        served_bins = [
            str(bins.iloc[index]["bin_id"])
            for index in route_bin_indices[route_position]
            if int(index) != -1
        ]
    else:
        served_bins = [str(value) for value in route_event.get("served_bins", [])]
    route_stops = route_event.get("routes", [])
    selected_route_stops = (
        route_stops[route_position]
        if route_position < len(route_stops)
        else ["DEPOT"]
    )
    route_base_id = str(selected_route_stops[0]) if selected_route_stops else "DEPOT"
    vehicle_ids = route_event.get("route_vehicle_ids", [])
    vehicle_types = route_event.get("route_vehicle_types", [])
    vehicle_id = (
        str(vehicle_ids[route_position])
        if route_position < len(vehicle_ids)
        else "UNASSIGNED"
    )
    vehicle_type = (
        str(vehicle_types[route_position])
        if route_position < len(vehicle_types)
        else "general_waste"
    )
    payload_capacity = max(
        (
            float(row.get("payload_capacity_kg", 0.0))
            for row in timeline
            if row.get("status") == "DISPATCHED"
        ),
        default=0.0,
    )
    segments: list[dict[str, Any]] = []
    completion_minutes: dict[str, float] = {}
    payload = 0.0
    bins_completed = 0
    trip_number = 0
    for row in timeline:
        status = str(row["status"])
        start = float(row["simulation_minute"])
        trip_number = int(row.get("trip_number", trip_number or 1))
        if "payload_kg" in row:
            payload = float(row["payload_kg"])
        if status in {
            "EN_ROUTE",
            "EN_ROUTE_TO_UNLOAD",
            "RETURNING_TO_DEPOT",
            "RETURNING_TO_RECYCLING_FACILITY",
        }:
            duration = max(0.0, float(row.get("travel_minutes", 0.0)))
            if duration <= 0:
                continue
            origin_id = str(row.get("origin", "DEPOT"))
            destination_id = str(row.get("destination", "DEPOT"))
            origin_service = service_index(origin_id)
            destination_service = service_index(destination_id)
            geometry = route_coordinates(
                service_network, [origin_service, destination_service], cache_path
            )
            cumulative, total = _geometry_distances(geometry)
            segments.append(
                {
                    "kind": "travel",
                    "status": status,
                    "trip_number": trip_number,
                    "start_minute": start,
                    "end_minute": start + duration,
                    "next_stop": destination_id,
                    "payload_kg": payload,
                    "payload_capacity_kg": payload_capacity,
                    "bins_completed": bins_completed,
                    "geometry": [[float(lat), float(lon)] for lat, lon in geometry],
                    "cumulative_m": [float(value) for value in cumulative],
                    "geometry_distance_m": float(total),
                }
            )
        elif status == "COLLECTING":
            bin_id = str(row["bin_id"])
            duration = max(0.0, float(row.get("duration_minutes", 0.0)))
            item = by_id[bin_id]
            segments.append(
                {
                    "kind": "service",
                    "status": status,
                    "trip_number": trip_number,
                    "start_minute": start,
                    "end_minute": start + duration,
                    "next_stop": bin_id,
                    "payload_kg": payload,
                    "payload_capacity_kg": payload_capacity,
                    "bins_completed": bins_completed,
                    "geometry": [[float(item.latitude), float(item.longitude)]],
                    "cumulative_m": [0.0],
                }
            )
        elif status == "COLLECTION_COMPLETE":
            bin_id = str(row["bin_id"])
            completion_minutes[bin_id] = start
            bins_completed = int(row.get("bins_completed", bins_completed + 1))
            payload = float(row.get("payload_kg", payload))
        elif status in {"UNLOADING", "TURNAROUND"}:
            duration = max(0.0, float(row.get("duration_minutes", 0.0)))
            stop_id = (
                str(row.get("unload_destination_id") or route_base_id)
                if status == "UNLOADING"
                else route_base_id
            )
            stop_service = service_index(stop_id)
            stop_coordinate = service_network.snapped_coordinates[stop_service]
            segments.append(
                {
                    "kind": "depot" if stop_service == 0 else "facility",
                    "status": status,
                    "trip_number": trip_number,
                    "start_minute": start,
                    "end_minute": start + duration,
                    "next_stop": stop_id,
                    "payload_kg": payload if status == "UNLOADING" else 0.0,
                    "payload_capacity_kg": payload_capacity,
                    "bins_completed": bins_completed,
                    "geometry": [
                        [float(stop_coordinate[0]), float(stop_coordinate[1])]
                    ],
                    "cumulative_m": [0.0],
                }
            )
            if status == "TURNAROUND":
                payload = 0.0

    if not segments:
        raise ValueError("The route event contains no trackable travel or service segments")
    site_selected: dict[str, list[str]] = {}
    for bin_id in served_bins:
        site_selected.setdefault(str(by_id[bin_id].site_id), []).append(bin_id)
    site_completion = {
        site_id: max(completion_minutes[bin_id] for bin_id in bin_ids)
        for site_id, bin_ids in site_selected.items()
        if all(bin_id in completion_minutes for bin_id in bin_ids)
    }
    start_minute = min(float(row["start_minute"]) for row in segments)
    end_minute = max(float(row["end_minute"]) for row in segments)
    return {
        "mode": "SIMULATED_LOCAL_TRACKING",
        "disclaimer": "Local playback only; no real vehicle is connected.",
        "route_id": (
            f"{route_event.get('policy', 'smart').upper()}-D{route_event.get('day', 0)}"
            f"-H{route_event.get('hour', 0)}-{vehicle_id}"
        ),
        "vehicle_id": vehicle_id,
        "vehicle_type": vehicle_type,
        "trip_number": int(trip_number or 1),
        "route_base_id": route_base_id,
        "start_minute": start_minute,
        "end_minute": end_minute,
        "duration_minutes": end_minute - start_minute,
        "served_bins": served_bins,
        "total_bins": len(served_bins),
        "payload_capacity_kg": payload_capacity,
        "completion_minutes": completion_minutes,
        "site_completion_minutes": site_completion,
        "segments": segments,
    }


def build_site_fill_profiles(
    bins: pd.DataFrame,
    snapshot_rows: list[dict[str, Any]],
    manifest: dict[str, Any],
) -> dict[str, list[dict[str, float | str | None]]]:
    """Build forecast-fill playback inputs for every bin at every site.

    Fill grows linearly from the dispatch snapshot to the supplied
    time-to-overflow estimate.  A bin resets to zero when its simulated
    collection completes.  This is a transparent UI interpolation, not a new
    sensor reading or a claim about actual waste generation between readings.
    """
    audit = {str(row.get("bin_id")): row for row in snapshot_rows}
    completions = {
        str(bin_id): float(minute)
        for bin_id, minute in manifest.get("completion_minutes", {}).items()
    }
    profiles: dict[str, list[dict[str, float | str | None]]] = {}
    for item in bins.itertuples():
        bin_id = str(item.bin_id)
        row = audit.get(bin_id, {})
        fill_value = row.get("fill_pct", 0.0)
        tto_value = row.get("time_to_overflow_hours")
        try:
            fill = float(fill_value)
        except (TypeError, ValueError):
            fill = 0.0
        if not np.isfinite(fill):
            fill = 0.0
        try:
            tto = float(tto_value)
        except (TypeError, ValueError):
            tto = float("nan")
        profiles.setdefault(str(item.site_id), []).append(
            {
                "bin_id": bin_id,
                "initial_fill_pct": min(100.0, max(0.0, fill)),
                "time_to_overflow_hours": (
                    tto if np.isfinite(tto) and tto > 0 else None
                ),
                "completion_minute": completions.get(bin_id),
            }
        )
    return profiles


def tracking_frame_at(manifest: dict[str, Any], simulation_minute: float) -> TrackingFrame:
    start = float(manifest["start_minute"])
    end = float(manifest["end_minute"])
    minute = min(end, max(start, float(simulation_minute)))
    segments = manifest["segments"]
    segment = next(
        (
            row
            for row in segments
            if float(row["start_minute"]) <= minute < float(row["end_minute"])
        ),
        segments[-1],
    )
    segment_start = float(segment["start_minute"])
    segment_end = float(segment["end_minute"])
    fraction = 1.0 if segment_end <= segment_start else (
        (minute - segment_start) / (segment_end - segment_start)
    )
    latitude, longitude = _interpolate_geometry(
        segment["geometry"], segment["cumulative_m"], fraction
    )
    completed = sum(
        float(value) <= minute for value in manifest.get("completion_minutes", {}).values()
    )
    status = "TRIP_COMPLETE" if minute >= end else str(segment["status"])
    return TrackingFrame(
        simulation_minute=minute,
        elapsed_simulation_minutes=minute - start,
        trip_number=int(segment["trip_number"]),
        status=status,
        latitude=latitude,
        longitude=longitude,
        next_stop="COMPLETE" if minute >= end else str(segment["next_stop"]),
        estimated_arrival_minute=None if minute >= end else segment_end,
        payload_kg=0.0 if minute >= end else float(segment["payload_kg"]),
        payload_capacity_kg=float(manifest["payload_capacity_kg"]),
        bins_completed=int(completed),
        bins_remaining=max(0, int(manifest["total_bins"]) - int(completed)),
    )
