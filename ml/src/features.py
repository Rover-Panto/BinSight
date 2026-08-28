"""
Feature engineering for BinSight overflow-risk model.

Operates on raw sensor telemetry streams. Primary input columns:
    - timestamp (ISO-8601 string or datetime)
    - bin_id (str)
    - fill_pct (float, 0-100)
    - confidence_flag (int, 0 or 1)
    - optional: estimated_density (float), weight_kg (float)

Compatible with PR2 edge-to-cloud schemas. Does NOT require weight_kg.
Produces model-ready feature table (FEATURE_COLUMNS).
"""
from pathlib import Path
import numpy as np
import pandas as pd

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"

FEATURE_COLUMNS = [
    "fill_pct",
    "fill_rate_1h",
    "fill_rate_6h",
    "hour_sin",
    "hour_cos",
    "dow_sin",
    "dow_cos",
    "is_weekend",
    "hist_avg_rate_same_slot",
    "time_since_reset_hours",
]


def add_time_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Extract calendar and cyclical time features from sensor timestamps.
    
    Transforms timestamp into sine/cosine encodings for hour-of-day (24h periodicity)
    and day-of-week (7d periodicity).
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
    Compute rolling rate-of-change metrics per bin over elapsed-time windows (1-hour and 6-hour).
    
    Uses exact timestamp differences rather than row indices to correctly handle:
    - Single readings (cold start -> rate = 0.0)
    - Duplicate timestamps (deduplicated or delta guarded)
    - Irregular sampling intervals and telemetry gaps
    - Collection events (rates are not calculated across collection resets)
    """
    df = df.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    # Sort and deduplicate timestamps per bin
    df = df.sort_values(["bin_id", "timestamp"]).drop_duplicates(subset=["bin_id", "timestamp"], keep="last")
    
    out = []
    for bin_id, g in df.groupby("bin_id", sort=False):
        g = g.copy()
        n = len(g)
        if n <= 1:
            g["fill_rate_1h"] = 0.0
            g["fill_rate_6h"] = 0.0
            out.append(g)
            continue
        
        ts_values = g["timestamp"].to_numpy()
        fill_values = g["fill_pct"].to_numpy(dtype=float)
        
        fill_rate_1h = np.zeros(n, dtype=float)
        fill_rate_6h = np.zeros(n, dtype=float)
        
        # Calculate rates by looking back in elapsed time
        for i in range(1, n):
            t_curr = ts_values[i]
            f_curr = fill_values[i]
            
            best_idx_1h = -1
            best_diff_1h = float("inf")
            
            best_idx_6h = -1
            best_diff_6h = float("inf")
            
            for j in range(i - 1, -1, -1):
                dt_ns = t_curr - ts_values[j]
                dt_sec = dt_ns / np.timedelta64(1, 's')
                
                # Check for collection reset: if a large drop occurred, do not search across reset
                if fill_values[j+1] - fill_values[j] < -30.0:
                    break
                
                # 1-hour window check (within 15m to 2h)
                diff_1h = abs(dt_sec - 3600.0)
                if 900.0 <= dt_sec <= 7200.0 and diff_1h < best_diff_1h:
                    best_diff_1h = diff_1h
                    best_idx_1h = j
                    
                # 6-hour window check (within 1.5h to 9h)
                diff_6h = abs(dt_sec - 21600.0)
                if 5400.0 <= dt_sec <= 32400.0 and diff_6h < best_diff_6h:
                    best_diff_6h = diff_6h
                    best_idx_6h = j
            
            # Fallback for 1-hour if no reading in [15m, 2h] but prior reading exists within 24h
            if best_idx_1h == -1:
                dt_prev = (t_curr - ts_values[i-1]) / np.timedelta64(1, 's')
                if 60.0 <= dt_prev <= 86400.0 and (fill_values[i] - fill_values[i-1] >= -30.0):
                    best_idx_1h = i - 1
            
            # Compute 1h rate (% per hour)
            if best_idx_1h != -1:
                dt_h = (t_curr - ts_values[best_idx_1h]) / np.timedelta64(3600, 's')
                if dt_h > 0.01:
                    fill_rate_1h[i] = (f_curr - fill_values[best_idx_1h]) / dt_h
            
            # Compute 6h rate (% per hour)
            if best_idx_6h != -1:
                dt_6h = (t_curr - ts_values[best_idx_6h]) / np.timedelta64(3600, 's')
                if dt_6h > 0.01:
                    fill_rate_6h[i] = (f_curr - fill_values[best_idx_6h]) / dt_6h
            else:
                # If <6h of history, fallback to 1h rate
                fill_rate_6h[i] = fill_rate_1h[i]

        g["fill_rate_1h"] = np.clip(fill_rate_1h, -50.0, 50.0)
        g["fill_rate_6h"] = np.clip(fill_rate_6h, -50.0, 50.0)
        out.append(g)
        
    return pd.concat(out, ignore_index=True)


def add_reset_features(df: pd.DataFrame, drop_pct: float = 35.0) -> pd.DataFrame:
    """
    Detect collection/reset events (a sharp drop in fill_pct) per bin and compute
    time_since_reset_hours.
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
    Does NOT require weight_kg; works seamlessly on PR2 telemetry payloads.
    
    Args:
        raw_log: Raw DataFrame with columns [timestamp, bin_id, fill_pct, confidence_flag].
        
    Returns:
        DataFrame containing all FEATURE_COLUMNS sorted by bin_id and timestamp.
    """
    df = add_time_features(raw_log)
    df = add_rate_features(df)
    df = add_reset_features(df)
    df = add_historical_slot_average(df)

    for col in ["fill_rate_1h", "fill_rate_6h", "hist_avg_rate_same_slot", "time_since_reset_hours"]:
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
