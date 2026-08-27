"""
BinSight — Quick Random Forest Regressor Training & Evaluation Script.

This script trains a standalone Random Forest Regressor to predict the hours
remaining until a smart bin reaches overflow threshold (default: >=90% fill).
It evaluates the model on held-out fill cycles and exports the trained artifact
to `models/overflow_model.joblib`.

Workflow:
1. Load preprocessed, labeled dataset (`data/labeled_dataset.csv`).
2. Partition data by independent fill cycles (70% train / 15% val / 15% test)
   stratified across bin usage archetypes to prevent data leakage.
3. Train a tuned Random Forest Regressor on the engineered feature columns.
4. Evaluate regression (MAE, RMSE) and classification safety metrics (accuracy, Critical recall).
5. Serialize and save the trained model artifact.
"""

import sys
import time
from pathlib import Path
import json
import joblib
import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, accuracy_score, recall_score

# Configure directories
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
MODELS_DIR = BASE_DIR / "models"
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
print(f"   Loaded {len(df):,} labeled rows in {time.time()-t0:.2f}s.")

# ---------------------------------------------------------------------------
# Step 2: Cycle-Based Split (Prevents Data Leakage Across Time)
# ---------------------------------------------------------------------------
# Split by complete (bin_id, cycle_id) trajectories rather than individual rows.
# Consecutive sensor readings from the same fill cycle are strongly autocorrelated.
cycles = df[["bin_id", "cycle_id", "profile"]].drop_duplicates().reset_index(drop=True)
rng = np.random.default_rng(42)

train_idx, val_idx, test_idx = [], [], []
for profile, group in cycles.groupby("profile"):
    idx = group.sample(frac=1.0, random_state=42).index.to_numpy().copy()
    rng.shuffle(idx)
    n = len(idx)
    n_train = int(n * 0.70)
    n_val = int(n * 0.15)
    train_idx += list(idx[:n_train])
    val_idx += list(idx[n_train:n_train + n_val])
    test_idx += list(idx[n_train + n_val:])

def subset(index_list: list) -> pd.DataFrame:
    """Extract all sensor rows belonging to the given cycle indices."""
    keys = cycles.loc[index_list, ["bin_id", "cycle_id"]]
    return df.merge(keys, on=["bin_id", "cycle_id"], how="inner")

train_df = subset(train_idx)
test_df = subset(test_idx)
print(f"   Train samples: {len(train_df):,} | Test samples: {len(test_df):,}")

X_train, y_train = train_df[FEATURE_COLUMNS], train_df["time_to_overflow_hours"]
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
# Step 4: Evaluate Test Set Performance
# ---------------------------------------------------------------------------
preds = rf.predict(X_test)
mae = mean_absolute_error(y_test, preds)
rmse = float(np.sqrt(mean_squared_error(y_test, preds)))

# Map continuous hour predictions into discrete operational risk categories
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
# Step 5: Save Model Artifact
# ---------------------------------------------------------------------------
joblib.dump(rf, MODELS_DIR / "overflow_model.joblib")
print(f"\n4. Saved native model -> {MODELS_DIR / 'overflow_model.joblib'}")
