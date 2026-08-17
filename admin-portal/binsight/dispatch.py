from __future__ import annotations

import io
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from uuid import uuid4

import numpy as np
import pandas as pd

from .config import Config
from .routing import (
    RoutePlan,
    incremental_proxy_distance_m,
    select_capacity_feasible,
    solve_routes,
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
ALLOWED_RISK_LEVELS = ("low", "medium", "high", "critical")
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

    @property
    def selected_count(self) -> int:
        return len(self.selected_bin_indices)


def _parse_json_records(raw_text: str) -> pd.DataFrame:
    try:
        payload = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"The JSON is invalid: {exc.msg} at line {exc.lineno}") from exc
    if isinstance(payload, dict):
        if "bins" not in payload:
            raise ValueError("A JSON object must contain a 'bins' array")
        payload = payload["bins"]
    if not isinstance(payload, list):
        raise ValueError("JSON input must be an array of bin records or an object with a 'bins' array")
    if not payload or any(not isinstance(row, dict) for row in payload):
        raise ValueError("The JSON bins array must contain record objects")
    return pd.DataFrame(payload)


def parse_snapshot_bytes(content: bytes, filename: str) -> pd.DataFrame:
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
        return _parse_json_records(text)
    raise ValueError("Upload a .csv or .json file")


def parse_snapshot_json(raw_text: str) -> pd.DataFrame:
    return _parse_json_records(raw_text)


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
) -> pd.DataFrame:
    """Validate and normalize one complete predictive-AI snapshot."""
    expected = [str(bin_id) for bin_id in expected_bin_ids]
    missing_columns = [column for column in PREDICTIVE_COLUMNS if column not in frame.columns]
    if missing_columns:
        raise ValueError("Missing required columns: " + ", ".join(missing_columns))

    normalized = frame.loc[:, PREDICTIVE_COLUMNS].copy()
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

    timestamp_errors: list[str] = []
    parsed_timestamps: list[datetime] = []
    for row_number, value in enumerate(normalized["timestamp"], start=2):
        try:
            parsed_timestamps.append(_parse_timestamp(value))
        except ValueError as exc:
            timestamp_errors.append(f"row {row_number}: {exc}")
    if timestamp_errors:
        raise ValueError("Timestamp validation failed: " + "; ".join(timestamp_errors[:5]))
    timestamp_values = {value.isoformat() for value in parsed_timestamps}
    if len(timestamp_values) != 1:
        raise ValueError("All 33 rows must have the same timestamp so they form one snapshot")
    normalized["timestamp"] = [value.isoformat() for value in parsed_timestamps]
    snapshot_time = parsed_timestamps[0]
    reference_time = (now_utc or datetime.now(timezone.utc)).astimezone(timezone.utc)
    age_hours = (reference_time - snapshot_time).total_seconds() / 3600.0
    if age_hours < -future_tolerance_minutes / 60.0:
        raise ValueError(
            f"Snapshot timestamp is {-age_hours * 60.0:.1f} minutes in the future; "
            f"the tolerance is {future_tolerance_minutes:g} minutes"
        )
    normalized["reading_age_hours"] = max(0.0, age_hours)
    normalized["stale_flag"] = age_hours > stale_after_hours

    for column in ("fill_pct", "weight_kg"):
        source = normalized[column]
        converted = pd.to_numeric(source, errors="coerce")
        invalid = converted.isna() & source.notna()
        if invalid.any():
            bad_rows = (np.flatnonzero(invalid.to_numpy()) + 2).tolist()
            raise ValueError(f"{column} must be numeric or null; invalid rows: {bad_rows[:5]}")
        normalized[column] = converted.astype(float)
    normalized["time_to_overflow_hours"] = pd.to_numeric(
        normalized["time_to_overflow_hours"], errors="coerce"
    )
    invalid_tto = ~np.isfinite(normalized["time_to_overflow_hours"].to_numpy(dtype=float))
    if invalid_tto.any():
        bad_rows = (np.flatnonzero(invalid_tto) + 2).tolist()
        raise ValueError(
            f"time_to_overflow_hours must be a finite number; invalid rows: {bad_rows[:5]}"
        )
    if ((normalized["fill_pct"].dropna() < 0) | (normalized["fill_pct"].dropna() > 100)).any():
        raise ValueError("fill_pct must be between 0 and 100 when present")
    if (
        (normalized["weight_kg"].dropna() < 0)
        | (normalized["weight_kg"].dropna() > crane_lift_limit_kg)
    ).any():
        raise ValueError(
            f"weight_kg must be null or between 0 and the {crane_lift_limit_kg:g} kg crane lift limit"
        )
    if (normalized["time_to_overflow_hours"] < 0).any():
        raise ValueError("time_to_overflow_hours cannot be negative")

    normalized["risk_level"] = normalized["risk_level"].astype(str).str.strip().str.lower()
    invalid_risks = sorted(set(normalized["risk_level"]) - set(ALLOWED_RISK_LEVELS))
    if invalid_risks:
        raise ValueError(
            "risk_level must be low, medium, high, or critical; invalid values: "
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
        "UGB-004": (94.0, 507.6, 6.0, "critical", True),
        "UGB-005": (58.0, 313.2, 64.0, "medium", True),
        "UGB-013": (82.0, 442.8, 30.0, "high", True),
        "UGB-025": (76.0, 410.4, 40.0, "high", False),
        "UGB-026": (52.0, 280.8, 70.0, "medium", True),
    }
    for bin_id, values in examples.items():
        mask = frame["bin_id"] == bin_id
        if mask.any():
            frame.loc[mask, [
                "fill_pct",
                "weight_kg",
                "time_to_overflow_hours",
                "risk_level",
                "confidence_flag",
            ]] = values
    return frame


