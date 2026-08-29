from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats


CORE_METRIC_DIRECTIONS = {
    "overflow_incidents": "lower",
    "overflow_bin_hours": "lower",
    "overflow_spilled_kg": "lower",
    "distance_km": "lower",
    "travel_time_hours": "lower",
    "service_time_hours": "lower",
    "depot_unloading_time_hours": "lower",
    "turnaround_time_hours": "lower",
    "idling_time_hours": "lower",
    "collection_trips": "lower",
    "collection_stops": "lower",
    "wasted_pickups": "lower",
    "base_driving_fuel_l": "lower",
    "traffic_fuel_penalty_l": "lower",
    "payload_fuel_penalty_l": "lower",
    "driving_fuel_l": "lower",
    "collection_idle_fuel_l": "lower",
    "depot_idle_fuel_l": "lower",
    "fuel_l": "lower",
    "co2_kg": "lower",
    "collected_kg": "higher",
    "mean_fill_at_collection_pct": "higher",
    "truck_utilization_pct": "higher",
    "unserved_required_bins": "lower",
    "inspection_events": "lower",
    "routing_fallbacks": "lower",
}
METRIC_DIRECTIONS = {
    **CORE_METRIC_DIRECTIONS,
    **{
        f"{metric}_post_warmup": direction
        for metric, direction in CORE_METRIC_DIRECTIONS.items()
    },
    "uncollected_kg_at_horizon": "lower",
    "unfinished_trip_count": "lower",
}


def summarize_replications(frame: pd.DataFrame, seed: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    working = frame.copy()
    if "scenario" not in working.columns:
        working["scenario"] = "base"
    missing_metrics = [metric for metric in METRIC_DIRECTIONS if metric not in working.columns]
    if missing_metrics:
        raise ValueError("Replication results are missing metrics: " + ", ".join(missing_metrics))
    summary_rows = []
    effect_rows = []
    rng = np.random.default_rng(seed)
    expected = {"fixed", "smart"}
    for scenario, scenario_frame in working.groupby("scenario", sort=True):
        if set(scenario_frame["policy"].unique()) != expected:
            raise ValueError(f"Scenario {scenario} must contain fixed and smart policies")
        counts = scenario_frame.groupby("policy")["replication"].nunique()
        if counts.nunique() != 1:
            raise ValueError(f"Scenario {scenario} does not have paired replications")
        n = int(counts.iloc[0])
        if n < 2:
            raise ValueError("At least two independent paired replications are required")
        for policy, group in scenario_frame.groupby("policy", sort=True):
            for metric in METRIC_DIRECTIONS:
                values = group[metric].astype(float).to_numpy()
                sd = float(np.std(values, ddof=1))
                half_width = float(stats.t.ppf(0.975, n - 1) * sd / math.sqrt(n))
                summary_rows.append(
                    {
                        "scenario": scenario,
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

        wide = scenario_frame.pivot(index="replication", columns="policy")
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
            p_value = float(
                (np.count_nonzero(np.abs(permuted) >= abs(mean_effect)) + 1)
                / (permutations + 1)
            )
            fixed_mean = float(np.mean(fixed))
            percent = (
                100.0 * mean_effect / abs(fixed_mean)
                if abs(fixed_mean) > 1e-12
                else np.nan
            )
            if 3 <= n <= 5000 and np.ptp(beneficial) > 0:
                shapiro_p = float(stats.shapiro(beneficial).pvalue)
            elif 3 <= n <= 5000:
                shapiro_p = 1.0
            else:
                shapiro_p = np.nan
            effect_rows.append(
                {
                    "scenario": scenario,
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
    return pd.DataFrame(summary_rows), pd.DataFrame(effect_rows)


def metric_unit(metric: str) -> str:
    base = metric.removesuffix("_post_warmup")
    if base.endswith("_kg_hours"):
        return "kg-hours"
    if base == "overflow_bin_hours":
        return "bin-hours"
    if base.endswith("_time_hours") or base == "idling_time_hours":
        return "hours"
    if base.endswith("_km"):
        return "km"
    if base.endswith("_kg") or "_kg_" in base:
        return "kg"
    if base.endswith("_l"):
        return "litres"
    if base.endswith("_pct"):
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
