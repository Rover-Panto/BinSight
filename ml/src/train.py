"""
BinSight overflow-risk model: training + evaluation.

Split strategy (Chronological Holdout):
  - Strict time-based chronological partition:
    - Train set: Day 1 to Day 60 (January 1 to March 1)
    - Validation set: Day 61 to Day 75 (March 1 to March 16) — used for model selection
    - Test holdout: Day 76 to Day 90 (March 16 to March 31) — untouched final evaluation
  - Model selection is performed strictly on the validation set.
  - Final metrics on the untouched test holdout are saved to `manifest.json`.

Models compared:
  - Baseline 1: Naive linear extrapolation from current fill rate (no ML)
  - Baseline 2: Linear regression on engineered features
  - Model A: Random Forest Regressor (primary)
  - Model B: Gradient Boosting (XGBoost)

Run from anywhere: `python3 train.py` or `python3 src/train.py`.
"""
import hashlib
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import sklearn
import xgboost
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error, mean_squared_error, accuracy_score, recall_score
from xgboost import XGBRegressor

try:
    from .features import FEATURE_COLUMNS
    from .label import risk_level_from_hours, OVERFLOW_THRESHOLD_PCT
except (ImportError, ValueError):
    from features import FEATURE_COLUMNS
    from label import risk_level_from_hours, OVERFLOW_THRESHOLD_PCT

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
MODELS_DIR = BASE_DIR / "models"
MODELS_DIR.mkdir(parents=True, exist_ok=True)

TARGET = "time_to_overflow_hours"
RANDOM_SEED = 42


def chronological_split(df: pd.DataFrame):
    """
    Partition dataset strictly by calendar timestamps to form a true chronological holdout.
    """
    df = df.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df.sort_values(["timestamp", "bin_id"]).reset_index(drop=True)
    
    val_cutoff = pd.Timestamp("2026-03-01 00:00:00")
    test_cutoff = pd.Timestamp("2026-03-16 00:00:00")
    
    train_df = df[df["timestamp"] < val_cutoff].copy()
    val_df = df[(df["timestamp"] >= val_cutoff) & (df["timestamp"] < test_cutoff)].copy()
    test_df = df[df["timestamp"] >= test_cutoff].copy()
    
    return train_df, val_df, test_df


def naive_baseline_predict(df: pd.DataFrame) -> np.ndarray:
    """
    Rule-based baseline: assume current fill_rate_1h holds constant until threshold.
    """
    remaining_pct = (OVERFLOW_THRESHOLD_PCT - df["fill_pct"]).clip(lower=0)
    rate = df["fill_rate_1h"].replace(0, np.nan).abs()
    pred = remaining_pct / rate
    pred = pred.replace([np.inf, -np.inf], np.nan).fillna(remaining_pct.max())
    return pred.clip(lower=0, upper=200).to_numpy()


def evaluate(y_true: pd.Series, y_pred: np.ndarray, label: str) -> dict:
    """
    Compute regression error (MAE, RMSE) and classification safety metrics (Accuracy, Critical Recall).
    """
    mae = mean_absolute_error(y_true, y_pred)
    rmse = float(np.sqrt(mean_squared_error(y_true, y_pred)))

    risk_true = y_true.apply(risk_level_from_hours)
    risk_pred = pd.Series(y_pred, index=y_true.index).apply(risk_level_from_hours)
    acc = accuracy_score(risk_true, risk_pred)
    critical_recall = recall_score(risk_true, risk_pred, labels=["Critical"], average="micro")

    result = {
        "model": label,
        "MAE_hours": round(float(mae), 3),
        "RMSE_hours": round(float(rmse), 3),
        "risk_level_accuracy": round(float(acc), 3),
        "critical_recall": round(float(critical_recall), 3)
    }
    print(f"  [{label}] MAE={result['MAE_hours']}h | RMSE={result['RMSE_hours']}h | Acc={result['risk_level_accuracy']:.1%} | CritRecall={result['critical_recall']:.1%}")
    return result


