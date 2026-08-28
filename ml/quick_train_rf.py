"""
BinSight — Standalone Random Forest Experiment & Fast Retraining Script.

Note: `src/train.py` is the primary production training pipeline. This script is intended
for rapid experimentation and development. It exports artifacts to `models/experiments/rf_standalone/`
along with a dedicated manifest to avoid overwriting production artifacts.

Workflow:
1. Load preprocessed, labeled dataset (`data/labeled_dataset.csv`).
2. Perform chronological partition (Train / Val / Test).
3. Train Random Forest Regressor on the fill-only feature columns.
4. Evaluate regression (MAE, RMSE) and safety metrics (Critical recall).
5. Serialize and save the experimental model artifact and manifest.
"""
import hashlib
import json
import sys
import time
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, accuracy_score, recall_score

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
EXP_DIR = BASE_DIR / "models" / "experiments" / "rf_standalone"
EXP_DIR.mkdir(parents=True, exist_ok=True)
SRC_DIR = BASE_DIR / "src"
sys.path.insert(0, str(SRC_DIR))

from features import FEATURE_COLUMNS
from label import risk_level_from_hours, OVERFLOW_THRESHOLD_PCT

# ---------------------------------------------------------------------------
# Step 1: Load Labeled Training Dataset
# ---------------------------------------------------------------------------
print("1. Loading labeled training dataset...")
t0 = time.time()
df = pd.read_csv(DATA_DIR / "labeled_dataset.csv")
df["timestamp"] = pd.to_datetime(df["timestamp"])
print(f"   Loaded {len(df):,} labeled rows in {time.time()-t0:.2f}s.")

# ---------------------------------------------------------------------------
# Step 2: Chronological Split
# ---------------------------------------------------------------------------
val_cutoff = pd.Timestamp("2026-03-01 00:00:00")
test_cutoff = pd.Timestamp("2026-03-16 00:00:00")

train_df = df[df["timestamp"] < val_cutoff].copy()
val_df = df[(df["timestamp"] >= val_cutoff) & (df["timestamp"] < test_cutoff)].copy()
test_df = df[df["timestamp"] >= test_cutoff].copy()
print(f"   Train samples: {len(train_df):,} | Val samples: {len(val_df):,} | Test samples: {len(test_df):,}")

X_train, y_train = train_df[FEATURE_COLUMNS], train_df["time_to_overflow_hours"]
X_val, y_val = val_df[FEATURE_COLUMNS], val_df["time_to_overflow_hours"]
X_test, y_test = test_df[FEATURE_COLUMNS], test_df["time_to_overflow_hours"]

# ---------------------------------------------------------------------------
# Step 3: Train Random Forest Regressor
# ---------------------------------------------------------------------------
print("\n2. Training Random Forest Regressor (n_estimators=100, max_depth=12)...")
t1 = time.time()
rf = RandomForestRegressor(
    n_estimators=100,
    max_depth=12,
    min_samples_leaf=5,
    random_state=42,
    n_jobs=1
)
rf.fit(X_train, y_train)
train_time = time.time() - t1
print(f"   Model trained successfully in {train_time:.2f}s!")

# ---------------------------------------------------------------------------
# Step 4: Evaluate Performance
# ---------------------------------------------------------------------------
preds = rf.predict(X_test)
mae = mean_absolute_error(y_test, preds)
rmse = float(np.sqrt(mean_squared_error(y_test, preds)))

risk_true = y_test.apply(risk_level_from_hours)
risk_pred = pd.Series(preds, index=y_test.index).apply(risk_level_from_hours)
acc = accuracy_score(risk_true, risk_pred)
crit_rec = recall_score(risk_true, risk_pred, labels=["Critical"], average="micro")

print(f"\n3. Test Set Performance Metrics:")
print(f"   - Mean Absolute Error (MAE) : {mae:.2f} hours")
print(f"   - Root Mean Sq Error (RMSE) : {rmse:.2f} hours")
print(f"   - Risk Category Accuracy    : {acc:.1%}")
print(f"   - Critical Recall (Safety)  : {crit_rec:.1%}")

# ---------------------------------------------------------------------------
# Step 5: Save Experimental Model Artifact and Manifest
# ---------------------------------------------------------------------------
exp_model_path = EXP_DIR / "rf_experiment.joblib"
joblib.dump(rf, exp_model_path)

with open(exp_model_path, "rb") as f:
    sha256_hash = hashlib.sha256(f.read()).hexdigest()

exp_manifest = {
    "experiment_name": "rf_standalone_fast_train",
    "estimator_class": type(rf).__name__,
    "sha256_checksum": sha256_hash,
    "feature_columns": FEATURE_COLUMNS,
    "metrics": {
        "MAE_hours": round(float(mae), 3),
        "RMSE_hours": round(float(rmse), 3),
        "accuracy": round(float(acc), 3),
        "critical_recall": round(float(crit_rec), 3),
    }
}

with open(EXP_DIR / "manifest.json", "w") as f:
    json.dump(exp_manifest, f, indent=2)

print(f"\n4. Saved experimental model -> {exp_model_path}")
print(f"   Saved experiment manifest -> {EXP_DIR / 'manifest.json'}")
