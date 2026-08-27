from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd
import pytest

from binsight.config import load_config
from binsight.cli import main as cli_main
from binsight.dispatch import build_dispatch_plan, validate_snapshot
from binsight.pr2_forecasting import (
    AdaptivePR2ForecastAdapter,
    ForecastEvent,
    PR2ForecastConfig,
    PR2HistoryCache,
    _growth_intervals,
    clean_pr2_history,
    rolling_origin_backtest,
)


ROOT = Path(__file__).resolve().parents[1]
START = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _config() -> PR2ForecastConfig:
    return PR2ForecastConfig.load(ROOT / "config" / "pr2_forecasting.json")


def _bins(count: int = 3) -> pd.DataFrame:
    return pd.read_csv(ROOT / "artifacts" / "district_bins.csv").iloc[:count].copy()


def _reading(
    source_bin_id: str,
    when: datetime,
    fill_pct: float,
    *,
    confidence: int = 1,
    density: float = 2.0,
    ingested_at: datetime | None = None,
) -> dict:
    return {
        "timestamp": when.isoformat(),
        "bin_id": source_bin_id,
        "fill_pct": fill_pct,
        "estimated_density": density,
        "confidence_flag": confidence,
        "ingested_at": (ingested_at or when).isoformat(),
    }


def _regular_history(
    source_ids: list[str],
    *,
    days: int = 35,
    start: datetime = START,
) -> list[dict]:
    rows: list[dict] = []
    for source_index, source_id in enumerate(source_ids):
        fill = 10.0 + source_index % 4
        for step in range(days * 4 + 1):
            when = start + timedelta(hours=step * 6)
            if step and step % 12 == 0:
                fill = 12.0 + source_index % 3
            else:
                hour_factor = 1.6 if when.hour in (12, 18) else 0.8
                fill = min(92.0, fill + hour_factor + 0.05 * source_index)
            rows.append(_reading(source_id, when, fill, density=1.0 + source_index / 20.0))
    return rows


def test_collection_reset_is_confirmed_and_never_becomes_negative_generation():
    config = _config()
    readings = [
        _reading("bin_01", START, 70.0),
        _reading("bin_01", START + timedelta(hours=6), 18.0),
        _reading("bin_01", START + timedelta(hours=12), 21.0),
    ]
    cleaned, diagnostics = clean_pr2_history(
        readings,
        config.mapping("physical-pilot"),
        START + timedelta(hours=12),
        config.forecast,
    )
    intervals = _growth_intervals(cleaned)

    assert diagnostics["confirmed_resets"] == 1
    assert cleaned.loc[cleaned["collection_reset"], "fill_pct"].tolist() == [18.0]
    assert intervals["growth_pct"].tolist() == [3.0]
    assert (intervals["rate_pct_per_hour"] >= 0).all()


def test_routing_owned_history_cache_is_idempotent_and_never_overwrites_conflicts(tmp_path):
    mapping = _config().mapping("physical-pilot")
    cache = PR2HistoryCache(tmp_path / "history.sqlite3", mapping)
    reading = _reading("bin_01", START, 30.0)
    try:
        assert cache.ingest([reading]) == {"stored": 1, "duplicate": 0, "invalid": 0}
        assert cache.ingest([reading]) == {"stored": 0, "duplicate": 1, "invalid": 0}
        conflicting = dict(reading, fill_pct=80.0)
        with pytest.raises(ValueError, match="cache was not overwritten"):
            cache.ingest([conflicting])
        loaded = cache.load(START + timedelta(hours=1))
    finally:
        cache.close()
    assert len(loaded) == 1
    assert loaded[0]["fill_pct"] == 30.0


