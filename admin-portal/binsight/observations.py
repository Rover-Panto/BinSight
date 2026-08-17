from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .config import Config


FORBIDDEN_INPUT_TOKENS = ("latent", "true", "future", "target")


@dataclass(frozen=True)
class SensorNoiseScenario:
    fill_random_pct: np.ndarray
    weight_random_kg: np.ndarray
    fill_bias_pct: np.ndarray
    weight_bias_kg: np.ndarray
    fill_drift_pct_per_day: np.ndarray
    weight_drift_kg_per_day: np.ndarray
    fill_outlier_pct: np.ndarray
    weight_outlier_kg: np.ndarray
    fill_missing: np.ndarray
    weight_missing: np.ndarray
    outlier_mask: np.ndarray


@dataclass(frozen=True)
class SensorObservationBatch:
    fill_pct: np.ndarray
    weight_kg: np.ndarray
    confidence_score: np.ndarray
    confidence_flag: np.ndarray
    upper_fill_pct: np.ndarray
    upper_weight_kg: np.ndarray
    disagreement_flag: np.ndarray
    missing_flag: np.ndarray
    quality_flags: tuple[tuple[str, ...], ...]


def assert_observation_only_columns(columns) -> None:
    forbidden = [
        str(column)
        for column in columns
        if any(token in str(column).lower() for token in FORBIDDEN_INPUT_TOKENS)
    ]
    if forbidden:
        raise ValueError("Hidden or future state cannot be a model/routing input: " + ", ".join(forbidden))


def generate_sensor_noise_scenario(
    config: Config,
    seed: int,
    observation_count: int,
    bin_count: int,
    *,
    missing_probability: float | None = None,
    outlier_probability: float | None = None,
) -> SensorNoiseScenario:
    """Generate policy-independent error streams for paired simulations."""
    if observation_count < 1 or bin_count < 1:
        raise ValueError("Sensor scenario dimensions must be positive")
    sensor = config.sensor
    missing_p = sensor.missing_probability if missing_probability is None else missing_probability
    outlier_p = sensor.outlier_probability if outlier_probability is None else outlier_probability
    if not 0 <= missing_p <= 1 or not 0 <= outlier_p <= 1:
        raise ValueError("Sensor failure probabilities must be in 0..1")

    streams = np.random.SeedSequence(seed).spawn(11)
    rng = [np.random.default_rng(stream) for stream in streams]
    shape = (observation_count, bin_count)
    fill_outlier_mask = rng[6].random(shape) < outlier_p
    weight_outlier_mask = rng[7].random(shape) < outlier_p
    return SensorNoiseScenario(
        fill_random_pct=rng[0].normal(0, sensor.fill_random_sd_pct, size=shape),
        weight_random_kg=rng[1].normal(0, sensor.weight_random_sd_kg, size=shape),
        fill_bias_pct=rng[2].normal(0, sensor.fill_bias_sd_pct, size=bin_count),
        weight_bias_kg=rng[3].normal(0, sensor.weight_bias_sd_kg, size=bin_count),
        fill_drift_pct_per_day=rng[4].normal(
            0, sensor.fill_drift_sd_pct_per_day, size=bin_count
        ),
        weight_drift_kg_per_day=rng[5].normal(
            0, sensor.weight_drift_sd_kg_per_day, size=bin_count
        ),
        fill_outlier_pct=np.where(
            fill_outlier_mask,
            rng[8].normal(0, sensor.fill_outlier_sd_pct, size=shape),
            0.0,
        ),
        weight_outlier_kg=np.where(
            weight_outlier_mask,
            rng[9].normal(0, sensor.weight_outlier_sd_kg, size=shape),
            0.0,
        ),
        fill_missing=rng[10].random(shape) < missing_p,
        weight_missing=np.random.default_rng(streams[10].spawn(1)[0]).random(shape) < missing_p,
        outlier_mask=fill_outlier_mask | weight_outlier_mask,
    )


