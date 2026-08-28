from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import numpy as np
import requests

from .config import Config


OSRM_BASE_URL = "https://router.project-osrm.org"
USER_AGENT = "BinSight-Focus-C/0.2 (competition research prototype)"


@dataclass(frozen=True)
class ServiceNetwork:
    provider: str
    requested_coordinates: tuple[tuple[float, float], ...]
    snapped_coordinates: tuple[tuple[float, float], ...]
    snap_distances_m: tuple[float, ...]
    road_names: tuple[str, ...]
    distance_matrix_m: np.ndarray
    duration_matrix_s: np.ndarray
    response_sha256: str
    retrieved_at_utc: str
    data_version: str | None

    @property
    def service_count(self) -> int:
        return len(self.snapped_coordinates)


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6_371_008.8
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * radius * math.asin(math.sqrt(a))


def _requested_coordinates(config: Config, sites: list[dict]) -> tuple[tuple[float, float], ...]:
    return (
        (config.pilot.depot_lat, config.pilot.depot_lon),
        (config.pilot.recycling_facility_lat, config.pilot.recycling_facility_lon),
        *(
            (float(site["latitude"]), float(site["longitude"]))
            for site in sites
        ),
    )


def _coordinates_url(coordinates: Iterable[tuple[float, float]]) -> str:
    return ";".join(f"{longitude:.6f},{latitude:.6f}" for latitude, longitude in coordinates)


def _request_json(url: str, timeout_seconds: int = 60) -> tuple[dict, bytes]:
    response = requests.get(
        url,
        timeout=timeout_seconds,
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
    )
    response.raise_for_status()
    payload = response.json()
    if payload.get("code") != "Ok":
        raise ValueError(f"OSRM request failed: {payload.get('code')} {payload.get('message', '')}")
    return payload, response.content


