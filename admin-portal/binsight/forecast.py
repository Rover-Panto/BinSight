from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.metrics import mean_absolute_error

from .config import Config
from .district import BinSpec, generate_hourly_waste
from .observations import (
    assert_observation_only_columns,
    generate_sensor_noise_scenario,
    observe_sensors,
)


FEATURE_COLUMNS = [
    "fill_pct",
    "weight_kg",
    "confidence_flag",
    "growth_6h_pct",
    "growth_24h_pct",
    "hour_sin",
    "hour_cos",
    "dow_sin",
    "dow_cos",
    "households",
    "commercial_units",
    "commercial_share",
]


@dataclass
class ForecastBundle:
    mean_model: HistGradientBoostingRegressor
    upper_model: HistGradientBoostingRegressor
    evaluation: dict[str, float]

    def predict(self, feature_frame: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
        assert_observation_only_columns(FEATURE_COLUMNS)
        features = feature_frame[FEATURE_COLUMNS]
        mean = np.maximum(0.0, self.mean_model.predict(features))
        upper = np.maximum(mean, self.upper_model.predict(features))
        return mean, upper


def make_feature_row(
    item: BinSpec,
    fill_pct: float,
    weight_kg: float,
    confidence_flag: bool,
    observations: Sequence[float],
    absolute_hour: int,
) -> dict[str, float]:
    interval = 6
    growth_6h = max(0.0, fill_pct - observations[-1]) if observations else 0.0
    recent = list(observations[-4:]) + [fill_pct]
    growth_24h = sum(max(0.0, b - a) for a, b in zip(recent[:-1], recent[1:]))
    hour = absolute_hour % 24
    dow = (absolute_hour // 24) % 7
    total_units = item.households + item.commercial_units
    return {
        "fill_pct": float(fill_pct),
        "weight_kg": float(weight_kg),
        "confidence_flag": float(bool(confidence_flag)),
        "growth_6h_pct": float(growth_6h),
        "growth_24h_pct": float(growth_24h),
        "hour_sin": float(np.sin(2 * np.pi * hour / 24)),
        "hour_cos": float(np.cos(2 * np.pi * hour / 24)),
        "dow_sin": float(np.sin(2 * np.pi * dow / 7)),
        "dow_cos": float(np.cos(2 * np.pi * dow / 7)),
        "households": float(item.households),
        "commercial_units": float(item.commercial_units),
        "commercial_share": float(item.commercial_units / total_units if total_units else 0),
    }


def training_frame(bins: list[BinSpec], config: Config, seed: int) -> pd.DataFrame:
    interval = config.waste.sensor_interval_hours
    history_hours = config.waste.history_days * 24
    future = config.operations.forecast_horizon_hours
    arrivals = generate_hourly_waste(
        bins, config, seed=seed, horizon_hours=history_hours + future, start_day=-config.waste.history_days
    )
    fill = np.zeros(len(bins), dtype=float)
    observations: list[list[float]] = [[] for _ in bins]
    rows: list[dict[str, float]] = []
    sensor_scenario = generate_sensor_noise_scenario(
        config,
        seed + 17,
        observation_count=history_hours // interval + 1,
        bin_count=len(bins),
    )
    capacities = np.array([item.capacity_kg for item in bins], dtype=float)
    sensor_index = 0
    for hour in range(history_hours):
        fill += arrivals[hour]
        first_fixed_hour = (
            config.operations.fixed_interval_days * 24 + config.operations.decision_hour
        )
        if (
            hour >= first_fixed_hour
            and (hour - config.operations.decision_hour)
            % (config.operations.fixed_interval_days * 24)
            == 0
        ):
            fill[:] = 0.0
        if hour % interval != 0:
            continue
        batch = observe_sensors(
            fill,
            capacities,
            sensor_scenario,
            sensor_index,
            hour,
            config,
        )
        for index, item in enumerate(bins):
            observed = float(batch.fill_pct[index])
            if not np.isfinite(observed):
                observed = observations[index][-1] if observations[index] else 0.0
            observed_weight = float(batch.weight_kg[index])
            if not np.isfinite(observed_weight):
                observed_weight = observed / 100.0 * item.capacity_kg
            feature = make_feature_row(
                item,
                observed,
                observed_weight,
                bool(batch.confidence_flag[index]),
                observations[index],
                hour,
            )
            target_growth = (
                100.0 * arrivals[hour + 1 : hour + future + 1, index].sum() / item.capacity_kg
            )
            feature.update(
                {
                    "timestamp_index": float(hour),
                    "bin_index": float(index),
                    "target_growth_horizon_pct": float(target_growth),
                    "naive_growth_horizon_pct": float(
                        feature["growth_24h_pct"] * future / 24.0
                    ),
                }
            )
            rows.append(feature)
            observations[index].append(observed)
        sensor_index += 1
    frame = pd.DataFrame(rows)
    assert_observation_only_columns(FEATURE_COLUMNS)
    return frame


def train_forecaster(bins: list[BinSpec], config: Config, seed: int) -> tuple[ForecastBundle, pd.DataFrame]:
    frame = training_frame(bins, config, seed)
    unique_times = np.sort(frame["timestamp_index"].unique())
    cutoff = unique_times[max(1, int(len(unique_times) * 0.8))]
    train = frame[frame["timestamp_index"] < cutoff]
    test = frame[frame["timestamp_index"] >= cutoff]
    if train.empty or test.empty:
        raise ValueError("Forecast history is too short for a chronological holdout")
    common = dict(max_iter=160, learning_rate=0.06, max_leaf_nodes=15, min_samples_leaf=25, random_state=seed)
    mean_model = HistGradientBoostingRegressor(loss="squared_error", **common)
    upper_model = HistGradientBoostingRegressor(loss="quantile", quantile=0.90, **common)
    mean_model.fit(train[FEATURE_COLUMNS], train["target_growth_horizon_pct"])
    upper_model.fit(train[FEATURE_COLUMNS], train["target_growth_horizon_pct"])
    prediction = np.maximum(0.0, mean_model.predict(test[FEATURE_COLUMNS]))
    naive = np.maximum(0.0, test["naive_growth_horizon_pct"].to_numpy())
    target = test["target_growth_horizon_pct"].to_numpy()
    evaluation = {
        "training_rows": float(len(train)),
        "holdout_rows": float(len(test)),
        "chronological_cutoff_hour": float(cutoff),
        "forecast_horizon_hours": float(config.operations.forecast_horizon_hours),
        "model_mae_growth_pct_horizon": float(mean_absolute_error(target, prediction)),
        "naive_mae_growth_pct_horizon": float(mean_absolute_error(target, naive)),
        "model_improvement_pct": float(
            100 * (mean_absolute_error(target, naive) - mean_absolute_error(target, prediction))
            / max(mean_absolute_error(target, naive), 1e-9)
        ),
    }
    return ForecastBundle(mean_model, upper_model, evaluation), frame