def observe_sensors(
    hidden_mass_kg: np.ndarray,
    capacities_kg: np.ndarray,
    scenario: SensorNoiseScenario,
    observation_index: int,
    absolute_hour: float,
    config: Config,
) -> SensorObservationBatch:
    """Convert private simulator state into noisy ultrasonic/load-cell observations."""
    mass = np.asarray(hidden_mass_kg, dtype=float)
    capacities = np.asarray(capacities_kg, dtype=float)
    if mass.shape != capacities.shape:
        raise ValueError("Hidden mass and capacities must have the same shape")
    if observation_index < 0 or observation_index >= scenario.fill_random_pct.shape[0]:
        raise IndexError("Sensor observation index is outside the generated scenario")

    days = float(absolute_hour) / 24.0
    physical_fill_pct = 100.0 * mass / capacities
    fill = (
        physical_fill_pct
        + scenario.fill_bias_pct
        + scenario.fill_drift_pct_per_day * days
        + scenario.fill_random_pct[observation_index]
        + scenario.fill_outlier_pct[observation_index]
    )
    weight = (
        mass
        + scenario.weight_bias_kg
        + scenario.weight_drift_kg_per_day * days
        + scenario.weight_random_kg[observation_index]
        + scenario.weight_outlier_kg[observation_index]
    )
    fill = np.clip(fill, 0.0, 100.0)
    weight = np.clip(weight, 0.0, config.operations.crane_lift_limit_kg)
    fill = fill.astype(float)
    weight = weight.astype(float)
    fill[scenario.fill_missing[observation_index]] = np.nan
    weight[scenario.weight_missing[observation_index]] = np.nan

    weight_fill_pct = 100.0 * weight / capacities
    both = np.isfinite(fill) & np.isfinite(weight)
    disagreement = both & (
        np.abs(fill - weight_fill_pct) > config.sensor.disagreement_threshold_pct
    )
    missing = ~np.isfinite(fill) | ~np.isfinite(weight)
    both_missing = ~np.isfinite(fill) & ~np.isfinite(weight)
    fused = np.where(
        np.isfinite(fill) & np.isfinite(weight_fill_pct),
        np.maximum(fill, weight_fill_pct),
        np.where(np.isfinite(fill), fill, weight_fill_pct),
    )

    score = np.ones(len(mass), dtype=float)
    score -= 0.45 * missing.astype(float)
    score -= 0.40 * disagreement.astype(float)
    score -= 0.35 * scenario.outlier_mask[observation_index].astype(float)
    score[both_missing] = 0.0
    score = np.clip(score, 0.0, 1.0)
    confidence = score >= config.sensor.confidence_threshold

    high_margin = config.sensor.upper_uncertainty_z * config.sensor.fill_random_sd_pct
    one_sensor_missing = missing & ~both_missing
    margin = np.where(
        confidence,
        high_margin,
        np.where(
            one_sensor_missing,
            config.sensor.single_sensor_margin_pct,
            config.sensor.low_confidence_margin_pct,
        ),
    )
    upper_fill = np.where(np.isfinite(fused), fused + margin, 100.0)
    upper_fill = np.clip(upper_fill, 0.0, 150.0)
    weight_margin = config.sensor.upper_uncertainty_z * config.sensor.weight_random_sd_kg
    upper_weight = np.where(
        np.isfinite(weight),
        weight + np.where(confidence, weight_margin, weight_margin * 2.0),
        upper_fill / 100.0 * capacities,
    )
    upper_weight = np.clip(upper_weight, 0.0, config.operations.crane_lift_limit_kg)

    flags: list[tuple[str, ...]] = []
    for index in range(len(mass)):
        row_flags: list[str] = []
        if not np.isfinite(fill[index]):
            row_flags.append("ultrasonic_missing")
        if not np.isfinite(weight[index]):
            row_flags.append("load_cell_missing")
        if disagreement[index]:
            row_flags.append("sensor_disagreement")
        if scenario.outlier_mask[observation_index, index]:
            row_flags.append("sensor_outlier")
        if not confidence[index]:
            row_flags.append("low_confidence")
        flags.append(tuple(row_flags))

    return SensorObservationBatch(
        fill_pct=fused.astype(float),
        weight_kg=weight,
        confidence_score=score,
        confidence_flag=confidence,
        upper_fill_pct=upper_fill,
        upper_weight_kg=upper_weight,
        disagreement_flag=disagreement,
        missing_flag=missing,
        quality_flags=tuple(flags),
    )