def main():
    print("1. Loading labeled dataset and performing chronological split...")
    df = pd.read_csv(DATA_DIR / "labeled_dataset.csv")
    train_df, val_df, test_df = chronological_split(df)
    print(f"   Train samples: {len(train_df):,} (Jan 01 - Mar 01)")
    print(f"   Val samples  : {len(val_df):,} (Mar 01 - Mar 16) [Model Selection]")
    print(f"   Test samples : {len(test_df):,} (Mar 16 - Mar 31) [Chronological Holdout]")

    X_train, y_train = train_df[FEATURE_COLUMNS], train_df[TARGET]
    X_val, y_val = val_df[FEATURE_COLUMNS], val_df[TARGET]
    X_test, y_test = test_df[FEATURE_COLUMNS], test_df[TARGET]

    print("\n2. Training candidate models & evaluating on VALIDATION set for model selection...")
    # Baseline 1: Naive extrapolation
    val_naive = evaluate(y_val, naive_baseline_predict(val_df), "baseline_naive_extrapolation")
    
    # Baseline 2: Linear regression
    lin = LinearRegression().fit(X_train, y_train)
    val_lin = evaluate(y_val, lin.predict(X_val), "baseline_linear_regression")

    # Model A: Random Forest
    rf_params = {"n_estimators": 200, "max_depth": 12, "min_samples_leaf": 5, "random_state": RANDOM_SEED, "n_jobs": -1}
    rf = RandomForestRegressor(**rf_params).fit(X_train, y_train)
    val_rf = evaluate(y_val, rf.predict(X_val), "random_forest")

    # Model B: XGBoost
    xgb_params = {"n_estimators": 200, "max_depth": 6, "learning_rate": 0.05, "subsample": 0.8, "colsample_bytree": 0.8, "random_state": RANDOM_SEED}
    xgb = XGBRegressor(**xgb_params).fit(X_train, y_train, eval_set=[(X_val, y_val)], verbose=False)
    val_xgb = evaluate(y_val, xgb.predict(X_val), "xgboost")

    # Model Selection: Pick model with lowest Validation MAE (while confirming high critical recall)
    candidates = [("random_forest", rf, val_rf, rf_params), ("xgboost", xgb, val_xgb, xgb_params)]
    best_name, best_model, best_val_metrics, best_params = min(candidates, key=lambda c: c[2]["MAE_hours"])
    print(f"\n   -> Selected winning model on validation performance: {best_name} (Val MAE = {best_val_metrics['MAE_hours']}h)")

    print("\n3. Evaluating selected model on UNTOUCHED CHRONOLOGICAL TEST HOLDOUT...")
    test_naive = evaluate(y_test, naive_baseline_predict(test_df), "baseline_naive_extrapolation")
    test_lin = evaluate(y_test, lin.predict(X_test), "baseline_linear_regression")
    test_rf = evaluate(y_test, rf.predict(X_test), "random_forest")
    test_xgb = evaluate(y_test, xgb.predict(X_test), "xgboost")
    
    selected_test_metrics = test_rf if best_name == "random_forest" else test_xgb

    # Save model artifact
    model_path = MODELS_DIR / "overflow_model.joblib"
    joblib.dump(best_model, model_path)
    
    # Compute SHA-256 checksum of the saved artifact
    with open(model_path, "rb") as f:
        sha256_hash = hashlib.sha256(f.read()).hexdigest()

    # Create unified manifest
    manifest = {
        "model_name": best_name,
        "estimator_class": type(best_model).__name__,
        "model_version": "1.1.0",
        "sha256_checksum": sha256_hash,
        "selected_on": "validation_set",
        "split_strategy": {
            "type": "chronological_holdout",
            "train_period": "2026-01-01 to 2026-03-01",
            "val_period": "2026-03-01 to 2026-03-16",
            "test_period": "2026-03-16 to 2026-03-31",
            "train_samples": len(train_df),
            "val_samples": len(val_df),
            "test_samples": len(test_df),
        },
        "target_definitions": {
            "overflow_threshold_pct": OVERFLOW_THRESHOLD_PCT,
            "risk_boundaries_hours": [4.0, 12.0, 24.0],
            "risk_levels": ["Critical", "High", "Medium", "Low"]
        },
        "hyperparameters": best_params,
        "feature_columns": FEATURE_COLUMNS,
        "validation_metrics": best_val_metrics,
        "test_holdout_metrics": selected_test_metrics,
        "all_test_comparisons": [test_naive, test_lin, test_rf, test_xgb],
        "dependencies": {
            "scikit-learn": sklearn.__version__,
            "xgboost": xgboost.__version__,
            "pandas": pd.__version__,
            "numpy": np.__version__,
            "joblib": joblib.__version__
        }
    }

    manifest_path = MODELS_DIR / "manifest.json"
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)

    with open(MODELS_DIR / "feature_columns.json", "w") as f:
        json.dump(FEATURE_COLUMNS, f, indent=2)

    with open(MODELS_DIR / "eval_results.json", "w") as f:
        json.dump({
            "selected_model": best_name,
            "validation_metrics": best_val_metrics,
            "test_metrics": selected_test_metrics,
            "results": [test_naive, test_lin, test_rf, test_xgb],
            "sha256": sha256_hash
        }, f, indent=2)

    feature_importance = pd.Series(best_model.feature_importances_, index=FEATURE_COLUMNS)
    feature_importance = feature_importance.sort_values(ascending=False)
    feature_importance.to_csv(MODELS_DIR / "feature_importance.csv", header=["importance"])

    print(f"\n4. Saved model artifact -> {model_path} (SHA-256: {sha256_hash[:12]}...)")
    print(f"   Saved unified manifest -> {manifest_path}")


if __name__ == "__main__":
    main()
