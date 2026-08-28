"""
Comprehensive test suite for the BinSight ML pipeline and serving wrapper.

Includes verification for:
- Data and feature table integrity (zero NaNs, valid schema)
- PR2 edge-to-cloud telemetry payload compatibility (no weight_kg required)
- Cold-start handling (single reading)
- Duplicate timestamp deduplication
- Irregular sampling intervals and Wi-Fi gap handling
- Model artifact manifest and SHA-256 checksum agreement
- Serving wrapper input validation and edge-case handling
"""
import hashlib
import json
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
MODELS_DIR = BASE_DIR / "models"
SRC_DIR = BASE_DIR / "src"
sys.path.insert(0, str(SRC_DIR))

from features import build_feature_table, FEATURE_COLUMNS
from serve import OverflowRiskModel


def test_raw_log_exists_and_well_formed():
    df = pd.read_csv(DATA_DIR / "raw_sensor_log.csv")
    required = {"timestamp", "bin_id", "fill_pct", "confidence_flag"}
    assert required.issubset(df.columns), f"raw_sensor_log.csv missing columns: {required - set(df.columns)}"
    assert len(df) > 0, "raw_sensor_log.csv is empty"
    assert df["fill_pct"].between(-50, 150).all(), "fill_pct has wildly out-of-range values"


def test_feature_table_has_no_nans():
    df = pd.read_csv(DATA_DIR / "feature_table.csv")
    nan_counts = df[FEATURE_COLUMNS].isna().sum()
    assert nan_counts.sum() == 0, f"feature_table.csv has NaNs:\n{nan_counts[nan_counts > 0]}"


def test_labeled_dataset_has_valid_labels():
    df = pd.read_csv(DATA_DIR / "labeled_dataset.csv")
    assert "time_to_overflow_hours" in df.columns
    assert "risk_level" in df.columns
    assert (df["time_to_overflow_hours"] >= 0).all(), "negative time_to_overflow_hours found"
    assert df["risk_level"].isin(["Critical", "High", "Medium", "Low"]).all()


def test_model_artifacts_and_manifest_exist_and_agree():
    for fname in ["overflow_model.joblib", "feature_columns.json", "eval_results.json", "manifest.json"]:
        path = MODELS_DIR / fname
        assert path.exists(), f"missing model artifact: {path}"

    with open(MODELS_DIR / "manifest.json") as f:
        manifest = json.load(f)

    # Check SHA-256 checksum matches actual artifact on disk
    with open(MODELS_DIR / "overflow_model.joblib", "rb") as f:
        actual_sha256 = hashlib.sha256(f.read()).hexdigest()
    assert manifest["sha256_checksum"] == actual_sha256, "Manifest SHA-256 does not match overflow_model.joblib"

    # Check model class matches
    model = joblib.load(MODELS_DIR / "overflow_model.joblib")
    assert type(model).__name__ == manifest["estimator_class"], "Manifest estimator class does not match loaded model"


def test_model_beats_baselines():
    with open(MODELS_DIR / "eval_results.json") as f:
        eval_results = json.load(f)
    results = {r["model"]: r for r in eval_results["results"]}
    naive_mae = results["baseline_naive_extrapolation"]["MAE_hours"]
    linear_mae = results["baseline_linear_regression"]["MAE_hours"]
    selected = eval_results["selected_model"]
    selected_mae = eval_results["test_metrics"]["MAE_hours"]
    assert selected_mae < linear_mae, "selected model does not beat the linear baseline on MAE"
    assert selected_mae < naive_mae, "selected model does not beat the naive baseline on MAE"


def test_feature_builder_handles_pr2_payload_without_weight():
    """R2 regression: verify PR2 telemetry without weight_kg processes cleanly."""
    pr2_readings = pd.DataFrame([
        {"timestamp": "2026-08-19T10:00:00Z", "bin_id": "bin_01", "fill_pct": 20.0, "estimated_density": 2.1, "confidence_flag": 1},
        {"timestamp": "2026-08-19T11:00:00Z", "bin_id": "bin_01", "fill_pct": 25.0, "estimated_density": 2.1, "confidence_flag": 1},
        {"timestamp": "2026-08-19T12:00:00Z", "bin_id": "bin_01", "fill_pct": 30.0, "estimated_density": 2.2, "confidence_flag": 1},
    ])
    feat = build_feature_table(pr2_readings)
    assert set(FEATURE_COLUMNS).issubset(feat.columns)
    assert feat[FEATURE_COLUMNS].isna().sum().sum() == 0


