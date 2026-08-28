"""
Comprehensive test suite for the BinSight ML pipeline and serving wrapper (v2.0).

Includes verification for:
- Data and feature table integrity (zero NaNs, valid schema)
- PR2 edge-to-cloud telemetry payload compatibility (no weight_kg required)
- Cold-start handling (single reading)
- Duplicate timestamp deduplication
- Irregular sampling intervals and Wi-Fi gap handling
- Model artifact manifest and SHA-256 checksum agreement
- Serving wrapper input validation and edge-case handling
- Item 1: Unsupported threshold rejection, correct field naming
- Item 2: Receipt-time filtering, model-training cutoff, staleness
- Item 3: Label-leakage purge verification
- Item 4: Probabilities are null/unsupported
- Item 5: Manifest required before load, hash before deserialization
- Item 6: Installable package import (binsight_ml)
- Item 7: Four-bin waste type support
"""
import hashlib
import json
import shutil
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import joblib
import numpy as np
import pandas as pd

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
MODELS_DIR = BASE_DIR / "models"
SRC_DIR = BASE_DIR / "src"
sys.path.insert(0, str(SRC_DIR))

from features import build_feature_table, FEATURE_COLUMNS
from serve import ForecastProvider, OverflowRiskModel


# ═══════════════════════════════════════════════════════════════════
#  Existing pipeline tests (updated for v2 schema)
# ═══════════════════════════════════════════════════════════════════

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
    assert "crossing_timestamp" in df.columns, "crossing_timestamp missing (Item 3)"
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

    # Item 3: training_data_cutoff must be present
    assert "training_data_cutoff" in manifest, "training_data_cutoff missing from manifest"
    assert "model_availability_after" in manifest, "model_availability_after missing"

    # Item 1: target_definitions must declare supported thresholds
    assert manifest["target_definitions"]["supported_thresholds"] == [90.0]
    assert manifest["target_definitions"]["waste_type_aware"] is False


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
    assert abs(last_rate - 10.0) < 1.0, f"Expected ~10.0 %/h rate, got {last_rate}"


def test_serve_wrapper_returns_valid_prediction():
    raw = pd.read_csv(DATA_DIR / "raw_sensor_log.csv")
    one_bin = raw[raw["bin_id"] == "bin_005"].head(60)
    model = ForecastProvider()
    result = model.predict_from_history(one_bin)
    required_keys = {
        "bin_id", "timestamp", "status", "time_to_service_threshold_hours",
        "risk_level", "fill_pct", "confidence_flag", "target_threshold_pct",
        "schema_version", "model_version", "model_sha256",
    }
    assert required_keys.issubset(result.keys()), f"Missing keys: {required_keys - set(result.keys())}"
    assert result["status"] in ["available", "cold_start"]
    assert result["risk_level"] in ["Critical", "High", "Medium", "Low"]
    assert result["time_to_service_threshold_hours"] >= 0
    assert result["schema_version"] == "2.0"


def test_serve_wrapper_handles_empty_and_invalid_inputs():
    model = ForecastProvider()

    # Empty DataFrame
    empty_res = model.predict_from_history(pd.DataFrame())
    assert empty_res["status"] == "invalid_input"
    assert empty_res["time_to_service_threshold_hours"] is None
    assert empty_res["risk_level"] is None

    # Single reading cold start
    single = pd.DataFrame([{"timestamp": "2026-08-19T10:00:00Z", "bin_id": "bin_01", "fill_pct": 30.0, "confidence_flag": 1}])
    single_res = model.predict_from_history(single)
    assert single_res["status"] == "cold_start"
    assert single_res["risk_level"] in ["Critical", "High", "Medium", "Low"]


# ═══════════════════════════════════════════════════════════════════
#  Item 1: Unsupported threshold rejection
# ═══════════════════════════════════════════════════════════════════

