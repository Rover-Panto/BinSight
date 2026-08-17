from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from binsight.config import load_config
from binsight.district import BinSpec
from binsight.simulation import fixed_service_due, run_policy


ROOT = Path(__file__).resolve().parents[1]


class ZeroGrowthForecaster:
    def predict(self, feature_frame):
        zeros = np.zeros(len(feature_frame), dtype=float)
        return zeros, zeros


def _bin(index: int, capacity_kg: float = 100.0) -> BinSpec:
    return BinSpec(
        bin_id=f"TEST-{index + 1:03d}",
        node_id=index + 1,
        latitude=3.06,
        longitude=101.58 + index * 0.001,
        households=1,
        commercial_units=0,
        capacity_kg=capacity_kg,
        area_type="residential",
        controller_id=f"ESP32-{index + 1:03d}",
        controller_channel=1,
        site_id=f"SITE-{index + 1:02d}",
        site_label=f"Test site {index + 1}",
        service_index=index + 1,
    )


def _config(
    *,
    horizon_days: int,
    truck_capacity_kg: float = 100.0,
    max_daily_trips: int = 2,
    service_minutes: float = 8.0,
    turnaround_minutes: float = 7.0,
):
    config = load_config(ROOT / "config.json")
    sensor = replace(
        config.sensor,
        fill_random_sd_pct=0.0,
        weight_random_sd_kg=0.0,
        fill_bias_sd_pct=0.0,
        weight_bias_sd_kg=0.0,
        fill_drift_sd_pct_per_day=0.0,
        weight_drift_sd_kg_per_day=0.0,
        outlier_probability=0.0,
        fill_outlier_sd_pct=0.0,
        weight_outlier_sd_kg=0.0,
        missing_probability=0.0,
        low_confidence_margin_pct=0.0,
    )
    operations = replace(
        config.operations,
        horizon_days=horizon_days,
        fixed_interval_days=1,
        smart_min_dispatch_gap_hours=0,
        truck_capacity_kg=truck_capacity_kg,
        max_daily_trips=max_daily_trips,
        service_minutes_per_bin=service_minutes,
        depot_unload_minutes=10.0,
        turnaround_minutes=turnaround_minutes,
        traffic_peak_duration_multiplier=1.0,
        traffic_shoulder_duration_multiplier=1.0,
        traffic_offpeak_duration_multiplier=1.0,
        traffic_peak_fuel_multiplier=1.0,
        traffic_shoulder_fuel_multiplier=1.0,
        traffic_offpeak_fuel_multiplier=1.0,
        analysis_warmup_days=0,
        route_solver_milliseconds=50,
    )
    return replace(config, sensor=sensor, operations=operations)


def _matrices(bin_count: int, duration_s: float):
    size = bin_count + 1
    distance = np.full((size, size), 1_000.0)
    duration = np.full((size, size), duration_s)
    np.fill_diagonal(distance, 0.0)
    np.fill_diagonal(duration, 0.0)
    return distance, duration


def _statuses(result):
    return result.route_events[0]["timeline"]


def test_fixed_policy_first_service_is_after_the_full_interval():
    config = load_config(ROOT / "config.json")
    assert not fixed_service_due(config.operations.decision_hour, config)
    assert fixed_service_due(
        config.operations.fixed_interval_days * 24 + config.operations.decision_hour,
        config,
    )

    test_config = _config(horizon_days=2)
    bins = [_bin(0)]
    distance, duration = _matrices(1, 60.0)
    arrivals = np.zeros((48, 1), dtype=float)
    arrivals[0, 0] = 60.0
    result = run_policy(
        "fixed", 0, bins, test_config, distance, duration, arrivals, 11
    )

    assert result.route_events[0]["dispatch_minute"] == pytest.approx(30 * 60)