def test_feature_builder_handles_single_reading_cold_start():
    """R6 regression: 1 reading should not crash and should produce 0.0 rates."""
    single = pd.DataFrame([
        {"timestamp": "2026-08-19T10:00:00Z", "bin_id": "bin_01", "fill_pct": 45.0, "confidence_flag": 1}
    ])
    feat = build_feature_table(single)
    assert len(feat) == 1
    assert feat["fill_rate_1h"].iloc[0] == 0.0
    assert feat["fill_rate_6h"].iloc[0] == 0.0


def test_feature_builder_handles_duplicate_timestamps():
    """R6 regression: duplicate timestamps should not cause division by zero."""
    dups = pd.DataFrame([
        {"timestamp": "2026-08-19T10:00:00Z", "bin_id": "bin_01", "fill_pct": 20.0, "confidence_flag": 1},
        {"timestamp": "2026-08-19T10:00:00Z", "bin_id": "bin_01", "fill_pct": 22.0, "confidence_flag": 1},
        {"timestamp": "2026-08-19T11:00:00Z", "bin_id": "bin_01", "fill_pct": 30.0, "confidence_flag": 1},
    ])
    feat = build_feature_table(dups)
    assert len(feat) == 2  # deduplicated to 2 timestamps
    assert np.isfinite(feat["fill_rate_1h"]).all()


def test_feature_builder_handles_irregular_sampling_and_gaps():
    """R6 regression: 10%/h trajectory with irregular gap must not distort rate to 45%/h."""
    irregular = pd.DataFrame([
        {"timestamp": "2026-08-19T00:00:00Z", "bin_id": "bin_01", "fill_pct": 0.0, "confidence_flag": 1},
        {"timestamp": "2026-08-19T00:30:00Z", "bin_id": "bin_01", "fill_pct": 5.0, "confidence_flag": 1},
        {"timestamp": "2026-08-19T01:00:00Z", "bin_id": "bin_01", "fill_pct": 10.0, "confidence_flag": 1},
        {"timestamp": "2026-08-19T05:00:00Z", "bin_id": "bin_01", "fill_pct": 50.0, "confidence_flag": 1},
    ])
    feat = build_feature_table(irregular)
    last_rate = feat["fill_rate_1h"].iloc[-1]
    # Rate at 5h from 1h reading should be (50-10)/4 = 10.0 %/h, NOT 45.0 %/h
    assert abs(last_rate - 10.0) < 1.0, f"Expected ~10.0 %/h rate, got {last_rate}"


def test_serve_wrapper_returns_valid_prediction():
    raw = pd.read_csv(DATA_DIR / "raw_sensor_log.csv")
    one_bin = raw[raw["bin_id"] == "bin_005"].head(60)
    model = OverflowRiskModel()
    result = model.predict_from_history(one_bin)
    required_keys = {"bin_id", "timestamp", "status", "time_to_overflow_hours", "risk_level", "fill_pct", "confidence_flag", "target_threshold_pct"}
    assert required_keys.issubset(result.keys())
    assert result["status"] in ["available", "ok"]
    assert result["risk_level"] in ["Critical", "High", "Medium", "Low"]
    assert result["time_to_overflow_hours"] >= 0


def test_serve_wrapper_handles_empty_and_invalid_inputs():
    model = OverflowRiskModel()
    
    # Empty DataFrame
    empty_res = model.predict_from_history(pd.DataFrame())
    assert empty_res["status"] == "invalid_input"
    assert empty_res["time_to_overflow_hours"] is None
    assert empty_res["risk_level"] == "Unavailable"
    
    # Single reading cold start
    single = pd.DataFrame([{"timestamp": "2026-08-19T10:00:00Z", "bin_id": "bin_01", "fill_pct": 30.0, "confidence_flag": 1}])
    single_res = model.predict_from_history(single)
    assert single_res["status"] == "cold_start"
    assert single_res["risk_level"] in ["Critical", "High", "Medium", "Low"]


def test_serve_wrapper_supports_pr1_snapshot_contract():
    """Verify PR1 snapshot prediction interface and future observation cutoff filtering."""
    model = OverflowRiskModel()
    readings = pd.DataFrame([
        {"timestamp": "2026-08-19T10:00:00Z", "bin_id": "bin_01", "fill_pct": 20.0, "confidence_flag": 1},
        {"timestamp": "2026-08-19T11:00:00Z", "bin_id": "bin_01", "fill_pct": 30.0, "confidence_flag": 1},
        {"timestamp": "2026-08-19T12:00:00Z", "bin_id": "bin_01", "fill_pct": 40.0, "confidence_flag": 1},
    ])
    # Pass decision_at cutoff at 11:00:00Z -> should exclude 12:00 reading
    result = model.predict_snapshot(readings, decision_at="2026-08-19T11:00:00Z", input_snapshot_id="SNAP-TEST-01")
    assert result["input_snapshot_id"] == "SNAP-TEST-01"
    assert result["decision_at"] == "2026-08-19T11:00:00Z"
    assert result["fill_pct"] == 30.0
    assert result["status"] == "available"
    assert result["schema_version"] == "1.0"


