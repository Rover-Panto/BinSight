from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Sequence

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.calibration import CalibratedClassifierCV, calibration_curve
from sklearn.metrics import (
    brier_score_loss,
    mean_absolute_error,
    mean_pinball_loss,
    precision_score,
    recall_score,
)
from sklearn.frozen import FrozenEstimator

from .config import Config
from .demand import DemandScenario, generate_demand_realization
from .district import BinSpec
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
    "growth_168h_pct",
    "hour_sin",
    "hour_cos",
    "dow_sin",
    "dow_cos",
    "month_sin",
    "month_cos",
    "year_sin",
    "year_cos",
    "households",
    "commercial_units",
    "commercial_share",
    "observation_count_24h",
    "max_observation_gap_hours",
    "collection_reset_24h",
    "hours_since_collection",
    "historical_bin_growth_24h",
    "known_event_intensity_48h",
    "known_event_intensity_168h",
    "current_event_intensity",
    "weight_available",
]

FORECAST_HORIZONS = (6, 24, 48, 168)


@dataclass
class ForecastBundle:
    mean_model: HistGradientBoostingRegressor
    upper_model: HistGradientBoostingRegressor
    evaluation: dict[str, object]
    upper_adjustment_pct: float = 0.0
    horizon_models: dict[int, HistGradientBoostingRegressor] = field(default_factory=dict)
    overflow_model_48h: CalibratedClassifierCV | None = None
    overflow_model_6h: CalibratedClassifierCV | None = None

    def predict(self, feature_frame: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
        assert_observation_only_columns(FEATURE_COLUMNS)
        features = feature_frame[FEATURE_COLUMNS]
        mean = np.maximum(0.0, self.mean_model.predict(features))
        upper = np.maximum(
            mean, self.upper_model.predict(features) + self.upper_adjustment_pct
        )
        return mean, upper

    def predict_horizons(self, feature_frame: pd.DataFrame) -> dict[int, np.ndarray]:
        assert_observation_only_columns(FEATURE_COLUMNS)
        features = feature_frame[FEATURE_COLUMNS]
        return {
            horizon: np.maximum(0.0, model.predict(features))
            for horizon, model in sorted(self.horizon_models.items())
        }

    def predict_overflow_probability_48h(self, feature_frame: pd.DataFrame) -> np.ndarray:
        if self.overflow_model_48h is None:
            return np.full(len(feature_frame), np.nan, dtype=float)
        return self.overflow_model_48h.predict_proba(feature_frame[FEATURE_COLUMNS])[:, 1]

    def predict_overflow_probability_6h(self, feature_frame: pd.DataFrame) -> np.ndarray:
        if self.overflow_model_6h is None:
            return np.full(len(feature_frame), np.nan, dtype=float)
        return self.overflow_model_6h.predict_proba(feature_frame[FEATURE_COLUMNS])[:, 1]


def _timed_history(
    observations: Sequence[float] | Sequence[tuple[float, float]],
    absolute_hour: float,
) -> list[tuple[float, float]]:
    timed: list[tuple[float, float]] = []
    if observations and isinstance(observations[0], (tuple, list)):
        for raw_hour, raw_fill in observations:  # type: ignore[misc]
            hour = float(raw_hour)
            fill = float(raw_fill)
            if np.isfinite(hour) and np.isfinite(fill) and hour <= absolute_hour:
                timed.append((hour, fill))
    else:
        values = [float(value) for value in observations if np.isfinite(value)]
        start = absolute_hour - 6.0 * len(values)
        timed = [(start + 6.0 * index, value) for index, value in enumerate(values)]
    return sorted(timed, key=lambda item: item[0])


def _window_growth(
    history: list[tuple[float, float]], current_fill: float, absolute_hour: float, hours: float
) -> float:
    window = [(hour, fill) for hour, fill in history if absolute_hour - hours <= hour <= absolute_hour]
    values = [fill for _, fill in window] + [float(current_fill)]
    if len(values) < 2:
        return 0.0
    # A large downward step is a collection reset, not negative waste growth.
    reset_positions = [
        index + 1 for index, (before, after) in enumerate(zip(values[:-1], values[1:]))
        if before - after >= 35.0
    ]
    if reset_positions:
        values = values[reset_positions[-1] :]
    return float(sum(max(0.0, after - before) for before, after in zip(values[:-1], values[1:])))


def make_feature_row(
    item: BinSpec,
    fill_pct: float,
    weight_kg: float | None,
    confidence_flag: bool,
    observations: Sequence[float] | Sequence[tuple[float, float]],
    absolute_hour: int,
    *,
    last_collection_hour: float | None = None,
    current_event_intensity: float = 0.0,
    known_event_intensity_48h: float = 0.0,
    known_event_intensity_168h: float = 0.0,
    calendar_timestamp: datetime | None = None,
) -> dict[str, float]:
    history = _timed_history(observations, float(absolute_hour))
    growth_6h = _window_growth(history, fill_pct, float(absolute_hour), 6.0)
    growth_24h = _window_growth(history, fill_pct, float(absolute_hour), 24.0)
    growth_168h = _window_growth(history, fill_pct, float(absolute_hour), 168.0)
    recent = [(hour, value) for hour, value in history if absolute_hour - 24 <= hour]
    gaps = [after[0] - before[0] for before, after in zip(recent[:-1], recent[1:])]
    reset = any(before[1] - after[1] >= 35.0 for before, after in zip(recent[:-1], recent[1:]))
    hour = absolute_hour % 24
    dow = (absolute_hour // 24) % 7
    timestamp = calendar_timestamp or (
        datetime(2026, 1, 1) + timedelta(hours=int(absolute_hour))
    )
    month = timestamp.month - 1
    day_of_year = timestamp.timetuple().tm_yday - 1
    total_units = item.households + item.commercial_units
    positive_growth = [
        max(0.0, after[1] - before[1])
        for before, after in zip(history[:-1], history[1:])
        if after[0] >= absolute_hour - 168
    ]
    observed_span_days = max(
        1.0,
        (
            (history[-1][0] - history[0][0]) / 24.0
            if len(history) >= 2
            else 1.0
        ),
    )
    return {
        "fill_pct": float(fill_pct),
        "weight_kg": float(weight_kg) if weight_kg is not None else float("nan"),
        "confidence_flag": float(bool(confidence_flag)),
        "growth_6h_pct": float(growth_6h),
        "growth_24h_pct": float(growth_24h),
        "growth_168h_pct": float(growth_168h),
        "hour_sin": float(np.sin(2 * np.pi * hour / 24)),
        "hour_cos": float(np.cos(2 * np.pi * hour / 24)),
        "dow_sin": float(np.sin(2 * np.pi * dow / 7)),
        "dow_cos": float(np.cos(2 * np.pi * dow / 7)),
        "month_sin": float(np.sin(2 * np.pi * month / 12)),
        "month_cos": float(np.cos(2 * np.pi * month / 12)),
        "year_sin": float(np.sin(2 * np.pi * day_of_year / 365.2425)),
        "year_cos": float(np.cos(2 * np.pi * day_of_year / 365.2425)),
        "households": float(item.households),
        "commercial_units": float(item.commercial_units),
        "commercial_share": float(item.commercial_units / total_units if total_units else 0),
        "observation_count_24h": float(len(recent) + 1),
        "max_observation_gap_hours": float(max(gaps) if gaps else 24.0),
        "collection_reset_24h": float(reset),
        "hours_since_collection": float(
            min(24.0 * 365.0, max(0.0, absolute_hour - last_collection_hour))
            if last_collection_hour is not None
            else 24.0 * 365.0
        ),
        "historical_bin_growth_24h": float(
            sum(positive_growth) / observed_span_days
        ),
        "known_event_intensity_48h": float(max(0.0, known_event_intensity_48h)),
        "known_event_intensity_168h": float(max(0.0, known_event_intensity_168h)),
        "current_event_intensity": float(max(0.0, current_event_intensity)),
        "weight_available": float(weight_kg is not None and np.isfinite(weight_kg)),
    }


def training_frame(bins: list[BinSpec], config: Config, seed: int) -> pd.DataFrame:
    interval = config.waste.sensor_interval_hours
    history_hours = config.waste.history_days * 24
    max_horizon = max(FORECAST_HORIZONS)
    realization = generate_demand_realization(
        bins,
        config,
        seed=seed,
        horizon_hours=history_hours,
        scenario=DemandScenario(
            name="forecast_history",
            calendar_start_day=-config.waste.history_days,
        ),
    )
    arrivals = realization.arrivals_kg
    fill = np.zeros(len(bins), dtype=float)
    observations: list[list[tuple[float, float]]] = [[] for _ in bins]
    rows: list[dict[str, float]] = []
    sensor_scenario = generate_sensor_noise_scenario(
        config,
        seed + 17,
        observation_count=history_hours // interval + 1,
        bin_count=len(bins),
    )
    capacities = np.array([item.capacity_kg for item in bins], dtype=float)
    last_collection_hour = np.full(len(bins), np.nan, dtype=float)
    reference_start = datetime.fromisoformat(config.demand.reference_start_utc)
    sensor_index = 0
    for local_hour in range(history_hours - max_horizon):
        absolute_hour = -history_hours + local_hour
        fill += arrivals[local_hour]
        if (
            (absolute_hour - config.operations.decision_hour)
            % (config.operations.fixed_interval_days * 24)
            == 0
        ):
            fill[:] = 0.0
            last_collection_hour[:] = absolute_hour
        if absolute_hour % interval != 0:
            continue
        batch = observe_sensors(
            fill,
            capacities,
            sensor_scenario,
            sensor_index,
            local_hour,
            config,
        )
        for index, item in enumerate(bins):
            observed = float(batch.fill_pct[index])
            if not np.isfinite(observed):
                observed = observations[index][-1][1] if observations[index] else 0.0
            observed_weight = float(batch.weight_kg[index])
            if not np.isfinite(observed_weight):
                observed_weight = observed / 100.0 * item.capacity_kg
            feature = make_feature_row(
                item,
                observed,
                observed_weight,
                bool(batch.confidence_flag[index]),
                observations[index],
                absolute_hour,
                last_collection_hour=(
                    float(last_collection_hour[index])
                    if np.isfinite(last_collection_hour[index])
                    else None
                ),
                current_event_intensity=float(
                    realization.context.current_event_intensity[local_hour, index]
                ),
                known_event_intensity_48h=float(
                    realization.context.known_event_intensity_48h[local_hour, index]
                ),
                known_event_intensity_168h=float(
                    realization.context.known_event_intensity_168h[local_hour, index]
                ),
                calendar_timestamp=reference_start + timedelta(hours=absolute_hour),
            )
            targets = {
                horizon: 100.0
                * arrivals[
                    local_hour + 1 : local_hour + horizon + 1, index
                ].sum()
                / item.capacity_kg
                for horizon in FORECAST_HORIZONS
            }
            cumulative = np.cumsum(
                arrivals[local_hour + 1 : local_hour + max_horizon + 1, index]
            )
            remaining_mass = max(0.0, item.capacity_kg - fill[index])
            crossings = np.flatnonzero(cumulative >= remaining_mass)
            actual_tto = float(crossings[0] + 1) if len(crossings) else np.nan
            feature.update(
                {
                    "timestamp_index": float(absolute_hour),
                    "bin_index": float(index),
                    **{
                        f"target_growth_{horizon}h_pct": float(target)
                        for horizon, target in targets.items()
                    },
                    "target_growth_horizon_pct": float(targets[48]),
                    "naive_growth_horizon_pct": float(
                        feature["growth_24h_pct"] * 2.0
                    ),
                    "actual_time_to_overflow_hours": actual_tto,
                    "actual_overflow_within_48h": float(
                        targets[48] >= max(0.0, 100.0 - observed)
                    ),
                    "actual_overflow_within_6h": float(
                        targets[6] >= max(0.0, 100.0 - observed)
                    ),
                }
            )
            rows.append(feature)
            observations[index].append((float(absolute_hour), observed))
        sensor_index += 1
    frame = pd.DataFrame(rows)
    assert_observation_only_columns(FEATURE_COLUMNS)
    return frame


def train_forecaster(bins: list[BinSpec], config: Config, seed: int) -> tuple[ForecastBundle, pd.DataFrame]:
    frame = training_frame(bins, config, seed)
    unique_times = np.sort(frame["timestamp_index"].unique())
    calibration_start = unique_times[max(1, int(len(unique_times) * 0.65))]
    holdout_start = unique_times[max(2, int(len(unique_times) * 0.82))]
    purge = float(max(FORECAST_HORIZONS))
    train = frame[frame["timestamp_index"] < calibration_start - purge]
    calibration = frame[
        (frame["timestamp_index"] >= calibration_start)
        & (frame["timestamp_index"] < holdout_start - purge)
    ]
    test = frame[frame["timestamp_index"] >= holdout_start]
    if train.empty or calibration.empty or test.empty:
        raise ValueError("Forecast history is too short for purged train/calibration/holdout windows")
    common = dict(max_iter=120, learning_rate=0.06, max_leaf_nodes=15, min_samples_leaf=25, random_state=seed)
    horizon_models = {
        horizon: HistGradientBoostingRegressor(loss="squared_error", **common)
        for horizon in FORECAST_HORIZONS
    }
    mean_model = horizon_models[48]
    quantile = float(config.operations.forecast_quantile)
    upper_model = HistGradientBoostingRegressor(loss="quantile", quantile=quantile, **common)
    for horizon, model in horizon_models.items():
        model.fit(train[FEATURE_COLUMNS], train[f"target_growth_{horizon}h_pct"])
    upper_model.fit(train[FEATURE_COLUMNS], train["target_growth_horizon_pct"])
    raw_calibration_upper = upper_model.predict(calibration[FEATURE_COLUMNS])
    calibration_target = calibration["target_growth_horizon_pct"].to_numpy()
    upper_adjustment = max(
        0.0,
        float(np.quantile(calibration_target - raw_calibration_upper, quantile)),
    )
    prediction = np.maximum(0.0, mean_model.predict(test[FEATURE_COLUMNS]))
    upper_prediction = np.maximum(
        prediction, upper_model.predict(test[FEATURE_COLUMNS]) + upper_adjustment
    )
    naive = np.maximum(0.0, test["naive_growth_horizon_pct"].to_numpy())
    target = test["target_growth_horizon_pct"].to_numpy()
    overflow_base_model = HistGradientBoostingClassifier(loss="log_loss", **common)
    overflow_base_model.fit(
        train[FEATURE_COLUMNS], train["actual_overflow_within_48h"]
    )
    overflow_model = CalibratedClassifierCV(
        FrozenEstimator(overflow_base_model), method="sigmoid"
    )
    overflow_model.fit(
        calibration[FEATURE_COLUMNS], calibration["actual_overflow_within_48h"]
    )
    overflow_probability = overflow_model.predict_proba(test[FEATURE_COLUMNS])[:, 1]
    probability_true, probability_predicted = calibration_curve(
        test["actual_overflow_within_48h"].to_numpy(),
        overflow_probability,
        n_bins=5,
        strategy="quantile",
    )
    actual_alert = test["actual_overflow_within_48h"].to_numpy(dtype=bool)
    predicted_alert = (
        test["fill_pct"].to_numpy() + upper_prediction >= 100.0
    )
    mean_rate = prediction / 48.0
    predicted_tto = np.divide(
        np.maximum(0.0, 100.0 - test["fill_pct"].to_numpy()),
        mean_rate,
        out=np.full(len(test), np.nan, dtype=float),
        where=mean_rate > 1e-9,
    )
    actual_tto = test["actual_time_to_overflow_hours"].to_numpy(dtype=float)
    valid_tto = np.isfinite(actual_tto) & np.isfinite(predicted_tto)
    overflow_base_model_6h = HistGradientBoostingClassifier(loss="log_loss", **common)
    overflow_base_model_6h.fit(
        train[FEATURE_COLUMNS], train["actual_overflow_within_6h"]
    )
    overflow_model_6h = CalibratedClassifierCV(
        FrozenEstimator(overflow_base_model_6h), method="sigmoid"
    )
    overflow_model_6h.fit(
        calibration[FEATURE_COLUMNS], calibration["actual_overflow_within_6h"]
    )
    overflow_probability_6h = overflow_model_6h.predict_proba(
        test[FEATURE_COLUMNS]
    )[:, 1]
    actual_alert_6h = test["actual_overflow_within_6h"].to_numpy(dtype=bool)
    horizon_metrics = {}
    for horizon, model in horizon_models.items():
        horizon_target = test[f"target_growth_{horizon}h_pct"].to_numpy()
        horizon_prediction = np.maximum(0.0, model.predict(test[FEATURE_COLUMNS]))
        naive_horizon = np.maximum(
            0.0, test["growth_24h_pct"].to_numpy() * horizon / 24.0
        )
        horizon_metrics[f"model_mae_growth_{horizon}h_pct"] = float(
            mean_absolute_error(horizon_target, horizon_prediction)
        )
        horizon_metrics[f"naive_mae_growth_{horizon}h_pct"] = float(
            mean_absolute_error(horizon_target, naive_horizon)
        )
    evaluation = {
        "training_rows": float(len(train)),
        "calibration_rows": float(len(calibration)),
        "holdout_rows": float(len(test)),
        "calibration_start_hour": float(calibration_start),
        "chronological_cutoff_hour": float(holdout_start),
        "training_target_end_before_hour": float(calibration_start),
        "calibration_target_end_before_hour": float(holdout_start),
        "forecast_horizon_hours": float(config.operations.forecast_horizon_hours),
        "maximum_evaluation_horizon_hours": purge,
        "operational_evaluation_start_hour": 0.0,
        "latest_historical_feature_hour": float(frame["timestamp_index"].max()),
        "latest_historical_target_end_hour": float(
            frame["timestamp_index"].max() + purge
        ),
        "model_mae_growth_pct_horizon": float(mean_absolute_error(target, prediction)),
        "naive_mae_growth_pct_horizon": float(mean_absolute_error(target, naive)),
        "model_improvement_pct": float(
            100 * (mean_absolute_error(target, naive) - mean_absolute_error(target, prediction))
            / max(mean_absolute_error(target, naive), 1e-9)
        ),
        "upper_quantile": quantile,
        "upper_adjustment_pct": upper_adjustment,
        "upper_empirical_coverage": float(np.mean(target <= upper_prediction)),
        "upper_coverage_error": float(abs(np.mean(target <= upper_prediction) - quantile)),
        "upper_pinball_loss": float(mean_pinball_loss(target, upper_prediction, alpha=quantile)),
        "upper_mean_width_pct": float(np.mean(upper_prediction - prediction)),
        "time_to_overflow_mae_hours": float(
            mean_absolute_error(actual_tto[valid_tto], predicted_tto[valid_tto])
            if valid_tto.any()
            else np.nan
        ),
        "overflow_alert_precision_48h": float(
            precision_score(actual_alert, predicted_alert, zero_division=0)
        ),
        "overflow_alert_recall_48h": float(
            recall_score(actual_alert, predicted_alert, zero_division=0)
        ),
        "overflow_probability_brier_48h": float(
            brier_score_loss(actual_alert, overflow_probability)
        ),
        "overflow_probability_brier_6h": float(
            brier_score_loss(actual_alert_6h, overflow_probability_6h)
        ),
        "overflow_alert_precision_6h_at_10pct": float(
            precision_score(
                actual_alert_6h, overflow_probability_6h >= 0.10, zero_division=0
            )
        ),
        "overflow_alert_recall_6h_at_10pct": float(
            recall_score(
                actual_alert_6h, overflow_probability_6h >= 0.10, zero_division=0
            )
        ),
        "overflow_probability_calibration": [
            {"predicted": float(predicted), "observed": float(observed)}
            for predicted, observed in zip(probability_predicted, probability_true)
        ],
        **horizon_metrics,
    }
    return (
        ForecastBundle(
            mean_model,
            upper_model,
            evaluation,
            upper_adjustment,
            horizon_models,
            overflow_model,
            overflow_model_6h,
        ),
        frame,
    )