def build_dispatch_plan(
    snapshot: pd.DataFrame,
    bins: pd.DataFrame,
    distance_matrix_m: np.ndarray,
    config: Config,
    last_valid_readings: dict[str, dict[str, Any]] | None = None,
) -> DispatchPlan:
    """Turn a validated AI snapshot into capacity-feasible OSM-road collection trips."""
    if snapshot["bin_id"].tolist() != bins["bin_id"].astype(str).tolist():
        raise ValueError("Snapshot rows must be normalized to the district bin order")
    if distance_matrix_m.shape != (len(bins) + 1, len(bins) + 1):
        raise ValueError("Road matrix must contain the depot plus every district bin")

    fill_pct = snapshot["fill_pct"].to_numpy(dtype=float)
    weights = snapshot["weight_kg"].to_numpy(dtype=float)
    tto = snapshot["time_to_overflow_hours"].to_numpy(dtype=float)
    risk = snapshot["risk_level"].to_numpy(dtype=object)
    confidence = snapshot["confidence_flag"].to_numpy(dtype=bool)
    operations = config.operations
    capacities = bins["capacity_kg"].to_numpy(dtype=float)
    stale = snapshot.get("stale_flag", pd.Series(False, index=snapshot.index)).to_numpy(dtype=bool)
    age_hours = snapshot.get("reading_age_hours", pd.Series(0.0, index=snapshot.index)).to_numpy(
        dtype=float
    )
    fill_missing = ~np.isfinite(fill_pct)
    weight_missing = ~np.isfinite(weights)
    weight_fill_pct = 100.0 * weights / capacities
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
    margin = np.where(
        confidence & ~stale & ~disagreement,
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
    snapshot_time = _parse_timestamp(snapshot.iloc[0]["timestamp"])
    for index, bin_id in enumerate(snapshot["bin_id"].astype(str)):
        previous = history.get(bin_id)
        if not previous or not (stale[index] or not confidence[index] or fill_missing[index] or weight_missing[index]):
            continue
        try:
            previous_time = _parse_timestamp(previous["timestamp"])
            previous_age = max(0.0, (snapshot_time - previous_time).total_seconds() / 3600.0)
            previous_fill = float(previous["fill_pct"])
            previous_weight = float(previous["weight_kg"])
        except (KeyError, TypeError, ValueError):
            continue
        retained_margin = (
            config.sensor.low_confidence_margin_pct
            if fill_missing[index] and weight_missing[index]
            else config.sensor.single_sensor_margin_pct
        )
        fallback_fill = (
            previous_fill
            + previous_age * config.sensor.conservative_growth_pct_per_hour
            + retained_margin
        )
        if fill_missing[index] and weight_missing[index]:
            conservative_fill[index] = fallback_fill
            conservative_weight[index] = max(
                previous_weight, fallback_fill / 100.0 * capacities[index]
            )
        else:
            conservative_fill[index] = max(conservative_fill[index], fallback_fill)
            conservative_weight[index] = max(conservative_weight[index], previous_weight)

    conservative_fill = np.clip(conservative_fill, 0.0, 150.0)
    conservative_weight = np.clip(
        conservative_weight, 0.0, config.operations.crane_lift_limit_kg
    )

    review_reasons: list[list[str]] = [[] for _ in range(len(bins))]
    for index in range(len(bins)):
        if stale[index]:
            review_reasons[index].append(f"stale reading ({age_hours[index]:.1f}h old)")
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
    review = [index for index, reasons in enumerate(review_reasons) if reasons]

    required = [
        index
        for index in range(len(bins))
        if risk[index] in {"high", "critical"}
        or tto[index] <= operations.smart_dispatch_time_to_overflow_hours
        or conservative_fill[index] >= operations.smart_dispatch_current_trigger_pct
    ]
    emergency = {
        index
        for index in required
        if risk[index] == "critical"
        or tto[index] <= operations.smart_emergency_time_to_overflow_hours
        or conservative_fill[index] >= operations.smart_emergency_current_trigger_pct
    }
    required = sorted(
        required,
        key=lambda index: (
            index not in emergency,
            tto[index],
            -conservative_fill[index],
            str(bins.iloc[index]["bin_id"]),
        ),
    )

    selected, unserved_required = select_capacity_feasible(
        required,
        conservative_weight,
        operations.truck_capacity_kg,
        operations.max_daily_trips,
    )

    selected_services = {int(bins.iloc[index]["service_index"]) for index in selected}
    siblings = sorted(
        (
            index
            for index in range(len(bins))
            if index not in selected
            and int(bins.iloc[index]["service_index"]) in selected_services
            and confidence[index]
            and (
                conservative_fill[index] >= operations.smart_sibling_include_current_pct
                or tto[index] <= operations.smart_sibling_include_time_to_overflow_hours
            )
        ),
        key=lambda index: (tto[index], -conservative_fill[index], str(bins.iloc[index]["bin_id"])),
    )
    selected_siblings: list[int] = []
    for index in siblings:
        proposal, rejected = select_capacity_feasible(
            selected + [index],
            conservative_weight,
            operations.truck_capacity_kg,
            operations.max_daily_trips,
        )
        if not rejected:
            selected = proposal
            selected_siblings.append(index)

    optional_candidates = sorted(
        (
            index
            for index in range(len(bins))
            if index not in selected
            and confidence[index]
            and (
                risk[index] == "medium"
                or conservative_fill[index] >= operations.smart_include_current_trigger_pct
                or tto[index] <= operations.smart_sibling_include_time_to_overflow_hours
            )
        ),
        key=lambda index: (tto[index], -conservative_fill[index], str(bins.iloc[index]["bin_id"])),
    )
    selected_optional: list[int] = []
    distance_budget_m = operations.smart_max_dispatch_distance_km * 1000.0
    increment_limit_m = operations.smart_optional_max_increment_km * 1000.0
    if required:
        for index in optional_candidates:
            capacity_proposal, rejected = select_capacity_feasible(
                selected + [index],
                conservative_weight,
                operations.truck_capacity_kg,
                operations.max_daily_trips,
            )
            if rejected:
                continue
            proposal, added = incremental_proxy_distance_m(
                selected,
                index,
                conservative_weight,
                distance_matrix_m,
                operations.truck_capacity_kg,
                operations.max_daily_trips,
            )
            if proposal <= distance_budget_m and added <= increment_limit_m:
                selected = capacity_proposal
                selected_optional.append(index)

    route_plan = solve_routes(
        selected,
        conservative_weight,
        distance_matrix_m,
        operations.truck_capacity_kg,
        operations.max_daily_trips,
        operations.route_solver_milliseconds,
    )

    warnings: list[str] = []
    if review:
        ids = ", ".join(str(bins.iloc[index]["bin_id"]) for index in review)
        warnings.append(f"Operator review required for low-confidence readings: {ids}")
    if unserved_required:
        ids = ", ".join(str(bins.iloc[index]["bin_id"]) for index in unserved_required)
        warnings.append(f"Daily truck capacity could not cover required bins: {ids}")
    if route_plan.distance_m > distance_budget_m and required:
        warnings.append(
            "The required route exceeds the optional 30 km planning budget; safety-critical bins were retained."
        )
    over_nominal = [
        index
        for index in selected
        if weights[index] > float(bins.iloc[index]["capacity_kg"]) + 1e-9
    ]
    if over_nominal:
        ids = ", ".join(str(bins.iloc[index]["bin_id"]) for index in over_nominal)
        warnings.append(f"Measured weight exceeds the nominal 540 kg bin capacity: {ids}")
    inconsistent = [
        index
        for index in selected
        if np.isfinite(fill_pct[index])
        and np.isfinite(weights[index])
        and fill_pct[index] >= 65
        and weights[index] <= 1.0
    ]
    if inconsistent:
        ids = ", ".join(str(bins.iloc[index]["bin_id"]) for index in inconsistent)
        warnings.append(f"High fill but near-zero weight needs sensor inspection: {ids}")

    required_set = set(required)
    sibling_set = set(selected_siblings)
    optional_set = set(selected_optional)
    served_set = set(route_plan.served_bin_indices)
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
            selection_class = "Efficient nearby pickup"
        else:
            selection_class = "Wait"
        reasons = list(review_reasons[index])
        if risk[index] in {"high", "critical"}:
            reasons.append(f"{risk[index]} risk")
        if tto[index] <= operations.smart_dispatch_time_to_overflow_hours:
            reasons.append(f"overflow in {tto[index]:g}h")
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
                "time_to_overflow_hours": float(tto[index]),
                "risk_level": str(risk[index]),
                "confidence_flag": bool(confidence[index]),
                "reading_age_hours": float(age_hours[index]),
                "collection_state": selection_class,
            }
        )
    rows = [row for index, row in enumerate(audit_rows) if index in served_set]
    inspection_required = bool(review)
    if required:
        decision_state = COLLECTION_REQUIRED
    elif inspection_required:
        decision_state = INSPECTION_REQUIRED
    else:
        decision_state = NO_COLLECTION_REQUIRED

    return DispatchPlan(
        snapshot_timestamp=str(snapshot.iloc[0]["timestamp"]),
        decision_state=decision_state,
        collection_required=bool(required),
        inspection_required=inspection_required,
        route_plan=route_plan,
        selected_bin_indices=list(route_plan.served_bin_indices),
        required_bin_indices=required,
        sibling_bin_indices=selected_siblings,
        optional_bin_indices=selected_optional,
        unserved_required_bin_indices=unserved_required,
        review_bin_indices=review,
        selection_rows=rows,
        audit_rows=audit_rows,
        warnings=tuple(warnings),
    )


