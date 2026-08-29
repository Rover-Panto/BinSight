from pathlib import Path

import pandas as pd

from binsight.config import load_config
from binsight.district import BinSpec
from binsight.forecast import make_feature_row, train_forecaster, training_frame


ROOT = Path(__file__).resolve().parents[1]


def _bins():
    frame = pd.read_csv(ROOT / "artifacts" / "district_bins.csv").head(3)
    return [BinSpec(**row.to_dict()) for _, row in frame.iterrows()]


def test_irregular_time_features_use_acquisition_windows_and_detect_reset():
    item = _bins()[0]
    row = make_feature_row(
        item,
        22.0,
        None,
        True,
        [(0.0, 10.0), (2.0, 11.0), (20.0, 20.0)],
        24,
    )
    assert row["growth_6h_pct"] == 2.0
    assert row["growth_24h_pct"] == 12.0
    assert row["max_observation_gap_hours"] == 18.0
    assert row["weight_available"] == 0.0

    reset = make_feature_row(
        item,
        12.0,
        50.0,
        True,
        [(0.0, 80.0), (6.0, 82.0), (12.0, 5.0), (18.0, 9.0)],
        24,
    )
    assert reset["collection_reset_24h"] == 1.0


def test_forecast_uses_purged_calibration_and_reports_upper_quantile_quality():
    config = load_config(ROOT / "config.json")
    bundle, _ = train_forecaster(_bins(), config, seed=1234)
    evaluation = bundle.evaluation
    assert evaluation["training_target_end_before_hour"] <= evaluation["calibration_start_hour"]
    assert evaluation["calibration_target_end_before_hour"] <= evaluation["chronological_cutoff_hour"]
    assert evaluation["latest_historical_target_end_hour"] <= evaluation[
        "operational_evaluation_start_hour"
    ]
    assert 0 <= evaluation["upper_empirical_coverage"] <= 1
    assert evaluation["upper_pinball_loss"] >= 0
    assert evaluation["upper_quantile"] == config.operations.forecast_quantile
    for horizon in (6, 24, 48, 168):
        assert evaluation[f"model_mae_growth_{horizon}h_pct"] >= 0
        assert evaluation[f"naive_mae_growth_{horizon}h_pct"] >= 0
    assert 0 <= evaluation["overflow_alert_precision_48h"] <= 1
    assert 0 <= evaluation["overflow_alert_recall_48h"] <= 1
    assert evaluation["overflow_probability_brier_48h"] >= 0
    assert evaluation["overflow_probability_brier_6h"] >= 0
    assert evaluation["overflow_probability_calibration"]


def test_timestamped_training_history_survives_missing_sensor_fallbacks():
    config = load_config(ROOT / "config.json")
    frame = training_frame(_bins(), config, seed=config.operations.base_seed + 90_000)
    assert not frame.empty
    assert frame["timestamp_index"].is_monotonic_increasing
    assert (frame["target_growth_6h_pct"] >= 0).all()
    assert (frame["target_growth_168h_pct"] >= 0).all()
    assert frame["timestamp_index"].max() + 168 <= 0
