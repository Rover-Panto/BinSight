import pandas as pd

from binsight.analysis import METRIC_DIRECTIONS, metric_unit, summarize_replications


def test_paired_effect_uses_beneficial_direction():
    rows = []
    for replication in range(6):
        common = {metric: 0.0 for metric in METRIC_DIRECTIONS}
        common.update({
            "replication": replication,
            "scenario": "base",
            "overflow_bin_hours": 20,
            "overflow_spilled_kg": 10,
            "collection_trips": 4,
            "collection_stops": 10,
            "collected_kg": 100,
            "mean_fill_at_collection_pct": 60,
            "truck_utilization_pct": 50,
            "fuel_l": 5,
            "co2_kg": 13,
            "uncollected_kg_at_horizon": 20,
            "routing_fallbacks": 0,
        })
        rows.append(
            common
            | {
                "policy": "fixed",
                "overflow_incidents": 10 + replication,
                "distance_km": 100 + replication,
                "wasted_pickups": 5,
            }
        )
        rows.append(
            common
            | {
                "policy": "smart",
                "overflow_incidents": 5 + replication,
                "distance_km": 70 + replication,
                "wasted_pickups": 2,
            }
        )
    _, effects = summarize_replications(pd.DataFrame(rows), seed=42)
    distance = effects.query("scenario == 'base'").set_index("metric").loc["distance_km"]
    assert distance["beneficial_difference"] == 30
    assert distance["beneficial_change_pct_vs_fixed"] > 0


def test_uncollected_mass_uses_kg_unit():
    assert metric_unit("uncollected_kg_at_horizon") == "kg"


def test_time_and_overflow_exposure_units_are_distinct():
    assert metric_unit("travel_time_hours") == "hours"
    assert metric_unit("service_time_hours_post_warmup") == "hours"
    assert metric_unit("overflow_bin_hours") == "bin-hours"


def test_scenarios_are_summarized_as_separate_paired_experiments():
    rows = []
    for scenario in ("base", "traffic"):
        for replication in range(3):
            for policy in ("fixed", "smart"):
                row = {metric: 0.0 for metric in METRIC_DIRECTIONS}
                row.update(
                    {
                        "scenario": scenario,
                        "replication": replication,
                        "policy": policy,
                        "distance_km": 10.0 if policy == "fixed" else 8.0,
                    }
                )
                rows.append(row)
    summary, effects = summarize_replications(pd.DataFrame(rows), seed=9)
    assert set(summary["scenario"]) == {"base", "traffic"}
    assert set(effects["scenario"]) == {"base", "traffic"}
