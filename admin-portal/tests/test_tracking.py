import json
from pathlib import Path
import shutil

import pandas as pd
import pytest

from binsight.config import load_config
from binsight.maps import build_tracking_map
from binsight.network import load_cached_service_network
from binsight.tracking import (
    build_site_fill_profiles,
    build_tracking_manifest,
    tracking_frame_at,
)


ROOT = Path(__file__).resolve().parents[1]


def _manifest():
    return {
        "mode": "SIMULATED_LOCAL_TRACKING",
        "route_id": "TEST-D1-H6",
        "start_minute": 0.0,
        "end_minute": 20.0,
        "duration_minutes": 20.0,
        "served_bins": ["UGB-001"],
        "total_bins": 1,
        "payload_capacity_kg": 9_000.0,
        "completion_minutes": {"UGB-001": 18.0},
        "site_completion_minutes": {"SJ-01": 18.0},
        "segments": [
            {
                "kind": "travel",
                "status": "EN_ROUTE",
                "trip_number": 1,
                "start_minute": 0.0,
                "end_minute": 10.0,
                "next_stop": "UGB-001",
                "payload_kg": 0.0,
                "payload_capacity_kg": 9_000.0,
                "bins_completed": 0,
                "geometry": [[3.06192, 101.55272], [3.07528, 101.575341]],
                "cumulative_m": [0.0, 3_000.0],
            },
            {
                "kind": "service",
                "status": "COLLECTING",
                "trip_number": 1,
                "start_minute": 10.0,
                "end_minute": 18.0,
                "next_stop": "UGB-001",
                "payload_kg": 0.0,
                "payload_capacity_kg": 9_000.0,
                "bins_completed": 0,
                "geometry": [[3.07528, 101.575341]],
                "cumulative_m": [0.0],
            },
            {
                "kind": "travel",
                "status": "RETURNING_TO_DEPOT",
                "trip_number": 1,
                "start_minute": 18.0,
                "end_minute": 20.0,
                "next_stop": "DEPOT",
                "payload_kg": 500.0,
                "payload_capacity_kg": 9_000.0,
                "bins_completed": 1,
                "geometry": [[3.07528, 101.575341], [3.06192, 101.55272]],
                "cumulative_m": [0.0, 3_000.0],
            },
        ],
    }


def test_tracking_interpolates_travel_and_pauses_during_collection():
    manifest = _manifest()
    start = tracking_frame_at(manifest, 0.0)
    halfway = tracking_frame_at(manifest, 5.0)
    service_start = tracking_frame_at(manifest, 10.0)
    service_later = tracking_frame_at(manifest, 17.9)
    completed = tracking_frame_at(manifest, 18.0)

    assert start.status == "EN_ROUTE"
    assert start.longitude < halfway.longitude < service_start.longitude
    assert (service_start.latitude, service_start.longitude) == pytest.approx(
        (service_later.latitude, service_later.longitude)
    )
    assert service_later.bins_completed == 0
    assert completed.bins_completed == 1
    assert completed.status == "RETURNING_TO_DEPOT"


def test_tracking_map_has_controls_layers_reduced_motion_and_11_sites():
    config = load_config(ROOT / "config.json")
    bins = pd.read_csv(ROOT / "artifacts" / "district_bins.csv")
    audit_rows = [
        {
            "bin_id": str(row.bin_id),
            "selection": "Required" if row.bin_id == "UGB-001" else "Wait",
            "fill_pct": 80.0 if row.bin_id == "UGB-001" else 30.0,
            "weight_kg": 432.0 if row.bin_id == "UGB-001" else 162.0,
            "time_to_overflow_hours": 20.0 if row.bin_id == "UGB-001" else 100.0,
            "risk_level": "high" if row.bin_id == "UGB-001" else "low",
            "confidence_flag": True,
            "reason": "test tracking state",
        }
        for row in bins.itertuples()
    ]
    rendered = build_tracking_map(config, bins, _manifest(), audit_rows).get_root().render()

    assert rendered.count("binsight-site-marker state-") == 11
    assert all(label in rendered for label in ("Resume", "Pause", "Reset"))
    assert "Active truck route" in rendered
    assert "Completed route segments" in rendered
    assert "Remaining route segments" in rendered
    assert "Simulated traffic intensity" in rendered
    assert "prefers-reduced-motion:reduce" in rendered
    assert "LOCAL SIMULATION" in rendered
    assert "tracking-completed" in rendered
    assert "tracking-fill" in rendered
    assert "siteFillProfiles" in rendered
    assert "--fill-level" in rendered
    assert "fillColor" in rendered


