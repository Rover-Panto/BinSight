"""
BinSight synthetic bin-filling simulator.

Generates realistic per-bin time series of fill_pct and weight_kg with
noise, sensor confidence flags, and known-by-construction time-to-overflow
labels. Used to produce a training set for the overflow-risk model, and can
be reused for the Deliverable 2 district-scale simulation.

Run from anywhere: `python3 simulate.py` or `python3 src/simulate.py`.
"""
from pathlib import Path

import numpy as np
import pandas as pd

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

RNG_SEED = 42
OVERFLOW_THRESHOLD_PCT = 90.0
STEP_MINUTES = 30
STEPS_PER_HOUR = 60 // STEP_MINUTES

# Bin usage archetypes: (name, base_items_per_hour, weight_kg_per_item_mean, weight_kg_per_item_sd,
#                        volume_pct_per_item_mean, volume_pct_per_item_sd)
BIN_PROFILES = {
    "residential_low": dict(base_rate=0.6, w_mean=0.35, w_sd=0.15, v_mean=1.8, v_sd=0.6),
    "commercial_high": dict(base_rate=2.4, w_mean=0.55, w_sd=0.25, v_mean=2.6, v_sd=0.9),
    "event_surge":     dict(base_rate=1.2, w_mean=0.30, w_sd=0.20, v_mean=2.0, v_sd=1.0),
}

# Hour-of-day multiplier (index 0-23), rough daytime/evening usage pattern
HOUR_MULTIPLIER = np.array([
    0.1, 0.1, 0.1, 0.1, 0.1, 0.2, 0.4, 0.8,
    1.2, 1.4, 1.5, 1.6, 1.8, 1.6, 1.4, 1.3,
    1.5, 1.8, 2.0, 1.7, 1.2, 0.7, 0.4, 0.2,
])

# Day-of-week multiplier (0=Monday ... 6=Sunday)
DOW_MULTIPLIER = np.array([1.0, 1.0, 1.0, 1.0, 1.1, 1.6, 1.3])


def simulate_bin(bin_id: str, profile_name: str, n_days: int, rng: np.random.Generator,
                  event_surge_prob: float = 0.03) -> pd.DataFrame:
    """
    Simulate one bin over n_days at STEP_MINUTES resolution.
    Returns raw (noisy) sensor rows: timestamp, bin_id, fill_pct, weight_kg, confidence_flag.
    The bin resets (collection event) whenever fill_pct crosses OVERFLOW_THRESHOLD_PCT,
    which closes one "fill cycle" so labels can be computed exactly.
    """
    profile = BIN_PROFILES[profile_name]
    n_steps = n_days * 24 * STEPS_PER_HOUR
    start = pd.Timestamp("2026-01-01")
    timestamps = start + pd.to_timedelta(np.arange(n_steps) * STEP_MINUTES, unit="m")

    fill_pct = np.zeros(n_steps)
    weight_kg = np.zeros(n_steps)
    cycle_id = np.zeros(n_steps, dtype=int)

    cur_fill, cur_weight, cur_cycle = 0.0, 0.0, 0

    for i, ts in enumerate(timestamps):
        hour = ts.hour
        dow = ts.dayofweek
        rate_mult = HOUR_MULTIPLIER[hour] * DOW_MULTIPLIER[dow]

        # Occasional surge day (festival/market) for the event_surge profile
        if profile_name == "event_surge" and rng.random() < event_surge_prob:
            rate_mult *= rng.uniform(2.0, 4.0)

        expected_items = profile["base_rate"] * rate_mult * (STEP_MINUTES / 60.0)
        n_items = rng.poisson(max(expected_items, 0.0))

        if n_items > 0:
            item_weights = rng.normal(profile["w_mean"], profile["w_sd"], n_items).clip(min=0.02)
            item_volumes = rng.normal(profile["v_mean"], profile["v_sd"], n_items).clip(min=0.1)
            cur_weight += item_weights.sum()
            cur_fill += item_volumes.sum()

        fill_pct[i] = min(cur_fill, 100.0)
        weight_kg[i] = cur_weight
        cycle_id[i] = cur_cycle

        if cur_fill >= OVERFLOW_THRESHOLD_PCT:
            # Collection happens; bin resets after a short response delay (1-2 steps)
            cur_fill, cur_weight = rng.uniform(0, 3), rng.uniform(0, 0.5)
            cur_cycle += 1

    df = pd.DataFrame({
        "timestamp": timestamps,
        "bin_id": bin_id,
        "profile": profile_name,
        "cycle_id": cycle_id,
        "fill_pct_true": fill_pct,
        "weight_kg_true": weight_kg,
    })

    # Sensor noise + occasional bad readings (confidence_flag)
    noise_fill = rng.normal(0, 1.5, n_steps)          # ultrasonic noise, ~1.5% std
    noise_weight = rng.normal(0, 0.05, n_steps)       # load cell noise, ~50g std
    df["fill_pct"] = (df["fill_pct_true"] + noise_fill).clip(0, 105)
    df["weight_kg"] = (df["weight_kg_true"] + noise_weight).clip(lower=0)

    bad_reading = rng.random(n_steps) < 0.02          # 2% of readings flagged bad
    df.loc[bad_reading, "fill_pct"] = df.loc[bad_reading, "fill_pct"] + rng.normal(0, 15, bad_reading.sum())
    df["confidence_flag"] = np.where(bad_reading, 0, 1)  # 1 = good, 0 = low confidence

    return df.drop(columns=["fill_pct_true", "weight_kg_true"])


def simulate_district(n_bins_per_profile: int = 5, n_days: int = 90, seed: int = RNG_SEED) -> pd.DataFrame:
    """Simulate a district of bins across all profiles. Reproducible via seed."""
    rng = np.random.default_rng(seed)
    frames = []
    bin_counter = 0
    for profile_name in BIN_PROFILES:
        for _ in range(n_bins_per_profile):
            bin_id = f"bin_{bin_counter:03d}"
            frames.append(simulate_bin(bin_id, profile_name, n_days, rng))
            bin_counter += 1
    return pd.concat(frames, ignore_index=True).sort_values(["bin_id", "timestamp"]).reset_index(drop=True)


if __name__ == "__main__":
    df = simulate_district(n_bins_per_profile=5, n_days=90, seed=RNG_SEED)
    out_path = DATA_DIR / "raw_sensor_log.csv"
    df.to_csv(out_path, index=False)
    print(f"Generated {len(df):,} rows across {df['bin_id'].nunique()} bins -> {out_path}")
    print(df.head())
