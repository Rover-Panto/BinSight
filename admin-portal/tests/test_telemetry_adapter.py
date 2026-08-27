import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pytest
import requests
from jsonschema import Draft202012Validator, FormatChecker

from binsight.dispatch import validate_snapshot
from binsight.registry import BinRegistry
from binsight.telemetry_adapter import normalize_telemetry_envelope
from binsight.telemetry_client import (
    TelemetryAuthenticationError,
    TelemetryClient,
    TelemetryUnavailableError,
)


ROOT = Path(__file__).resolve().parents[1]


def _registry():
    return BinRegistry.load(ROOT / "config" / "bin_registry.json")


def _payload():
    return json.loads(
        (ROOT / "tests" / "fixtures" / "telemetry_v2_valid.json").read_text(
            encoding="utf-8"
        )
    )


def test_registry_separates_physical_and_simulation_profiles():
    registry = _registry()
    assert registry.profile("physical-pilot").bin_ids == (
        "UGB-001",
        "UGB-002",
        "UGB-003",
    )
    assert registry.profile("competition-simulation").source_mode == "synthetic"
    registry.validate_matrix("physical-pilot", np.zeros((4, 4)))
    with pytest.raises(ValueError, match="must be 4x4"):
        registry.validate_matrix("physical-pilot", np.zeros((3, 3)))
    with pytest.raises(ValueError, match="Unknown or conflicting"):
        registry.map_hardware_id("physical-pilot", "NOT-A-BIN")


def test_shared_v2_fixture_matches_the_published_schema():
    schema = json.loads(
        (ROOT / "hardware" / "telemetry-routing-v2.schema.json").read_text(
            encoding="utf-8"
        )
    )
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    assert list(validator.iter_errors(_payload())) == []


def test_v2_adapter_preserves_per_bin_time_null_weight_and_unknown_forecast():
    decision = datetime(2026, 8, 27, 8, 0, tzinfo=timezone.utc)
    result = normalize_telemetry_envelope(
        _payload(), _registry(), "physical-pilot", decision_at=decision
    )
    assert result.coverage_complete
    assert result.frame["bin_id"].tolist() == ["UGB-001", "UGB-002", "UGB-003"]
    assert result.frame["reading_age_hours"].tolist() == pytest.approx(
        [2 / 60, 10 / 60, 25 / 60]
    )
    assert np.isnan(result.frame.loc[0, "weight_kg"])
    assert result.frame.loc[0, "forecast_status"] == "unavailable"
    assert result.frame.loc[1, "forecast_status"] == "available"
    normalized = validate_snapshot(
        result.frame,
        result.frame["bin_id"],
        1500,
        now_utc=decision,
        stale_after_hours=0.25,
        offline_after_hours=1.0,
    )
    assert normalized["reading_age_hours"].nunique() == 3
    assert normalized["stale_flag"].tolist() == [False, False, True]


def test_unknown_contract_and_old_replay_are_not_accepted_as_current():
    payload = _payload()
    payload["schema_version"] = "99.0"
    with pytest.raises(ValueError, match="Unsupported telemetry schema_version"):
        normalize_telemetry_envelope(payload, _registry(), "physical-pilot")

    current = normalize_telemetry_envelope(_payload(), _registry(), "physical-pilot")
    prior = {row["bin_id"]: row for row in current.frame.to_dict(orient="records")}
    replay = _payload()
    replay["partial"] = True
    replay["events"] = [dict(replay["events"][0])]
    replay["events"][0]["event_id"] = "OLD-REPLAY"
    replay["events"][0]["observed_at"] = "2026-08-26T07:58:00Z"
    result = normalize_telemetry_envelope(
        replay,
        _registry(),
        "physical-pilot",
        previous_events=prior,
    )
    assert result.rejected_events[0]["reason"] == "older replay than retained event"
    assert result.frame.loc[0, "event_id"] != "OLD-REPLAY"


def test_recycling_fill_is_routable_but_recognition_events_are_rejected():
    payload = _payload()
    result = normalize_telemetry_envelope(payload, _registry(), "physical-pilot")
    assert result.frame["bin_type"].tolist() == [
        "general_waste",
        "recycling_return",
        "recycling_return",
    ]
    payload["events"][1]["event_kind"] = "recognition_result"
    with pytest.raises(ValueError, match="only event_kind 'fill_observation'"):
        normalize_telemetry_envelope(payload, _registry(), "physical-pilot")


class _Response:
    def __init__(self, status_code, payload=None):
        self.status_code = status_code
        self._payload = payload
        self.ok = 200 <= status_code < 300

    def json(self):
        return self._payload


class _Session:
    def __init__(self, response):
        self.response = response

    def get(self, *args, **kwargs):
        return self.response


class _FailingSession:
    def get(self, *args, **kwargs):
        raise requests.Timeout("fixture timeout")


def test_client_surfaces_authentication_and_temporary_failures():
    client = TelemetryClient(
        "https://telemetry.example",
        "test-key",
        session=_Session(_Response(401)),
    )
    with pytest.raises(TelemetryAuthenticationError):
        client.fetch_events()
    client = TelemetryClient(
        "https://telemetry.example",
        "test-key",
        session=_Session(_Response(503)),
    )
    with pytest.raises(TelemetryUnavailableError):
        client.fetch_events()
    client = TelemetryClient(
        "https://telemetry.example",
        "test-key",
        session=_FailingSession(),
    )
    with pytest.raises(TelemetryUnavailableError, match="timed out"):
        client.fetch_events()


def test_partial_fetch_stays_explicitly_incomplete():
    payload = _payload()
    payload["partial"] = True
    result = normalize_telemetry_envelope(payload, _registry(), "physical-pilot")
    assert not result.coverage_complete
    assert not result.frame["coverage_complete"].any()