def test_site_fill_profiles_reset_collected_bins_and_keep_forecast_inputs():
    bins = pd.DataFrame(
        [
            {"bin_id": "A", "site_id": "SITE-1"},
            {"bin_id": "B", "site_id": "SITE-1"},
        ]
    )
    rows = [
        {"bin_id": "A", "fill_pct": 80.0, "time_to_overflow_hours": 4.0},
        {"bin_id": "B", "fill_pct": 30.0, "time_to_overflow_hours": None},
    ]
    manifest = {"completion_minutes": {"A": 18.0}}

    profiles = build_site_fill_profiles(bins, rows, manifest)["SITE-1"]

    assert profiles[0] == {
        "bin_id": "A",
        "initial_fill_pct": 80.0,
        "time_to_overflow_hours": 4.0,
        "completion_minute": 18.0,
    }
    assert profiles[1]["initial_fill_pct"] == 30.0
    assert profiles[1]["time_to_overflow_hours"] is None
    assert profiles[1]["completion_minute"] is None


def test_recycling_facility_is_a_trackable_stop_and_unload_location(tmp_path):
    config = load_config(ROOT / "config.json")
    bins = pd.read_csv(ROOT / "artifacts" / "district_bins.csv")
    network = load_cached_service_network(ROOT / "data" / "subang_jaya_osrm_network.json")
    recycling_index = int(bins.index[bins["waste_stream"] == "dry_recycling"][0])
    recycling_bin = str(bins.iloc[recycling_index]["bin_id"])
    facility_id = config.pilot.recycling_facility_id
    recycling_event = {
        "policy": "smart",
        "day": 4,
        "hour": 78,
        "route_bin_indices": [[-1, recycling_index, -1]],
        "routes": [[facility_id, recycling_bin, facility_id]],
        "route_vehicle_ids": ["RECYCLING-01"],
        "route_vehicle_types": ["recycling"],
        "served_bins": [recycling_bin],
        "timeline": [
            {
                "status": "DISPATCHED",
                "simulation_minute": 0.0,
                "trip_number": 1,
                "payload_capacity_kg": 9_000.0,
            },
            {
                "status": "EN_ROUTE",
                "simulation_minute": 0.0,
                "trip_number": 1,
                "origin": facility_id,
                "destination": recycling_bin,
                "travel_minutes": 10.0,
                "payload_kg": 0.0,
            },
            {
                "status": "COLLECTING",
                "simulation_minute": 10.0,
                "trip_number": 1,
                "bin_id": recycling_bin,
                "duration_minutes": 8.0,
            },
            {
                "status": "COLLECTION_COMPLETE",
                "simulation_minute": 18.0,
                "trip_number": 1,
                "bin_id": recycling_bin,
                "payload_kg": 80.0,
                "bins_completed": 1,
            },
            {
                "status": "RETURNING_TO_RECYCLING_FACILITY",
                "simulation_minute": 18.0,
                "trip_number": 1,
                "origin": recycling_bin,
                "destination": facility_id,
                "travel_minutes": 10.0,
                "payload_kg": 80.0,
            },
            {
                "status": "UNLOADING",
                "simulation_minute": 28.0,
                "trip_number": 1,
                "unload_destination": "recycling_facility",
                "payload_kg": 80.0,
                "duration_minutes": 20.0,
            },
            {
                "status": "TRIP_COMPLETE",
                "simulation_minute": 48.0,
                "trip_number": 1,
            },
        ],
    }

    route_cache = tmp_path / "route-cache.json"
    shutil.copy2(ROOT / "data" / "osrm_route_geometry_cache.json", route_cache)
    manifest = build_tracking_manifest(
        recycling_event,
        bins,
        network,
        route_cache,
        {config.pilot.recycling_facility_id: 1},
        trip_number=1,
    )

    facility_segments = [
        segment for segment in manifest["segments"] if segment["kind"] == "facility"
    ]
    assert facility_segments
    assert facility_segments[0]["next_stop"] == config.pilot.recycling_facility_id
    assert facility_segments[0]["geometry"][0] == pytest.approx(
        network.snapped_coordinates[1]
    )
    assert manifest["vehicle_id"] == "RECYCLING-01"
    assert manifest["route_base_id"] == facility_id
    assert any(
        segment["status"] == "RETURNING_TO_RECYCLING_FACILITY"
        for segment in manifest["segments"]
    )
    assert not any(
        segment["status"] == "RETURNING_TO_DEPOT"
        for segment in manifest["segments"]
    )