def test_reject_unsupported_threshold():
    """Requesting 100% when model trained on 90% must return unsupported_threshold."""
    provider = ForecastProvider()
    readings = pd.DataFrame([
        {"timestamp": "2026-08-19T10:00:00Z", "bin_id": "bin_01", "fill_pct": 50.0, "confidence_flag": 1},
        {"timestamp": "2026-08-19T11:00:00Z", "bin_id": "bin_01", "fill_pct": 60.0, "confidence_flag": 1},
    ])
    result = provider.predict_from_history(readings, target_threshold_pct=100.0)
    assert result["status"] == "unsupported_threshold", f"Expected unsupported_threshold, got {result['status']}"
    assert result["time_to_service_threshold_hours"] is None


def test_output_uses_service_threshold_naming():
    """Output must use time_to_service_threshold_hours, not time_to_overflow_hours."""
    provider = ForecastProvider()
    readings = pd.DataFrame([
        {"timestamp": "2026-08-19T10:00:00Z", "bin_id": "bin_01", "fill_pct": 50.0, "confidence_flag": 1},
        {"timestamp": "2026-08-19T11:00:00Z", "bin_id": "bin_01", "fill_pct": 60.0, "confidence_flag": 1},
    ])
    result = provider.predict_from_history(readings)
    assert "time_to_service_threshold_hours" in result, "Missing time_to_service_threshold_hours"
    assert "time_to_overflow_hours" not in result, "Old field time_to_overflow_hours should not exist"
    assert result["target_threshold_pct"] == 90.0
    assert result["estimate_type"] == "expected_hours_to_service_threshold"


# ═══════════════════════════════════════════════════════════════════
#  Item 2: Point-in-time correctness
# ═══════════════════════════════════════════════════════════════════

def test_future_observation_excluded_by_receipt_time():
    """Observation with received_at after decision_at must be filtered out."""
    provider = ForecastProvider()
    readings = pd.DataFrame([
        {"timestamp": "2026-03-19T10:00:00Z", "bin_id": "bin_01", "fill_pct": 20.0,
         "received_at": "2026-03-19T10:00:01Z", "confidence_flag": 1},
        {"timestamp": "2026-03-19T11:00:00Z", "bin_id": "bin_01", "fill_pct": 30.0,
         "received_at": "2026-03-19T12:00:00Z", "confidence_flag": 1},  # late ingestion
    ])
    result = provider.predict_snapshot(readings, decision_at="2026-03-19T11:30:00Z")
    # The second reading has received_at 12:00 > decision_at 11:30 → filtered out
    assert result["fill_pct"] == 20.0, f"Expected fill_pct 20.0 (late receipt filtered), got {result['fill_pct']}"


def test_model_unavailable_before_training_cutoff():
    """Decision before the model's training-data cutoff returns model_unavailable."""
    provider = ForecastProvider()
    readings = pd.DataFrame([
        {"timestamp": "2026-01-02T10:00:00Z", "bin_id": "bin_01", "fill_pct": 20.0, "confidence_flag": 1},
        {"timestamp": "2026-01-02T11:00:00Z", "bin_id": "bin_01", "fill_pct": 30.0, "confidence_flag": 1},
    ])
    # Decision is in January, model trained through end-of-Feb
    result = provider.predict_snapshot(readings, decision_at="2026-01-02T12:00:00Z")
    # May return a list with one entry if bins auto-discovered
    if isinstance(result, list):
        result = result[0]
    assert result["status"] == "model_unavailable", f"Expected model_unavailable, got {result['status']}"


def test_stale_history_returns_stale_status():
    """Months-old data with a current decision_at should return stale."""
    provider = ForecastProvider()
    readings = pd.DataFrame([
        {"timestamp": "2026-03-19T10:00:00Z", "bin_id": "bin_01", "fill_pct": 20.0, "confidence_flag": 1},
        {"timestamp": "2026-03-19T11:00:00Z", "bin_id": "bin_01", "fill_pct": 30.0, "confidence_flag": 1},
    ])
    # Decision is in August — data is 5 months old
    result = provider.predict_snapshot(readings, decision_at="2026-08-28T11:00:00Z")
    assert result["status"] == "stale", f"Expected stale, got {result['status']}"


