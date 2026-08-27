"""
Sanity tests for the BinSight ML pipeline. Not a full unit-test suite --
these are the checks that matter for "did the pipeline actually work",
meant to be run right after src/train.py, before handing the repo off.

Usage:
    cd binsight_ml
    python3 -m pytest tests/ -v
    # or, without pytest:
    python3 tests/test_pipeline.py
"""
import json
import sys
from pathlib import Path

import pandas as pd

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
MODELS_DIR = BASE_DIR / "models"
SRC_DIR = BASE_DIR / "src"
sys.path.insert(0, str(SRC_DIR))

from features import FEATURE_COLUMNS  # noqa: E402


def test_raw_log_exists_and_well_formed():
    df = pd.read_csv(DATA_DIR / "raw_sensor_log.csv")
    required = {"timestamp", "bin_id", "fill_pct", "weight_kg", "confidence_flag"}
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


def test_model_artifacts_exist():
    for fname in ["overflow_model.joblib", "feature_columns.json", "eval_results.json"]:
        path = MODELS_DIR / fname
        assert path.exists(), f"missing model artifact: {path}"


def test_model_beats_baselines():
    with open(MODELS_DIR / "eval_results.json") as f:
        eval_results = json.load(f)
    results = {r["model"]: r for r in eval_results["results"]}
    naive_mae = results["baseline_naive_extrapolation"]["MAE_hours"]
    linear_mae = results["baseline_linear_regression"]["MAE_hours"]
    selected = eval_results["selected_model"]
    selected_mae = results[selected]["MAE_hours"]
    assert selected_mae < linear_mae, "selected model does not beat the linear baseline on MAE"
    assert selected_mae < naive_mae, "selected model does not beat the naive baseline on MAE"


def test_serve_wrapper_returns_valid_prediction():
    from serve import OverflowRiskModel
    raw = pd.read_csv(DATA_DIR / "raw_sensor_log.csv")
    one_bin = raw[raw["bin_id"] == raw["bin_id"].iloc[0]].head(60)
    model = OverflowRiskModel()
    result = model.predict_from_history(one_bin)
    required_keys = {"bin_id", "timestamp", "time_to_overflow_hours", "risk_level", "fill_pct", "confidence_flag"}
    assert required_keys.issubset(result.keys())
    assert result["risk_level"] in ["Critical", "High", "Medium", "Low"]
    assert result["time_to_overflow_hours"] >= 0


if __name__ == "__main__":
    tests = [
        test_raw_log_exists_and_well_formed,
        test_feature_table_has_no_nans,
        test_labeled_dataset_has_valid_labels,
        test_model_artifacts_exist,
        test_model_beats_baselines,
        test_serve_wrapper_returns_valid_prediction,
    ]
    failures = 0
    for t in tests:
        try:
            t()
            print(f"PASS  {t.__name__}")
        except AssertionError as e:
            failures += 1
            print(f"FAIL  {t.__name__}: {e}")
    print(f"\n{len(tests) - failures}/{len(tests)} tests passed")
    sys.exit(1 if failures else 0)