def download_or_load_service_network(
    config: Config,
    sites: list[dict],
    cache_path: str | Path,
    refresh: bool = False,
) -> ServiceNetwork:
    path = Path(cache_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    requested = _requested_coordinates(config, sites)
    if path.exists() and not refresh:
        cached = json.loads(path.read_text(encoding="utf-8"))
        cached_requested = tuple(tuple(row) for row in cached["requested_coordinates"])
        if cached_requested == requested:
            return _network_from_payload(cached)

    coordinates = _coordinates_url(requested)
    url = f"{OSRM_BASE_URL}/table/v1/driving/{coordinates}?annotations=distance,duration"
    response, raw = _request_json(url)
    sources = response.get("sources", [])
    distances = response.get("distances")
    durations = response.get("durations")
    size = len(requested)
    if len(sources) != size or not isinstance(distances, list) or len(distances) != size:
        raise ValueError("OSRM table response has an unexpected size")
    if not isinstance(durations, list) or len(durations) != size:
        raise ValueError("OSRM duration response has an unexpected size")
    if any(len(row) != size or any(value is None for value in row) for row in distances):
        raise ValueError("OSRM returned an incomplete road-distance matrix")
    if any(len(row) != size or any(value is None for value in row) for row in durations):
        raise ValueError("OSRM returned an incomplete duration matrix")
    snapped = tuple((float(row["location"][1]), float(row["location"][0])) for row in sources)
    snap_distances = tuple(float(row["distance"]) for row in sources)
    if any(distance > 250 for distance in snap_distances):
        bad = [index for index, distance in enumerate(snap_distances) if distance > 250]
        raise ValueError(f"Service points {bad} are more than 250 m from a routable road")
    payload = {
        "source": "OpenStreetMap road routing via the OSRM demo service",
        "provider": OSRM_BASE_URL,
        "attribution": "© OpenStreetMap contributors; ODbL",
        "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
        "data_version": response.get("data_version"),
        "requested_coordinates": requested,
        "snapped_coordinates": snapped,
        "snap_distances_m": snap_distances,
        "road_names": [str(row.get("name", "")) for row in sources],
        "distance_matrix_m": distances,
        "duration_matrix_s": durations,
        "response_sha256": hashlib.sha256(raw).hexdigest(),
        "pilot_label": config.pilot.label,
        "depot_label": config.pilot.depot_label,
        "recycling_facility_label": config.pilot.recycling_facility_label,
        "routing_profile": "driving (fastest-route distances)",
        "service_points": size,
    }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return _network_from_payload(payload)


def _network_from_payload(payload: dict) -> ServiceNetwork:
    network = ServiceNetwork(
        provider=str(payload["provider"]),
        requested_coordinates=tuple(tuple(row) for row in payload["requested_coordinates"]),
        snapped_coordinates=tuple(tuple(row) for row in payload["snapped_coordinates"]),
        snap_distances_m=tuple(float(value) for value in payload["snap_distances_m"]),
        road_names=tuple(str(value) for value in payload["road_names"]),
        distance_matrix_m=np.asarray(payload["distance_matrix_m"], dtype=np.int64),
        duration_matrix_s=np.asarray(payload["duration_matrix_s"], dtype=float),
        response_sha256=str(payload["response_sha256"]),
        retrieved_at_utc=str(payload["retrieved_at_utc"]),
        data_version=payload.get("data_version"),
    )
    _validate_service_network(network)
    return network


def load_cached_service_network(path: str | Path) -> ServiceNetwork:
    """Load and validate a previously downloaded OSRM service network."""
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return _network_from_payload(payload)


def _validate_service_network(network: ServiceNetwork) -> None:
    size = network.service_count
    if size < 2 or network.distance_matrix_m.shape != (size, size):
        raise ValueError("OSRM service network has an invalid distance-matrix shape")
    if network.duration_matrix_s.shape != (size, size):
        raise ValueError("OSRM service network has an invalid duration-matrix shape")
    if np.any(network.distance_matrix_m < 0) or np.any(network.duration_matrix_s < 0):
        raise ValueError("OSRM service network contains negative costs")
    if any(distance > 250 for distance in network.snap_distances_m):
        raise ValueError("A cached point no longer meets the 250 m snap-distance gate")


def expand_bin_distance_matrix(
    service_network: ServiceNetwork,
    bin_service_indices: Iterable[int],
) -> np.ndarray:
    indices = [0] + [int(index) for index in bin_service_indices]
    if any(index < 0 or index >= service_network.service_count for index in indices):
        raise ValueError("Bin service index is outside the OSRM service network")
    return service_network.distance_matrix_m[np.ix_(indices, indices)].copy()


def expand_bin_duration_matrix(
    service_network: ServiceNetwork,
    bin_service_indices: Iterable[int],
) -> np.ndarray:
    indices = [0] + [int(index) for index in bin_service_indices]
    if any(index < 0 or index >= service_network.service_count for index in indices):
        raise ValueError("Bin service index is outside the OSRM service network")
    return service_network.duration_matrix_s[np.ix_(indices, indices)].copy()


def expand_base_distance_matrix(
    service_network: ServiceNetwork,
    bin_service_indices: Iterable[int],
    base_service_index: int,
) -> np.ndarray:
    """Build a loop matrix whose virtual node zero is a vehicle's real base."""
    base = int(base_service_index)
    indices = [base] + [int(index) for index in bin_service_indices]
    if any(index < 0 or index >= service_network.service_count for index in indices):
        raise ValueError("Base or bin service index is outside the OSRM service network")
    return service_network.distance_matrix_m[np.ix_(indices, indices)].copy()


def expand_base_duration_matrix(
    service_network: ServiceNetwork,
    bin_service_indices: Iterable[int],
    base_service_index: int,
) -> np.ndarray:
    """Duration counterpart to :func:`expand_base_distance_matrix`."""
    base = int(base_service_index)
    indices = [base] + [int(index) for index in bin_service_indices]
    if any(index < 0 or index >= service_network.service_count for index in indices):
        raise ValueError("Base or bin service index is outside the OSRM service network")
    return service_network.duration_matrix_s[np.ix_(indices, indices)].copy()


def expand_destination_distance_matrix(
    service_network: ServiceNetwork,
    bin_service_indices: Iterable[int],
    destination_service_index: int,
) -> np.ndarray:
    """Build depot-start tours that unload at a destination before returning.

    The routing solver uses one virtual depot node for both tour ends. For a
    non-depot unload destination, every bin-to-virtual-depot arc is therefore
    the exact road distance bin -> destination -> depot. Depot-to-bin arcs and
    all bin-to-bin arcs are unchanged.
    """
    bin_indices = [int(index) for index in bin_service_indices]
    matrix = expand_bin_distance_matrix(service_network, bin_indices)
    destination = int(destination_service_index)
    if destination < 0 or destination >= service_network.service_count:
        raise ValueError("Destination service index is outside the OSRM network")
    if destination == 0:
        return matrix
    destination_to_depot = service_network.distance_matrix_m[destination, 0]
    for local_index, service_index in enumerate(bin_indices, start=1):
        matrix[local_index, 0] = (
            service_network.distance_matrix_m[service_index, destination]
            + destination_to_depot
        )
    matrix[0, 0] = 0
    return matrix


def expand_destination_duration_matrix(
    service_network: ServiceNetwork,
    bin_service_indices: Iterable[int],
    destination_service_index: int,
) -> np.ndarray:
    """Duration counterpart to :func:`expand_destination_distance_matrix`."""
    bin_indices = [int(index) for index in bin_service_indices]
    matrix = expand_bin_duration_matrix(service_network, bin_indices)
    destination = int(destination_service_index)
    if destination < 0 or destination >= service_network.service_count:
        raise ValueError("Destination service index is outside the OSRM network")
    if destination == 0:
        return matrix
    destination_to_depot = service_network.duration_matrix_s[destination, 0]
    for local_index, service_index in enumerate(bin_indices, start=1):
        matrix[local_index, 0] = (
            service_network.duration_matrix_s[service_index, destination]
            + destination_to_depot
        )
    matrix[0, 0] = 0
    return matrix


def route_coordinates(
    service_network: ServiceNetwork,
    service_indices: list[int],
    cache_path: str | Path,
) -> list[tuple[float, float]]:
    if not service_indices:
        return []
    deduplicated = [service_indices[0]]
    for index in service_indices[1:]:
        if index != deduplicated[-1]:
            deduplicated.append(index)
    if len(deduplicated) == 1:
        return [service_network.snapped_coordinates[deduplicated[0]]]
    if any(index < 0 or index >= service_network.service_count for index in deduplicated):
        raise ValueError("Representative route contains an invalid service index")

    cache_file = Path(cache_path)
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    cache = json.loads(cache_file.read_text(encoding="utf-8")) if cache_file.exists() else {}
    key = "-".join(str(index) for index in deduplicated)
    if key in cache:
        return [tuple(row) for row in cache[key]["coordinates_latlon"]]

    coordinates = [service_network.snapped_coordinates[index] for index in deduplicated]
    url = (
        f"{service_network.provider}/route/v1/driving/{_coordinates_url(coordinates)}"
        "?overview=full&geometries=geojson&steps=false"
    )
    response, raw = _request_json(url)
    route = response["routes"][0]
    lon_lat = route["geometry"]["coordinates"]
    lat_lon = [(float(latitude), float(longitude)) for longitude, latitude in lon_lat]
    cache[key] = {
        "service_indices": deduplicated,
        "coordinates_latlon": lat_lon,
        "distance_m": float(route["distance"]),
        "duration_s": float(route["duration"]),
        "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
        "response_sha256": hashlib.sha256(raw).hexdigest(),
    }
    cache_file.write_text(json.dumps(cache, indent=2), encoding="utf-8")
    return lat_lon
