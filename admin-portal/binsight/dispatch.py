from __future__ import annotations

import hashlib
import io
import json
import os
import time
from collections import Counter
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from uuid import uuid4

import numpy as np
import pandas as pd

from .config import Config
from .routing import (
    RoutePlan,
    select_dual_capacity_feasible,
    solve_routes,
    solve_value_routes,
)


PREDICTIVE_COLUMNS = (
    "timestamp",
    "bin_id",
    "fill_pct",
    "weight_kg",
    "time_to_overflow_hours",
    "risk_level",
    "confidence_flag",
)
ALLOWED_RISK_LEVELS = ("unknown", "low", "medium", "high", "critical")
FORECAST_STATUSES = (
    "available",
    "unavailable",
    "cold_start",
    "model_error",
    "stable_no_overflow",
)
POLICY_VERSION = "dynamic-trip-value-v2"
PLAN_SCHEMA_VERSION = "2.0"
COLLECTION_REQUIRED = "COLLECTION_REQUIRED"
INSPECTION_REQUIRED = "INSPECTION_REQUIRED"
NO_COLLECTION_REQUIRED = "NO_COLLECTION_REQUIRED"


@dataclass(frozen=True)
class DispatchPlan:
    snapshot_timestamp: str
    decision_state: str
    collection_required: bool
    inspection_required: bool
    route_plan: RoutePlan
    selected_bin_indices: list[int]
    required_bin_indices: list[int]
    sibling_bin_indices: list[int]
    optional_bin_indices: list[int]
    unserved_required_bin_indices: list[int]
    review_bin_indices: list[int]
    selection_rows: list[dict[str, Any]]
    audit_rows: list[dict[str, Any]]
    warnings: tuple[str, ...]
    plan_id: str = ""
    plan_schema_version: str = PLAN_SCHEMA_VERSION
    policy_version: str = POLICY_VERSION
    source_mode: str = "legacy"
    source_event_ids: tuple[str, ...] = ()
    decision_at: str = ""
    deferred_bin_indices: list[int] | None = None

    @property
    def selected_count(self) -> int:
        return len(self.selected_bin_indices)


def _parse_json_records(
    raw_text: str,
    *,
    registry=None,
    profile_id: str | None = None,
) -> pd.DataFrame:
    try:
        payload = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"The JSON is invalid: {exc.msg} at line {exc.lineno}") from exc
    if isinstance(payload, dict):
        if "events" in payload:
            if registry is None or not profile_id:
                raise ValueError(
                    "A telemetry v2 envelope requires a configured bin registry and operating profile"
                )
            from .telemetry_adapter import normalize_telemetry_envelope

            return normalize_telemetry_envelope(
                payload, registry, profile_id
            ).frame
        if "bins" not in payload:
            raise ValueError("A JSON object must contain a 'bins' array")
        payload = payload["bins"]
    if not isinstance(payload, list):
        raise ValueError("JSON input must be an array of bin records or an object with a 'bins' array")
    if not payload or any(not isinstance(row, dict) for row in payload):
        raise ValueError("The JSON bins array must contain record objects")
    return pd.DataFrame(payload)


def parse_snapshot_bytes(
    content: bytes,
    filename: str,
    *,
    registry=None,
    profile_id: str | None = None,
) -> pd.DataFrame:
    """Parse a predictive-AI snapshot from CSV or JSON bytes."""
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError("Input must be UTF-8 encoded") from exc
    suffix = Path(filename).suffix.lower()
    if suffix == ".csv":
        try:
            return pd.read_csv(io.StringIO(text))
        except Exception as exc:
            raise ValueError(f"The CSV could not be read: {exc}") from exc
    if suffix == ".json":
        return _parse_json_records(text, registry=registry, profile_id=profile_id)
    raise ValueError("Upload a .csv or .json file")


def parse_snapshot_json(
    raw_text: str,
    *,
    registry=None,
    profile_id: str | None = None,
) -> pd.DataFrame:
    return _parse_json_records(raw_text, registry=registry, profile_id=profile_id)


def _parse_timestamp(value: Any) -> datetime:
    text = str(value).strip()
    if not text:
        raise ValueError("timestamp cannot be blank")
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"'{text}' is not a valid ISO 8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"'{text}' must include a timezone, such as +08:00 or Z")
    return parsed.astimezone(timezone.utc)


def _parse_confidence(value: Any) -> bool:
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    if isinstance(value, (int, np.integer)) and int(value) in (0, 1):
        return bool(value)
    text = str(value).strip().lower()
    if text in {"true", "1", "yes", "y"}:
        return True
    if text in {"false", "0", "no", "n"}:
        return False
    raise ValueError(f"'{value}' is not a valid confidence_flag; use true or false")


