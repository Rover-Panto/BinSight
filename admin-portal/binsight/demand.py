from __future__ import annotations

import hashlib
import math
from calendar import monthrange
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from functools import lru_cache
from typing import Any, Sequence

import numpy as np

from .config import Config, DemandEventTemplateConfig


@dataclass(frozen=True)
class DemandEvent:
    event_id: str
    event_type: str
    location: str
    start_hour: int
    end_hour: int
    buildup_hours: int
    decay_hours: int
    intensity: float
    known_at_hour: int
    target_area_types: tuple[str, ...] = ()
    target_site_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class DemandScenario:
    name: str = "normal_patterned"
    calendar_start_day: int = 0
    demand_multiplier: float = 1.0
    event_intensity_multiplier: float = 1.0
    event_frequency_multiplier: int = 1
    trend_per_year: float | None = None
    shared_surge_windows: tuple[tuple[int, int, float], ...] = ()
    local_surge_windows: tuple[tuple[int, int, float], ...] = ()
    local_surge_bin_ids: tuple[str, ...] = ()
    change_point_day: int | None = None
    change_point_multiplier: float = 1.0
    change_point_bin_ids: tuple[str, ...] = ()
    add_unannounced_event: bool = False


@dataclass(frozen=True)
class DemandContext:
    absolute_hours: np.ndarray
    actual_event_intensity: np.ndarray
    current_event_intensity: np.ndarray
    known_event_intensity_48h: np.ndarray
    known_event_intensity_168h: np.ndarray
    shared_regime: np.ndarray
    local_regime: np.ndarray
    regime_labels: tuple[str, ...]
    events: tuple[DemandEvent, ...]


@dataclass(frozen=True)
class DemandRealization:
    arrivals_kg: np.ndarray
    expected_mean_kg: np.ndarray
    context: DemandContext
    factor_diagnostics: dict[str, float] = field(default_factory=dict)


def _normalized(values: Sequence[float]) -> np.ndarray:
    array = np.asarray(values, dtype=float)
    return array / float(array.mean())