# ═══════════════════════════════════════════════════════════════════
#  Item 3: Label-leakage purge
# ═══════════════════════════════════════════════════════════════════

def test_label_crossing_purged_across_split():
    """Manifest must record label-leakage purge counts."""
    with open(MODELS_DIR / "manifest.json") as f:
        manifest = json.load(f)
    split = manifest["split_strategy"]
    assert split["type"] == "chronological_holdout_with_label_purge"
    assert "train_label_leakage_purged" in split
    assert "val_label_leakage_purged" in split
    assert split["train_label_leakage_purged"] >= 0
    assert split["val_label_leakage_purged"] >= 0
    assert split["train_samples_clean"] == split["train_samples_raw"] - split["train_label_leakage_purged"]


# ═══════════════════════════════════════════════════════════════════
#  Item 4: No fabricated probabilities
# ═══════════════════════════════════════════════════════════════════

def test_probabilities_are_null_and_unsupported():
    """All overflow_probability values must be null with unsupported status."""
    provider = ForecastProvider()
    readings = pd.DataFrame([
        {"timestamp": "2026-08-19T10:00:00Z", "bin_id": "bin_01", "fill_pct": 50.0, "confidence_flag": 1},
        {"timestamp": "2026-08-19T11:00:00Z", "bin_id": "bin_01", "fill_pct": 60.0, "confidence_flag": 1},
    ])
    result = provider.predict_from_history(readings)
    assert "horizons" in result
    for h_key, h_val in result["horizons"].items():
        assert h_val["overflow_probability"] is None, f"Horizon {h_key}: probability should be null"
        assert h_val["overflow_probability_status"] == "unsupported", f"Horizon {h_key}: status should be unsupported"


def test_no_simulation_growth_methods():
    """Old predict(), predict_overflow_probability_48h/6h methods must not exist."""
    provider = ForecastProvider()
    assert not hasattr(provider, "predict_overflow_probability_48h"), \
        "predict_overflow_probability_48h should be removed"
    assert not hasattr(provider, "predict_overflow_probability_6h"), \
        "predict_overflow_probability_6h should be removed"
    # predict() should not exist as a growth-returning method
    # (ForecastProvider only has predict_from_history and predict_snapshot)
    assert not hasattr(provider, "predict") or "predict" not in ForecastProvider.__dict__, \
        "predict() simulation method should be removed from ForecastProvider"


# ═══════════════════════════════════════════════════════════════════
#  Item 5: Fail closed on artifact loading
# ═══════════════════════════════════════════════════════════════════

def test_manifest_required_before_load():
    """Missing manifest must raise FileNotFoundError; model must NOT be loaded."""
    with tempfile.TemporaryDirectory(prefix="binsight-test-") as tmpdir:
        model_dir = Path(tmpdir)
        # Copy model and features but NOT manifest
        shutil.copy(MODELS_DIR / "overflow_model.joblib", model_dir / "overflow_model.joblib")
        shutil.copy(MODELS_DIR / "feature_columns.json", model_dir / "feature_columns.json")

        load_called = False
        original_load = joblib.load

        def tracking_load(*args, **kwargs):
            nonlocal load_called
            load_called = True
            return original_load(*args, **kwargs)

        with patch.object(joblib, "load", side_effect=tracking_load):
            try:
                ForecastProvider(model_dir)
                assert False, "Should have raised FileNotFoundError"
            except FileNotFoundError:
                pass

        assert not load_called, "joblib.load was called despite missing manifest"


