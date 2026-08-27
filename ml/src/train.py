"""
BinSight overflow-risk model: training + evaluation.

Split strategy:
  - Split by INDEPENDENT (bin_id, cycle_id) fill-cycles into train/val/test,
    not by random row shuffling. Rows within a cycle are highly correlated
    (same underlying trajectory), so row-level shuffling leaks information
    across the split. Splitting by whole cycles keeps train/val/test independent.
  - 70% cycles -> train, 15% -> val, 15% -> test. Stratify the split roughly
    by bin profile so all three sets see all usage archetypes.

Models compared:
  - Baseline 1: naive linear extrapolation from current fill rate (no ML)
  - Baseline 2: linear regression on engineered features
  - Model A: Random Forest Regressor (primary)
  - Model B: Gradient Boosting (XGBoost) (secondary comparison)

Run from anywhere: `python3 train.py` or `python3 src/train.py`.
"""
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error, mean_squared_error, accuracy_score, recall_score
from xgboost import XGBRegressor

from features import FEATURE_COLUMNS
from label import risk_level_from_hours, OVERFLOW_THRESHOLD_PCT

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
MODELS_DIR = BASE_DIR / "models"
MODELS_DIR.mkdir(parents=True, exist_ok=True)

TARGET = "time_to_overflow_hours"
SPLIT_SEED = 42


def split_by_cycle(df: pd.DataFrame, seed: int = SPLIT_SEED):
    """
    Partition dataset into train (70%), validation (15%), and test (15%) sets by whole fill cycles.
    
    Prevents temporal data leakage by grouping by (bin_id, cycle_id) and stratifying across bin profiles.
    
    Args:
        df: Labeled dataset DataFrame containing 'bin_id', 'cycle_id', and 'profile'.
        seed: Random seed for reproducibility.
        
    Returns:
        Tuple of (train_df, val_df, test_df).
    """
    cycles = df[["bin_id", "cycle_id", "profile"]].drop_duplicates().reset_index(drop=True)
    rng = np.random.default_rng(seed)

    train_idx, val_idx, test_idx = [], [], []
    for profile, group in cycles.groupby("profile"):
        idx = group.sample(frac=1.0, random_state=seed).index.to_numpy().copy()
        rng.shuffle(idx)
        n = len(idx)
        n_train = int(n * 0.70)
        n_val = int(n * 0.15)
        train_idx += list(idx[:n_train])
        val_idx += list(idx[n_train:n_train + n_val])
        test_idx += list(idx[n_train + n_val:])

    def subset(index_list):
        keys = cycles.loc[index_list, ["bin_id", "cycle_id"]]
        merged = df.merge(keys, on=["bin_id", "cycle_id"], how="inner")
        return merged

    return subset(train_idx), subset(val_idx), subset(test_idx)


def naive_baseline_predict(df: pd.DataFrame) -> np.ndarray:
    """
    Rule-based baseline: assume current fill_rate_1h holds constant until threshold.
    
    Args:
        df: DataFrame containing 'fill_pct' and 'fill_rate_1h'.
        
    Returns:
        NumPy array of predicted hours until overflow.
    """
    remaining_pct = (OVERFLOW_THRESHOLD_PCT - df["fill_pct"]).clip(lower=0)
    rate = df["fill_rate_1h"].replace(0, np.nan).abs()
    pred = remaining_pct / rate
    pred = pred.replace([np.inf, -np.inf], np.nan).fillna(remaining_pct.max())
    return pred.clip(lower=0, upper=200).to_numpy()


def evaluate(y_true: pd.Series, y_pred: np.ndarray, label: str) -> dict:
    """
    Compute regression error (MAE, RMSE) and classification safety metrics (Accuracy, Critical Recall).
    
    Args:
        y_true: Series of ground-truth hours to overflow.
        y_pred: Array of model predicted hours.
        label: Descriptive name of the model.
        
    Returns:
        Dictionary of evaluation metrics.
    """
    mae = mean_absolute_error(y_true, y_pred)
    rmse = float(np.sqrt(mean_squared_error(y_true, y_pred)))

    risk_true = y_true.apply(risk_level_from_hours)
    risk_pred = pd.Series(y_pred, index=y_true.index).apply(risk_level_from_hours)
    acc = accuracy_score(risk_true, risk_pred)
    critical_recall = recall_score(risk_true, risk_pred, labels=["Critical"], average="micro")

    result = {"model": label, "MAE_hours": round(mae, 3), "RMSE_hours": round(rmse, 3),
              "risk_level_accuracy": round(acc, 3), "critical_recall": round(critical_recall, 3)}
    print(result)
    return result


def main():
    df = pd.read_csv(DATA_DIR / "labeled_dataset.csv")
    train_df, val_df, test_df = split_by_cycle(df)
    print(f"Rows -> train: {len(train_df):,}  val: {len(val_df):,}  test: {len(test_df):,}")

    X_train, y_train = train_df[FEATURE_COLUMNS], train_df[TARGET]
    X_val, y_val = val_df[FEATURE_COLUMNS], val_df[TARGET]
    X_test, y_test = test_df[FEATURE_COLUMNS], test_df[TARGET]

    results = []

    # Baseline 1: naive extrapolation (no training needed)
    results.append(evaluate(y_test, naive_baseline_predict(test_df), "baseline_naive_extrapolation"))

    # Baseline 2: linear regression
    lin = LinearRegression().fit(X_train, y_train)
    results.append(evaluate(y_test, lin.predict(X_test), "baseline_linear_regression"))

    # Model A: Random Forest (primary)
    rf = RandomForestRegressor(
        n_estimators=300, max_depth=12, min_samples_leaf=5,
        random_state=SPLIT_SEED, n_jobs=-1,
    ).fit(X_train, y_train)
    results.append(evaluate(y_test, rf.predict(X_test), "random_forest"))

    # Model B: Gradient Boosting (secondary comparison)
    xgb = XGBRegressor(
        n_estimators=300, max_depth=6, learning_rate=0.05,
        subsample=0.8, colsample_bytree=0.8, random_state=SPLIT_SEED,
    ).fit(X_train, y_train, eval_set=[(X_val, y_val)], verbose=False)
    results.append(evaluate(y_test, xgb.predict(X_test), "xgboost"))

    # Select best model by test MAE among the two ML candidates.
    # NOTE: review eval_results.json before trusting this blindly -- Random Forest
    # vs XGBoost can trade off MAE against critical-recall (see README / spec doc).
    ml_results = [r for r in results if r["model"] in ("random_forest", "xgboost")]
    best = min(ml_results, key=lambda r: r["MAE_hours"])
    best_model = rf if best["model"] == "random_forest" else xgb
    print(f"\nSelected model: {best['model']} (MAE={best['MAE_hours']}h)")

    joblib.dump(best_model, MODELS_DIR / "overflow_model.joblib")
    with open(MODELS_DIR / "feature_columns.json", "w") as f:
        json.dump(FEATURE_COLUMNS, f, indent=2)
    with open(MODELS_DIR / "eval_results.json", "w") as f:
        json.dump({"results": results, "selected_model": best["model"]}, f, indent=2)

    feature_importance = pd.Series(best_model.feature_importances_, index=FEATURE_COLUMNS)
    feature_importance = feature_importance.sort_values(ascending=False)
    print("\nFeature importances:\n", feature_importance)
    feature_importance.to_csv(MODELS_DIR / "feature_importance.csv", header=["importance"])

    print(f"\nSaved model artifacts -> {MODELS_DIR}")


if __name__ == "__main__":
    main()