def test_single_unconfirmed_ultrasonic_jump_cannot_create_critical_alert():
    adapter = AdaptivePR2ForecastAdapter(_config(), _bins(), "physical-pilot")
    readings = []
    for source in ("bin_01", "bin_02", "bin_03"):
        readings.extend(
            [
                _reading(source, START, 35.0),
                _reading(source, START + timedelta(hours=6), 38.0),
            ]
        )
    readings.append(_reading("bin_01", START + timedelta(hours=12), 96.0))

    result = adapter.build_snapshot(readings, START + timedelta(hours=12))
    row = result.frame.set_index("bin_id").loc["UGB-001"]

    assert row["fill_pct"] == 38.0
    assert row["risk_level"] != "critical"
    assert not bool(row["confidence_flag"])
    assert "unconfirmed_single_jump" in row["quality_flags"]


def test_known_event_increases_distribution_without_using_future_event_outcome():
    readings = _regular_history(["bin_01", "bin_02", "bin_03"], days=35)
    decision = START + timedelta(days=35)
    event = ForecastEvent.from_mapping(
        {
            "event_id": "market-1",
            "event_type": "market",
            "known_at": (decision - timedelta(days=3)).isoformat(),
            "start_at": (decision + timedelta(hours=6)).isoformat(),
            "end_at": (decision + timedelta(hours=30)).isoformat(),
            "affected_bin_ids": ["UGB-001"],
            "proximity_km_by_bin": {"UGB-001": 0.2},
            "intensity": 1.4,
            "expected_attendance": 800,
            "data_quality": 0.9,
            "actual_attendance": 5000,
        }
    )
    baseline = AdaptivePR2ForecastAdapter(_config(), _bins(), "physical-pilot").build_snapshot(
        readings, decision
    )
    event_result = AdaptivePR2ForecastAdapter(_config(), _bins(), "physical-pilot").build_snapshot(
        readings, decision, events=[event]
    )
    normal = baseline.frame.set_index("bin_id").loc["UGB-001"]
    uplift = event_result.frame.set_index("bin_id").loc["UGB-001"]

    assert uplift["expected_fill_24h_pct"] > normal["expected_fill_24h_pct"]
    assert uplift["overflow_probability_48h"] >= normal["overflow_probability_48h"]
    assert (
        event_result.model_state["own_patterns"]["UGB-001"]
        ["event_uplift_by_type"]["market"]
        == _config().forecast.event_prior_uplift
    )


def test_missing_stale_low_confidence_and_id_mapping_are_explicit():
    config = _config()
    adapter = AdaptivePR2ForecastAdapter(config, _bins(), "physical-pilot")
    decision = START + timedelta(days=2)
    result = adapter.build_snapshot(
        [_reading("bin_01", START, 45.0, confidence=0)], decision
    )
    rows = result.frame.set_index("bin_id")

    assert rows.loc["UGB-001", "risk_level"] == "medium"
    assert not bool(rows.loc["UGB-001", "confidence_flag"])
    assert "stale_observation" in rows.loc["UGB-001", "quality_flags"]
    assert pd.isna(rows.loc["UGB-002", "fill_pct"])
    assert rows.loc["UGB-002", "forecast_status"] == "unavailable"
    assert not bool(rows.loc["UGB-002", "confidence_flag"])
    assert result.diagnostics["coverage_complete"] is True
    assert result.diagnostics["source_evidence_complete"] is False
    with pytest.raises(ValueError, match="Unknown PR #2 bin_id"):
        adapter.build_snapshot([_reading("silently-renamed", START, 20.0)], decision)