def test_second_trip_starts_only_after_return_unload_and_turnaround():
    config = _config(horizon_days=2)
    bins = [_bin(0), _bin(1)]
    distance, duration = _matrices(2, 600.0)
    arrivals = np.zeros((48, 2), dtype=float)
    arrivals[0] = 80.0
    result = run_policy("fixed", 0, bins, config, distance, duration, arrivals, 12)
    timeline = _statuses(result)

    dispatched = [row for row in timeline if row["status"] == "DISPATCHED"]
    first_complete = next(
        row for row in timeline
        if row["status"] == "TRIP_COMPLETE" and row["trip_number"] == 1
    )
    assert len(dispatched) == 2
    assert dispatched[1]["simulation_minute"] >= first_complete["simulation_minute"]
    assert any(row["status"] == "UNLOADING" for row in timeline)
    assert any(row["status"] == "TURNAROUND" for row in timeline)
    assert result.metrics["collection_trips"] == 2


def test_bin_is_not_emptied_until_collection_service_completes():
    config = _config(horizon_days=2, service_minutes=90.0)
    bins = [_bin(0)]
    distance, duration = _matrices(1, 60.0)
    arrivals = np.zeros((48, 1), dtype=float)
    arrivals[30, 0] = 99.0
    arrivals[31, 0] = 2.0
    result = run_policy("fixed", 0, bins, config, distance, duration, arrivals, 13)
    timeline = _statuses(result)

    collecting = next(row for row in timeline if row["status"] == "COLLECTING")
    completed = next(row for row in timeline if row["status"] == "COLLECTION_COMPLETE")
    overflow = next(row for row in timeline if row["status"] == "OVERFLOW_DETECTED")
    assert overflow["truck_status"] == "COLLECTING"
    assert completed["simulation_minute"] - collecting["simulation_minute"] == pytest.approx(90.0)
    assert completed["collected_kg"] == pytest.approx(100.0)


def test_overflow_can_occur_while_truck_is_still_en_route():
    config = _config(horizon_days=2)
    bins = [_bin(0)]
    distance, duration = _matrices(1, 7_200.0)
    arrivals = np.zeros((48, 1), dtype=float)
    arrivals[30, 0] = 99.0
    arrivals[31, 0] = 2.0
    result = run_policy("fixed", 0, bins, config, distance, duration, arrivals, 14)

    overflow = next(
        row for row in _statuses(result) if row["status"] == "OVERFLOW_DETECTED"
    )
    assert overflow["truck_status"] == "EN_ROUTE"
    assert result.metrics["overflow_incidents"] >= 1
    assert result.metrics["overflow_spilled_kg"] >= 1.0


def test_daily_trip_limit_is_shared_by_morning_and_evening_decisions():
    config = _config(horizon_days=1, max_daily_trips=1)
    bins = [_bin(0)]
    distance, duration = _matrices(1, 60.0)
    arrivals = np.zeros((24, 1), dtype=float)
    arrivals[6, 0] = 80.0
    arrivals[18, 0] = 80.0
    result = run_policy(
        "smart",
        0,
        bins,
        config,
        distance,
        duration,
        arrivals,
        15,
        forecaster=ZeroGrowthForecaster(),
    )

    assert result.metrics["collection_trips"] == 1
    assert len(result.route_events) == 1
    assert result.final_fill_kg[0] == pytest.approx(80.0)


def test_two_missing_sensors_request_inspection_without_fabricating_full_bin():
    base = _config(horizon_days=1)
    config = replace(base, sensor=replace(base.sensor, missing_probability=1.0))
    bins = [_bin(0)]
    distance, duration = _matrices(1, 60.0)
    arrivals = np.zeros((24, 1), dtype=float)

    result = run_policy(
        "smart",
        0,
        bins,
        config,
        distance,
        duration,
        arrivals,
        16,
        forecaster=ZeroGrowthForecaster(),
    )

    assert result.metrics["collection_trips"] == 0
    assert result.metrics["inspection_events"] == 2
    assert result.final_fill_kg[0] == 0.0
