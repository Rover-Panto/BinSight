from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import numpy as np


REGISTRY_SCHEMA_VERSION = "1.0"


@dataclass(frozen=True)
class RegistryEntry:
    hardware_bin_id: str
    canonical_bin_id: str
    profile: str
    controller_id: str
    controller_channel: int
    service_site_id: str
    service_index: int
    latitude: float
    longitude: float
    capacity_kg: float
    capacity_litres: float
    calibration_version: str
    bin_type: str
    waste_stream: str


@dataclass(frozen=True)
class OperatingProfile:
    profile_id: str
    label: str
    source_mode: str
    bin_ids: tuple[str, ...]
    road_matrix_order: tuple[str, ...]
    controller_topology: dict[str, tuple[str, ...]]
    live_integration_enabled: bool


class BinRegistry:
    """Versioned hardware-to-routing identity map.

    Physical controller topology is deliberately independent from service-site
    grouping. A controller may report multiple channels without implying that
    those channels share a collection location.
    """

    def __init__(
        self,
        registry_version: str,
        profiles: dict[str, OperatingProfile],
        entries: Iterable[RegistryEntry],
    ) -> None:
        self.registry_version = registry_version
        self.profiles = dict(profiles)
        self.entries = tuple(entries)
        self._validate()

    @classmethod
    def load(cls, path: str | Path) -> "BinRegistry":
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        if payload.get("schema_version") != REGISTRY_SCHEMA_VERSION:
            raise ValueError(
                f"Unsupported registry schema_version: {payload.get('schema_version')}"
            )
        raw_profiles = payload.get("profiles")
        raw_entries = payload.get("mappings")
        if not isinstance(raw_profiles, list) or not raw_profiles:
            raise ValueError("Registry must define at least one operating profile")
        if not isinstance(raw_entries, list):
            raise ValueError("Registry mappings must be an array")
        profiles: dict[str, OperatingProfile] = {}
        for row in raw_profiles:
            topology = row.get("controller_topology", {})
            if not isinstance(topology, dict):
                raise ValueError("controller_topology must be an object")
            profile = OperatingProfile(
                profile_id=str(row["profile_id"]),
                label=str(row["label"]),
                source_mode=str(row["source_mode"]),
                bin_ids=tuple(str(value) for value in row["bin_ids"]),
                road_matrix_order=tuple(str(value) for value in row["road_matrix_order"]),
                controller_topology={
                    str(controller): tuple(str(value) for value in bin_ids)
                    for controller, bin_ids in topology.items()
                },
                live_integration_enabled=bool(row.get("live_integration_enabled", False)),
            )
            if profile.profile_id in profiles:
                raise ValueError(f"Duplicate profile_id: {profile.profile_id}")
            profiles[profile.profile_id] = profile
        return cls(
            registry_version=str(payload["registry_version"]),
            profiles=profiles,
            entries=(RegistryEntry(**row) for row in raw_entries),
        )

    def _validate(self) -> None:
        if not self.registry_version.strip():
            raise ValueError("registry_version cannot be blank")
        by_profile: dict[str, list[RegistryEntry]] = {key: [] for key in self.profiles}
        for entry in self.entries:
            if entry.profile not in self.profiles:
                raise ValueError(f"Mapping references unknown profile: {entry.profile}")
            if not (-90 <= entry.latitude <= 90 and -180 <= entry.longitude <= 180):
                raise ValueError(f"Invalid coordinates for {entry.canonical_bin_id}")
            if entry.controller_channel < 1:
                raise ValueError("controller_channel must be positive")
            if entry.service_index < 1:
                raise ValueError("service_index must be positive")
            if entry.capacity_kg <= 0 or entry.capacity_litres <= 0:
                raise ValueError("Bin capacity values must be positive")
            if entry.bin_type not in {"general_waste", "recycling_return"}:
                raise ValueError(f"Unsupported bin_type for {entry.canonical_bin_id}")
            if not entry.waste_stream.strip():
                raise ValueError(f"waste_stream cannot be blank for {entry.canonical_bin_id}")
            by_profile[entry.profile].append(entry)

        for profile_id, profile in self.profiles.items():
            if len(profile.bin_ids) != len(set(profile.bin_ids)):
                raise ValueError(f"Profile {profile_id} contains duplicate canonical bin IDs")
            if profile.road_matrix_order != ("DEPOT",) + profile.bin_ids:
                raise ValueError(
                    f"Profile {profile_id} road_matrix_order must be DEPOT followed by bin_ids"
                )
            entries = by_profile[profile_id]
            hardware = [entry.hardware_bin_id for entry in entries]
            canonical = [entry.canonical_bin_id for entry in entries]
            if len(hardware) != len(set(hardware)):
                raise ValueError(f"Profile {profile_id} contains duplicate hardware mappings")
            if len(canonical) != len(set(canonical)):
                raise ValueError(f"Profile {profile_id} contains conflicting canonical mappings")
            if profile.source_mode == "synthetic" and not entries:
                if profile.controller_topology:
                    raise ValueError(
                        f"Synthetic profile {profile_id} must not imply a physical controller topology"
                    )
                continue
            if set(canonical) != set(profile.bin_ids):
                missing = sorted(set(profile.bin_ids) - set(canonical))
                extra = sorted(set(canonical) - set(profile.bin_ids))
                raise ValueError(
                    f"Profile {profile_id} mapping coverage mismatch; missing={missing}, extra={extra}"
                )
            topology_bins = [value for values in profile.controller_topology.values() for value in values]
            if sorted(topology_bins) != sorted(hardware):
                raise ValueError(
                    f"Profile {profile_id} controller topology must cover every hardware bin once"
                )

    def profile(self, profile_id: str) -> OperatingProfile:
        try:
            return self.profiles[profile_id]
        except KeyError as exc:
            raise ValueError(f"Unknown operating profile: {profile_id}") from exc

    def entries_for(self, profile_id: str) -> tuple[RegistryEntry, ...]:
        profile = self.profile(profile_id)
        order = {bin_id: index for index, bin_id in enumerate(profile.bin_ids)}
        return tuple(
            sorted(
                (entry for entry in self.entries if entry.profile == profile_id),
                key=lambda entry: order[entry.canonical_bin_id],
            )
        )

    def map_hardware_id(self, profile_id: str, hardware_bin_id: str) -> RegistryEntry:
        matches = [
            entry
            for entry in self.entries_for(profile_id)
            if entry.hardware_bin_id == hardware_bin_id
        ]
        if len(matches) != 1:
            raise ValueError(
                f"Unknown or conflicting hardware_bin_id for {profile_id}: {hardware_bin_id}"
            )
        return matches[0]

    def validate_matrix(self, profile_id: str, matrix: np.ndarray) -> None:
        profile = self.profile(profile_id)
        expected = len(profile.road_matrix_order)
        if matrix.shape != (expected, expected):
            raise ValueError(
                f"Road matrix for {profile_id} must be {expected}x{expected}; got {matrix.shape}"
            )
        if not np.isfinite(matrix).all() or (matrix < 0).any():
            raise ValueError("Road matrix must contain finite non-negative values")