def test_future_reading_is_excluded_density_never_becomes_weight_and_forecast_updates():
    adapter = AdaptivePR2ForecastAdapter(_config(), _bins(), "physical-pilot")
    readings = _regular_history(["bin_01", "bin_02", "bin_03"], days=20)
    decision = START + timedelta(days=20)
    readings.append(_reading("bin_01", decision + timedelta(hours=1), 99.0, density=49.0))
    first = adapter.build_snapshot(readings, decision)
    first_row = first.frame.set_index("bin_id").loc["UGB-001"]
    assert first.diagnostics["rejected_future"] == 1
    assert first.frame["weight_kg"].isna().all()
    assert not first.frame["estimated_density_used"].any()

    delayed = list(readings)
    delayed.append(
        _reading(
            "bin_02",
            decision - timedelta(hours=1),
            88.0,
            ingested_at=decision + timedelta(seconds=1),
        )
    )
    delayed_result = AdaptivePR2ForecastAdapter(
        _config(), _bins(), "physical-pilot"
    ).build_snapshot(delayed, decision)
    assert delayed_result.diagnostics["rejected_future_ingestion"] == 1

    updated = list(readings)
    updated.extend(
        [
            _reading("bin_01", decision + timedelta(hours=6), 75.0),
            _reading("bin_01", decision + timedelta(hours=12), 78.0),
        ]
    )
    second = adapter.build_snapshot(updated, decision + timedelta(hours=12))
    second_row = second.frame.set_index("bin_id").loc["UGB-001"]
    assert second_row["observed_at"] != first_row["observed_at"]
    assert second_row["fill_pct"] > first_row["fill_pct"]
    assert second_row["time_to_overflow_hours"] < first_row["time_to_overflow_hours"]


def test_confirmed_collection_resets_trajectory_but_keeps_learned_pattern():
    config = _config()
    readings = _regular_history(["bin_01", "bin_02", "bin_03"], days=35)
    decision = START + timedelta(days=35)
    adapter = AdaptivePR2ForecastAdapter(config, _bins(), "physical-pilot")
    before = adapter.build_snapshot(readings, decision)
    version = before.diagnostics["model_version"]
    prior_fill = float(before.frame.set_index("bin_id").loc["UGB-001", "fill_pct"])
    readings.extend(
        [
            _reading("bin_01", decision + timedelta(hours=6), max(91.0, prior_fill)),
            _reading("bin_01", decision + timedelta(hours=12), 12.0),
            _reading("bin_01", decision + timedelta(hours=18), 14.0),
        ]
    )
    after = adapter.build_snapshot(readings, decision + timedelta(hours=18))
    row = after.frame.set_index("bin_id").loc["UGB-001"]

    assert row["fill_pct"] == 14.0
    assert row["last_collection_at"] == (decision + timedelta(hours=12)).isoformat()
    assert after.diagnostics["model_version"] == version
    assert "hour_of_day" in row["seasonality_used"]


def test_online_residual_updates_each_reading_and_scheduled_retrain_is_controlled():
    config = _config()
    readings = _regular_history(["bin_01", "bin_02", "bin_03"], days=35)
    decision = START + timedelta(days=35)
    adapter = AdaptivePR2ForecastAdapter(config, _bins(), "physical-pilot")
    first = adapter.build_snapshot(readings, decision)
    first_row = first.frame.set_index("bin_id").loc["UGB-001"]

    updated = list(readings)
    starting_fill = float(first_row["fill_pct"])
    for step, fill in enumerate(
        (starting_fill + 8.0, starting_fill + 16.0, starting_fill + 24.0),
        start=1,
    ):
        updated.append(
            _reading("bin_01", decision + timedelta(hours=6 * step), fill)
        )
    online = adapter.build_snapshot(updated, decision + timedelta(hours=18))
    online_row = online.frame.set_index("bin_id").loc["UGB-001"]

    assert online.diagnostics["model_retrained"] is False
    assert online.diagnostics["model_version"] == first.diagnostics["model_version"]
    assert online_row["online_residual_mae_pct"] != first_row["online_residual_mae_pct"]

    extended = _regular_history(
        ["bin_01", "bin_02", "bin_03"], days=49
    )
    retrained = adapter.build_snapshot(extended, START + timedelta(days=49))
    assert retrained.diagnostics["model_retrained"] is True
    assert retrained.diagnostics["model_version"] != first.diagnostics["model_version"]


