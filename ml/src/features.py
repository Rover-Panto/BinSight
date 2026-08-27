"""
Feature engineering for BinSight overflow-risk model.
Operates on a raw sensor log with columns: timestamp, bin_id, fill_pct, weight_kg, confidence_flag.
Produces the model-ready feature table (see FEATURE_COLUMNS below).

Run from anywhere: `python3 features.py` or `python3 src/features.py`.
"""
from pathlib import Path

import numpy as np
import pandas as pd

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"

FEATURE_COLUMNS = [
    "fill_pct", "weight_kg", "density_proxy",
    "fill_rate_1h", "fill_rate_6h", "weight_rate_1h",
    "hour_sin", "hour_cos", "dow_sin", "dow_cos", "is_weekend",
    "hist_avg_rate_same_slot", "time_since_reset_hours",
]


def add_time_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Extract calendar and cyclical time features from sensor timestamps.
    
    Transforms timestamp into sine/cosine encodings for hour-of-day (24h periodicity)
    and day-of-week (7d periodicity) to allow tree models to capture daily and weekly cycles smoothly.
    
    Args:
        df: DataFrame containing at least a 'timestamp' column.
        
    Returns:
        DataFrame with added columns: hour_sin, hour_cos, dow_sin, dow_cos, is_weekend.
    """
    df = df.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    hour = df["timestamp"].dt.hour + df["timestamp"].dt.minute / 60.0
    dow = df["timestamp"].dt.dayofweek
    df["hour_sin"] = np.sin(2 * np.pi * hour / 24)
    df["hour_cos"] = np.cos(2 * np.pi * hour / 24)
    df["dow_sin"] = np.sin(2 * np.pi * dow / 7)
    df["dow_cos"] = np.cos(2 * np.pi * dow / 7)
    df["is_weekend"] = (dow >= 5).astype(int)
    return df


def add_rate_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute rolling rate-of-change metrics per bin over 1-hour and 6-hour windows.
    
    Calculates:
    - `fill_rate_1h`: Rate of fill percentage change (%/hour) over the last hour.
    - `fill_rate_6h`: Smoothed trend rate of fill percentage change (%/hour) over 6 hours.
    - `weight_rate_1h`: Rate of weight change (kg/hour) over the last hour.
    
    Args:
        df: DataFrame sorted by bin_id and timestamp.
        
    Returns:
        DataFrame with rolling rate features added per bin.
    """
    df = df.sort_values(["bin_id", "timestamp"]).copy()
    out = []
    for bin_id, g in df.groupby("bin_id", sort=False):
        g = g.copy()
        # infer step size in hours from median timestamp delta
        dt_hours = g["timestamp"].diff().median().total_seconds() / 3600.0
        steps_1h = max(int(round(1.0 / dt_hours)), 1)
        steps_6h = max(int(round(6.0 / dt_hours)), 1)

        g["fill_rate_1h"] = (g["fill_pct"] - g["fill_pct"].shift(steps_1h)) / max(dt_hours * steps_1h, 1e-6)
        g["fill_rate_6h"] = (g["fill_pct"] - g["fill_pct"].shift(steps_6h)) / max(dt_hours * steps_6h, 1e-6)
        g["weight_rate_1h"] = (g["weight_kg"] - g["weight_kg"].shift(steps_1h)) / max(dt_hours * steps_1h, 1e-6)
        out.append(g)
    return pd.concat(out, ignore_index=True)