def update_last_valid_readings(
    history: dict[str, dict[str, Any]],
    snapshot: pd.DataFrame,
    bins: pd.DataFrame,
    config: Config,
) -> dict[str, dict[str, Any]]:
    """Retain only fresh, high-confidence, mutually consistent readings."""
    updated = dict(history)
    capacities = bins["capacity_kg"].to_numpy(dtype=float)
    for index, row in snapshot.iterrows():
        fill = row["fill_pct"]
        weight = row["weight_kg"]
        if (
            not bool(row["confidence_flag"])
            or bool(row.get("stale_flag", False))
            or not np.isfinite(fill)
            or not np.isfinite(weight)
        ):
            continue
        weight_fill = 100.0 * float(weight) / capacities[index]
        if abs(float(fill) - weight_fill) > config.sensor.disagreement_threshold_pct:
            continue
        updated[str(row["bin_id"])] = {
            "timestamp": str(row["timestamp"]),
            "fill_pct": float(fill),
            "weight_kg": float(weight),
        }
    return updated


def load_last_valid_readings(path: str | Path) -> dict[str, dict[str, Any]]:
    source = Path(path)
    if not source.exists():
        return {}
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def save_last_valid_readings(history: dict[str, dict[str, Any]], path: str | Path) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(history, indent=2), encoding="utf-8")


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
        stops = ["DEPOT" if index == -1 else str(bins.iloc[index]["bin_id"]) for index in route]
        routes.append(
            {
                "trip_number": trip_number,
                "vehicle_id": "MOCK-TRUCK-01",
                "stops": stops,
                "estimated_load_kg": round(load, 1),
            }
        )
    return {
        "dispatch_id": f"MOCK-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}-{uuid4().hex[:8].upper()}",
        "mode": "MOCK",
        "status": "MOCK_SENT_TO_TRUCK",
        "created_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "snapshot_timestamp": plan.snapshot_timestamp,
        "vehicle_id": "MOCK-TRUCK-01",
        "depot": {
            "label": config.pilot.depot_label,
            "latitude": config.pilot.depot_lat,
            "longitude": config.pilot.depot_lon,
        },
        "route_distance_km": round(plan.route_plan.distance_m / 1000.0, 3),
        "trip_count": len(plan.route_plan.routes),
        "selected_bin_count": plan.selected_count,
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