def test_output_is_deterministic_and_threshold_crossing_is_interpolated():
    readings = _regular_history(["bin_01", "bin_02", "bin_03"], days=35)
    decision = START + timedelta(days=35)
    one = AdaptivePR2ForecastAdapter(_config(), _bins(), "physical-pilot").build_snapshot(
        readings, decision
    )
    two = AdaptivePR2ForecastAdapter(_config(), _bins(), "physical-pilot").build_snapshot(
        list(reversed(readings)), decision
    )

    pd.testing.assert_frame_equal(one.frame, two.frame)
    assert one.diagnostics["model_version"] == two.diagnostics["model_version"]
    tto = one.frame["time_to_overflow_hours"].dropna()
    assert (tto >= 0).all()
    assert any(abs(value / 6.0 - round(value / 6.0)) > 1e-6 for value in tto)
    row = one.frame.iloc[0]
    assert row["recent_fill_rate_6h_pct_per_hour"] is not None
    assert row["recent_fill_rate_24h_pct_per_hour"] is not None
    assert row["recent_fill_rate_168h_pct_per_hour"] is not None
    assert row["recent_growth_6h_pct"] is not None
    assert row["recent_growth_24h_pct"] is not None
    assert row["recent_growth_168h_pct"] is not None
    assert row["typical_fill_between_collections_pct"] is not None


def test_rolling_origin_evaluation_is_chronological_and_compares_all_baselines():
    readings = _regular_history(["bin_01", "bin_02", "bin_03"], days=50)
    evaluation = rolling_origin_backtest(
        _config(),
        _bins(),
        "physical-pilot",
        readings,
        origins=[START + timedelta(days=35), START + timedelta(days=42)],
    )

    assert evaluation["evaluation_design"].startswith("chronological rolling origin")
    assert evaluation["future_feature_leakage_check"] is True
    assert evaluation["estimated_density_used"] is False
    for horizon in (6, 24, 48, 168):
        assert f"model_mae_{horizon}h_pct" in evaluation["overall"]
        assert f"current_fill_mae_{horizon}h_pct" in evaluation["overall"]
        assert f"last_rate_mae_{horizon}h_pct" in evaluation["overall"]
        assert f"previous_week_mae_{horizon}h_pct" in evaluation["overall"]
        assert f"seasonal_moving_average_mae_{horizon}h_pct" in evaluation["overall"]


def test_realistic_pr2_history_produces_valid_routable_33_bin_snapshot():
    config = _config()
    bins = _bins(33)
    source_ids = [f"bin_{index:02d}" for index in range(1, 34)]
    readings = _regular_history(source_ids, days=21)
    decision = START + timedelta(days=21)
    result = AdaptivePR2ForecastAdapter(
        config, bins, "competition-simulation"
    ).build_snapshot(readings, decision)
    application_config = load_config(ROOT / "config.json")
    validated = validate_snapshot(
        result.frame,
        bins["bin_id"],
        application_config.operations.crane_lift_limit_kg,
        now_utc=decision,
    )

    assert len(validated) == 33
    assert validated["bin_id"].tolist() == bins["bin_id"].tolist()
    assert set(result.frame["timestamp"]) == {decision.isoformat()}
    assert (pd.to_datetime(result.cleaned_history["observed_at"], utc=True) <= decision).all()
    distance = np.load(ROOT / "artifacts" / "road_distance_matrix_m.npy")
    duration = np.load(ROOT / "artifacts" / "road_duration_matrix_s.npy")
    plan = build_dispatch_plan(
        validated,
        bins,
        distance,
        application_config,
        duration_matrix_s=duration,
    )
    assert plan.decision_state in {
        "COLLECTION_REQUIRED",
        "INSPECTION_REQUIRED",
        "NO_COLLECTION_REQUIRED",
    }


def test_forecast_cli_writes_strict_json_snapshot(tmp_path, monkeypatch):
    history_path = tmp_path / "history.json"
    output_path = tmp_path / "snapshot.json"
    history_path.write_text(
        json.dumps(_regular_history(["bin_01", "bin_02", "bin_03"], days=21)),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "binsight.cli",
            "forecast-pr2",
            "--history",
            str(history_path),
            "--profile",
            "physical-pilot",
            "--decision-at",
            (START + timedelta(days=21)).isoformat(),
            "--output",
            str(output_path),
        ],
    )

    cli_main()

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "pr2-predictive-snapshot-1.0"
    assert len(payload["bins"]) == 3
    assert all(row["weight_kg"] is None for row in payload["bins"])