def add_reset_features(df: pd.DataFrame, drop_pct: float = 40.0) -> pd.DataFrame:
    """
    Detect collection/reset events (a sharp drop in fill_pct) per bin and compute
    time_since_reset_hours. Also assigns a cycle_id if not already present, used
    for leakage-safe labeling in label.py.
    """
    df = df.sort_values(["bin_id", "timestamp"]).copy()
    out = []
    for bin_id, g in df.groupby("bin_id", sort=False):
        g = g.copy()
        drop = g["fill_pct"].diff() < -drop_pct
        reset_id = drop.cumsum()
        if "cycle_id" not in g.columns:
            g["cycle_id"] = reset_id
        reset_time = g["timestamp"].where(drop).ffill()
        first_ts = g["timestamp"].iloc[0]
        reset_time = reset_time.fillna(first_ts)
        g["time_since_reset_hours"] = (g["timestamp"] - reset_time).dt.total_seconds() / 3600.0
        out.append(g)
    return pd.concat(out, ignore_index=True)


def add_historical_slot_average(df: pd.DataFrame) -> pd.DataFrame:
    """
    hist_avg_rate_same_slot: expanding average of fill_rate_1h for the same bin and
    same hour-of-day, using ONLY strictly earlier calendar days (no look-ahead leakage).
    """
    df = df.sort_values(["bin_id", "timestamp"]).copy()
    df["_date"] = df["timestamp"].dt.date
    df["_hour_bucket"] = df["timestamp"].dt.hour

    out = []
    for (bin_id, hour_bucket), g in df.groupby(["bin_id", "_hour_bucket"], sort=False):
        g = g.sort_values("timestamp").copy()
        daily = g.groupby("_date")["fill_rate_1h"].mean()
        expanding_prior_mean = daily.expanding().mean().shift(1)  # shift(1) excludes current day
        g["hist_avg_rate_same_slot"] = g["_date"].map(expanding_prior_mean)
        out.append(g)
    result = pd.concat(out, ignore_index=True)
    result["hist_avg_rate_same_slot"] = result["hist_avg_rate_same_slot"].fillna(result["fill_rate_1h"])
    return result.drop(columns=["_date", "_hour_bucket"])


def build_feature_table(raw_log: pd.DataFrame) -> pd.DataFrame:
    """
    Full feature pipeline: transform raw sensor logs into a model-ready feature table.
    
    Pipeline Steps:
    1. Cyclical time encoding (hour_sin/cos, dow_sin/cos, is_weekend).
    2. Short-term and medium-term rate of fill/weight change (fill_rate_1h, fill_rate_6h, weight_rate_1h).
    3. Density proxy estimation (weight_kg / fill_pct).
    4. Reset event detection & cycle elapsed time (time_since_reset_hours, cycle_id).
    5. Historical same-slot average fill rate without future leakage (hist_avg_rate_same_slot).
    6. Handling cold starts and filling initial NaNs with 0.0.
    
    Args:
        raw_log: Raw DataFrame with columns [timestamp, bin_id, fill_pct, weight_kg, confidence_flag].
        
    Returns:
        DataFrame containing all FEATURE_COLUMNS sorted by bin_id and timestamp.
    """
    df = add_time_features(raw_log)
    df = add_rate_features(df)
    df["density_proxy"] = df["weight_kg"] / df["fill_pct"].clip(lower=1.0)
    df = add_reset_features(df)
    df = add_historical_slot_average(df)

    # first-row-per-bin rate features will be NaN (no prior sample) -> fill with 0 (no observed change yet)
    for col in ["fill_rate_1h", "fill_rate_6h", "weight_rate_1h", "hist_avg_rate_same_slot"]:
        df[col] = df[col].fillna(0.0)

    return df.sort_values(["bin_id", "timestamp"]).reset_index(drop=True)


if __name__ == "__main__":
    raw = pd.read_csv(DATA_DIR / "raw_sensor_log.csv")
    feat = build_feature_table(raw)
    out_path = DATA_DIR / "feature_table.csv"
    feat.to_csv(out_path, index=False)
    print(feat[["bin_id", "timestamp"] + FEATURE_COLUMNS].head(10))
    print("\nNaN check:\n", feat[FEATURE_COLUMNS].isna().sum())
    print(f"\nWrote {len(feat):,} rows -> {out_path}")