def _stable_fraction(text: str, salt: str) -> float:
    digest = hashlib.sha256(f"{salt}|{text}".encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") / float(2**64 - 1)


def _calendar(config: Config, absolute_hours: np.ndarray) -> list[datetime]:
    start = datetime.fromisoformat(config.demand.reference_start_utc)
    if start.tzinfo is None:
        raise ValueError("demand.reference_start_utc must include a timezone")
    return [start + timedelta(hours=int(hour)) for hour in absolute_hours]


def cyclic_month_factor(timestamp: datetime, monthly_pattern: Sequence[float]) -> float:
    """Smoothly interpolate monthly control points, including December to January."""
    values = np.asarray(monthly_pattern, dtype=float)
    if values.shape != (12,):
        raise ValueError("monthly_pattern must contain exactly 12 values")
    days = monthrange(timestamp.year, timestamp.month)[1]
    position = (
        timestamp.day - 1
        + timestamp.hour / 24.0
        + timestamp.minute / 1440.0
        + timestamp.second / 86400.0
    ) / days
    # Smoothstep avoids a derivative jump at each monthly control point.
    blend = position * position * (3.0 - 2.0 * position)
    current = timestamp.month - 1
    following = (current + 1) % 12
    return float((1.0 - blend) * values[current] + blend * values[following])


def smooth_annual_factor(
    day_of_year: float | np.ndarray,
    amplitude: float,
    peak_day: float,
) -> float | np.ndarray:
    """Cyclic annual component with a continuous year boundary."""
    result = 1.0 + float(amplitude) * np.cos(
        2.0 * np.pi * (np.asarray(day_of_year, dtype=float) - float(peak_day)) / 365.2425
    )
    return float(result) if np.ndim(result) == 0 else result


def _raw_deterministic_factor(
    item: Any,
    config: Config,
    calendar: Sequence[datetime],
    *,
    commercial: bool,
) -> np.ndarray:
    demand = config.demand
    hourly = _normalized(
        demand.commercial_hourly_factors
        if commercial
        else demand.residential_hourly_factors
    )
    weekly = _normalized(
        demand.commercial_day_of_week_factors
        if commercial
        else demand.residential_day_of_week_factors
    )
    monthly = _normalized(demand.month_of_year_factors)
    key = str(item.bin_id)
    hour_phase = int(round((_stable_fraction(key, "hour") - 0.5) * 4.0))
    week_phase = int(math.floor(_stable_fraction(key, "week") * 7.0))
    month_phase = int(math.floor(_stable_fraction(key, "month") * 12.0))
    amplitude = config.demand.bin_pattern_amplitude

    hour_pattern = np.roll(hourly, hour_phase)
    hour_pattern *= 1.0 + amplitude * np.cos(
        2 * np.pi * (np.arange(24) - (hour_phase % 24)) / 24.0
    )
    hour_pattern = _normalized(hour_pattern)
    week_pattern = weekly * (
        1.0
        + 0.5
        * amplitude
        * np.cos(2 * np.pi * (np.arange(7) - week_phase) / 7.0)
    )
    week_pattern = _normalized(week_pattern)
    month_pattern = monthly * (
        1.0
        + 0.35
        * amplitude
        * np.cos(2 * np.pi * (np.arange(12) - month_phase) / 12.0)
    )
    month_pattern = _normalized(month_pattern)
    annual_amplitude = (
        demand.commercial_annual_amplitude
        if commercial
        else demand.residential_annual_amplitude
    )
    annual_peak = (
        demand.commercial_annual_peak_day
        if commercial
        else demand.residential_annual_peak_day
    )

    result = np.empty(len(calendar), dtype=float)
    for index, timestamp in enumerate(calendar):
        day_of_year = timestamp.timetuple().tm_yday - 1
        annual = smooth_annual_factor(day_of_year, annual_amplitude, annual_peak)
        result[index] = (
            hour_pattern[timestamp.hour]
            * week_pattern[timestamp.weekday()]
            * cyclic_month_factor(timestamp, month_pattern)
            * annual
        )
    return result


def deterministic_seasonal_factor(
    item: Any,
    config: Config,
    absolute_hours: np.ndarray,
    *,
    commercial: bool,
) -> np.ndarray:
    """Return the normalized recurring factor for one bin/component.

    The complete hourly × weekly × monthly × annual product is normalized over
    a non-leap reference year. This prevents correlated seasonal factors from
    silently changing long-run demand while preserving each pattern's shape.
    """
    calendar = _calendar(config, np.asarray(absolute_hours, dtype=int))
    raw = _raw_deterministic_factor(item, config, calendar, commercial=commercial)
    normalizer = _deterministic_normalizer(item, config, commercial)
    return raw / normalizer


@lru_cache(maxsize=256)
def _deterministic_normalizer(item: Any, config: Config, commercial: bool) -> float:
    timezone = datetime.fromisoformat(config.demand.reference_start_utc).tzinfo
    reference_start = datetime(2025, 1, 1, tzinfo=timezone)
    reference_calendar = [
        reference_start + timedelta(hours=hour) for hour in range(365 * 24)
    ]
    return float(
        _raw_deterministic_factor(
            item, config, reference_calendar, commercial=commercial
        ).mean()
    )


def _event_targets(event: DemandEvent, item: Any) -> bool:
    site_match = not event.target_site_ids or str(item.site_id) in event.target_site_ids
    area_match = not event.target_area_types or str(item.area_type) in event.target_area_types
    return site_match and area_match


def event_effect(event: DemandEvent, absolute_hour: int) -> float:
    """Return additive event intensity with buildup, peak and decay."""
    hour = int(absolute_hour)
    if event.buildup_hours and event.start_hour - event.buildup_hours <= hour < event.start_hour:
        progress = (hour - (event.start_hour - event.buildup_hours) + 1) / event.buildup_hours
        return event.intensity * 0.5 * min(1.0, max(0.0, progress))
    if event.start_hour <= hour < event.end_hour:
        duration = max(1, event.end_hour - event.start_hour)
        progress = (hour - event.start_hour + 0.5) / duration
        return event.intensity * (0.5 + 0.5 * math.sin(math.pi * progress))
    if event.decay_hours and event.end_hour <= hour < event.end_hour + event.decay_hours:
        progress = (hour - event.end_hour + 1) / event.decay_hours
        return event.intensity * 0.5 * max(0.0, 1.0 - progress)
    return 0.0


def _template_events(
    template: DemandEventTemplateConfig,
    scenario: DemandScenario,
    range_start: int,
    range_end: int,
) -> list[DemandEvent]:
    period = max(
        24,
        template.recurrence_days * 24 // max(1, scenario.event_frequency_multiplier),
    )
    first = template.first_day * 24 + template.start_hour
    first_index = math.floor((range_start - first) / period) - 1
    last_index = math.ceil((range_end - first) / period) + 1
    events: list[DemandEvent] = []
    for occurrence in range(first_index, last_index + 1):
        start = first + occurrence * period
        end = start + template.duration_hours
        if end + template.decay_hours < range_start or start - template.buildup_hours >= range_end:
            continue
        events.append(
            DemandEvent(
                event_id=f"{template.event_type}:{start}",
                event_type=template.event_type,
                location=(
                    ",".join(template.target_site_ids)
                    if template.target_site_ids
                    else ",".join(template.target_area_types) or "district"
                ),
                start_hour=start,
                end_hour=end,
                buildup_hours=template.buildup_hours,
                decay_hours=template.decay_hours,
                intensity=template.intensity * scenario.event_intensity_multiplier,
                known_at_hour=start - template.known_lead_hours,
                target_area_types=template.target_area_types,
                target_site_ids=template.target_site_ids,
            )
        )
    return events


def build_event_calendar(
    bins: Sequence[Any],
    config: Config,
    scenario: DemandScenario,
    absolute_hours: np.ndarray,
) -> tuple[DemandEvent, ...]:
    range_start = int(absolute_hours[0])
    range_end = int(absolute_hours[-1]) + 1
    events = [
        event
        for template in config.demand.event_templates
        for event in _template_events(template, scenario, range_start, range_end)
    ]
    if scenario.add_unannounced_event and bins:
        start = scenario.calendar_start_day * 24 + 13 * 24 + 17
        target_site = str(bins[0].site_id)
        events.append(
            DemandEvent(
                event_id=f"unannounced-commercial-surge:{start}",
                event_type="unannounced-commercial-surge",
                location=target_site,
                start_hour=start,
                end_hour=start + 10,
                buildup_hours=3,
                decay_hours=18,
                intensity=1.20 * scenario.event_intensity_multiplier,
                known_at_hour=start + 1,
                target_site_ids=(target_site,),
            )
        )
    return tuple(sorted(events, key=lambda event: (event.start_hour, event.event_id)))


def _ar1_factors(
    rng: np.random.Generator,
    length: int,
    width: int,
    phi: float,
    sigma: float,
) -> np.ndarray:
    burn_in = 240
    state = np.zeros(width, dtype=float)
    values = np.zeros((length, width), dtype=float)
    stationary_variance = sigma**2 / max(1e-12, 1.0 - phi**2)
    for index in range(length + burn_in):
        state = phi * state + rng.normal(0.0, sigma, size=width)
        if index >= burn_in:
            values[index - burn_in] = np.exp(state - 0.5 * stationary_variance)
    return values


def _event_context(
    bins: Sequence[Any],
    absolute_hours: np.ndarray,
    events: Sequence[DemandEvent],
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    shape = (len(absolute_hours), len(bins))
    actual_current = np.zeros(shape, dtype=float)
    observable_current = np.zeros(shape, dtype=float)
    known_48 = np.zeros(shape, dtype=float)
    known_168 = np.zeros(shape, dtype=float)
    first_hour = int(absolute_hours[0])
    last_hour = int(absolute_hours[-1])
    for event in events:
        targets = [index for index, item in enumerate(bins) if _event_targets(event, item)]
        if not targets:
            continue
        active_start = max(first_hour, event.start_hour - event.buildup_hours)
        active_end = min(last_hour + 1, event.end_hour + event.decay_hours)
        for absolute_hour in range(active_start, active_end):
            effect = event_effect(event, absolute_hour)
            if effect > 0:
                actual_current[absolute_hour - first_hour, targets] += effect
                if absolute_hour >= event.known_at_hour:
                    observable_current[absolute_hour - first_hour, targets] += effect
        decision_start = max(first_hour, event.known_at_hour)
        decision_end_48 = min(last_hour + 1, event.end_hour + event.decay_hours)
        for absolute_hour in range(decision_start, decision_end_48):
            if event.start_hour - event.buildup_hours <= absolute_hour + 48:
                known_48[absolute_hour - first_hour, targets] = np.maximum(
                    known_48[absolute_hour - first_hour, targets], event.intensity
                )
            if event.start_hour - event.buildup_hours <= absolute_hour + 168:
                known_168[absolute_hour - first_hour, targets] = np.maximum(
                    known_168[absolute_hour - first_hour, targets], event.intensity
                )
    return actual_current, observable_current, known_48, known_168


def generate_demand_realization(
    bins: Sequence[Any],
    config: Config,
    seed: int,
    horizon_hours: int,
    *,
    start_day: int = 0,
    scenario: DemandScenario | None = None,
) -> DemandRealization:
    """Generate paired, exogenous patterned waste arrivals.

    ``mean[b,t]`` is the base residential/commercial demand multiplied by
    normalized recurring factors, event shape, trend, a district AR(1) regime,
    and an independent local AR(1) regime. Gamma sampling keeps arrivals
    non-negative. Nothing in this function observes a routing policy.
    """
    active = scenario or DemandScenario(calendar_start_day=start_day)
    effective_start_day = active.calendar_start_day if scenario is not None else start_day
    absolute_hours = effective_start_day * 24 + np.arange(horizon_hours, dtype=int)
    rng = np.random.default_rng(seed)
    shared = _ar1_factors(
        rng,
        horizon_hours,
        1,
        config.demand.shared_regime_phi,
        config.demand.shared_regime_sigma,
    )[:, 0]
    local = _ar1_factors(
        rng,
        horizon_hours,
        len(bins),
        config.demand.local_regime_phi,
        config.demand.local_regime_sigma,
    )
    relative_days = np.arange(horizon_hours, dtype=float) / 24.0
    for start, end, multiplier in active.shared_surge_windows:
        mask = (relative_days >= start) & (relative_days < end)
        shared[mask] *= multiplier
    selected_local = set(active.local_surge_bin_ids)
    for start, end, multiplier in active.local_surge_windows:
        mask = (relative_days >= start) & (relative_days < end)
        for index, item in enumerate(bins):
            if not selected_local or str(item.bin_id) in selected_local:
                local[mask, index] *= multiplier

    events = build_event_calendar(bins, config, active, absolute_hours)
    actual_event, current_event, known_48, known_168 = _event_context(
        bins, absolute_hours, events
    )
    event_multiplier = 1.0 + actual_event
    means = np.zeros((horizon_hours, len(bins)), dtype=float)
    trend_rate = (
        config.demand.base_trend_per_year
        if active.trend_per_year is None
        else active.trend_per_year
    )
    trend = np.maximum(
        0.5,
        1.0 + trend_rate * absolute_hours.astype(float) / (365.2425 * 24.0),
    )
    for index, item in enumerate(bins):
        residential_factor = deterministic_seasonal_factor(
            item, config, absolute_hours, commercial=False
        )
        commercial_factor = deterministic_seasonal_factor(
            item, config, absolute_hours, commercial=True
        )
        base = (
            item.households
            * config.waste.household_kg_per_day
            / 24.0
            * residential_factor
            + item.commercial_units
            * config.waste.commercial_kg_per_day
            / 24.0
            * commercial_factor
        )
        base *= float(getattr(item, "demand_rate_multiplier", 1.0))
        means[:, index] = (
            base
            * event_multiplier[:, index]
            * trend
            * shared
            * local[:, index]
            * active.demand_multiplier
        )
        if active.change_point_day is not None:
            target_ids = set(active.change_point_bin_ids)
            if not target_ids or str(item.bin_id) in target_ids:
                means[relative_days >= active.change_point_day, index] *= (
                    active.change_point_multiplier
                )

    means = np.maximum(means, 1e-12)
    arrivals = rng.gamma(config.demand.gamma_shape, means / config.demand.gamma_shape)
    labels = tuple(
        "surge" if value >= 1.20 else ("quiet" if value <= 0.82 else "normal")
        for value in shared
    )
    context = DemandContext(
        absolute_hours=absolute_hours,
        actual_event_intensity=actual_event,
        current_event_intensity=current_event,
        known_event_intensity_48h=known_48,
        known_event_intensity_168h=known_168,
        shared_regime=shared,
        local_regime=local,
        regime_labels=labels,
        events=events,
    )
    return DemandRealization(
        arrivals_kg=arrivals,
        expected_mean_kg=means,
        context=context,
        factor_diagnostics={
            "expected_total_kg": float(means.sum()),
            "sampled_total_kg": float(arrivals.sum()),
            "shared_regime_mean": float(shared.mean()),
            "local_regime_mean": float(local.mean()),
            "event_affected_bin_hours": float(np.count_nonzero(actual_event)),
        },
    )