def validate_snapshot(
    frame: pd.DataFrame,
    expected_bin_ids: Iterable[str],
    crane_lift_limit_kg: float,
    *,
    now_utc: datetime | None = None,
    stale_after_hours: float = 12.0,
    future_tolerance_minutes: float = 5.0,
    offline_after_hours: float | None = None,
) -> pd.DataFrame:
    """Validate a legacy predictive snapshot or a version-2 decision frame.

    Version-2 input keeps immutable event/provenance columns and supports
    per-bin acquisition times plus an explicit unavailable forecast. Legacy
    CSV/JSON retains its original shared-timestamp contract.
    """
    expected = [str(bin_id) for bin_id in expected_bin_ids]
    snapshot_versions = (
        set(frame["schema_version"].dropna().astype(str))
        if "schema_version" in frame.columns
        else set()
    )
    is_v2 = len(snapshot_versions) == 1 and snapshot_versions.issubset({"2.0", "2.1"})
    required_columns = (
        ("bin_id", "fill_pct", "weight_kg", "confidence_flag", "forecast_status", "risk_level")
        if is_v2
        else PREDICTIVE_COLUMNS
    )
    missing_columns = [column for column in required_columns if column not in frame.columns]
    if missing_columns:
        raise ValueError("Missing required columns: " + ", ".join(missing_columns))

    normalized = frame.copy() if is_v2 else frame.loc[:, PREDICTIVE_COLUMNS].copy()
    if len(normalized) != len(expected):
        raise ValueError(
            f"Expected exactly {len(expected)} rows, one for every bin; received {len(normalized)}"
        )
    normalized["bin_id"] = normalized["bin_id"].astype(str).str.strip().str.upper()
    duplicates = normalized.loc[normalized["bin_id"].duplicated(), "bin_id"].unique().tolist()
    if duplicates:
        raise ValueError("Duplicate bin_id values: " + ", ".join(duplicates))
    received = set(normalized["bin_id"])
    missing_ids = sorted(set(expected) - received)
    unexpected_ids = sorted(received - set(expected))
    if missing_ids or unexpected_ids:
        details = []
        if missing_ids:
            details.append("missing " + ", ".join(missing_ids))
        if unexpected_ids:
            details.append("unexpected " + ", ".join(unexpected_ids))
        raise ValueError("bin_id coverage is invalid: " + "; ".join(details))

    reference_time = (now_utc or datetime.now(timezone.utc)).astimezone(timezone.utc)
    parsed_timestamps: list[datetime | None] = []
    timestamp_errors: list[str] = []
    source_times = (
        normalized.get("observed_at", normalized.get("timestamp"))
        if is_v2
        else normalized["timestamp"]
    )
    clock_states = normalized.get(
        "clock_status", pd.Series("synchronized", index=normalized.index)
    ).astype(str).str.lower()
    for position, (value, clock_state) in enumerate(zip(source_times, clock_states), start=2):
        if clock_state not in {"synchronized", "unsynchronized", "ambiguous"}:
            timestamp_errors.append(f"row {position}: unsupported clock_status '{clock_state}'")
            parsed_timestamps.append(None)
            continue
        if clock_state != "synchronized":
            if value is not None and not pd.isna(value):
                timestamp_errors.append(
                    f"row {position}: {clock_state} clocks must not claim an acquisition timestamp"
                )
            parsed_timestamps.append(None)
            continue
        try:
            parsed_timestamps.append(_parse_timestamp(value))
        except ValueError as exc:
            timestamp_errors.append(f"row {position}: {exc}")
    if timestamp_errors:
        raise ValueError("Timestamp validation failed: " + "; ".join(timestamp_errors[:5]))
    valid_times = [value for value in parsed_timestamps if value is not None]
    if not is_v2 and len({value.isoformat() for value in valid_times}) != 1:
        raise ValueError(f"All {len(expected)} rows must have the same timestamp so they form one snapshot")
    age_values: list[float] = []
    for position, value in enumerate(parsed_timestamps, start=2):
        if value is None:
            age_values.append(float("nan"))
            continue
        age = (reference_time - value).total_seconds() / 3600.0
        if age < -future_tolerance_minutes / 60.0:
            raise ValueError(
                f"row {position}: observation is {-age * 60.0:.1f} minutes in the future; "
                f"the tolerance is {future_tolerance_minutes:g} minutes"
            )
        age_values.append(max(0.0, age))
    normalized["observed_at"] = [value.isoformat() if value else None for value in parsed_timestamps]
    normalized["timestamp"] = normalized["observed_at"]
    normalized["reading_age_hours"] = age_values
    normalized["stale_flag"] = [not np.isfinite(value) or value > stale_after_hours for value in age_values]
    normalized["offline_flag"] = [
        not np.isfinite(value)
        or (offline_after_hours is not None and value > offline_after_hours)
        for value in age_values
    ]
    if is_v2:
        decision_values = normalized.get("decision_at")
        if decision_values is not None and len(set(decision_values.astype(str))) != 1:
            raise ValueError("All version-2 rows must share one decision_at")

    for column in ("fill_pct", "weight_kg"):
        source = normalized[column]
        converted = pd.to_numeric(source, errors="coerce")
        invalid = converted.isna() & source.notna()
        if invalid.any():
            bad_rows = (np.flatnonzero(invalid.to_numpy()) + 2).tolist()
            raise ValueError(f"{column} must be numeric or null; invalid rows: {bad_rows[:5]}")
        normalized[column] = converted.astype(float)
    if "time_to_overflow_hours" not in normalized.columns:
        normalized["time_to_overflow_hours"] = np.nan
    normalized["time_to_overflow_hours"] = pd.to_numeric(
        normalized["time_to_overflow_hours"], errors="coerce"
    ).astype(float)
    if is_v2:
        forecast_status = normalized["forecast_status"].astype(str).str.lower()
        invalid_status = sorted(set(forecast_status) - set(FORECAST_STATUSES))
        if invalid_status:
            raise ValueError("Unsupported forecast_status values: " + ", ".join(invalid_status))
        has_tto = np.isfinite(normalized["time_to_overflow_hours"].to_numpy(dtype=float))
        if ((forecast_status == "available").to_numpy() != has_tto).any():
            raise ValueError(
                "time_to_overflow_hours must be finite only when forecast_status is available"
            )
        normalized["forecast_status"] = forecast_status
    else:
        invalid_tto = ~np.isfinite(normalized["time_to_overflow_hours"].to_numpy(dtype=float))
        if invalid_tto.any():
            bad_rows = (np.flatnonzero(invalid_tto) + 2).tolist()
            raise ValueError(
                f"time_to_overflow_hours must be a finite number; invalid rows: {bad_rows[:5]}"
            )
        normalized["forecast_status"] = "available"
    if ((normalized["fill_pct"].dropna() < 0) | (normalized["fill_pct"].dropna() > 100)).any():
        raise ValueError("fill_pct must be between 0 and 100 when present")
    if (
        (normalized["weight_kg"].dropna() < 0)
        | (normalized["weight_kg"].dropna() > crane_lift_limit_kg)
    ).any():
        raise ValueError(
            f"weight_kg must be null or between 0 and the {crane_lift_limit_kg:g} kg crane lift limit"
        )
    if (normalized["time_to_overflow_hours"].dropna() < 0).any():
        raise ValueError("time_to_overflow_hours cannot be negative")

    normalized["risk_level"] = normalized["risk_level"].astype(str).str.strip().str.lower()
    invalid_risks = sorted(set(normalized["risk_level"]) - set(ALLOWED_RISK_LEVELS))
    if invalid_risks:
        raise ValueError(
            "risk_level must be unknown, low, medium, high, or critical; invalid values: "
            + ", ".join(invalid_risks)
        )
    confidence: list[bool] = []
    confidence_errors: list[str] = []
    for row_number, value in enumerate(normalized["confidence_flag"], start=2):
        try:
            confidence.append(_parse_confidence(value))
        except ValueError as exc:
            confidence_errors.append(f"row {row_number}: {exc}")
    if confidence_errors:
        raise ValueError("Confidence validation failed: " + "; ".join(confidence_errors[:5]))
    normalized["confidence_flag"] = confidence
    if "source_mode" not in normalized.columns:
        normalized["source_mode"] = "legacy"
    if "snapshot_id" not in normalized.columns:
        source_stamp = valid_times[0].isoformat() if valid_times else reference_time.isoformat()
        digest = hashlib.sha256(
            (source_stamp + "|" + "|".join(expected)).encode("utf-8")
        ).hexdigest()[:20].upper()
        normalized["snapshot_id"] = f"LEGACY-{digest}"
    if "decision_at" not in normalized.columns:
        normalized["decision_at"] = reference_time.isoformat()
    if "event_id" not in normalized.columns:
        normalized["event_id"] = None
    if "quality_flags" not in normalized.columns:
        normalized["quality_flags"] = [tuple() for _ in range(len(normalized))]
    if "clock_status" not in normalized.columns:
        normalized["clock_status"] = "synchronized"
    if "forecast_method" not in normalized.columns:
        normalized["forecast_method"] = "legacy-upstream"
    if "model_version" not in normalized.columns:
        normalized["model_version"] = None

    order = {bin_id: index for index, bin_id in enumerate(expected)}
    normalized["_bin_order"] = normalized["bin_id"].map(order)
    normalized = normalized.sort_values("_bin_order").drop(columns="_bin_order").reset_index(drop=True)
    return normalized


