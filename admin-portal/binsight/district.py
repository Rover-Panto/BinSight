from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from .config import Config
from .network import ServiceNetwork


@dataclass(frozen=True)
class BinSpec:
    bin_id: str
    node_id: object
    latitude: float
    longitude: float
    households: int
    commercial_units: int
    capacity_kg: float
    area_type: str
    controller_id: str = "SIM-GROUP-001"
    controller_channel: int = 1
    site_id: str = "SITE-01"
    site_label: str = "Prototype site"
    requested_latitude: float | None = None
    requested_longitude: float | None = None
    snap_distance_m: float = 0.0
    service_index: int = 0

    @property
    def household_share(self) -> float:
        total = self.households + self.commercial_units
        return self.households / total if total else 0.0


def _split_integer(total: int, parts: int) -> list[int]:
    quotient, remainder = divmod(total, parts)
    return [quotient + (index < remainder) for index in range(parts)]


def load_site_plan(path: str | Path, config: Config) -> list[dict]:
    site_path = Path(path)
    sites = json.loads(site_path.read_text(encoding="utf-8"))
    expected_sites = config.pilot.bin_count // config.pilot.bins_per_service_site
    if not isinstance(sites, list) or len(sites) != expected_sites:
        raise ValueError(f"Site plan must contain exactly {expected_sites} sites")
    required = {"site_id", "label", "latitude", "longitude", "households", "commercial_units"}
    if any(not required.issubset(site) for site in sites):
        raise ValueError("Every site-plan row must contain all required fields")
    if len({site["site_id"] for site in sites}) != len(sites):
        raise ValueError("Site IDs must be unique")
    if sum(int(site["households"]) for site in sites) != config.pilot.households:
        raise ValueError("Site-plan household total does not match the competition scenario")
    if sum(int(site["commercial_units"]) for site in sites) != config.pilot.commercial_units:
        raise ValueError("Site-plan commercial total does not match the competition scenario")
    usable_site_capacity_kg = (
        config.pilot.bins_per_service_site
        * config.waste.bin_capacity_kg
        * config.waste.sizing_target_fill_pct
        / 100.0
    )
    for site in sites:
        daily_demand_kg = (
            int(site["households"]) * config.waste.household_kg_per_day
            + int(site["commercial_units"]) * config.waste.commercial_kg_per_day
        )
        design_interval_demand_kg = (
            daily_demand_kg
            * config.operations.fixed_interval_days
            * config.waste.sizing_reserve_factor
        )
        if design_interval_demand_kg > usable_site_capacity_kg + 1e-9:
            raise ValueError(
                f"{site['site_id']} exceeds its three-bin design capacity: "
                f"{design_interval_demand_kg:.1f} kg demand vs "
                f"{usable_site_capacity_kg:.1f} kg usable"
            )
    return sites


def build_district(
    config: Config,
    service_network: ServiceNetwork,
    site_plan_path: str | Path,
) -> tuple[int, list[BinSpec]]:
    service_site_count = config.pilot.bin_count // config.pilot.bins_per_service_site
    sites = load_site_plan(site_plan_path, config)
    if len(sites) != service_site_count:
        raise ValueError("Service-site count and site plan are inconsistent")
    if service_network.service_count != len(sites) + 1:
        raise ValueError("OSRM network must contain depot plus every collection site")
    depot = 0
    bins: list[BinSpec] = []
    for site_index, site in enumerate(sites):
        requested_lat = float(site["latitude"])
        requested_lon = float(site["longitude"])
        service_index = site_index + 1
        snapped_lat, snapped_lon = service_network.snapped_coordinates[service_index]
        snap_distance = service_network.snap_distances_m[service_index]
        if snap_distance > 250:
            raise ValueError(
                f"{site['site_id']} is {snap_distance:.1f} m from an accessible drive node"
            )
        household_counts = _split_integer(
            int(site["households"]), config.pilot.bins_per_service_site
        )
        commercial_counts = _split_integer(
            int(site["commercial_units"]), config.pilot.bins_per_service_site
        )
        for channel in range(config.pilot.bins_per_service_site):
            index = site_index * config.pilot.bins_per_service_site + channel
            commercial = commercial_counts[channel]
            bins.append(
                BinSpec(
                    bin_id=f"UGB-{index + 1:03d}",
                    node_id=f"OSRM-SERVICE-{service_index:02d}",
                    latitude=snapped_lat,
                    longitude=snapped_lon,
                    households=household_counts[channel],
                    commercial_units=commercial,
                    capacity_kg=config.waste.bin_capacity_kg,
                    area_type=(
                        "mixed/commercial"
                        if int(site["commercial_units"]) >= 2
                        else "residential"
                    ),
                    controller_id=f"SIM-GROUP-{site_index + 1:03d}",
                    controller_channel=channel + 1,
                    site_id=str(site["site_id"]),
                    site_label=str(site["label"]),
                    requested_latitude=requested_lat,
                    requested_longitude=requested_lon,
                    snap_distance_m=snap_distance,
                    service_index=service_index,
                )
            )
    assert sum(item.households for item in bins) == config.pilot.households
    assert sum(item.commercial_units for item in bins) == config.pilot.commercial_units
    return depot, bins


def bins_frame(bins: list[BinSpec]) -> pd.DataFrame:
    rows = []
    for item in bins:
        row = asdict(item)
        row["node_id"] = str(row["node_id"])
        rows.append(row)
    return pd.DataFrame(rows)


def save_district(bins: list[BinSpec], path: str | Path) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    bins_frame(bins).to_csv(output, index=False)


def generate_hourly_waste(
    bins: list[BinSpec], config: Config, seed: int, horizon_hours: int, start_day: int = 0
) -> np.ndarray:
    """Backward-compatible arrival-only view of the patterned demand model."""
    from .demand import generate_demand_realization

    return generate_demand_realization(
        bins,
        config,
        seed,
        horizon_hours,
        start_day=start_day,
    ).arrivals_kg
