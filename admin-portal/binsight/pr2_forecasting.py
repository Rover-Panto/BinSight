from __future__ import annotations

import hashlib
import json
import math
import sqlite3
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence

import numpy as np
import pandas as pd


PR2_FORECAST_CONFIG_VERSION = "1.0"
PR2_FORECAST_STATE_VERSION = "1.0"


def _as_utc(value: Any, field: str) -> datetime:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{field} is required")
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def _finite(value: Any, field: str, low: float, high: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field} must be numeric")
    number = float(value)
    if not math.isfinite(number) or not low <= number <= high:
        raise ValueError(f"{field} must be finite and in [{low}, {high}]")
    return number


def _weighted_quantile(values: Sequence[float], weights: Sequence[float], q: float) -> float:
    if not values:
        return float("nan")
    array = np.asarray(values, dtype=float)
    weight = np.asarray(weights, dtype=float)
    valid = np.isfinite(array) & np.isfinite(weight) & (weight > 0)
    if not valid.any():
        return float("nan")
    array = array[valid]
    weight = weight[valid]
    order = np.argsort(array, kind="mergesort")
    array = array[order]
    weight = weight[order]
    cumulative = np.cumsum(weight)
    target = float(np.clip(q, 0.0, 1.0)) * cumulative[-1]
    return float(array[min(int(np.searchsorted(cumulative, target, side="left")), len(array) - 1)])


def _normal_exceedance(threshold: float, mean: float, sd: float) -> float:
    if sd <= 1e-9:
        return float(mean >= threshold)
    z = (threshold - mean) / sd
    return float(np.clip(0.5 * math.erfc(z / math.sqrt(2.0)), 0.0, 1.0))


@dataclass(frozen=True)
class ForecastSettings:
    step_hours: int
    horizons_hours: tuple[int, ...]
    overflow_threshold_pct: float
    emergency_fill_pct: float
    earliest_collection_hours: float
    critical_probability: float
    high_probability_48h: float
    medium_probability_168h: float
    upper_quantile_z: float
    stale_after_hours: float
    offline_after_hours: float
    reset_drop_pct: float
    reset_confirmation_hours: float
    single_jump_pct: float
    single_jump_return_pct: float
    minimum_default_rate_pct_per_hour: float
    minimum_process_sd_pct: float
    own_history_min_intervals: int
    own_history_min_days: float
    weekly_min_days: float
    monthly_min_days: float
    yearly_min_days: float
    pool_min_intervals: int
    retrain_interval_hours: float
    retrain_min_new_readings: int
    drift_recent_days: float
    drift_reference_days: float
    drift_rate_ratio: float
    confidence_max_interval_width_pct: float
    confidence_max_residual_mae_pct: float
    event_prior_uplift: float


@dataclass(frozen=True)
class PR2ForecastConfig:
    model_family: str
    profiles: dict[str, dict[str, str]]
    forecast: ForecastSettings

    @classmethod
    def load(cls, path: str | Path) -> "PR2ForecastConfig":
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        if payload.get("schema_version") != PR2_FORECAST_CONFIG_VERSION:
            raise ValueError(
                f"Unsupported PR #2 forecast config version: {payload.get('schema_version')}"
            )
        raw_profiles = payload.get("profiles")
        if not isinstance(raw_profiles, dict) or not raw_profiles:
            raise ValueError("PR #2 forecast config requires explicit profile mappings")
        profiles: dict[str, dict[str, str]] = {}
        for profile_id, raw_mapping in raw_profiles.items():
            if not isinstance(raw_mapping, dict) or not raw_mapping:
                raise ValueError(f"Profile {profile_id} requires an explicit ID mapping")
            mapping = {str(source): str(target) for source, target in raw_mapping.items()}
            if len(mapping) != len(set(mapping.values())):
                raise ValueError(f"Profile {profile_id} contains conflicting canonical IDs")
            profiles[str(profile_id)] = mapping
        raw_forecast = dict(payload.get("forecast") or {})
        raw_forecast["horizons_hours"] = tuple(int(v) for v in raw_forecast["horizons_hours"])
        settings = ForecastSettings(**raw_forecast)
        if settings.step_hours <= 0 or any(
            horizon <= 0 or horizon % settings.step_hours for horizon in settings.horizons_hours
        ):
            raise ValueError("Forecast horizons must be positive multiples of step_hours")
        if max(settings.horizons_hours) < 168:
            raise ValueError("Forecast configuration must include at least the 168-hour horizon")
        if not 0 < settings.overflow_threshold_pct <= 100:
            raise ValueError("overflow_threshold_pct must be in (0, 100]")
        return cls(
            model_family=str(payload["model_family"]),
            profiles=profiles,
            forecast=settings,
        )

    def mapping(self, profile_id: str) -> dict[str, str]:
        try:
            return dict(self.profiles[profile_id])
        except KeyError as exc:
            raise ValueError(f"No PR #2 ID mapping for profile {profile_id}") from exc


@dataclass(frozen=True)
class ForecastEvent:
    event_id: str
    event_type: str
    start_at: datetime
    end_at: datetime
    known_at: datetime
    affected_bin_ids: tuple[str, ...]
    proximity_km_by_bin: dict[str, float]
    intensity: float
    expected_attendance: float | None
    data_quality: float

    @classmethod
    def from_mapping(cls, payload: dict[str, Any]) -> "ForecastEvent":
        start = _as_utc(payload.get("start_at"), "event.start_at")
        end = _as_utc(payload.get("end_at"), "event.end_at")
        known = _as_utc(payload.get("known_at", payload.get("start_at")), "event.known_at")
        if end <= start:
            raise ValueError("event.end_at must be after event.start_at")
        affected = payload.get("affected_bin_ids", [])
        if not isinstance(affected, list):
            raise ValueError("event.affected_bin_ids must be an array")
        raw_proximity = payload.get("proximity_km_by_bin", {})
        if not isinstance(raw_proximity, dict):
            raise ValueError("event.proximity_km_by_bin must be an object")
        attendance = payload.get("expected_attendance")
        if attendance is not None:
            attendance = _finite(attendance, "event.expected_attendance", 0.0, 10_000_000.0)
        return cls(
            event_id=str(payload.get("event_id") or "").strip(),
            event_type=str(payload.get("event_type") or "unspecified").strip().lower(),
            start_at=start,
            end_at=end,
            known_at=known,
            affected_bin_ids=tuple(str(v).upper() for v in affected),
            proximity_km_by_bin={
                str(key).upper(): _finite(value, "event.proximity_km", 0.0, 1000.0)
                for key, value in raw_proximity.items()
            },
            intensity=_finite(payload.get("intensity", 1.0), "event.intensity", 0.0, 10.0),
            expected_attendance=attendance,
            data_quality=_finite(payload.get("data_quality", 1.0), "event.data_quality", 0.0, 1.0),
        )

    def strength(self, bin_id: str, when: datetime) -> float:
        canonical = bin_id.upper()
        if self.affected_bin_ids and canonical not in self.affected_bin_ids:
            return 0.0
        if not self.start_at <= when <= self.end_at:
            return 0.0
        distance = self.proximity_km_by_bin.get(canonical, 0.0)
        proximity = math.exp(-distance / 2.0)
        attendance_factor = (
            min(2.0, math.log1p(self.expected_attendance) / math.log(1001.0))
            if self.expected_attendance is not None
            else 1.0
        )
        return float(self.intensity * proximity * attendance_factor)


@dataclass(frozen=True)
class PR2ForecastResult:
    frame: pd.DataFrame
    cleaned_history: pd.DataFrame
    model_state: dict[str, Any]
    diagnostics: dict[str, Any]