def make_snapshot_template(bin_ids: Iterable[str], timestamp: datetime | None = None) -> pd.DataFrame:
    stamp = (timestamp or datetime.now(timezone.utc)).astimezone(timezone.utc).replace(microsecond=0)
    return pd.DataFrame(
        {
            "timestamp": stamp.isoformat(),
            "bin_id": list(bin_ids),
            "fill_pct": 0.0,
            "weight_kg": 0.0,
            "time_to_overflow_hours": 120.0,
            "risk_level": "low",
            "confidence_flag": True,
        }
    )


def make_demo_snapshot(bins: pd.DataFrame, timestamp: datetime | None = None) -> pd.DataFrame:
    """Create a deterministic, valid example with a non-trivial collection route."""
    frame = make_snapshot_template(bins["bin_id"], timestamp)
    capacities = bins["capacity_kg"].to_numpy(dtype=float)
    base_fill = np.array([28 + (index * 7) % 18 for index in range(len(frame))], dtype=float)
    frame["fill_pct"] = base_fill
    frame["weight_kg"] = np.round(capacities * base_fill / 100.0, 1)
    frame["time_to_overflow_hours"] = np.array(
        [120 + (index % 5) * 12 for index in range(len(frame))], dtype=float
    )

    examples = {
        "UGB-004": (94.0, 6.0, "critical", True),
        "UGB-005": (58.0, 64.0, "medium", True),
        "UGB-013": (82.0, 30.0, "high", True),
        "UGB-025": (76.0, 40.0, "high", False),
        "UGB-026": (52.0, 70.0, "medium", True),
    }
    for bin_id, values in examples.items():
        mask = frame["bin_id"] == bin_id
        if mask.any():
            fill, tto, risk, confidence = values
            capacity = float(bins.loc[mask, "capacity_kg"].iloc[0])
            frame.loc[mask, [
                "fill_pct",
                "weight_kg",
                "time_to_overflow_hours",
                "risk_level",
                "confidence_flag",
            ]] = (fill, round(capacity * fill / 100.0, 1), tto, risk, confidence)
    return frame


