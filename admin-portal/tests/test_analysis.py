import pandas as pd

from binsight.analysis import metric_unit, summarize_replications


def test_paired_effect_uses_beneficial_direction():
    rows = []
    for replication in range(6):
        common = {
            "replication": replication,
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
        }
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
    distance = effects.set_index("metric").loc["distance_km"]
    assert distance["beneficial_difference"] == 30
    assert distance["beneficial_change_pct_vs_fixed"] > 0


def test_uncollected_mass_uses_kg_unit():
    assert metric_unit("uncollected_kg_at_horizon") == "kg"
