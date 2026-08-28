from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd

from .registry import BinRegistry


TELEMETRY_ROUTING_SCHEMA_VERSION = "2.1"
SUPPORTED_TELEMETRY_ROUTING_SCHEMA_VERSIONS = {"2.0", "2.1"}
SOURCE_MODES = {"hardware", "replay", "synthetic", "legacy"}
CLOCK_STATES = {"synchronized", "unsynchronized", "ambiguous"}
FORECAST_STATES = {
    "available",
    "unavailable",
    "cold_start",
    "model_error",
    "stable_no_overflow",
}


@dataclass(frozen=True)
class AdapterResult:
    frame: pd.DataFrame
    snapshot_id: str
    decision_at: str
    accepted_event_ids: tuple[str, ...]
    rejected_events: tuple[dict[str, str], ...]
    coverage_complete: bool
    source_mode: str


def parse_utc(value: Any, name: str, *, nullable: bool = False) -> datetime | None:
    if value is None and nullable:
        return None
    text = str(value or "").strip()
    if not text:
        if nullable:
            return None
        raise ValueError(f"{name} cannot be blank")
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{name} must be an ISO 8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{name} must include an explicit timezone")
    return parsed.astimezone(timezone.utc)


def _finite_optional(value: Any, name: str, low: float, high: float) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be numeric or null")
    number = float(value)
    if not math.isfinite(number) or not low <= number <= high:
        raise ValueError(f"{name} must be finite and in [{low}, {high}]")
    return number


def _event_identity(event: dict[str, Any]) -> str:
    explicit = str(event.get("event_id") or "").strip()
    if explicit:
        return explicit
    device = str(event.get("device_id") or "").strip()
    boot = str(event.get("boot_id") or "").strip()
    sequence = event.get("sequence")
    hardware_bin = str(event.get("hardware_bin_id") or "").strip()
    if not device or not boot or isinstance(sequence, bool) or not isinstance(sequence, int):
        raise ValueError(
            "Each event needs event_id or the complete device_id/boot_id/sequence identity"
        )
    if sequence < 0 or not hardware_bin:
        raise ValueError("Event sequence must be non-negative and hardware_bin_id is required")
    return f"{device}:{boot}:{sequence}:{hardware_bin}"


def _snapshot_identity(source_mode: str, decision_at: datetime, event_ids: Iterable[str]) -> str:
    material = json.dumps(
        [source_mode, decision_at.isoformat(), sorted(event_ids)], separators=(",", ":")
    ).encode("utf-8")
    return "SNAP-" + hashlib.sha256(material).hexdigest()[:20].upper()


