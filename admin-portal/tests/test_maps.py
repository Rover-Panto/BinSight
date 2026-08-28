from pathlib import Path

import pandas as pd

from binsight.config import load_config
from binsight.maps import (
    build_dispatch_map,
    build_fleet_playback_map,
    build_overview_map,
    build_site_records,
    create_restricted_map,
)


ROOT = Path(__file__).resolve().parents[1]


def _inputs():
    config = load_config(ROOT / "config.json")
    bins = pd.read_csv(ROOT / "artifacts" / "district_bins.csv")
    rows = [
        {
            "bin_id": str(row.bin_id),
            "selection": "Wait",
            "collection_state": "Wait",
            "fill_pct": 30.0,
            "weight_kg": 162.0,
            "time_to_overflow_hours": 100.0,
            "risk_level": "low",
            "confidence_flag": True,
            "reason": "can wait",
        }
        for row in bins.itertuples()
    ]
    return config, bins, rows


def test_44_bins_are_consolidated_into_exactly_11_unoffset_site_records():
    _, bins, rows = _inputs()
    records = build_site_records(bins, rows)

    assert len(records) == 11
    assert all(record["bin_count"] == 4 for record in records)
    for record in records:
        site = bins[bins["site_id"] == record["site_id"]]
        assert site[["latitude", "longitude"]].drop_duplicates().shape[0] == 1
        assert record["latitude"] == site.iloc[0]["latitude"]
        assert record["longitude"] == site.iloc[0]["longitude"]
        assert {detail["bin_id"] for detail in record["bins"]} == set(site["bin_id"])


def test_site_state_priority_and_all_bin_details_are_rendered():
    config, bins, rows = _inputs()
    rows[0]["selection"] = "Required"
    rows[4]["selection"] = "Inspection required"
    rows[8]["selection"] = "Positive-value optional pickup"
    rows[12]["selection"] = "Completed"
    records = build_site_records(bins, rows, {str(bins.iloc[12]["bin_id"])})
    states = {record["site_id"]: record["state"] for record in records}
    assert list(states.values())[:4] == ["required", "inspection", "optional", "completed"]

    geometry = [[
        (config.pilot.depot_lat, config.pilot.depot_lon),
        (float(bins.iloc[0]["latitude"]), float(bins.iloc[0]["longitude"])),
    ]]
    rendered = build_dispatch_map(config, bins, geometry, rows).get_root().render()
    assert rendered.count("binsight-site-marker state-") == 11
    assert rendered.count("4 co-located underground bins") == 11
    assert "state-required" in rendered
    assert "state-inspection" in rendered
    assert "state-optional" in rendered
    assert "state-completed" in rendered
    assert "Collection required" in rendered
    assert "Inspection required" in rendered
    assert "No collection required" in rendered
    assert "Mixed General Waste" in rendered
    assert "Plastic Cups" in rendered
    assert "Metal Cans" in rendered
    assert "Glass Bottles" in rendered
    assert "MBSJ USJ 9 Recycling Centre" in rendered
    assert "no API key" in rendered


def test_operations_map_renders_four_independent_fill_quadrants_per_site():
    config, bins, rows = _inputs()
    for row, fill in zip(rows[:4], (12.3, 45.6, 78.9, 100.0)):
        row["fill_pct"] = fill

    rendered = build_overview_map(
        config,
        bins,
        {"features": []},
        rows,
    ).get_root().render()

    assert rendered.count("site-quarter-marker state-") == 11
    assert rendered.count("site-quarter quarter-") == 44
    assert rendered.count("data-material") == 44
    assert all(
        material in rendered
        for material in (
            "mixed_general_waste",
            "plastic_cups",
            "metal_cans",
            "glass_bottles",
        )
    )
    assert "--bin-fill:12.300%" in rendered
    assert "--fill-angle:11.070deg" in rendered
    assert "--bin-fill:45.600%" in rendered
    assert "--fill-angle:41.040deg" in rendered
    assert "--bin-fill:78.900%" in rendered
    assert "--fill-angle:71.010deg" in rendered
    assert "--bin-fill:100.000%" in rendered
    assert "--fill-angle:90.000deg" in rendered
    assert "OPERATIONS SNAPSHOT · SIMULATED" in rendered
    assert "Red quarter-circle wedge + number = each bin's unchanged fill percentage" in rendered


def test_monthly_fleet_map_keeps_both_trucks_visible_and_exposes_playback_controls():
    config, bins, _ = _inputs()
    manifest = {
        "mode": "SIMULATED_MONTHLY_FLEET_PLAYBACK",
        "day": 1,
        "start_minute": 0.0,
        "end_minute": 1440.0,
        "duration_minutes": 1440.0,
        "has_dispatch": False,
        "vehicles": [
            {
                "vehicle_id": "GENERAL-01",
                "vehicle_type": "general_waste",
                "base_id": "DEPOT",
                "base_coordinate": [
                    config.pilot.depot_lat,
                    config.pilot.depot_lon,
                ],
                "color": "#47d7ff",
                "segments": [],
                "served_bins": [],
                "distance_km": 0.0,
                "trip_count": 0,
            },
            {
                "vehicle_id": "RECYCLING-01",
                "vehicle_type": "recycling",
                "base_id": config.pilot.recycling_facility_id,
                "base_coordinate": [
                    config.pilot.recycling_facility_lat,
                    config.pilot.recycling_facility_lon,
                ],
                "color": "#55a879",
                "segments": [],
                "served_bins": [],
                "distance_km": 0.0,
                "trip_count": 0,
            },
        ],
    }

    rendered = build_fleet_playback_map(config, bins, manifest).get_root().render()

    assert "DAY 01 / 30 · TWO-TRUCK PLAYBACK" in rendered
    assert "GENERAL-01" in rendered
    assert "RECYCLING-01" in rendered
    assert "No dispatches on this day. Both trucks remain at their bases." in rendered
    # Each site includes the phrase once in its tooltip and once in its ARIA label.
    assert rendered.count("four-bin service site") == 22
    assert all(label in rendered for label in ("Resume", "Pause", "Reset"))
    assert all(label in rendered for label in ("1× · 60 sec/day", "10× · 6 sec/day"))
    assert "window.binsightFleetPlayback" in rendered
    assert "30-DAY FLEET PLAYBACK · SIMULATED" in rendered


def test_map_is_hard_bounded_and_tiles_do_not_wrap():
    config, _, _ = _inputs()
    rendered = create_restricted_map(config).get_root().render()

    assert '"maxBounds"' in rendered
    assert '"maxBoundsViscosity": 1.0' in rendered
    assert f'"minZoom": {config.pilot.map_min_zoom}' in rendered
    assert f'"maxZoom": {config.pilot.map_max_zoom}' in rendered
    assert '"noWrap": true' in rendered
    assert "Reset to Subang Jaya pilot bounds" in rendered
    assert str(config.pilot.map_southwest_lat) in rendered
    assert str(config.pilot.map_northeast_lon) in rendered