def test_forecast_provider_multi_bin_snapshot_and_missing_bins():
    """Verify multi-bin snapshots never silently drop configured bins with insufficient evidence."""
    provider = OverflowRiskModel()
    readings = pd.DataFrame([
        {"timestamp": "2026-08-19T10:00:00Z", "bin_id": "bin_01", "fill_pct": 20.0, "confidence_flag": 1},
        {"timestamp": "2026-08-19T11:00:00Z", "bin_id": "bin_01", "fill_pct": 35.0, "confidence_flag": 1},
        {"timestamp": "2026-08-19T11:00:00Z", "bin_id": "bin_02", "fill_pct": 50.0, "confidence_flag": 1},
    ])
    results = provider.predict_snapshot(
        readings,
        bins=["bin_01", "bin_02", "bin_03_no_data"],
        decision_at="2026-08-19T12:00:00Z",
        input_snapshot_id="SNAP-MULTI-01"
    )
    assert isinstance(results, list)
    assert len(results) == 3
    res_map = {r["bin_id"]: r for r in results}
    assert res_map["bin_01"]["status"] == "available"
    assert res_map["bin_02"]["status"] == "cold_start"
    assert res_map["bin_03_no_data"]["status"] == "unavailable"
    assert res_map["bin_03_no_data"]["time_to_overflow_hours"] is None


def test_forecast_provider_horizons_and_probabilities():
    """Verify 6h, 24h, 48h, 168h horizon growth and calibrated exceedance probabilities."""
    provider = OverflowRiskModel()
    readings = pd.DataFrame([
        {"timestamp": "2026-08-19T10:00:00Z", "bin_id": "bin_01", "fill_pct": 50.0, "confidence_flag": 1},
        {"timestamp": "2026-08-19T11:00:00Z", "bin_id": "bin_01", "fill_pct": 60.0, "confidence_flag": 1},
    ])
    res = provider.predict_from_history(readings)
    assert "horizons" in res
    assert set(res["horizons"].keys()) == {"6", "24", "48", "168"}
    h6 = res["horizons"]["6"]
    assert h6["expected_fill_pct"] >= 60.0
    assert 0.0 <= h6["overflow_probability"] <= 1.0


def test_forecast_provider_simulation_interface():
    """Verify PR1 simulation caller compatibility (mean, upper, and probability arrays)."""
    provider = OverflowRiskModel()
    df = pd.read_csv(DATA_DIR / "feature_table.csv").head(10)
    mean, upper = provider.predict(df)
    assert len(mean) == 10
    assert len(upper) == 10
    assert (upper >= mean).all()
    
    prob48 = provider.predict_overflow_probability_48h(df)
    assert len(prob48) == 10
    assert (prob48 >= 0.0).all() and (prob48 <= 1.0).all()


if __name__ == "__main__":
    tests = [
        test_raw_log_exists_and_well_formed,
        test_feature_table_has_no_nans,
        test_labeled_dataset_has_valid_labels,
        test_model_artifacts_and_manifest_exist_and_agree,
        test_model_beats_baselines,
        test_feature_builder_handles_pr2_payload_without_weight,
        test_feature_builder_handles_single_reading_cold_start,
        test_feature_builder_handles_duplicate_timestamps,
        test_feature_builder_handles_irregular_sampling_and_gaps,
        test_serve_wrapper_returns_valid_prediction,
        test_serve_wrapper_handles_empty_and_invalid_inputs,
        test_serve_wrapper_supports_pr1_snapshot_contract,
        test_forecast_provider_multi_bin_snapshot_and_missing_bins,
        test_forecast_provider_horizons_and_probabilities,
        test_forecast_provider_simulation_interface,
    ]
    failures = 0
    for t in tests:
        try:
            t()
            print(f"PASS  {t.__name__}")
        except Exception as e:
            failures += 1
            print(f"FAIL  {t.__name__}: {e}")
    print(f"\n{len(tests) - failures}/{len(tests)} tests passed")
    sys.exit(1 if failures else 0)


