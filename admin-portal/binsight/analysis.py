from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats


METRIC_DIRECTIONS = {
    "overflow_incidents": "lower",
    "overflow_bin_hours": "lower",
    "overflow_spilled_kg": "lower",
    "distance_km": "lower",
    "collection_trips": "lower",
    "collection_stops": "lower",
    "wasted_pickups": "lower",
    "fuel_l": "lower",
    "co2_kg": "lower",
    "uncollected_kg_at_horizon": "lower",
    "collected_kg": "higher",
    "mean_fill_at_collection_pct": "higher",
    "truck_utilization_pct": "higher",
    "routing_fallbacks": "lower",
}


def summarize_replications(frame: pd.DataFrame, seed: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    expected = {"fixed", "smart"}
    if set(frame["policy"].unique()) != expected:
        raise ValueError("Replication results must contain fixed and smart policies")
    counts = frame.groupby("policy")["replication"].nunique()
    if counts.nunique() != 1:
        raise ValueError("Policies must have the same number of paired replications")
    n = int(counts.iloc[0])
    if n < 2:
        raise ValueError("At least two independent paired replications are required")

    summary_rows = []
    for policy, group in frame.groupby("policy", sort=True):
        for metric in METRIC_DIRECTIONS:
            values = group[metric].astype(float).to_numpy()
            sd = float(np.std(values, ddof=1))
            half_width = float(stats.t.ppf(0.975, n - 1) * sd / math.sqrt(n))
            summary_rows.append(
                {
                    "policy": policy,
                    "metric": metric,
                    "n_replications": n,
                    "mean": float(np.mean(values)),
                    "sd": sd,
                    "ci95_low": float(np.mean(values) - half_width),
                    "ci95_high": float(np.mean(values) + half_width),
                    "unit": metric_unit(metric),
                }
            )
    summary = pd.DataFrame(summary_rows)

    wide = frame.pivot(index="replication", columns="policy")
    effect_rows = []
    rng = np.random.default_rng(seed)
    for metric, direction in METRIC_DIRECTIONS.items():
        fixed = wide[(metric, "fixed")].astype(float).to_numpy()
        smart = wide[(metric, "smart")].astype(float).to_numpy()
        beneficial = fixed - smart if direction == "lower" else smart - fixed
        mean_effect = float(np.mean(beneficial))
        sd_effect = float(np.std(beneficial, ddof=1))
        half_width = float(stats.t.ppf(0.975, n - 1) * sd_effect / math.sqrt(n))
        permutations = 19_999
        signs = rng.choice(np.array([-1.0, 1.0]), size=(permutations, n), replace=True)
        permuted = np.mean(signs * beneficial, axis=1)
        p_value = float((np.count_nonzero(np.abs(permuted) >= abs(mean_effect)) + 1) / (permutations + 1))
        fixed_mean = float(np.mean(fixed))
        percent = 100.0 * mean_effect / abs(fixed_mean) if abs(fixed_mean) > 1e-12 else np.nan
        if 3 <= n <= 5000 and np.ptp(beneficial) > 0:
            shapiro_p = float(stats.shapiro(beneficial).pvalue)
        elif 3 <= n <= 5000:
            shapiro_p = 1.0
        else:
            shapiro_p = np.nan
        effect_rows.append(
            {
                "metric": metric,
                "direction_better": direction,
                "n_paired_replications": n,
                "fixed_mean": fixed_mean,
                "smart_mean": float(np.mean(smart)),
                "beneficial_difference": mean_effect,
                "beneficial_difference_ci95_low": mean_effect - half_width,
                "beneficial_difference_ci95_high": mean_effect + half_width,
                "beneficial_change_pct_vs_fixed": percent,
                "paired_sign_flip_p": p_value,
                "paired_difference_shapiro_p": shapiro_p,
                "unit": metric_unit(metric),
            }
        )
    return summary, pd.DataFrame(effect_rows)


def metric_unit(metric: str) -> str:
    if metric.endswith("_kg_hours"):
        return "kg-hours"
    if metric.endswith("_hours"):
        return "bin-hours"
    if metric.endswith("_km"):
        return "km"
    if metric.endswith("_kg") or "_kg_" in metric:
        return "kg"
    if metric.endswith("_l"):
        return "litres"
    if metric.endswith("_pct"):
        return "%"
    return "count"


def save_analysis(
    replication_frame: pd.DataFrame,
    output_dir: str | Path,
    seed: int,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    summary, effects = summarize_replications(replication_frame, seed)
    replication_frame.to_csv(output / "replication_metrics.csv", index=False)
    summary.to_csv(output / "policy_summary.csv", index=False)
    effects.to_csv(output / "paired_effects.csv", index=False)
    return summary, effects