def test_hash_verified_before_deserialization():
    """Bad checksum must reject BEFORE joblib.load() is called."""
    with tempfile.TemporaryDirectory(prefix="binsight-test-") as tmpdir:
        model_dir = Path(tmpdir)
        shutil.copy(MODELS_DIR / "overflow_model.joblib", model_dir / "overflow_model.joblib")
        shutil.copy(MODELS_DIR / "feature_columns.json", model_dir / "feature_columns.json")

        # Write manifest with wrong checksum
        with open(MODELS_DIR / "manifest.json") as f:
            manifest = json.load(f)
        manifest["sha256_checksum"] = "0" * 64
        with open(model_dir / "manifest.json", "w") as f:
            json.dump(manifest, f)

        load_called = False
        original_load = joblib.load

        def tracking_load(*args, **kwargs):
            nonlocal load_called
            load_called = True
            return original_load(*args, **kwargs)

        with patch.object(joblib, "load", side_effect=tracking_load):
            try:
                ForecastProvider(model_dir)
                assert False, "Should have raised ValueError for bad checksum"
            except ValueError:
                pass

        assert not load_called, "joblib.load was called BEFORE bad checksum was rejected"


def test_tampered_artifact_rejected():
    """Modified artifact bytes must be rejected."""
    with tempfile.TemporaryDirectory(prefix="binsight-test-") as tmpdir:
        model_dir = Path(tmpdir)
        shutil.copy(MODELS_DIR / "feature_columns.json", model_dir / "feature_columns.json")
        shutil.copy(MODELS_DIR / "manifest.json", model_dir / "manifest.json")

        # Write tampered model file
        (model_dir / "overflow_model.joblib").write_bytes(b"tampered-artifact-bytes")

        try:
            ForecastProvider(model_dir)
            assert False, "Should have raised ValueError for tampered artifact"
        except ValueError as e:
            assert "mismatch" in str(e).lower() or "SHA-256" in str(e)


# ═══════════════════════════════════════════════════════════════════
#  Item 6: Installable package import
# ═══════════════════════════════════════════════════════════════════

def test_binsight_ml_package_importable():
    """binsight_ml package must be importable and export ForecastProvider."""
    binsight_ml_dir = BASE_DIR / "binsight_ml"
    assert binsight_ml_dir.exists(), "binsight_ml/ package directory missing"
    assert (binsight_ml_dir / "__init__.py").exists(), "binsight_ml/__init__.py missing"

    # Add ml/ to path and import
    if str(BASE_DIR) not in sys.path:
        sys.path.insert(0, str(BASE_DIR))
    import importlib
    mod = importlib.import_module("binsight_ml")
    assert hasattr(mod, "ForecastProvider"), "binsight_ml must export ForecastProvider"
    assert hasattr(mod, "build_feature_table"), "binsight_ml must export build_feature_table"
    assert hasattr(mod, "FEATURE_COLUMNS"), "binsight_ml must export FEATURE_COLUMNS"


# ═══════════════════════════════════════════════════════════════════
#  Item 7: Four-bin waste type support
# ═══════════════════════════════════════════════════════════════════

def test_four_waste_types_preserved():
    """waste_type must be preserved in input/output for all four types."""
    provider = ForecastProvider()
    waste_types = ["general", "plastic", "metal", "glass"]
    for wt in waste_types:
        readings = pd.DataFrame([
            {"timestamp": "2026-08-19T10:00:00Z", "bin_id": f"bin_{wt}", "fill_pct": 40.0,
             "waste_type": wt, "confidence_flag": 1},
            {"timestamp": "2026-08-19T11:00:00Z", "bin_id": f"bin_{wt}", "fill_pct": 50.0,
             "waste_type": wt, "confidence_flag": 1},
        ])
        result = provider.predict_from_history(readings)
        assert result["waste_type"] == wt, f"waste_type should be '{wt}', got {result['waste_type']}"
        assert result["waste_type_used_as_feature"] is False