def build_dispatch_plan(
    snapshot: pd.DataFrame,
    bins: pd.DataFrame,
    distance_matrix_m: np.ndarray,
    config: Config,
    last_valid_readings: dict[str, dict[str, Any]] | None = None,
    duration_matrix_s: np.ndarray | None = None,
    *,
    optional_dispatch_allowed: bool = True,
    destination_matrices: dict[str, tuple[np.ndarray, np.ndarray]] | None = None,
) -> DispatchPlan:
    """Build a dynamic safety-constrained, trip-value collection proposal."""
    if snapshot["bin_id"].tolist() != bins["bin_id"].astype(str).tolist():
        raise ValueError("Snapshot rows must be normalized to the district bin order")
    if distance_matrix_m.shape != (len(bins) + 1, len(bins) + 1):
        raise ValueError("Road matrix must contain the depot plus every district bin")
    if duration_matrix_s is None:
        speed_mps = config.operations.fallback_road_speed_kph / 3.6
        duration_matrix_s = np.asarray(distance_matrix_m, dtype=float) / speed_mps
    if duration_matrix_s.shape != distance_matrix_m.shape:
        raise ValueError("Road duration matrix must match the distance matrix")
    destination_matrices = dict(destination_matrices or {})
    destination_matrices.setdefault(
        "waste_depot", (distance_matrix_m, duration_matrix_s)
    )
    for destination_id, (destination_distance, destination_duration) in destination_matrices.items():
        if destination_distance.shape != distance_matrix_m.shape:
            raise ValueError(
                f"Distance matrix for {destination_id} must contain the depot plus every bin"
            )
        if destination_duration.shape != duration_matrix_s.shape:
            raise ValueError(
                f"Duration matrix for {destination_id} must contain the depot plus every bin"
            )

    fill_pct = snapshot["fill_pct"].to_numpy(dtype=float)
    weights = snapshot["weight_kg"].to_numpy(dtype=float)
    tto = snapshot["time_to_overflow_hours"].to_numpy(dtype=float)
    risk = snapshot["risk_level"].to_numpy(dtype=object)
    confidence = snapshot["confidence_flag"].to_numpy(dtype=bool)
    operations = config.operations
    capacities = bins["capacity_kg"].to_numpy(dtype=float)
    capacity_litres = np.full(
        len(bins), config.waste.bin_capacity_litres, dtype=float
    )
    stale = snapshot.get("stale_flag", pd.Series(False, index=snapshot.index)).to_numpy(dtype=bool)
    age_hours = snapshot.get("reading_age_hours", pd.Series(0.0, index=snapshot.index)).to_numpy(
        dtype=float
    )
    fill_missing = ~np.isfinite(fill_pct)
    weight_missing = ~np.isfinite(weights)
    weight_fill_pct = np.divide(
        100.0 * weights,
        capacities,
        out=np.full_like(weights, np.nan),
        where=np.isfinite(weights) & (capacities > 0),
    )
    disagreement = (
        np.isfinite(fill_pct)
        & np.isfinite(weight_fill_pct)
        & (np.abs(fill_pct - weight_fill_pct) > config.sensor.disagreement_threshold_pct)
    )
    base_fill = np.where(
        np.isfinite(fill_pct) & np.isfinite(weight_fill_pct),
        np.maximum(fill_pct, weight_fill_pct),
        np.where(np.isfinite(fill_pct), fill_pct, weight_fill_pct),
    )
    high_margin = config.sensor.upper_uncertainty_z * config.sensor.fill_random_sd_pct
    one_sensor_missing = fill_missing ^ weight_missing
    trusted_dual = confidence & ~stale & ~disagreement & ~fill_missing & ~weight_missing
    margin = np.where(
        trusted_dual,
        high_margin,
        np.where(
            one_sensor_missing,
            config.sensor.single_sensor_margin_pct,
            config.sensor.low_confidence_margin_pct,
        ),
    )
    conservative_fill = np.where(np.isfinite(base_fill), base_fill + margin, np.nan)
    conservative_weight = np.where(
        np.isfinite(weights),
        weights + config.sensor.upper_uncertainty_z * config.sensor.weight_random_sd_kg,
        np.where(
            np.isfinite(conservative_fill),
            conservative_fill / 100.0 * capacities,
            capacities,
        ),
    )

    history = last_valid_readings or {}
    decision_text = str(
        snapshot.iloc[0].get("decision_at")
        or snapshot.iloc[0].get("timestamp")
        or datetime.now(timezone.utc).isoformat()
    )
    decision_time = _parse_timestamp(decision_text)
    for index, bin_id in enumerate(snapshot["bin_id"].astype(str)):
        previous = history.get(bin_id)
        if not previous or not (stale[index] or not confidence[index] or fill_missing[index] or weight_missing[index]):
            continue
        legacy = "fill" not in previous and "weight" not in previous
        fill_record = (
            {"observed_at": previous.get("timestamp"), "value": previous.get("fill_pct")}
            if legacy
            else previous.get("fill")
        )
        weight_record = (
            {"observed_at": previous.get("timestamp"), "value": previous.get("weight_kg")}
            if legacy
            else previous.get("weight")
        )
        previous_fill: float | None = None
        previous_fill_age = 0.0
        if isinstance(fill_record, dict):
            try:
                previous_fill = float(fill_record["value"])
                previous_fill_time = _parse_timestamp(fill_record["observed_at"])
                previous_fill_age = max(
                    0.0, (decision_time - previous_fill_time).total_seconds() / 3600.0
                )
            except (KeyError, TypeError, ValueError):
                previous_fill = None
        previous_weight: float | None = None
        if isinstance(weight_record, dict):
            try:
                previous_weight = float(weight_record["value"])
            except (KeyError, TypeError, ValueError):
                previous_weight = None
        retained_margin = (
            config.sensor.low_confidence_margin_pct
            if fill_missing[index] and weight_missing[index]
            else config.sensor.single_sensor_margin_pct
        )
        if previous_fill is not None:
            fallback_fill = (
                previous_fill
                + previous_fill_age * config.sensor.conservative_growth_pct_per_hour
                + retained_margin
            )
            conservative_fill[index] = (
                fallback_fill
                if not np.isfinite(conservative_fill[index])
                else max(conservative_fill[index], fallback_fill)
            )
            derived_weight = fallback_fill / 100.0 * capacities[index]
            conservative_weight[index] = (
                derived_weight
                if not np.isfinite(conservative_weight[index])
                else max(conservative_weight[index], derived_weight)
            )
        if previous_weight is not None:
            conservative_weight[index] = (
                previous_weight
                if not np.isfinite(conservative_weight[index])
                else max(conservative_weight[index], previous_weight)
            )

    conservative_fill = np.clip(conservative_fill, 0.0, 150.0)
    conservative_weight = np.clip(
        conservative_weight, 0.0, config.operations.crane_lift_limit_kg
    )

    review_reasons: list[list[str]] = [[] for _ in range(len(bins))]
    for index in range(len(bins)):
        clock_status = str(snapshot.iloc[index].get("clock_status", "synchronized"))
        if clock_status != "synchronized":
            review_reasons[index].append(f"clock {clock_status}; acquisition age unknown")
        if stale[index]:
            if np.isfinite(age_hours[index]):
                review_reasons[index].append(f"stale reading ({age_hours[index]:.1f}h old)")
            else:
                review_reasons[index].append("observation age unavailable")
        if bool(snapshot.iloc[index].get("offline_flag", False)):
            review_reasons[index].append("sensor offline by reporting-cadence policy")
        if fill_missing[index]:
            review_reasons[index].append("ultrasonic fill missing")
        if weight_missing[index]:
            review_reasons[index].append("load-cell weight missing")
        if fill_missing[index] and weight_missing[index] and not np.isfinite(conservative_fill[index]):
            review_reasons[index].append("no valid reading available; inspection required")
        if disagreement[index]:
            review_reasons[index].append("fill and weight sensors disagree")
        if not confidence[index]:
            review_reasons[index].append("low confidence")
        raw_quality = snapshot.iloc[index].get("quality_flags", ())
        quality_flags = (
            list(raw_quality)
            if isinstance(raw_quality, (list, tuple, set))
            else ([str(raw_quality)] if raw_quality else [])
        )
        for flag in quality_flags:
            if flag and flag not in {"weight_channel_unavailable"}:
                review_reasons[index].append(str(flag).replace("_", " "))
    review = [index for index, reasons in enumerate(review_reasons) if reasons]

    forecast_available = np.isfinite(tto)
    effective_tto = tto.copy()
    fallback_growth = max(config.sensor.conservative_growth_pct_per_hour, 1e-9)
    fallback_mask = ~forecast_available & np.isfinite(conservative_fill)
    effective_tto[fallback_mask] = np.maximum(
        0.0, (100.0 - conservative_fill[fallback_mask]) / fallback_growth
    )
    projected_fill_next = conservative_fill.copy()
    for index in range(len(bins)):
        if not np.isfinite(conservative_fill[index]):
            continue
        if forecast_available[index] and effective_tto[index] > 0:
            implied_growth = max(0.0, 100.0 - conservative_fill[index]) / effective_tto[index]
        else:
            implied_growth = fallback_growth
        projected_fill_next[index] = conservative_fill[index] + (
            implied_growth * operations.next_planning_opportunity_hours
        )

    # This is an explicit planning-risk proxy, not a calibrated probability.
    # `effective_tto` is derived from an upper q90 growth forecast. When that
    # upper path crosses after the next service opportunity, the chance of an
    # earlier overflow should be below the 10% service tolerance, not a flat
    # 5-12% merely because the legacy risk band says medium/high.
    risk_probability = {
        "unknown": 0.0,
        "low": 0.001,
        "medium": 0.005,
        "high": 0.02,
        "critical": 0.25,
    }
    overflow_probability = np.zeros(len(bins), dtype=float)
    model_probability = pd.to_numeric(
        snapshot.get(
            "overflow_probability_next_opportunity",
            pd.Series(np.nan, index=snapshot.index),
        ),
        errors="coerce",
    ).to_numpy(dtype=float)
    invalid_model_probability = np.isfinite(model_probability) & (
        (model_probability < 0.0) | (model_probability > 1.0)
    )
    if invalid_model_probability.any():
        raise ValueError("overflow_probability_next_opportunity must be in [0, 1]")
    model_probability_48h = pd.to_numeric(
        snapshot.get(
            "overflow_probability_48h",
            pd.Series(np.nan, index=snapshot.index),
        ),
        errors="coerce",
    ).to_numpy(dtype=float)
    invalid_model_probability_48h = np.isfinite(model_probability_48h) & (
        (model_probability_48h < 0.0) | (model_probability_48h > 1.0)
    )
    if invalid_model_probability_48h.any():
        raise ValueError("overflow_probability_48h must be in [0, 1]")
    for index in range(len(bins)):
        probability = risk_probability[str(risk[index])]
        horizon = effective_tto[index]
        if np.isfinite(horizon):
            opportunity = operations.next_planning_opportunity_hours
            if horizon <= 0:
                tto_probability = 1.0
            elif horizon <= opportunity:
                tto_probability = 0.10 + 0.90 * (1.0 - horizon / opportunity)
            else:
                tto_probability = 0.10 * (opportunity / horizon) ** 2
            probability = max(probability, tto_probability)
        if np.isfinite(projected_fill_next[index]):
            if projected_fill_next[index] >= 100:
                probability = max(probability, 0.10)
            elif projected_fill_next[index] >= operations.smart_dispatch_predicted_trigger_pct:
                probability = max(probability, 0.05)
            elif projected_fill_next[index] >= operations.smart_dispatch_current_trigger_pct:
                probability = max(probability, 0.01)
        if confidence[index] and not stale[index] and np.isfinite(model_probability[index]):
            probability = float(model_probability[index])
        overflow_probability[index] = min(1.0, probability)

    mandatory = sorted(
        (
            index
            for index in range(len(bins))
            if risk[index] == "critical"
            or (
                confidence[index]
                and not stale[index]
                and not np.isfinite(model_probability[index])
                and np.isfinite(effective_tto[index])
                and effective_tto[index]
                <= operations.smart_emergency_time_to_overflow_hours
            )
            or (
                confidence[index]
                and not stale[index]
                and conservative_fill[index] >= operations.uncertain_service_trigger_pct
            )
            or (
                confidence[index]
                and not stale[index]
                and overflow_probability[index]
                >= 1.0 - operations.overflow_service_probability
            )
        ),
        key=lambda index: (
            effective_tto[index] if np.isfinite(effective_tto[index]) else float("inf"),
            -conservative_fill[index] if np.isfinite(conservative_fill[index]) else 0.0,
            str(bins.iloc[index]["bin_id"]),
        ),
    )

    compacted_volume_m3 = np.where(
        np.isfinite(conservative_fill),
        np.clip(conservative_fill, 0.0, 100.0)
        / 100.0
        * capacity_litres
        / 1000.0
        / operations.truck_compaction_ratio,
        capacity_litres / 1000.0 / operations.truck_compaction_ratio,
    )
    truck_volume_m3 = operations.truck_body_volume_m3
    feasible_mandatory, unserved_required = select_dual_capacity_feasible(
        mandatory,
        conservative_weight,
        compacted_volume_m3,
        operations.truck_capacity_kg,
        truck_volume_m3,
        operations.max_daily_trips,
    )
    feasible_mandatory_set = set(feasible_mandatory)
    mandatory_services = {
        int(bins.iloc[index]["service_index"]) for index in feasible_mandatory
    }

    candidate_set = set(feasible_mandatory)
    sibling_candidates: set[int] = set()
    economic_fill_estimate = np.clip(base_fill, 0.0, 100.0)
    for index in range(len(bins)):
        quality_eligible = confidence[index] and not stale[index] and np.isfinite(conservative_fill[index])
        economically_ready = (
            np.isfinite(economic_fill_estimate[index])
            and economic_fill_estimate[index]
            >= operations.smart_optional_min_central_fill_pct
        )
        due_before_next_batch = (
            optional_dispatch_allowed
            and confidence[index]
            and not stale[index]
            and np.isfinite(effective_tto[index])
            and effective_tto[index] <= operations.smart_min_dispatch_gap_hours
        )
        if index in feasible_mandatory_set:
            continue
        same_service = int(bins.iloc[index]["service_index"]) in mandatory_services
        projected_trigger = (
            np.isfinite(projected_fill_next[index])
            and projected_fill_next[index] >= operations.smart_include_predicted_trigger_pct
        )
        is_candidate = (
            quality_eligible
            and (economically_ready or due_before_next_batch)
            and (
                risk[index] in {"medium", "high"}
                or conservative_fill[index] >= operations.smart_include_current_trigger_pct
                or (
                    np.isfinite(effective_tto[index])
                    and effective_tto[index] <= operations.smart_sibling_include_time_to_overflow_hours
                )
                or projected_trigger
            )
        )
        is_sibling = quality_eligible and economically_ready and same_service and (
            conservative_fill[index] >= operations.smart_sibling_include_current_pct
            or (
                np.isfinite(effective_tto[index])
                and effective_tto[index] <= operations.smart_sibling_include_time_to_overflow_hours
            )
        )
        if is_candidate or is_sibling:
            candidate_set.add(index)
        if is_sibling:
            sibling_candidates.add(index)

    # A fresh uncertain/high-fill bin may join a scheduled batch only when its
    # site already has at least two confident eligible bins (or mandatory
    # service). It cannot bootstrap a route from its own uncertainty margin.
    confident_service_counts = Counter(
        int(bins.iloc[index]["service_index"]) for index in candidate_set
    )
    for index in range(len(bins)):
        service_index = int(bins.iloc[index]["service_index"])
        uncertain_scheduled_candidate = (
            optional_dispatch_allowed
            and index not in candidate_set
            and not stale[index]
            and not confidence[index]
            and np.isfinite(conservative_fill[index])
            and conservative_fill[index]
            >= operations.smart_dispatch_current_trigger_pct
            and (
                service_index in mandatory_services
                or confident_service_counts[service_index] >= 2
            )
        )
        if uncertain_scheduled_candidate:
            candidate_set.add(index)

    # A six-hour alarm alone creates one-stop emergency trips. For optional
    # consolidation, amortize the calibrated 48-hour probability across the
    # eight six-hour planning opportunities in that horizon. Candidates still
    # must meet fill/risk/TTO eligibility; the longer horizon cannot make a stop
    # mandatory and it is ignored when evidence is stale or low confidence.
    trip_value_probability = overflow_probability.copy()
    consolidation_discount = min(
        1.0,
        operations.next_planning_opportunity_hours
        / max(operations.forecast_horizon_hours, 1e-9),
    )
    eligible_probability_48h = (
        confidence
        & ~stale
        & np.isfinite(model_probability_48h)
    )
    trip_value_probability[eligible_probability_48h] = np.maximum(
        trip_value_probability[eligible_probability_48h],
        model_probability_48h[eligible_probability_48h] * consolidation_discount,
    )
    skip_penalties = (
        trip_value_probability * operations.overflow_avoidance_value_m
        + np.maximum(
            0.0,
            trip_value_probability - operations.overflow_service_probability,
        )
        * operations.emergency_avoidance_value_m
    )
    low_fill_costs = np.maximum(
        0.0, operations.wasted_pickup_threshold_pct - economic_fill_estimate
    ) * operations.low_fill_cost_m_per_pct
    low_fill_costs = np.where(np.isfinite(low_fill_costs), low_fill_costs, 0.0)
    candidates = sorted(
        candidate_set,
        key=lambda index: (
            index not in feasible_mandatory_set,
            -float(skip_penalties[index]),
            effective_tto[index] if np.isfinite(effective_tto[index]) else float("inf"),
            str(bins.iloc[index]["bin_id"]),
        ),
    )
    stream_values = (
        bins["waste_stream"].fillna("mixed_general_waste").astype(str).tolist()
        if "waste_stream" in bins.columns
        else ["mixed_general_waste"] * len(bins)
    )
    destination_values = (
        bins["destination_id"].fillna("waste_depot").astype(str).tolist()
        if "destination_id" in bins.columns
        else ["waste_depot"] * len(bins)
    )

    def stream_destination_and_matrices(
        indices: list[int],
    ) -> tuple[str, np.ndarray, np.ndarray]:
        destinations = {destination_values[index] for index in indices}
        if len(destinations) != 1:
            raise ValueError("A compatible waste stream cannot mix unload destinations")
        destination_id = next(iter(destinations))
        matrices = destination_matrices.get(destination_id)
        if matrices is None:
            raise ValueError(
                f"No trusted road matrix is configured for unload destination {destination_id}"
            )
        return destination_id, matrices[0], matrices[1]

    candidate_streams = sorted({stream_values[index] for index in candidates})
    if not feasible_mandatory and not optional_dispatch_allowed:
        route_plan = RoutePlan(
            routes=[],
            distance_m=0,
            served_bin_indices=[],
            solver_method="optional_consolidation_gap",
            dropped_bin_indices=candidates,
            dispatch_reason="optional_consolidation_gap",
        )
    elif not candidates:
        route_plan = RoutePlan(
            routes=[],
            distance_m=0,
            served_bin_indices=[],
            solver_method="value_none",
            dispatch_reason="no_candidate",
        )
    elif len(candidate_streams) <= 1:
        destination_id, active_distance_matrix, active_duration_matrix = (
            stream_destination_and_matrices(candidates)
        )
        route_plan = solve_value_routes(
            candidates,
            feasible_mandatory,
            conservative_weight,
            compacted_volume_m3,
            active_distance_matrix,
            active_duration_matrix,
            skip_penalties,
            operations.truck_capacity_kg,
            truck_volume_m3,
            operations.max_daily_trips,
            operations.service_minutes_per_bin * 60.0,
            operations.max_route_duration_minutes * 60.0,
            operations.route_fixed_cost_m_equivalent,
            operations.travel_time_cost_m_per_minute,
            operations.service_cost_m_per_minute,
            low_fill_costs,
            operations.route_solver_milliseconds,
            minimum_net_value_m_equivalent=operations.minimum_route_value_m,
            post_optimize=operations.route_post_optimization_enabled,
        )
        route_plan = replace(
            route_plan,
            route_destinations=[destination_id] * len(route_plan.routes),
        )
    else:
        stream_plans: list[RoutePlan] = []
        remaining_trips = operations.max_daily_trips
        for stream in sorted(
            candidate_streams,
            key=lambda value: (
                not any(
                    stream_values[index] == value for index in feasible_mandatory
                ),
                value,
            ),
        ):
            stream_candidates = [
                index for index in candidates if stream_values[index] == stream
            ]
            destination_id, active_distance_matrix, active_duration_matrix = (
                stream_destination_and_matrices(stream_candidates)
            )
            stream_mandatory = [
                index for index in feasible_mandatory if stream_values[index] == stream
            ]
            if remaining_trips <= 0:
                stream_plans.append(
                    RoutePlan(
                        [],
                        0,
                        [],
                        "stream_trip_limit",
                        dropped_bin_indices=stream_candidates,
                        dispatch_reason="stream_trip_limit",
                    )
                )
                continue
            stream_plan = solve_value_routes(
                stream_candidates,
                stream_mandatory,
                conservative_weight,
                compacted_volume_m3,
                active_distance_matrix,
                active_duration_matrix,
                skip_penalties,
                operations.truck_capacity_kg,
                truck_volume_m3,
                remaining_trips,
                operations.service_minutes_per_bin * 60.0,
                operations.max_route_duration_minutes * 60.0,
                operations.route_fixed_cost_m_equivalent,
                operations.travel_time_cost_m_per_minute,
                operations.service_cost_m_per_minute,
                low_fill_costs,
                operations.route_solver_milliseconds,
                minimum_net_value_m_equivalent=operations.minimum_route_value_m,
                post_optimize=operations.route_post_optimization_enabled,
            )
            stream_plan = replace(
                stream_plan,
                route_destinations=[destination_id] * len(stream_plan.routes),
            )
            stream_plans.append(stream_plan)
            remaining_trips -= len(stream_plan.routes)
        combined_routes = [route for plan in stream_plans for route in plan.routes]
        route_plan = RoutePlan(
            routes=combined_routes,
            distance_m=sum(plan.distance_m for plan in stream_plans),
            served_bin_indices=[
                index for plan in stream_plans for index in plan.served_bin_indices
            ],
            solver_method="stream_separated:" + "+".join(
                sorted({plan.solver_method for plan in stream_plans})
            ),
            dropped_bin_indices=sorted(
                {index for plan in stream_plans for index in plan.dropped_bin_indices}
            ),
            route_duration_s=[
                value for plan in stream_plans for value in plan.route_duration_s
            ],
            route_loads_kg=[
                value for plan in stream_plans for value in plan.route_loads_kg
            ],
            route_volumes_m3=[
                value for plan in stream_plans for value in plan.route_volumes_m3
            ],
            objective_cost_m_equivalent=sum(
                plan.objective_cost_m_equivalent for plan in stream_plans
            ),
            operating_cost_m_equivalent=sum(
                plan.operating_cost_m_equivalent for plan in stream_plans
            ),
            avoided_loss_value_m_equivalent=sum(
                plan.avoided_loss_value_m_equivalent for plan in stream_plans
            ),
            net_value_m_equivalent=sum(
                plan.net_value_m_equivalent for plan in stream_plans
            ),
            dispatch_reason=(
                "stream_separated_emergency_service"
                if feasible_mandatory
                else (
                    "stream_separated_positive_value"
                    if combined_routes
                    else "no_positive_value_route"
                )
            ),
            route_destinations=[
                destination
                for plan in stream_plans
                for destination in plan.route_destinations
            ],
        )
    served_set = set(route_plan.served_bin_indices)
    unserved_required = sorted(set(unserved_required) | (set(mandatory) - served_set))
    selected_siblings = sorted(served_set & sibling_candidates)
    selected_optional = sorted(served_set - feasible_mandatory_set - sibling_candidates)
    deferred = sorted(set(candidates) - served_set)
    distance_budget_m = operations.smart_max_dispatch_distance_km * 1000.0

    warnings: list[str] = []
    if review:
        ids = ", ".join(str(bins.iloc[index]["bin_id"]) for index in review)
        warnings.append(f"Operator review required for stale, missing, or low-quality readings: {ids}")
    if unserved_required:
        ids = ", ".join(str(bins.iloc[index]["bin_id"]) for index in unserved_required)
        warnings.append(f"Daily truck capacity could not cover required bins: {ids}")
    if not optional_dispatch_allowed and not mandatory and candidates:
        warnings.append(
            "Optional work is deferred inside the configured consolidation gap; "
            "emergency/service constraints remain eligible."
        )
    if route_plan.distance_m > distance_budget_m and mandatory:
        warnings.append(
            "The required route exceeds the optional 30 km planning budget; safety-critical bins were retained."
        )
    over_nominal = [
        index
        for index in served_set
        if weights[index] > float(bins.iloc[index]["capacity_kg"]) + 1e-9
    ]
    if over_nominal:
        ids = ", ".join(str(bins.iloc[index]["bin_id"]) for index in over_nominal)
        warnings.append(f"Measured weight exceeds the nominal 540 kg bin capacity: {ids}")
    inconsistent = [
        index
        for index in served_set
        if np.isfinite(fill_pct[index])
        and np.isfinite(weights[index])
        and fill_pct[index] >= 65
        and weights[index] <= 1.0
    ]
    if inconsistent:
        ids = ", ".join(str(bins.iloc[index]["bin_id"]) for index in inconsistent)
        warnings.append(f"High fill but near-zero weight needs sensor inspection: {ids}")

    required_set = set(mandatory)
    sibling_set = set(selected_siblings)
    optional_set = set(selected_optional)
    unserved_set = set(unserved_required)
    audit_rows: list[dict[str, Any]] = []
    for index in range(len(bins)):
        if index in required_set and index in served_set:
            selection_class = "Required"
        elif index in unserved_set:
            selection_class = "Unserved required"
        elif index in review and index not in served_set:
            selection_class = "Inspection required"
        elif index in sibling_set:
            selection_class = "Co-located sibling"
        elif index in optional_set:
            selection_class = "Positive-value optional pickup"
        elif index in deferred:
            selection_class = "Defer – wait or merge"
        else:
            selection_class = "Wait"
        reasons = list(review_reasons[index])
        if risk[index] in {"high", "critical"}:
            reasons.append(f"{risk[index]} risk")
        if np.isfinite(effective_tto[index]) and effective_tto[index] <= operations.smart_dispatch_time_to_overflow_hours:
            method = "forecast" if forecast_available[index] else "fallback"
            reasons.append(f"{method} overflow horizon {effective_tto[index]:g}h")
        if conservative_fill[index] >= operations.smart_dispatch_current_trigger_pct:
            reasons.append(f"conservative upper fill {conservative_fill[index]:.1f}%")
        if not reasons:
            reasons.append(selection_class.lower())
        audit_rows.append(
            {
                "bin_id": str(bins.iloc[index]["bin_id"]),
                "site_id": str(bins.iloc[index]["site_id"]),
                "selection": selection_class,
                "reason": ", ".join(reasons),
                "fill_pct": float(fill_pct[index]) if np.isfinite(fill_pct[index]) else None,
                "weight_kg": float(weights[index]) if np.isfinite(weights[index]) else None,
                "conservative_upper_fill_pct": (
                    float(conservative_fill[index])
                    if np.isfinite(conservative_fill[index])
                    else None
                ),
                "conservative_upper_weight_kg": (
                    float(conservative_weight[index])
                    if np.isfinite(conservative_weight[index])
                    else None
                ),
                "time_to_overflow_hours": (
                    float(tto[index]) if np.isfinite(tto[index]) else None
                ),
                "effective_time_to_overflow_hours": (
                    float(effective_tto[index]) if np.isfinite(effective_tto[index]) else None
                ),
                "forecast_status": str(snapshot.iloc[index].get("forecast_status", "available")),
                "forecast_method": str(snapshot.iloc[index].get("forecast_method", "legacy-upstream")),
                "projected_fill_next_opportunity_pct": (
                    float(projected_fill_next[index]) if np.isfinite(projected_fill_next[index]) else None
                ),
                "overflow_probability_before_next_opportunity": float(overflow_probability[index]),
                "overflow_probability_48h": (
                    float(model_probability_48h[index])
                    if np.isfinite(model_probability_48h[index])
                    else None
                ),
                "trip_value_overflow_probability": float(trip_value_probability[index]),
                "pickup_avoided_loss_value_m_equivalent": float(skip_penalties[index]),
                "low_fill_service_cost_m_equivalent": float(low_fill_costs[index]),
                "risk_level": str(risk[index]),
                "confidence_flag": bool(confidence[index]),
                "reading_age_hours": float(age_hours[index]),
                "collection_state": selection_class,
            }
        )
    rows = [row for index, row in enumerate(audit_rows) if index in served_set]
    inspection_required = bool(review)
    if mandatory or route_plan.routes:
        decision_state = COLLECTION_REQUIRED
    elif inspection_required:
        decision_state = INSPECTION_REQUIRED
    else:
        decision_state = NO_COLLECTION_REQUIRED

    snapshot_id = str(snapshot.iloc[0].get("snapshot_id", ""))
    config_hash = hashlib.sha256(
        json.dumps(config.to_dict(), sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()[:12]
    plan_material = f"{snapshot_id}|{POLICY_VERSION}|{config_hash}|{','.join(map(str, route_plan.served_bin_indices))}"
    plan_id = "PLAN-" + hashlib.sha256(plan_material.encode("utf-8")).hexdigest()[:20].upper()
    source_event_ids = tuple(
        sorted(str(value) for value in snapshot.get("event_id", pd.Series(dtype=object)).dropna())
    )
    return DispatchPlan(
        snapshot_timestamp=decision_time.isoformat(),
        decision_state=decision_state,
        collection_required=bool(mandatory or route_plan.routes),
        inspection_required=inspection_required,
        route_plan=route_plan,
        selected_bin_indices=list(route_plan.served_bin_indices),
        required_bin_indices=mandatory,
        sibling_bin_indices=selected_siblings,
        optional_bin_indices=selected_optional,
        unserved_required_bin_indices=unserved_required,
        review_bin_indices=review,
        selection_rows=rows,
        audit_rows=audit_rows,
        warnings=tuple(warnings),
        plan_id=plan_id,
        source_mode=str(snapshot.iloc[0].get("source_mode", "legacy")),
        source_event_ids=source_event_ids,
        decision_at=decision_time.isoformat(),
        deferred_bin_indices=deferred,
    )


def update_last_valid_readings(
    history: dict[str, dict[str, Any]],
    snapshot: pd.DataFrame,
    bins: pd.DataFrame,
    config: Config,
) -> dict[str, dict[str, Any]]:
    """Retain fresh last-good values independently for fill and weight."""
    updated = dict(history)
    capacities = bins["capacity_kg"].to_numpy(dtype=float)
    for index, row in snapshot.iterrows():
        fill = row["fill_pct"]
        weight = row["weight_kg"]
        if not bool(row["confidence_flag"]) or bool(row.get("stale_flag", False)):
            continue
        bin_id = str(row["bin_id"])
        prior = dict(updated.get(bin_id, {}))
        observed_at = str(row.get("observed_at") or row.get("timestamp"))
        provenance = {
            "observed_at": observed_at,
            "event_id": row.get("event_id"),
            "calibration_version": row.get("calibration_version"),
            "source_mode": row.get("source_mode", "legacy"),
        }
        if np.isfinite(fill):
            prior["fill"] = provenance | {"value": float(fill), "unit": "percent"}
        if np.isfinite(weight):
            mutually_consistent = True
            if np.isfinite(fill):
                weight_fill = 100.0 * float(weight) / capacities[index]
                mutually_consistent = (
                    abs(float(fill) - weight_fill)
                    <= config.sensor.disagreement_threshold_pct
                )
            if mutually_consistent:
                prior["weight"] = provenance | {"value": float(weight), "unit": "kg"}
        if prior:
            updated[bin_id] = prior
    return updated


def load_last_valid_readings(path: str | Path) -> dict[str, dict[str, Any]]:
    source = Path(path)
    if not source.exists():
        return {}
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValueError(f"Last-good history could not be read: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Last-good history is corrupt at line {exc.lineno}; the original file was preserved"
        ) from exc
    if not isinstance(payload, dict):
        raise ValueError("Last-good history must be a JSON object")
    if "schema_version" not in payload:
        return payload
    if payload.get("schema_version") != "2.0" or not isinstance(payload.get("bins"), dict):
        raise ValueError(
            f"Unsupported last-good history schema_version: {payload.get('schema_version')}"
        )
    return payload["bins"]


def save_last_valid_readings(history: dict[str, dict[str, Any]], path: str | Path) -> None:
    """Atomically replace history while excluding other UI/runner writers."""
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    lock = output.with_suffix(output.suffix + ".lock")
    deadline = time.monotonic() + 5.0
    lock_fd: int | None = None
    while lock_fd is None:
        try:
            lock_fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(lock_fd, str(os.getpid()).encode("ascii"))
        except FileExistsError as exc:
            if time.monotonic() >= deadline:
                raise ValueError(
                    f"Last-good history is locked by another writer: {lock}"
                ) from exc
            time.sleep(0.05)
    try:
        _write_last_valid_readings_unlocked(history, output)
    finally:
        os.close(lock_fd)
        lock.unlink(missing_ok=True)


def _write_last_valid_readings_unlocked(
    history: dict[str, dict[str, Any]], output: Path
) -> None:
    payload = {
        "schema_version": "2.0",
        "updated_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "bins": history,
    }
    temporary = output.with_suffix(output.suffix + f".{uuid4().hex}.tmp")
    temporary.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    try:
        os.replace(temporary, output)
    finally:
        temporary.unlink(missing_ok=True)


def update_last_valid_readings_file(
    snapshot: pd.DataFrame,
    bins: pd.DataFrame,
    config: Config,
    path: str | Path,
) -> dict[str, dict[str, Any]]:
    """Serialize the complete read/merge/write operation across UI and runner."""
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    lock = output.with_suffix(output.suffix + ".lock")
    deadline = time.monotonic() + 5.0
    lock_fd: int | None = None
    while lock_fd is None:
        try:
            lock_fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(lock_fd, str(os.getpid()).encode("ascii"))
        except FileExistsError as exc:
            if time.monotonic() >= deadline:
                raise ValueError(
                    f"Last-good history is locked by another writer: {lock}"
                ) from exc
            time.sleep(0.05)
    try:
        current = load_last_valid_readings(output)
        merged = update_last_valid_readings(current, snapshot, bins, config)
        _write_last_valid_readings_unlocked(merged, output)
        return merged
    finally:
        os.close(lock_fd)
        lock.unlink(missing_ok=True)


def route_loads_kg(plan: DispatchPlan, snapshot: pd.DataFrame) -> list[float]:
    weights = np.array(
        [row["conservative_upper_weight_kg"] for row in plan.audit_rows],
        dtype=float,
    )
    return [
        float(sum(weights[index] for index in route if index != -1))
        for route in plan.route_plan.routes
    ]


def mock_dispatch_payload(
    plan: DispatchPlan,
    snapshot: pd.DataFrame,
    bins: pd.DataFrame,
    config: Config,
) -> dict[str, Any]:
    loads = route_loads_kg(plan, snapshot)
    routes = []
    for trip_number, (route, load) in enumerate(zip(plan.route_plan.routes, loads), start=1):
        route_position = trip_number - 1
        route_destinations = plan.route_plan.route_destinations
        destination_id = (
            route_destinations[route_position]
            if route_position < len(route_destinations)
            else "waste_depot"
        )
        bin_stops = [str(bins.iloc[index]["bin_id"]) for index in route if index != -1]
        stops = ["DEPOT", *bin_stops]
        if destination_id == "recycling_facility":
            stops.extend([config.pilot.recycling_facility_id, "DEPOT"])
        else:
            stops.append("DEPOT")
        routes.append(
            {
                "trip_number": trip_number,
                "vehicle_id": "MOCK-TRUCK-01",
                "stops": stops,
                "unload_destination": destination_id,
                "estimated_load_kg": round(load, 1),
            }
        )
    return {
        "dispatch_id": f"MOCK-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}-{uuid4().hex[:8].upper()}",
        "mode": "MOCK",
        "status": "MOCK_SENT_TO_TRUCK",
        "created_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "snapshot_timestamp": plan.snapshot_timestamp,
        "plan_id": plan.plan_id,
        "plan_schema_version": plan.plan_schema_version,
        "policy_version": plan.policy_version,
        "source_mode": plan.source_mode,
        "source_event_ids": list(plan.source_event_ids),
        "vehicle_id": "MOCK-TRUCK-01",
        "depot": {
            "label": config.pilot.depot_label,
            "latitude": config.pilot.depot_lat,
            "longitude": config.pilot.depot_lon,
        },
        "recycling_facility": {
            "id": config.pilot.recycling_facility_id,
            "label": config.pilot.recycling_facility_label,
            "latitude": config.pilot.recycling_facility_lat,
            "longitude": config.pilot.recycling_facility_lon,
        },
        "route_distance_km": round(plan.route_plan.distance_m / 1000.0, 3),
        "trip_count": len(plan.route_plan.routes),
        "selected_bin_count": plan.selected_count,
        "operating_cost_m_equivalent": round(
            plan.route_plan.operating_cost_m_equivalent, 1
        ),
        "avoided_loss_value_m_equivalent": round(
            plan.route_plan.avoided_loss_value_m_equivalent, 1
        ),
        "net_trip_value_m_equivalent": round(
            plan.route_plan.net_value_m_equivalent, 1
        ),
        "dispatch_reason": plan.route_plan.dispatch_reason,
        "selected_bins": plan.selection_rows,
        "routes": routes,
        "warnings": list(plan.warnings),
        "disclaimer": "Prototype-only local record. No message was sent to a real vehicle.",
    }


def save_mock_dispatch(payload: dict[str, Any], path: str | Path) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def load_mock_dispatches(path: str | Path, limit: int = 20) -> list[dict[str, Any]]:
    source = Path(path)
    if not source.exists():
        return []
    records: list[dict[str, Any]] = []
    for line in source.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(record, dict):
            records.append(record)
    return records[-max(1, int(limit)) :][::-1]