def normalize_telemetry_envelope(
    payload: dict[str, Any],
    registry: BinRegistry,
    profile_id: str,
    *,
    decision_at: datetime | None = None,
    previous_events: dict[str, dict[str, Any]] | None = None,
) -> AdapterResult:
    """Normalize producer events into one reproducible routing snapshot.

    Older replays never replace newer accepted observations. Missing known bins
    remain in the frame as explicit unknown rows so coverage cannot look healthy.
    """
    if not isinstance(payload, dict):
        raise ValueError("Telemetry envelope must be an object")
    schema_version = str(payload.get("schema_version") or "")
    if schema_version not in SUPPORTED_TELEMETRY_ROUTING_SCHEMA_VERSIONS:
        raise ValueError(f"Unsupported telemetry schema_version: {payload.get('schema_version')}")
    source_mode = str(payload.get("source_mode") or "").strip().lower()
    if source_mode not in SOURCE_MODES:
        raise ValueError(f"source_mode must be one of {sorted(SOURCE_MODES)}")
    decision = decision_at or parse_utc(payload.get("decision_at"), "decision_at")
    assert decision is not None
    decision = decision.astimezone(timezone.utc)
    profile = registry.profile(profile_id)
    events = payload.get("events")
    if not isinstance(events, list):
        raise ValueError("Telemetry envelope events must be an array")

    accepted: dict[str, dict[str, Any]] = dict(previous_events or {})
    accepted_ids: list[str] = []
    rejected: list[dict[str, str]] = []
    seen_event_ids: set[str] = set()
    seen_in_batch: set[str] = set()
    for position, raw in enumerate(events):
        if not isinstance(raw, dict):
            raise ValueError(f"events[{position}] must be an object")
        event = dict(raw)
        bin_type = str(event.get("bin_type") or "").strip().lower()
        event_kind = str(event.get("event_kind") or "").strip().lower()
        if schema_version == "2.0":
            event_kind = event_kind or "fill_observation"
            if bin_type != "general_waste":
                raise ValueError(
                    "Legacy telemetry 2.0 accepts only general_waste fill observations"
                )
        if event_kind != "fill_observation":
            raise ValueError(
                "Routing accepts only event_kind 'fill_observation'; recognition and "
                "return-session events use a separate contract"
            )
        event_id = _event_identity(event)
        if event_id in seen_event_ids:
            raise ValueError(f"Duplicate producer event identity: {event_id}")
        seen_event_ids.add(event_id)
        hardware_bin_id = str(event.get("hardware_bin_id") or "").strip()
        mapping = registry.map_hardware_id(profile_id, hardware_bin_id)
        if bin_type != mapping.bin_type:
            raise ValueError(
                f"bin_type for {hardware_bin_id} must match registry value {mapping.bin_type}"
            )
        canonical = mapping.canonical_bin_id
        if canonical in seen_in_batch:
            raise ValueError(f"Multiple events supplied for canonical bin {canonical}")
        seen_in_batch.add(canonical)
        clock_status = str(event.get("clock_status") or "synchronized").lower()
        if clock_status not in CLOCK_STATES:
            raise ValueError(f"Invalid clock_status for {event_id}: {clock_status}")
        observed = parse_utc(
            event.get("observed_at"),
            "observed_at",
            nullable=clock_status != "synchronized",
        )
        if clock_status == "synchronized" and observed is None:
            raise ValueError(f"Synchronized event {event_id} requires observed_at")
        received = parse_utc(event.get("received_at"), "received_at")
        assert received is not None
        if observed is not None and observed > decision:
            rejected.append({"event_id": event_id, "reason": "observation is after decision cutoff"})
            continue
        fill = _finite_optional(event.get("fill_pct"), "fill_pct", 0.0, 100.0)
        weight = _finite_optional(event.get("weight_kg"), "weight_kg", 0.0, 1500.0)
        confidence = _finite_optional(
            event.get("fill_confidence"), "fill_confidence", 0.0, 1.0
        )
        forecast_status = str(event.get("forecast_status") or "unavailable").lower()
        if forecast_status not in FORECAST_STATES:
            raise ValueError(f"Invalid forecast_status for {event_id}: {forecast_status}")
        tto = _finite_optional(
            event.get("time_to_overflow_hours"),
            "time_to_overflow_hours",
            0.0,
            100_000.0,
        )
        if forecast_status == "available" and tto is None:
            raise ValueError(f"Available forecast for {event_id} requires time_to_overflow_hours")
        if forecast_status != "available" and tto is not None:
            raise ValueError(f"Unavailable forecast for {event_id} must use null time-to-overflow")
        quality_flags = event.get("quality_flags", [])
        if not isinstance(quality_flags, list) or any(not isinstance(v, str) for v in quality_flags):
            raise ValueError(f"quality_flags for {event_id} must be an array of strings")
        normalized = {
            "event_id": event_id,
            "device_id": str(event.get("device_id") or ""),
            "boot_id": str(event.get("boot_id") or ""),
            "sequence": event.get("sequence"),
            "hardware_bin_id": hardware_bin_id,
            "bin_type": bin_type,
            "event_kind": event_kind,
            "waste_stream": mapping.waste_stream,
            "material_type": mapping.material_type,
            "bin_id": canonical,
            "observed_at": observed.isoformat() if observed else None,
            "received_at": received.isoformat(),
            "clock_status": clock_status,
            "fill_pct": fill,
            "weight_kg": weight,
            "confidence_flag": bool(confidence is not None and confidence >= 0.70),
            "fill_confidence": confidence,
            "quality_flags": tuple(sorted(set(quality_flags))),
            "forecast_status": forecast_status,
            "time_to_overflow_hours": tto,
            "risk_level": str(event.get("risk_level") or "unknown").lower(),
            "forecast_method": str(event.get("forecast_method") or "fill-threshold-fallback"),
            "model_version": (
                str(event["model_version"]) if event.get("model_version") is not None else None
            ),
            "calibration_version": str(
                event.get("calibration_version") or mapping.calibration_version
            ),
            "source_mode": source_mode,
            "profile_id": profile_id,
            "registry_version": registry.registry_version,
            "capacity_kg": mapping.capacity_kg,
            "capacity_litres": mapping.capacity_litres,
            "service_site_id": mapping.service_site_id,
            "service_index": mapping.service_index,
        }
        prior = accepted.get(canonical)
        prior_observed = (
            parse_utc(prior.get("observed_at"), "prior observed_at", nullable=True)
            if prior
            else None
        )
        if prior and prior_observed is not None and (observed is None or observed < prior_observed):
            rejected.append({"event_id": event_id, "reason": "older replay than retained event"})
            continue
        accepted[canonical] = normalized
        accepted_ids.append(event_id)

    rows: list[dict[str, Any]] = []
    for canonical in profile.bin_ids:
        row = accepted.get(canonical)
        if row is None:
            entry = next(value for value in registry.entries_for(profile_id) if value.canonical_bin_id == canonical)
            row = {
                "event_id": None,
                "device_id": None,
                "boot_id": None,
                "sequence": None,
                "hardware_bin_id": entry.hardware_bin_id,
                "bin_type": entry.bin_type,
                "event_kind": "fill_observation",
                "waste_stream": entry.waste_stream,
                "material_type": entry.material_type,
                "bin_id": canonical,
                "observed_at": None,
                "received_at": None,
                "clock_status": "unsynchronized",
                "fill_pct": None,
                "weight_kg": None,
                "confidence_flag": False,
                "fill_confidence": None,
                "quality_flags": ("missing_observation",),
                "forecast_status": "unavailable",
                "time_to_overflow_hours": None,
                "risk_level": "unknown",
                "forecast_method": "fill-threshold-fallback",
                "model_version": None,
                "calibration_version": entry.calibration_version,
                "source_mode": source_mode,
                "profile_id": profile_id,
                "registry_version": registry.registry_version,
                "capacity_kg": entry.capacity_kg,
                "capacity_litres": entry.capacity_litres,
                "service_site_id": entry.service_site_id,
                "service_index": entry.service_index,
            }
        rows.append(dict(row))

    all_source_ids = [str(row["event_id"]) for row in rows if row.get("event_id")]
    snapshot_id = str(payload.get("snapshot_id") or "").strip() or _snapshot_identity(
        source_mode, decision, all_source_ids
    )
    frame = pd.DataFrame(rows)
    frame["schema_version"] = schema_version
    frame["snapshot_id"] = snapshot_id
    frame["decision_at"] = decision.isoformat()
    frame["timestamp"] = frame["observed_at"]
    frame["reading_age_hours"] = frame["observed_at"].map(
        lambda value: (
            max(0.0, (decision - parse_utc(value, "observed_at")).total_seconds() / 3600.0)
            if value is not None
            else np.nan
        )
    )
    coverage_complete = bool(frame["event_id"].notna().all()) and not bool(payload.get("partial"))
    frame["coverage_complete"] = coverage_complete
    return AdapterResult(
        frame=frame,
        snapshot_id=snapshot_id,
        decision_at=decision.isoformat(),
        accepted_event_ids=tuple(accepted_ids),
        rejected_events=tuple(rejected),
        coverage_complete=coverage_complete,
        source_mode=source_mode,
    )


def load_fixture(
    path: str | Path,
    registry: BinRegistry,
    profile_id: str,
    *,
    decision_at: datetime | None = None,
) -> AdapterResult:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return normalize_telemetry_envelope(
        payload, registry, profile_id, decision_at=decision_at
    )