class PR2HistoryCache:
    """Routing-owned, append-only cache for the PR #2 read API.

    PR #2 currently caps a history response at 2,000 rows. The cache lets the
    forecasting consumer accumulate older observations without writing to or
    silently mutating the producer database.
    """

    def __init__(self, path: str | Path, source_to_canonical: dict[str, str]) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.source_to_canonical = dict(source_to_canonical)
        self.connection = sqlite3.connect(self.path)
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.execute("PRAGMA foreign_keys=ON")
        self.connection.execute(
            """
            CREATE TABLE IF NOT EXISTS pr2_readings (
                source_bin_id TEXT NOT NULL,
                observed_at TEXT NOT NULL,
                ingested_at TEXT NOT NULL,
                fill_pct REAL NOT NULL,
                estimated_density REAL NOT NULL,
                confidence_flag INTEGER NOT NULL CHECK(confidence_flag IN (0,1)),
                PRIMARY KEY (source_bin_id, observed_at)
            )
            """
        )
        self.connection.commit()

    def close(self) -> None:
        self.connection.close()

    def ingest(self, readings: Iterable[dict[str, Any]]) -> dict[str, int]:
        counts = {"stored": 0, "duplicate": 0, "invalid": 0}
        with self.connection:
            for raw in readings:
                try:
                    source_bin_id = str(raw.get("bin_id") or "").strip()
                    if source_bin_id not in self.source_to_canonical:
                        raise ValueError(f"Unknown PR #2 bin_id: {source_bin_id or '<blank>'}")
                    observed = _as_utc(raw.get("timestamp"), "timestamp").isoformat()
                    ingested = _as_utc(
                        raw.get("ingested_at", raw.get("timestamp")), "ingested_at"
                    ).isoformat()
                    fill = _finite(raw.get("fill_pct"), "fill_pct", 0.0, 100.0)
                    density = _finite(
                        raw.get("estimated_density"), "estimated_density", 0.0, 50.0
                    )
                    confidence = int(_parse_confidence(raw.get("confidence_flag")))
                except ValueError as exc:
                    if "Unknown PR #2 bin_id" in str(exc):
                        raise
                    counts["invalid"] += 1
                    continue
                existing = self.connection.execute(
                    """
                    SELECT ingested_at, fill_pct, estimated_density, confidence_flag
                    FROM pr2_readings WHERE source_bin_id=? AND observed_at=?
                    """,
                    (source_bin_id, observed),
                ).fetchone()
                signature = (ingested, fill, density, confidence)
                if existing is not None:
                    existing_signature = (
                        str(existing[0]),
                        float(existing[1]),
                        float(existing[2]),
                        int(existing[3]),
                    )
                    if existing_signature != signature:
                        raise ValueError(
                            "Contradictory PR #2 duplicate for "
                            f"{source_bin_id} at {observed}; cache was not overwritten"
                        )
                    counts["duplicate"] += 1
                    continue
                self.connection.execute(
                    """
                    INSERT INTO pr2_readings
                    (source_bin_id, observed_at, ingested_at, fill_pct, estimated_density, confidence_flag)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (source_bin_id, observed, ingested, fill, density, confidence),
                )
                counts["stored"] += 1
        return counts

    def load(self, decision_at: datetime) -> list[dict[str, Any]]:
        cutoff = decision_at.astimezone(timezone.utc).isoformat()
        placeholders = ",".join("?" for _ in self.source_to_canonical)
        rows = self.connection.execute(
            f"""
            SELECT source_bin_id, observed_at, fill_pct, estimated_density,
                   confidence_flag, ingested_at
            FROM pr2_readings
            WHERE source_bin_id IN ({placeholders})
              AND observed_at <= ?
              AND ingested_at <= ?
            ORDER BY observed_at, source_bin_id
            """,
            (*self.source_to_canonical.keys(), cutoff, cutoff),
        ).fetchall()
        return [
            {
                "bin_id": row[0],
                "timestamp": row[1],
                "fill_pct": row[2],
                "estimated_density": row[3],
                "confidence_flag": row[4],
                "ingested_at": row[5],
            }
            for row in rows
        ]


def _parse_confidence(value: Any) -> bool:
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    if isinstance(value, (int, np.integer)) and int(value) in (0, 1):
        return bool(value)
    text = str(value).strip().lower()
    if text in {"1", "true", "yes"}:
        return True
    if text in {"0", "false", "no"}:
        return False
    raise ValueError("confidence_flag must be 0/1 or Boolean")


def clean_pr2_history(
    readings: Iterable[dict[str, Any]],
    source_to_canonical: dict[str, str],
    decision_at: datetime,
    settings: ForecastSettings,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Validate, map, deduplicate, and annotate PR #2 readings.

    Receipt time is retained but never replaces acquisition time. Contradictory
    duplicates are removed, future readings are excluded, and confirmed resets
    split growth segments so a collection cannot become negative generation.
    """
    decision = decision_at.astimezone(timezone.utc)
    candidates: list[dict[str, Any]] = []
    diagnostics: dict[str, Any] = {
        "input_readings": 0,
        "accepted_readings": 0,
        "rejected_invalid": 0,
        "rejected_future": 0,
        "rejected_future_observation": 0,
        "rejected_future_ingestion": 0,
        "deduplicated": 0,
        "contradictory_duplicates": 0,
        "confirmed_resets": 0,
        "suspected_resets": 0,
        "single_reading_spikes": 0,
    }
    for position, raw in enumerate(readings):
        diagnostics["input_readings"] += 1
        if not isinstance(raw, dict):
            diagnostics["rejected_invalid"] += 1
            continue
        try:
            source_bin_id = str(raw.get("bin_id") or "").strip()
            if source_bin_id not in source_to_canonical:
                raise ValueError(
                    f"Unknown PR #2 bin_id at row {position + 1}: {source_bin_id or '<blank>'}"
                )
            observed = _as_utc(raw.get("timestamp"), "timestamp")
            ingested = _as_utc(raw.get("ingested_at", raw.get("timestamp")), "ingested_at")
            fill = _finite(raw.get("fill_pct"), "fill_pct", 0.0, 100.0)
            density = _finite(
                raw.get("estimated_density"), "estimated_density", 0.0, 50.0
            )
            confidence = _parse_confidence(raw.get("confidence_flag"))
        except ValueError as exc:
            if "Unknown PR #2 bin_id" in str(exc):
                raise
            diagnostics["rejected_invalid"] += 1
            continue
        if observed > decision:
            diagnostics["rejected_future"] += 1
            diagnostics["rejected_future_observation"] += 1
            continue
        if ingested > decision:
            diagnostics["rejected_future"] += 1
            diagnostics["rejected_future_ingestion"] += 1
            continue
        candidates.append(
            {
                "source_bin_id": source_bin_id,
                "bin_id": source_to_canonical[source_bin_id],
                "observed_at": observed,
                "ingested_at": ingested,
                "fill_pct": fill,
                "estimated_density": density,
                "sensor_confidence": confidence,
            }
        )

    accepted: list[dict[str, Any]] = []
    if candidates:
        raw_frame = pd.DataFrame(candidates).sort_values(
            ["source_bin_id", "observed_at", "ingested_at"], kind="mergesort"
        )
        for _, group in raw_frame.groupby(["source_bin_id", "observed_at"], sort=False):
            signatures = {
                (
                    round(float(row.fill_pct), 9),
                    round(float(row.estimated_density), 9),
                    bool(row.sensor_confidence),
                )
                for row in group.itertuples(index=False)
            }
            if len(signatures) > 1:
                diagnostics["contradictory_duplicates"] += int(len(group))
                continue
            diagnostics["deduplicated"] += int(len(group) - 1)
            accepted.append(group.iloc[0].to_dict())

    columns = [
        "source_bin_id",
        "bin_id",
        "observed_at",
        "ingested_at",
        "fill_pct",
        "estimated_density",
        "sensor_confidence",
        "usable",
        "collection_reset",
        "segment_id",
        "quality_flags",
    ]
    if not accepted:
        return pd.DataFrame(columns=columns), diagnostics
    frame = pd.DataFrame(accepted).sort_values(["bin_id", "observed_at"], kind="mergesort")
    output: list[pd.DataFrame] = []
    for _, group in frame.groupby("bin_id", sort=False):
        current = group.reset_index(drop=True).copy()
        usable = np.ones(len(current), dtype=bool)
        resets = np.zeros(len(current), dtype=bool)
        flags: list[list[str]] = [[] for _ in range(len(current))]
        fills = current["fill_pct"].to_numpy(dtype=float)
        times = current["observed_at"].tolist()
        for index in range(1, len(current)):
            increase = fills[index] - fills[index - 1]
            decrease = fills[index - 1] - fills[index]
            if increase >= settings.single_jump_pct:
                confirmed = False
                if index + 1 < len(current):
                    confirm_gap = (times[index + 1] - times[index]).total_seconds() / 3600.0
                    confirmed = (
                        confirm_gap <= settings.reset_confirmation_hours
                        and fills[index + 1] >= fills[index] - settings.single_jump_return_pct
                    )
                if not confirmed:
                    usable[index] = False
                    flags[index].append("unconfirmed_single_jump")
                    diagnostics["single_reading_spikes"] += 1
            if decrease >= settings.reset_drop_pct:
                confirmed = False
                if index + 1 < len(current):
                    confirm_gap = (times[index + 1] - times[index]).total_seconds() / 3600.0
                    confirmed = (
                        confirm_gap <= settings.reset_confirmation_hours
                        and fills[index + 1] <= fills[index] + 10.0
                        and fills[index + 1] <= fills[index - 1] - settings.reset_drop_pct / 2.0
                    )
                if confirmed:
                    resets[index] = True
                    diagnostics["confirmed_resets"] += 1
                else:
                    usable[index] = False
                    flags[index].append("suspected_collection_reset")
                    diagnostics["suspected_resets"] += 1
            if not bool(current.loc[index, "sensor_confidence"]):
                flags[index].append("low_sensor_confidence")
        if len(current) and not bool(current.loc[0, "sensor_confidence"]):
            flags[0].append("low_sensor_confidence")
        segment = 0
        segments: list[int] = []
        for reset in resets:
            if reset:
                segment += 1
            segments.append(segment)
        current["usable"] = usable
        current["collection_reset"] = resets
        current["segment_id"] = segments
        current["quality_flags"] = [tuple(sorted(set(value))) for value in flags]
        output.append(current)
    cleaned = pd.concat(output, ignore_index=True).sort_values(
        ["bin_id", "observed_at"], kind="mergesort"
    )
    diagnostics["accepted_readings"] = int(len(cleaned))
    return cleaned[columns].reset_index(drop=True), diagnostics


def _growth_intervals(cleaned: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for bin_id, group in cleaned.groupby("bin_id", sort=False):
        usable = group.loc[group["usable"]].sort_values("observed_at")
        previous = None
        for row in usable.itertuples(index=False):
            if previous is None:
                previous = row
                continue
            duration = (row.observed_at - previous.observed_at).total_seconds() / 3600.0
            if duration <= 0 or row.segment_id != previous.segment_id or row.collection_reset:
                previous = row
                continue
            delta = max(0.0, float(row.fill_pct) - float(previous.fill_pct))
            midpoint = previous.observed_at + (row.observed_at - previous.observed_at) / 2
            rows.append(
                {
                    "bin_id": bin_id,
                    "start_at": previous.observed_at,
                    "end_at": row.observed_at,
                    "midpoint": midpoint,
                    "duration_hours": duration,
                    "growth_pct": delta,
                    "rate_pct_per_hour": delta / duration,
                    "weight": (
                        1.0
                        if bool(previous.sensor_confidence) and bool(row.sensor_confidence)
                        else 0.25
                    )
                    * (0.5 if duration > 24.0 else 1.0),
                    "missing_gap": bool(duration > 12.0),
                }
            )
            previous = row
    return pd.DataFrame(
        rows,
        columns=[
            "bin_id",
            "start_at",
            "end_at",
            "midpoint",
            "duration_hours",
            "growth_pct",
            "rate_pct_per_hour",
            "weight",
            "missing_gap",
        ],
    )


def _event_strength(
    events: Sequence[ForecastEvent], bin_id: str, when: datetime, decision_at: datetime
) -> tuple[float, float]:
    known = [event for event in events if event.known_at <= decision_at]
    strengths = [event.strength(bin_id, when) for event in known]
    active = [
        event.data_quality
        for event, strength in zip(known, strengths)
        if strength > 0
    ]
    return (float(sum(strengths)), float(min(active)) if active else 1.0)


def _event_adjustment(
    events: Sequence[ForecastEvent],
    bin_id: str,
    when: datetime,
    decision_at: datetime,
    pattern: dict[str, Any],
) -> tuple[float, float]:
    contributions: list[float] = []
    qualities: list[float] = []
    by_type = pattern.get("event_uplift_by_type", {})
    default_uplift = float(pattern.get("event_uplift", 1.0))
    for event in events:
        if event.known_at > decision_at:
            continue
        strength = event.strength(bin_id, when)
        if strength <= 0:
            continue
        uplift = float(by_type.get(event.event_type, default_uplift))
        contributions.append(max(0.0, uplift - 1.0) * strength)
        qualities.append(event.data_quality)
    return (
        float(1.0 + sum(contributions)),
        float(min(qualities)) if qualities else 1.0,
    )


def _factor_map(
    intervals: pd.DataFrame, key_values: pd.Series, base_rate: float, minimum_count: int = 4
) -> dict[str, float]:
    factors: dict[str, float] = {}
    if intervals.empty or base_rate <= 1e-9:
        return factors
    table = intervals.assign(_key=key_values.to_numpy())
    for key, group in table.groupby("_key"):
        if len(group) < minimum_count:
            continue
        rate = _weighted_quantile(
            group["rate_pct_per_hour"].tolist(), group["weight"].tolist(), 0.5
        )
        if np.isfinite(rate):
            factors[str(int(key))] = float(np.clip(rate / base_rate, 0.4, 2.5))
    return factors


def _fit_pattern(
    intervals: pd.DataFrame,
    settings: ForecastSettings,
    events: Sequence[ForecastEvent],
    decision_at: datetime,
    *,
    sufficient_intervals: int,
    sufficient_days: float,
) -> dict[str, Any]:
    if intervals.empty:
        return {
            "interval_count": 0,
            "span_days": 0.0,
            "sufficient": False,
            "base_rate": settings.minimum_default_rate_pct_per_hour,
            "upper_rate": settings.minimum_default_rate_pct_per_hour * 2.0,
            "residual_mae": settings.minimum_process_sd_pct,
            "hour_factors": {},
            "dow_factors": {},
            "week_of_month_factors": {},
            "month_factors": {},
            "yearly_factor_enabled": False,
            "event_uplift": settings.event_prior_uplift,
            "event_uplift_by_type": {},
        }
    ordered = intervals.sort_values("midpoint")
    weights = ordered["weight"].tolist()
    rates = ordered["rate_pct_per_hour"].tolist()
    base = max(
        settings.minimum_default_rate_pct_per_hour,
        _weighted_quantile(rates, weights, 0.5),
    )
    upper = max(base, _weighted_quantile(rates, weights, 0.85))
    residual = _weighted_quantile(
        [abs(value - base) for value in rates], weights, 0.5
    )
    span_days = max(
        0.0,
        (ordered["end_at"].max() - ordered["start_at"].min()).total_seconds() / 86400.0,
    )
    midpoint = pd.to_datetime(ordered["midpoint"], utc=True)
    hour_factors = _factor_map(ordered, midpoint.dt.hour, base)
    dow_factors = (
        _factor_map(ordered, midpoint.dt.dayofweek, base)
        if span_days >= settings.weekly_min_days
        else {}
    )
    wom_factors = (
        _factor_map(ordered, ((midpoint.dt.day - 1) // 7), base)
        if span_days >= settings.monthly_min_days
        else {}
    )
    month_factors = (
        _factor_map(ordered, midpoint.dt.month, base, minimum_count=8)
        if span_days >= settings.yearly_min_days
        else {}
    )
    event_rates: list[float] = []
    ordinary_rates: list[float] = []
    for row in ordered.itertuples(index=False):
        strength, _ = _event_strength(events, str(row.bin_id), row.midpoint, decision_at)
        (event_rates if strength > 0 else ordinary_rates).append(float(row.rate_pct_per_hour))
    if len(event_rates) >= 3 and ordinary_rates:
        event_uplift = float(
            np.clip(
                np.median(event_rates) / max(settings.minimum_default_rate_pct_per_hour, np.median(ordinary_rates)),
                1.0,
                3.0,
            )
        )
    else:
        event_uplift = settings.event_prior_uplift
    event_uplift_by_type: dict[str, float] = {}
    event_types = sorted({event.event_type for event in events})
    for event_type in event_types:
        type_rates: list[float] = []
        for row in ordered.itertuples(index=False):
            if any(
                event.event_type == event_type
                and event.known_at <= decision_at
                and event.strength(str(row.bin_id), row.midpoint) > 0
                for event in events
            ):
                type_rates.append(float(row.rate_pct_per_hour))
        if len(type_rates) >= 3 and ordinary_rates:
            event_uplift_by_type[event_type] = float(
                np.clip(
                    np.median(type_rates)
                    / max(
                        settings.minimum_default_rate_pct_per_hour,
                        np.median(ordinary_rates),
                    ),
                    1.0,
                    3.0,
                )
            )
        else:
            event_uplift_by_type[event_type] = settings.event_prior_uplift
    return {
        "interval_count": int(len(ordered)),
        "span_days": float(span_days),
        "sufficient": bool(
            len(ordered) >= sufficient_intervals and span_days >= sufficient_days
        ),
        "base_rate": float(base),
        "upper_rate": float(upper),
        "residual_mae": float(max(settings.minimum_process_sd_pct / 6.0, residual)),
        "hour_factors": hour_factors,
        "dow_factors": dow_factors,
        "week_of_month_factors": wom_factors,
        "month_factors": month_factors,
        "yearly_factor_enabled": bool(month_factors),
        "event_uplift": event_uplift,
        "event_uplift_by_type": event_uplift_by_type,
    }


def _metadata(bins: pd.DataFrame) -> dict[str, dict[str, str]]:
    result: dict[str, dict[str, str]] = {}
    for row in bins.to_dict(orient="records"):
        result[str(row["bin_id"])] = {
            "site_id": str(row.get("site_id") or "unknown-site"),
            "area_type": str(row.get("area_type") or "unknown-area"),
        }
    return result


def _history_digest(cleaned: pd.DataFrame) -> str:
    material: list[list[Any]] = []
    for row in cleaned.itertuples(index=False):
        material.append(
            [
                row.source_bin_id,
                row.bin_id,
                row.observed_at.isoformat(),
                round(float(row.fill_pct), 6),
                bool(row.sensor_confidence),
                bool(row.usable),
                bool(row.collection_reset),
            ]
        )
    return hashlib.sha256(json.dumps(material, separators=(",", ":")).encode()).hexdigest()


def _detect_drift(
    intervals: pd.DataFrame, decision_at: datetime, settings: ForecastSettings
) -> dict[str, bool]:
    result: dict[str, bool] = {}
    if intervals.empty:
        return result
    for bin_id, group in intervals.groupby("bin_id", sort=False):
        recent_start = decision_at - timedelta(days=settings.drift_recent_days)
        reference_start = decision_at - timedelta(days=settings.drift_reference_days)
        recent = group.loc[group["end_at"] >= recent_start]
        reference = group.loc[
            (group["end_at"] >= reference_start) & (group["end_at"] < recent_start)
        ]
        if len(recent) < 3 or len(reference) < 6:
            result[str(bin_id)] = False
            continue
        recent_rate = _weighted_quantile(
            recent["rate_pct_per_hour"].tolist(), recent["weight"].tolist(), 0.5
        )
        reference_rate = _weighted_quantile(
            reference["rate_pct_per_hour"].tolist(), reference["weight"].tolist(), 0.5
        )
        ratio = (recent_rate + 0.05) / (reference_rate + 0.05)
        result[str(bin_id)] = bool(
            ratio >= settings.drift_rate_ratio or ratio <= 1.0 / settings.drift_rate_ratio
        )
    return result


def _fit_model_state(
    config: PR2ForecastConfig,
    profile_id: str,
    cleaned: pd.DataFrame,
    intervals: pd.DataFrame,
    bins: pd.DataFrame,
    events: Sequence[ForecastEvent],
    decision_at: datetime,
) -> dict[str, Any]:
    settings = config.forecast
    metadata = _metadata(bins)
    own: dict[str, dict[str, Any]] = {}
    for bin_id in bins["bin_id"].astype(str):
        own_pattern = _fit_pattern(
            intervals.loc[intervals["bin_id"] == bin_id] if not intervals.empty else intervals,
            settings,
            events,
            decision_at,
            sufficient_intervals=settings.own_history_min_intervals,
            sufficient_days=settings.own_history_min_days,
        )
        bin_history = cleaned.loc[(cleaned["bin_id"] == bin_id) & cleaned["usable"]]
        cycle_additions = [
            float(group["fill_pct"].max() - group["fill_pct"].min())
            for _, group in bin_history.groupby("segment_id")
            if len(group) >= 2
        ]
        own_pattern["typical_fill_between_collections_pct"] = (
            float(np.median(cycle_additions)) if cycle_additions else None
        )
        own[bin_id] = own_pattern
    site: dict[str, dict[str, Any]] = {}
    area: dict[str, dict[str, Any]] = {}
    for site_id in sorted({value["site_id"] for value in metadata.values()}):
        ids = [key for key, value in metadata.items() if value["site_id"] == site_id]
        group = intervals.loc[intervals["bin_id"].isin(ids)] if not intervals.empty else intervals
        site[site_id] = _fit_pattern(
            group,
            settings,
            events,
            decision_at,
            sufficient_intervals=settings.pool_min_intervals,
            sufficient_days=7.0,
        )
    for area_type in sorted({value["area_type"] for value in metadata.values()}):
        ids = [key for key, value in metadata.items() if value["area_type"] == area_type]
        group = intervals.loc[intervals["bin_id"].isin(ids)] if not intervals.empty else intervals
        area[area_type] = _fit_pattern(
            group,
            settings,
            events,
            decision_at,
            sufficient_intervals=settings.pool_min_intervals,
            sufficient_days=7.0,
        )
    digest = _history_digest(cleaned)
    model_version = f"{config.model_family}-{digest[:12]}"
    cutoff = (
        max(cleaned["observed_at"]).isoformat() if not cleaned.empty else decision_at.isoformat()
    )
    return {
        "schema_version": PR2_FORECAST_STATE_VERSION,
        "profile_id": profile_id,
        "model_family": config.model_family,
        "model_version": model_version,
        "trained_at": decision_at.isoformat(),
        "trained_data_cutoff": cutoff,
        "trained_record_count": int(cleaned["usable"].sum()) if not cleaned.empty else 0,
        "history_digest": digest,
        "own_patterns": own,
        "site_patterns": site,
        "area_patterns": area,
    }


def _should_retrain(
    state: dict[str, Any] | None,
    profile_id: str,
    model_family: str,
    cleaned: pd.DataFrame,
    drift: dict[str, bool],
    decision_at: datetime,
    settings: ForecastSettings,
) -> bool:
    if not state or state.get("schema_version") != PR2_FORECAST_STATE_VERSION:
        return True
    if state.get("profile_id") != profile_id:
        return True
    if state.get("model_family") != model_family:
        return True
    try:
        trained_at = _as_utc(state.get("trained_at"), "state.trained_at")
        trained_count = int(state.get("trained_record_count", 0))
    except (TypeError, ValueError):
        return True
    current_count = int(cleaned["usable"].sum()) if not cleaned.empty else 0
    new_count = max(0, current_count - trained_count)
    elapsed = (decision_at - trained_at).total_seconds() / 3600.0
    scheduled = (
        elapsed >= settings.retrain_interval_hours
        and new_count >= settings.retrain_min_new_readings
    )
    drift_trigger = any(drift.values()) and new_count >= max(6, settings.retrain_min_new_readings // 4)
    return bool(scheduled or drift_trigger)


def _pattern_for_bin(
    bin_id: str,
    state: dict[str, Any],
    metadata: dict[str, dict[str, str]],
    settings: ForecastSettings,
) -> tuple[dict[str, Any], str]:
    own = state.get("own_patterns", {}).get(bin_id, {})
    if own.get("sufficient"):
        return own, "own_history"
    meta = metadata[bin_id]
    site = state.get("site_patterns", {}).get(meta["site_id"], {})
    if site.get("sufficient"):
        return site, "pooled_service_site"
    area = state.get("area_patterns", {}).get(meta["area_type"], {})
    if area.get("sufficient"):
        return area, "pooled_area_type"
    return (
        own
        or {
            "base_rate": settings.minimum_default_rate_pct_per_hour,
            "upper_rate": settings.minimum_default_rate_pct_per_hour * 2.0,
            "residual_mae": settings.minimum_process_sd_pct / 6.0,
            "hour_factors": {},
            "dow_factors": {},
            "week_of_month_factors": {},
            "month_factors": {},
            "event_uplift": settings.event_prior_uplift,
            "event_uplift_by_type": {},
            "span_days": 0.0,
        },
        "conservative_recent_rate",
    )


def _seasonal_factor(pattern: dict[str, Any], when: datetime) -> tuple[float, tuple[str, ...]]:
    factor = 1.0
    used: list[str] = []
    keys = (
        ("hour_factors", when.hour, "hour_of_day"),
        ("dow_factors", when.weekday(), "day_of_week"),
        ("week_of_month_factors", (when.day - 1) // 7, "week_of_month"),
        ("month_factors", when.month, "month_of_year"),
    )
    for field, key, label in keys:
        values = pattern.get(field, {})
        if str(key) in values:
            factor *= float(values[str(key)])
            used.append(label)
    return float(np.clip(factor, 0.25, 4.0)), tuple(used)


def _online_residual_rate_mae(
    intervals: pd.DataFrame,
    pattern: dict[str, Any],
    events: Sequence[ForecastEvent],
    bin_id: str,
    decision: datetime,
) -> float:
    """Update recent residual error without changing the fitted seasonal model.

    This statistic is recomputed from observations available at the decision
    cutoff. It therefore reacts to every valid reading, while the slower model
    parameters remain subject to the controlled retraining policy.
    """
    if intervals.empty:
        return float(pattern.get("residual_mae", 0.0))
    recent = intervals.loc[
        intervals["end_at"] >= decision - timedelta(days=7)
    ].tail(28)
    if recent.empty:
        return float(pattern.get("residual_mae", 0.0))
    residuals: list[float] = []
    weights: list[float] = []
    base_rate = float(pattern.get("base_rate", 0.0))
    for row in recent.itertuples(index=False):
        seasonal, _ = _seasonal_factor(pattern, row.midpoint)
        event_factor, _ = _event_adjustment(
            events,
            bin_id,
            row.midpoint,
            decision,
            pattern,
        )
        expected_rate = base_rate * seasonal * event_factor
        residuals.append(abs(float(row.rate_pct_per_hour) - expected_rate))
        weights.append(float(row.weight))
    recency = np.linspace(0.25, 1.0, len(residuals))
    combined_weights = np.asarray(weights, dtype=float) * recency
    recent_mae = (
        float(np.average(np.asarray(residuals, dtype=float), weights=combined_weights))
        if combined_weights.sum() > 0
        else float("nan")
    )
    fitted_mae = float(pattern.get("residual_mae", 0.0))
    if not np.isfinite(recent_mae):
        return fitted_mae
    return float(0.7 * recent_mae + 0.3 * fitted_mae)


def _risk_level(
    fill_pct: float,
    confirmed_current: bool,
    tto_hours: float,
    probability_6h: float,
    probability_48h: float,
    probability_168h: float,
    confidence: bool,
    settings: ForecastSettings,
) -> str:
    if (
        confirmed_current and fill_pct >= settings.emergency_fill_pct
    ) or probability_6h >= settings.critical_probability or tto_hours <= settings.earliest_collection_hours:
        return "critical"
    if probability_48h >= settings.high_probability_48h or tto_hours <= 48.0:
        return "high"
    if probability_168h >= settings.medium_probability_168h or tto_hours <= 168.0 or not confidence:
        return "medium"
    return "low"


class AdaptivePR2ForecastAdapter:
    """Convert PR #2 history into a complete, probabilistic PR #1 snapshot."""

    def __init__(
        self,
        config: PR2ForecastConfig,
        bins: pd.DataFrame,
        profile_id: str,
        *,
        model_state: dict[str, Any] | None = None,
    ) -> None:
        self.config = config
        self.profile_id = profile_id
        self.source_to_canonical = config.mapping(profile_id)
        self.bins = bins.copy()
        expected = list(self.bins["bin_id"].astype(str))
        mapped = list(self.source_to_canonical.values())
        if set(expected) != set(mapped) or len(expected) != len(mapped):
            raise ValueError(
                f"PR #2 mapping for {profile_id} must cover every configured bin exactly"
            )
        self.bins = self.bins.set_index("bin_id").loc[expected].reset_index()
        self.model_state = dict(model_state) if model_state else None

    def build_snapshot(
        self,
        readings: Iterable[dict[str, Any]],
        decision_at: datetime,
        *,
        events: Iterable[ForecastEvent | dict[str, Any]] = (),
    ) -> PR2ForecastResult:
        if decision_at.tzinfo is None or decision_at.utcoffset() is None:
            raise ValueError("decision_at must be timezone-aware")
        decision = decision_at.astimezone(timezone.utc).replace(microsecond=0)
        parsed_events = tuple(
            event if isinstance(event, ForecastEvent) else ForecastEvent.from_mapping(event)
            for event in events
        )
        known_events = tuple(event for event in parsed_events if event.known_at <= decision)
        cleaned, diagnostics = clean_pr2_history(
            readings, self.source_to_canonical, decision, self.config.forecast
        )
        intervals = _growth_intervals(cleaned)
        drift = _detect_drift(intervals, decision, self.config.forecast)
        retrained = _should_retrain(
            self.model_state,
            self.profile_id,
            self.config.model_family,
            cleaned,
            drift,
            decision,
            self.config.forecast,
        )
        if retrained:
            self.model_state = _fit_model_state(
                self.config,
                self.profile_id,
                cleaned,
                intervals,
                self.bins,
                known_events,
                decision,
            )
        assert self.model_state is not None
        rows = self._forecast_rows(cleaned, intervals, known_events, drift, decision)
        digest_material = [
            self.profile_id,
            decision.isoformat(),
            self.model_state["model_version"],
            [
                [row["bin_id"], row.get("event_id"), row.get("observed_at")]
                for row in rows
            ],
        ]
        snapshot_id = "PR2F-" + hashlib.sha256(
            json.dumps(digest_material, separators=(",", ":")).encode()
        ).hexdigest()[:20].upper()
        for row in rows:
            row["snapshot_id"] = snapshot_id
        frame = pd.DataFrame(rows)
        order = {value: index for index, value in enumerate(self.bins["bin_id"].astype(str))}
        frame["_order"] = frame["bin_id"].map(order)
        frame = frame.sort_values("_order").drop(columns="_order").reset_index(drop=True)
        diagnostics.update(
            {
                "coverage_complete": bool(
                    len(frame) == len(self.bins)
                    and set(frame["bin_id"]) == set(self.bins["bin_id"].astype(str))
                ),
                "source_evidence_complete": bool(frame["event_id"].notna().all()),
                "available_forecast_count": int(
                    (frame["forecast_status"] == "available").sum()
                ),
                "model_retrained": retrained,
                "model_version": self.model_state["model_version"],
                "model_data_cutoff": (
                    max(cleaned["observed_at"]).isoformat() if not cleaned.empty else None
                ),
                "drift_bins": sorted(key for key, value in drift.items() if value),
                "estimated_density_used_for_weight": False,
            }
        )
        return PR2ForecastResult(frame, cleaned, dict(self.model_state), diagnostics)

    def _forecast_rows(
        self,
        cleaned: pd.DataFrame,
        intervals: pd.DataFrame,
        events: Sequence[ForecastEvent],
        drift: dict[str, bool],
        decision: datetime,
    ) -> list[dict[str, Any]]:
        settings = self.config.forecast
        metadata = _metadata(self.bins)
        reverse = {target: source for source, target in self.source_to_canonical.items()}
        rows: list[dict[str, Any]] = []
        for bin_id in self.bins["bin_id"].astype(str):
            source_id = reverse[bin_id]
            history = cleaned.loc[cleaned["bin_id"] == bin_id].sort_values("observed_at")
            usable = history.loc[history["usable"]]
            raw_latest = history.iloc[-1] if not history.empty else None
            latest = usable.iloc[-1] if not usable.empty else None
            if latest is None:
                rows.append(
                    self._unavailable_row(bin_id, source_id, decision, raw_latest)
                )
                continue
            quality_flags = set(raw_latest["quality_flags"] if raw_latest is not None else ())
            if raw_latest is not None and not bool(raw_latest["usable"]):
                quality_flags.update(raw_latest["quality_flags"])
                quality_flags.add("latest_observation_excluded")
            selected_time = latest["observed_at"]
            age_hours = max(0.0, (decision - selected_time).total_seconds() / 3600.0)
            sensor_confident = bool(latest["sensor_confidence"])
            current_fill = float(latest["fill_pct"])
            if not sensor_confident:
                prior_high = usable.loc[usable["sensor_confidence"]]
                if not prior_high.empty:
                    prior = prior_high.iloc[-1]
                    prior_age_hours = (
                        selected_time - prior["observed_at"]
                    ).total_seconds() / 3600.0
                    if prior_age_hours <= settings.stale_after_hours:
                        current_fill = (
                            0.6 * current_fill + 0.4 * float(prior["fill_pct"])
                        )
                    else:
                        quality_flags.add("no_recent_high_confidence_observation")
                quality_flags.add("low_sensor_confidence")
            if age_hours > settings.stale_after_hours:
                quality_flags.add("stale_observation")
            if age_hours > settings.offline_after_hours:
                quality_flags.add("offline_observation")
            if drift.get(bin_id, False):
                quality_flags.add("concept_drift_detected")
            bin_intervals = (
                intervals.loc[intervals["bin_id"] == bin_id].sort_values("end_at")
                if not intervals.empty
                else intervals
            )
            recent = (
                bin_intervals.loc[
                    bin_intervals["end_at"] >= decision - timedelta(days=7)
                ]
                if not bin_intervals.empty
                else bin_intervals
            )
            def window_rate(hours: float) -> float:
                if bin_intervals.empty:
                    return float("nan")
                window = bin_intervals.loc[
                    bin_intervals["end_at"] >= decision - timedelta(hours=hours)
                ]
                if window.empty:
                    return float("nan")
                return _weighted_quantile(
                    window["rate_pct_per_hour"].tolist(), window["weight"].tolist(), 0.5
                )

            def window_growth(hours: float) -> float | None:
                if bin_intervals.empty:
                    return None
                window = bin_intervals.loc[
                    bin_intervals["end_at"] >= decision - timedelta(hours=hours)
                ]
                if window.empty:
                    return None
                window_start = decision - timedelta(hours=hours)
                total = 0.0
                for interval in window.itertuples(index=False):
                    overlap_start = max(window_start, interval.start_at)
                    overlap_end = min(decision, interval.end_at)
                    overlap_hours = max(
                        0.0,
                        (overlap_end - overlap_start).total_seconds() / 3600.0,
                    )
                    total += float(interval.growth_pct) * min(
                        1.0,
                        overlap_hours / max(1e-9, float(interval.duration_hours)),
                    )
                return float(total)

            rate_6h = window_rate(6.0)
            rate_24h = window_rate(24.0)
            rate_168h = window_rate(168.0)
            growth_6h = window_growth(6.0)
            growth_24h = window_growth(24.0)
            growth_168h = window_growth(168.0)
            recent_rate = _weighted_quantile(
                recent["rate_pct_per_hour"].tolist(), recent["weight"].tolist(), 0.5
            ) if not recent.empty else float("nan")
            recent_upper = _weighted_quantile(
                recent["rate_pct_per_hour"].tolist(), recent["weight"].tolist(), 0.85
            ) if not recent.empty else float("nan")
            pattern, method = _pattern_for_bin(
                bin_id, self.model_state or {}, metadata, settings
            )
            online_residual_rate_mae = _online_residual_rate_mae(
                bin_intervals,
                pattern,
                events,
                bin_id,
                decision,
            )
            if not np.isfinite(recent_rate):
                recent_rate = float(pattern.get("base_rate", settings.minimum_default_rate_pct_per_hour))
            if not np.isfinite(recent_upper):
                recent_upper = max(recent_rate, float(pattern.get("upper_rate", recent_rate)))
            if not recent.empty and bool(recent["missing_gap"].any()):
                quality_flags.add("recent_missing_gap")
            if method == "own_history":
                blend = 0.65
            elif method.startswith("pooled"):
                blend = 0.60
                quality_flags.add("pooled_history")
            else:
                blend = 0.0
                quality_flags.add("fallback_recent_rate")
            expected_raw: dict[int, float] = {}
            upper_raw: dict[int, float] = {}
            lower_raw: dict[int, float] = {}
            probabilities: dict[int, float] = {}
            used_seasonality: set[str] = set()
            event_quality = 1.0
            mean_fill = current_fill
            variance = 0.0
            upper_fill = current_fill
            previous_upper = current_fill
            tto: float | None = 0.0 if current_fill >= settings.overflow_threshold_pct else None
            for horizon in range(settings.step_hours, max(settings.horizons_hours) + 1, settings.step_hours):
                midpoint = decision + timedelta(hours=horizon - settings.step_hours / 2.0)
                seasonal, used = _seasonal_factor(pattern, midpoint)
                used_seasonality.update(used)
                event_factor, quality = _event_adjustment(
                    events,
                    bin_id,
                    midpoint,
                    decision,
                    pattern,
                )
                event_quality = min(event_quality, quality)
                pattern_rate = float(pattern.get("base_rate", recent_rate)) * seasonal * event_factor
                expected_rate = (
                    blend * pattern_rate + (1.0 - blend) * max(settings.minimum_default_rate_pct_per_hour, recent_rate)
                    if blend > 0
                    else max(settings.minimum_default_rate_pct_per_hour, recent_rate) * event_factor
                )
                conservative_rate = max(
                    expected_rate,
                    recent_upper * event_factor,
                    float(pattern.get("upper_rate", expected_rate)) * seasonal * event_factor,
                )
                mean_fill += expected_rate * settings.step_hours
                residual_rate = max(
                    settings.minimum_process_sd_pct / settings.step_hours,
                    online_residual_rate_mae,
                    max(0.0, conservative_rate - expected_rate) / 2.0,
                )
                variance += (residual_rate * settings.step_hours) ** 2
                if not sensor_confident or age_hours > settings.stale_after_hours:
                    variance += 4.0
                sd = max(settings.minimum_process_sd_pct, math.sqrt(variance))
                upper_fill = max(mean_fill, mean_fill + settings.upper_quantile_z * sd)
                lower_fill = max(current_fill, mean_fill - settings.upper_quantile_z * sd)
                probability = _normal_exceedance(settings.overflow_threshold_pct, mean_fill, sd)
                expected_raw[horizon] = mean_fill
                upper_raw[horizon] = upper_fill
                lower_raw[horizon] = lower_fill
                probabilities[horizon] = probability
                if tto is None and upper_fill >= settings.overflow_threshold_pct:
                    fraction = (
                        (settings.overflow_threshold_pct - previous_upper)
                        / max(1e-9, upper_fill - previous_upper)
                    )
                    tto = max(
                        0.0,
                        horizon - settings.step_hours + settings.step_hours * float(np.clip(fraction, 0.0, 1.0)),
                    )
                previous_upper = upper_fill
            if tto is None:
                extrapolation_rate = max(
                    settings.minimum_default_rate_pct_per_hour,
                    (upper_raw[max(settings.horizons_hours)] - current_fill)
                    / max(settings.horizons_hours),
                )
                tto = max(settings.horizons_hours) + max(
                    0.0,
                    (settings.overflow_threshold_pct - upper_raw[max(settings.horizons_hours)])
                    / extrapolation_rate,
                )
            width_48 = max(0.0, upper_raw[48] - lower_raw[48])
            residual_fill_mae = online_residual_rate_mae * settings.step_hours
            overall_confidence = bool(
                sensor_confident
                and age_hours <= settings.stale_after_hours
                and method == "own_history"
                and width_48 <= settings.confidence_max_interval_width_pct
                and residual_fill_mae <= settings.confidence_max_residual_mae_pct
                and event_quality >= 0.7
                and not drift.get(bin_id, False)
                and not {"unconfirmed_single_jump", "suspected_collection_reset"}.intersection(quality_flags)
            )
            confirmed_current = bool(
                raw_latest is not None
                and bool(raw_latest["usable"])
                and bool(raw_latest["sensor_confidence"])
                and raw_latest["observed_at"] == selected_time
            )
            risk = _risk_level(
                current_fill,
                confirmed_current,
                float(tto),
                probabilities[6],
                probabilities[48],
                probabilities[168],
                overall_confidence,
                settings,
            )
            resets = history.loc[history["collection_reset"]]
            hours_since_collection = (
                max(
                    0.0,
                    (decision - resets.iloc[-1]["observed_at"]).total_seconds() / 3600.0,
                )
                if not resets.empty
                else None
            )
            data_cutoff = max(cleaned["observed_at"]).isoformat() if not cleaned.empty else None
            row: dict[str, Any] = {
                "schema_version": "2.1",
                "timestamp": decision.isoformat(),
                "decision_at": decision.isoformat(),
                "bin_id": bin_id,
                "hardware_bin_id": source_id,
                "observed_at": selected_time.isoformat(),
                "received_at": latest["ingested_at"].isoformat(),
                "clock_status": "synchronized",
                "event_id": f"pr2:{source_id}:{selected_time.isoformat()}",
                "event_kind": "fill_observation",
                "fill_pct": round(float(np.clip(current_fill, 0.0, 100.0)), 6),
                "source_fill_pct": float(latest["fill_pct"]),
                "weight_kg": None,
                "estimated_density_context": float(latest["estimated_density"]),
                "estimated_density_used": False,
                "weight_calibration_status": "unavailable",
                "time_to_overflow_hours": round(float(tto), 6),
                "risk_level": risk,
                "confidence_flag": overall_confidence,
                "fill_confidence": 1.0 if overall_confidence else 0.5 if sensor_confident else 0.25,
                "quality_flags": tuple(sorted(quality_flags)),
                "forecast_status": "available",
                "forecast_method": method,
                "model_version": self.model_state["model_version"],
                "model_trained_cutoff": self.model_state["trained_data_cutoff"],
                "model_data_cutoff": data_cutoff,
                "reading_age_hours": round(age_hours, 6),
                "source_mode": "hardware",
                "profile_id": self.profile_id,
                "overflow_threshold_pct": settings.overflow_threshold_pct,
                "seasonality_used": tuple(sorted(used_seasonality)),
                "event_data_quality": event_quality,
                "concept_drift_detected": bool(drift.get(bin_id, False)),
                "last_collection_at": (
                    resets.iloc[-1]["observed_at"].isoformat() if not resets.empty else None
                ),
                "hours_since_collection": hours_since_collection,
                "recent_fill_rate_6h_pct_per_hour": (
                    float(rate_6h) if np.isfinite(rate_6h) else None
                ),
                "recent_fill_rate_24h_pct_per_hour": (
                    float(rate_24h) if np.isfinite(rate_24h) else None
                ),
                "recent_fill_rate_168h_pct_per_hour": (
                    float(rate_168h) if np.isfinite(rate_168h) else None
                ),
                "recent_growth_6h_pct": growth_6h,
                "recent_growth_24h_pct": growth_24h,
                "recent_growth_168h_pct": growth_168h,
                "robust_recent_fill_rate_pct_per_hour": float(recent_rate),
                "typical_fill_between_collections_pct": pattern.get(
                    "typical_fill_between_collections_pct"
                ),
                "online_residual_mae_pct": residual_fill_mae,
                "historical_span_days": float(pattern.get("span_days", 0.0)),
            }
            for horizon in settings.horizons_hours:
                row[f"expected_fill_{horizon}h_pct"] = round(
                    float(np.clip(expected_raw[horizon], 0.0, 100.0)), 6
                )
                row[f"upper_fill_{horizon}h_pct"] = round(
                    float(np.clip(upper_raw[horizon], 0.0, 100.0)), 6
                )
                row[f"lower_fill_{horizon}h_pct"] = round(
                    float(np.clip(lower_raw[horizon], 0.0, 100.0)), 6
                )
                row[f"overflow_probability_{horizon}h"] = round(
                    probabilities[horizon], 8
                )
            row["overflow_probability_next_opportunity"] = row[
                f"overflow_probability_{int(settings.earliest_collection_hours)}h"
            ]
            rows.append(row)
        return rows

    def _unavailable_row(
        self,
        bin_id: str,
        source_id: str,
        decision: datetime,
        raw_latest: pd.Series | None,
    ) -> dict[str, Any]:
        flags = {"missing_usable_observation"}
        if raw_latest is not None:
            flags.update(raw_latest["quality_flags"])
        row: dict[str, Any] = {
            "schema_version": "2.1",
            "timestamp": decision.isoformat(),
            "decision_at": decision.isoformat(),
            "bin_id": bin_id,
            "hardware_bin_id": source_id,
            "observed_at": None,
            "received_at": None,
            "clock_status": "unsynchronized",
            "event_id": None,
            "event_kind": "fill_observation",
            "fill_pct": None,
            "source_fill_pct": None,
            "weight_kg": None,
            "estimated_density_context": None,
            "estimated_density_used": False,
            "weight_calibration_status": "unavailable",
            "time_to_overflow_hours": None,
            "risk_level": "medium",
            "confidence_flag": False,
            "fill_confidence": None,
            "quality_flags": tuple(sorted(flags)),
            "forecast_status": "unavailable",
            "forecast_method": "no_usable_observation",
            "model_version": self.model_state["model_version"] if self.model_state else None,
            "model_trained_cutoff": (
                self.model_state.get("trained_data_cutoff") if self.model_state else None
            ),
            "model_data_cutoff": None,
            "reading_age_hours": None,
            "source_mode": "hardware",
            "profile_id": self.profile_id,
            "overflow_threshold_pct": self.config.forecast.overflow_threshold_pct,
            "seasonality_used": tuple(),
            "event_data_quality": None,
            "concept_drift_detected": False,
            "last_collection_at": None,
            "hours_since_collection": None,
            "recent_fill_rate_6h_pct_per_hour": None,
            "recent_fill_rate_24h_pct_per_hour": None,
            "recent_fill_rate_168h_pct_per_hour": None,
            "recent_growth_6h_pct": None,
            "recent_growth_24h_pct": None,
            "recent_growth_168h_pct": None,
            "robust_recent_fill_rate_pct_per_hour": None,
            "typical_fill_between_collections_pct": None,
            "online_residual_mae_pct": None,
            "historical_span_days": 0.0,
        }
        for horizon in self.config.forecast.horizons_hours:
            row[f"expected_fill_{horizon}h_pct"] = None
            row[f"upper_fill_{horizon}h_pct"] = None
            row[f"lower_fill_{horizon}h_pct"] = None
            row[f"overflow_probability_{horizon}h"] = None
        row["overflow_probability_next_opportunity"] = None
        return row


def load_pr2_history_file(path: str | Path) -> list[dict[str, Any]]:
    source = Path(path)
    if source.suffix.lower() == ".csv":
        return pd.read_csv(source).replace({np.nan: None}).to_dict(orient="records")
    payload = json.loads(source.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        readings = payload
    elif isinstance(payload, dict) and isinstance(payload.get("readings"), list):
        readings = payload["readings"]
    elif isinstance(payload, dict) and isinstance(payload.get("histories"), dict):
        readings = []
        for source_bin_id, values in payload["histories"].items():
            if not isinstance(values, list):
                raise ValueError("Each histories entry must be an array")
            for value in values:
                row = dict(value)
                row.setdefault("bin_id", source_bin_id)
                readings.append(row)
    else:
        raise ValueError("PR #2 history JSON must be an array or contain readings/histories")
    if any(not isinstance(value, dict) for value in readings):
        raise ValueError("PR #2 readings must be JSON objects")
    return [dict(value) for value in readings]


def load_forecast_events(path: str | Path | None) -> tuple[ForecastEvent, ...]:
    if path is None:
        return tuple()
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("Event calendar must be a JSON array")
    return tuple(ForecastEvent.from_mapping(value) for value in payload)


def load_model_state(path: str | Path | None) -> dict[str, Any] | None:
    if path is None or not Path(path).exists():
        return None
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Forecast model state must be a JSON object")
    return payload


def save_model_state(path: str | Path, state: dict[str, Any]) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")
    temporary.replace(output)


def snapshot_json(result: PR2ForecastResult) -> dict[str, Any]:
    records = result.frame.replace({np.nan: None}).to_dict(orient="records")
    return {
        "schema_version": "pr2-predictive-snapshot-1.0",
        "snapshot_id": str(result.frame.iloc[0]["snapshot_id"]),
        "decision_at": str(result.frame.iloc[0]["decision_at"]),
        "model_version": result.diagnostics["model_version"],
        "diagnostics": result.diagnostics,
        "bins": records,
    }


def _interpolated_actual_tto(
    future: pd.DataFrame, current_fill: float, origin: datetime, threshold: float
) -> float | None:
    previous_fill = current_fill
    previous_time = origin
    for row in future.sort_values("observed_at").itertuples(index=False):
        if bool(row.collection_reset):
            previous_fill = float(row.fill_pct)
            previous_time = row.observed_at
            continue
        fill = float(row.fill_pct)
        if fill >= threshold:
            interval = (row.observed_at - previous_time).total_seconds() / 3600.0
            fraction = (threshold - previous_fill) / max(1e-9, fill - previous_fill)
            crossing = previous_time + timedelta(hours=interval * float(np.clip(fraction, 0, 1)))
            return max(0.0, (crossing - origin).total_seconds() / 3600.0)
        previous_fill = fill
        previous_time = row.observed_at
    return None


def rolling_origin_backtest(
    config: PR2ForecastConfig,
    bins: pd.DataFrame,
    profile_id: str,
    readings: Sequence[dict[str, Any]],
    origins: Sequence[datetime],
    *,
    events: Iterable[ForecastEvent | dict[str, Any]] = (),
) -> dict[str, Any]:
    """Chronological rolling-origin evaluation with operational baselines.

    Each origin receives the same complete raw collection, but the adapter
    excludes observations after its cutoff. Future values are used only after
    prediction for scoring. State advances in origin order, matching controlled
    online retraining rather than a random train/test split.
    """
    if not origins:
        raise ValueError("rolling_origin_backtest requires at least one origin")
    if not readings:
        raise ValueError("rolling_origin_backtest requires PR #2 readings")
    ordered_origins = sorted(origins)
    if any(value.tzinfo is None or value.utcoffset() is None for value in ordered_origins):
        raise ValueError("Every rolling origin must be timezone-aware")
    parsed_events = tuple(
        event if isinstance(event, ForecastEvent) else ForecastEvent.from_mapping(event)
        for event in events
    )
    maximum_time = max(
        max(
            _as_utc(value.get("timestamp"), "timestamp"),
            _as_utc(value.get("ingested_at", value.get("timestamp")), "ingested_at"),
        )
        for value in readings
    )
    full_history, _ = clean_pr2_history(
        readings,
        config.mapping(profile_id),
        maximum_time,
        config.forecast,
    )
    scores: list[dict[str, Any]] = []
    state: dict[str, Any] | None = None
    cutoff_checks: list[bool] = []
    for origin in ordered_origins:
        origin_utc = origin.astimezone(timezone.utc).replace(microsecond=0)
        adapter = AdaptivePR2ForecastAdapter(
            config, bins, profile_id, model_state=state
        )
        result = adapter.build_snapshot(readings, origin_utc, events=parsed_events)
        state = result.model_state
        cutoff_text = result.diagnostics.get("model_data_cutoff")
        cutoff_checks.append(
            cutoff_text is None or _as_utc(cutoff_text, "model_data_cutoff") <= origin_utc
        )
        predictions = result.frame.set_index("bin_id")
        for bin_id, prediction in predictions.iterrows():
            current_fill = prediction.get("fill_pct")
            if current_fill is None or pd.isna(current_fill):
                continue
            history_before = full_history.loc[
                (full_history["bin_id"] == bin_id)
                & (full_history["observed_at"] <= origin_utc)
                & full_history["usable"]
            ].sort_values("observed_at")
            future = full_history.loc[
                (full_history["bin_id"] == bin_id)
                & (full_history["observed_at"] > origin_utc)
                & (full_history["observed_at"] <= origin_utc + timedelta(hours=max(config.forecast.horizons_hours)))
                & full_history["usable"]
            ].sort_values("observed_at")
            if future.empty:
                continue
            recent = history_before.loc[
                history_before["observed_at"] >= origin_utc - timedelta(hours=24)
            ]
            sensor_failure = bool(
                not recent.empty and (~recent["sensor_confidence"].astype(bool)).mean() >= 0.5
            )
            sparse = len(history_before) < config.forecast.own_history_min_intervals + 1
            event_window = any(
                event.known_at <= origin_utc
                and event.end_at >= origin_utc
                and event.start_at <= origin_utc + timedelta(hours=168)
                and (
                    not event.affected_bin_ids
                    or str(bin_id).upper() in event.affected_bin_ids
                )
                for event in parsed_events
            )
            if sensor_failure:
                regime = "sensor_failure"
            elif sparse:
                regime = "sparse_history"
            elif bool(prediction.get("concept_drift_detected", False)):
                regime = "distribution_drift"
            elif event_window:
                regime = "event"
            else:
                regime = "normal"
            actual_tto = _interpolated_actual_tto(
                future.loc[
                    future["observed_at"]
                    < (
                        future.loc[future["collection_reset"], "observed_at"].min()
                        if bool(future["collection_reset"].any())
                        else origin_utc + timedelta(hours=max(config.forecast.horizons_hours) + 1)
                    )
                ],
                float(current_fill),
                origin_utc,
                config.forecast.overflow_threshold_pct,
            )
            reset_times = future.loc[future["collection_reset"], "observed_at"]
            first_reset_at = reset_times.min() if not reset_times.empty else None
            first_cycle_future = (
                future.loc[future["observed_at"] < first_reset_at]
                if first_reset_at is not None
                else future
            )
            previous_week_values = history_before.set_index("observed_at")["fill_pct"]
            if len(history_before) >= 2:
                prior_row = history_before.iloc[-2]
                latest_row = history_before.iloc[-1]
                last_duration = (
                    latest_row["observed_at"] - prior_row["observed_at"]
                ).total_seconds() / 3600.0
                last_observed_rate = (
                    max(
                        0.0,
                        float(latest_row["fill_pct"]) - float(prior_row["fill_pct"]),
                    )
                    / last_duration
                    if last_duration > 0
                    and latest_row["segment_id"] == prior_row["segment_id"]
                    else 0.0
                )
            else:
                last_observed_rate = 0.0
            for horizon in config.forecast.horizons_hours:
                target = origin_utc + timedelta(hours=horizon)
                eligible = first_cycle_future.loc[first_cycle_future["observed_at"] <= target]
                if eligible.empty:
                    continue
                actual_row = eligible.iloc[-1]
                actual = float(actual_row["fill_pct"])
                prior_target = target - timedelta(hours=168)
                prior_distance = abs(previous_week_values.index - prior_target)
                prior = previous_week_values.loc[
                    prior_distance <= timedelta(hours=config.forecast.step_hours / 2.0)
                ]
                previous_week = (
                    float(prior.iloc[-1]) if not prior.empty else float(current_fill)
                )
                seasonal_candidates = history_before.loc[
                    (history_before["observed_at"].dt.weekday == target.weekday())
                    & (history_before["observed_at"].dt.hour == target.hour)
                ]
                seasonal_average = (
                    float(seasonal_candidates.tail(8)["fill_pct"].mean())
                    if not seasonal_candidates.empty
                    else float(current_fill)
                )
                future_to_horizon = first_cycle_future.loc[
                    first_cycle_future["observed_at"] <= target
                ]
                overflow_event = bool(
                    (future_to_horizon["fill_pct"] >= config.forecast.overflow_threshold_pct).any()
                )
                censored_before_target = bool(
                    first_reset_at is not None and first_reset_at <= target
                )
                scores.append(
                    {
                        "origin": origin_utc,
                        "bin_id": bin_id,
                        "regime": regime,
                        "horizon": horizon,
                        "actual": actual,
                        "model": float(prediction[f"expected_fill_{horizon}h_pct"]),
                        "lower": float(prediction[f"lower_fill_{horizon}h_pct"]),
                        "upper": float(prediction[f"upper_fill_{horizon}h_pct"]),
                        "probability": float(prediction[f"overflow_probability_{horizon}h"]),
                        "current_fill": float(current_fill),
                        "last_rate": float(
                            np.clip(
                                float(current_fill) + last_observed_rate * horizon,
                                0,
                                100,
                            )
                        ),
                        "previous_week": previous_week,
                        "seasonal_moving_average": seasonal_average,
                        "overflow_event": overflow_event,
                        "actual_tto": actual_tto,
                        "predicted_tto": float(prediction["time_to_overflow_hours"]),
                        "fill_score_eligible": not censored_before_target,
                        "decision_score_eligible": not (
                            censored_before_target and not overflow_event
                        ),
                    }
                )
    frame = pd.DataFrame(scores)
    if frame.empty:
        raise ValueError("No future observations were available after the requested origins")

    def summarize(group: pd.DataFrame) -> dict[str, Any]:
        metrics: dict[str, Any] = {
            "scored_rows": int(len(group)),
            "fill_scored_rows": int(group["fill_score_eligible"].sum()),
            "decision_scored_rows": int(
                (
                    (group["horizon"] == 48)
                    & group["decision_score_eligible"]
                ).sum()
            ),
        }
        for horizon in config.forecast.horizons_hours:
            subset = group.loc[
                (group["horizon"] == horizon) & group["fill_score_eligible"]
            ]
            if subset.empty:
                continue
            for method in ("model", "current_fill", "last_rate", "previous_week", "seasonal_moving_average"):
                metrics[f"{method}_mae_{horizon}h_pct"] = float(
                    np.mean(np.abs(subset[method] - subset["actual"]))
                )
            metrics[f"interval_coverage_{horizon}h"] = float(
                ((subset["actual"] >= subset["lower"]) & (subset["actual"] <= subset["upper"])).mean()
            )
        decisions = group.loc[
            (group["horizon"] == 48) & group["decision_score_eligible"]
        ].copy()
        if not decisions.empty:
            predicted = decisions["probability"] >= config.forecast.high_probability_48h
            actual = decisions["overflow_event"].astype(bool)
            true_positive = int((predicted & actual).sum())
            false_positive = int((predicted & ~actual).sum())
            false_negative = int((~predicted & actual).sum())
            metrics["overflow_precision_48h"] = (
                true_positive / (true_positive + false_positive)
                if true_positive + false_positive
                else None
            )
            metrics["overflow_recall_48h"] = (
                true_positive / (true_positive + false_negative)
                if true_positive + false_negative
                else None
            )
            metrics["probability_brier_48h"] = float(
                np.mean((decisions["probability"] - actual.astype(float)) ** 2)
            )
            metrics["false_collection_trigger_rate_48h"] = float(
                false_positive / max(1, int(predicted.sum()))
            )
            metrics["missed_overflow_rate_48h"] = float(
                false_negative / max(1, int(actual.sum()))
            )
        tto = group.loc[
            group["actual_tto"].notna()
            & group["predicted_tto"].notna()
            & (group["horizon"] == max(config.forecast.horizons_hours))
        ]
        metrics["time_to_overflow_mae_hours"] = (
            float(np.mean(np.abs(tto["predicted_tto"] - tto["actual_tto"])))
            if not tto.empty
            else None
        )
        return metrics

    by_regime = {
        str(regime): summarize(group)
        for regime, group in frame.groupby("regime", sort=True)
    }
    calibration = []
    decisions = frame.loc[
        (frame["horizon"] == 48) & frame["decision_score_eligible"]
    ].copy()
    if not decisions.empty:
        decisions["probability_bin"] = pd.cut(
            decisions["probability"], bins=np.linspace(0, 1, 6), include_lowest=True
        )
        for _, group in decisions.groupby("probability_bin", observed=True):
            calibration.append(
                {
                    "predicted": float(group["probability"].mean()),
                    "observed": float(group["overflow_event"].astype(float).mean()),
                    "count": int(len(group)),
                }
            )
    return {
        "evaluation_design": "chronological rolling origin; no random split",
        "origins": [value.astimezone(timezone.utc).isoformat() for value in ordered_origins],
        "origin_count": len(ordered_origins),
        "future_feature_leakage_check": bool(all(cutoff_checks)),
        "estimated_density_used": False,
        "overall": summarize(frame),
        "by_regime": by_regime,
        "probability_calibration_48h": calibration,
    }