def test_missing_waste_type_still_works():
    """Absence of waste_type column must not break predictions."""
    provider = ForecastProvider()
    readings = pd.DataFrame([
        {"timestamp": "2026-08-19T10:00:00Z", "bin_id": "bin_01", "fill_pct": 40.0, "confidence_flag": 1},
        {"timestamp": "2026-08-19T11:00:00Z", "bin_id": "bin_01", "fill_pct": 50.0, "confidence_flag": 1},
    ])
    result = provider.predict_from_history(readings)
    assert result["waste_type"] is None
    assert result["status"] in ["available", "cold_start"]


def test_snapshot_pr1_contract():
    """Verify PR1 snapshot prediction interface with cutoff filtering."""
    model = ForecastProvider()
    readings = pd.DataFrame([
        {"timestamp": "2026-03-19T10:00:00Z", "bin_id": "bin_01", "fill_pct": 20.0, "confidence_flag": 1},
        {"timestamp": "2026-03-19T11:00:00Z", "bin_id": "bin_01", "fill_pct": 30.0, "confidence_flag": 1},
        {"timestamp": "2026-03-19T12:00:00Z", "bin_id": "bin_01", "fill_pct": 40.0, "confidence_flag": 1},
    ])
    result = model.predict_snapshot(readings, decision_at="2026-03-19T11:00:00Z", input_snapshot_id="SNAP-TEST-01")
    assert result["input_snapshot_id"] == "SNAP-TEST-01"
    assert result["decision_at"] == "2026-03-19T11:00:00Z"
    assert result["fill_pct"] == 30.0
    assert result["status"] == "available"
    assert result["schema_version"] == "2.0"


def test_multi_bin_snapshot_and_missing_bins():
    """Multi-bin snapshots must never silently drop configured bins."""
    provider = ForecastProvider()
    readings = pd.DataFrame([
        {"timestamp": "2026-03-19T10:00:00Z", "bin_id": "bin_01", "fill_pct": 20.0, "confidence_flag": 1},
        {"timestamp": "2026-03-19T11:00:00Z", "bin_id": "bin_01", "fill_pct": 35.0, "confidence_flag": 1},
        {"timestamp": "2026-03-19T11:00:00Z", "bin_id": "bin_02", "fill_pct": 50.0, "confidence_flag": 1},
    ])
    results = provider.predict_snapshot(
        readings,
        bins=["bin_01", "bin_02", "bin_03_no_data"],
        decision_at="2026-03-19T12:00:00Z",
        input_snapshot_id="SNAP-MULTI-01"
    )
    assert isinstance(results, list)
    assert len(results) == 3
    res_map = {r["bin_id"]: r for r in results}
    assert res_map["bin_01"]["status"] == "available"
    assert res_map["bin_02"]["status"] == "cold_start"
    assert res_map["bin_03_no_data"]["status"] == "unavailable"
    assert res_map["bin_03_no_data"]["time_to_service_threshold_hours"] is None


# ═══════════════════════════════════════════════════════════════════
#  Runner
# ═══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    tests = [
        # Existing pipeline tests
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
        # Item 1: Threshold semantics
        test_reject_unsupported_threshold,
        test_output_uses_service_threshold_naming,
        # Item 2: Point-in-time correctness
        test_future_observation_excluded_by_receipt_time,
        test_model_unavailable_before_training_cutoff,
        test_stale_history_returns_stale_status,
        # Item 3: Label leakage purge
        test_label_crossing_purged_across_split,
        # Item 4: No fabricated probabilities
        test_probabilities_are_null_and_unsupported,
        test_no_simulation_growth_methods,
        # Item 5: Fail closed on loading
        test_manifest_required_before_load,
        test_hash_verified_before_deserialization,
        test_tampered_artifact_rejected,
        # Item 6: Installable package
        test_binsight_ml_package_importable,
        # Item 7: Waste type support
        test_four_waste_types_preserved,
        test_missing_waste_type_still_works,
        # Integration contract
        test_snapshot_pr1_contract,
        test_multi_bin_snapshot_and_missing_bins,
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
