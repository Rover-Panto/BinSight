from pathlib import Path

import pandas as pd

from binsight.config import load_config
from binsight.maps import build_dispatch_map, build_site_records, create_restricted_map


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
