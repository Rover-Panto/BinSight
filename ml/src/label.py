"""
Labeling for BinSight overflow-risk model.

For every row at time t_i within a bin's fill cycle, the label is the time
(in hours) until fill_pct next crosses OVERFLOW_THRESHOLD_PCT within that
SAME cycle. Rows in a cycle that never reaches the threshold before the log
ends are dropped (right-censored, not enough information to label).

Run from anywhere: `python3 label.py` or `python3 src/label.py`.
"""
from pathlib import Path

import numpy as np
import pandas as pd

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"

OVERFLOW_THRESHOLD_PCT = 90.0

RISK_BINS = [
    (0, 4, "Critical"),
    (4, 12, "High"),
    (12, 24, "Medium"),
    (24, np.inf, "Low"),
]


def time_to_overflow_hours(row_time: pd.Timestamp, crossing_time: pd.Timestamp) -> float:
    """Calculate elapsed time in hours between two timestamps."""
    return (crossing_time - row_time).total_seconds() / 3600.0


def label_cycle(g: pd.DataFrame) -> pd.DataFrame:
    """
    Compute exact time-to-overflow target label for a single fill cycle.
    
    Identifies the exact timestamp when the bin crosses OVERFLOW_THRESHOLD_PCT (90%).
    For each row prior to the event, computes (crossing_timestamp - row_timestamp) in hours.
    Cycles that do not reach the threshold are marked with NaN (censored).
    
    Args:
        g: DataFrame containing rows for one (bin_id, cycle_id) pair.
        
    Returns:
        DataFrame with 'time_to_overflow_hours' column added.
    """
    g = g.sort_values("timestamp").copy()
    above = g["fill_pct"] >= OVERFLOW_THRESHOLD_PCT
    if not above.any():
        g["time_to_overflow_hours"] = np.nan  # censored: never reached threshold in this cycle
        return g
    crossing_time = g.loc[above, "timestamp"].iloc[0]
    g["time_to_overflow_hours"] = g["timestamp"].apply(lambda t: time_to_overflow_hours(t, crossing_time))
    # Rows AT/AFTER the crossing get label 0 (already overflowing) rather than negative
    g["time_to_overflow_hours"] = g["time_to_overflow_hours"].clip(lower=0)
    return g


def risk_level_from_hours(hours: float) -> str:
    """
    Map continuous hours-to-overflow into standardized operational risk buckets:
    - Critical : < 4 hours (Immediate dispatch required)
    - High     : 4 - 12 hours (Queue for next scheduled collection)
    - Medium   : 12 - 24 hours (Routine monitoring)
    - Low      : >= 24 hours (No intervention needed)
    
    Args:
        hours: Float representing hours remaining until overflow.
        
    Returns:
        String risk category name.
    """
    for lo, hi, label in RISK_BINS:
        if lo <= hours < hi:
            return label
    return "Low"


def build_labels(feature_table: pd.DataFrame, drop_censored: bool = True) -> pd.DataFrame:
    df = feature_table.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"])

    # Explicit loop (not groupby.apply) so bin_id/cycle_id survive regardless of pandas version.
    parts = []
    for (bin_id, cycle_id), g in df.groupby(["bin_id", "cycle_id"], sort=False):
        labeled_g = label_cycle(g)
        labeled_g["bin_id"] = bin_id
        labeled_g["cycle_id"] = cycle_id
        parts.append(labeled_g)
    labeled = pd.concat(parts, ignore_index=True)

    n_censored = labeled["time_to_overflow_hours"].isna().sum()
    if drop_censored:
        labeled = labeled.dropna(subset=["time_to_overflow_hours"])
    print(f"Censored rows (cycle never reached threshold in log window): "
          f"{n_censored:,} / {len(df):,} ({'dropped' if drop_censored else 'kept as NaN'})")

    labeled["risk_level"] = labeled["time_to_overflow_hours"].apply(risk_level_from_hours)
    return labeled.reset_index(drop=True)


if __name__ == "__main__":
    feat = pd.read_csv(DATA_DIR / "feature_table.csv")
    labeled = build_labels(feat)
    out_path = DATA_DIR / "labeled_dataset.csv"
    labeled.to_csv(out_path, index=False)
    print(labeled[["bin_id", "cycle_id", "timestamp", "fill_pct",
                    "time_to_overflow_hours", "risk_level"]].head(10))
    print("\nRisk level distribution:\n", labeled["risk_level"].value_counts())
    print("\nLabel stats (hours):\n", labeled["time_to_overflow_hours"].describe())
    print(f"\nWrote {len(labeled):,} rows -> {out_path}")
