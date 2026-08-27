"""Generate deterministic acceptance evidence for the PR #2 forecast adapter.

This fixture is intentionally synthetic. It exercises normal, scheduled-event,
sparse-history, sensor-failure, and distribution-drift regimes without claiming
field performance from hardware data that PR #2 does not yet retain long enough.
"""

from __future__ import annotations

import json
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from binsight.pr2_forecasting import PR2ForecastConfig, rolling_origin_backtest


ROOT = Path(__file__).resolve().parents[1]
START = datetime(2025, 1, 1, tzinfo=timezone.utc)
TOTAL_DAYS = 156
ORIGIN_DAYS = (105, 120, 135, 148)
EVENT_BIN_IDS = tuple(f"UGB-{index:03d}" for index in range(4, 9))


def _events() -> list[dict]:
    events: list[dict] = []
    for number, day in enumerate(ORIGIN_DAYS, start=1):
        origin = START + timedelta(days=day, minutes=1)
        events.append(
            {
                "event_id": f"fixture-market-{number}",
                "event_type": "market",
                "known_at": (origin - timedelta(days=7)).isoformat(),
                "start_at": (origin + timedelta(hours=6)).isoformat(),
                "end_at": (origin + timedelta(hours=36)).isoformat(),
                "affected_bin_ids": list(EVENT_BIN_IDS),
                "proximity_km_by_bin": {
                    bin_id: 0.2 + 0.15 * offset
                    for offset, bin_id in enumerate(EVENT_BIN_IDS)
                },
                "intensity": 1.5,
                "expected_attendance": 900,
                "data_quality": 0.9,
            }
        )
    return events


def _event_active(bin_id: str, when: datetime, events: list[dict]) -> bool:
    return any(
        bin_id in event["affected_bin_ids"]
        and datetime.fromisoformat(event["start_at"]) <= when <= datetime.fromisoformat(event["end_at"])
        for event in events
    )


def build_fixture() -> tuple[list[dict], list[dict]]:
    events = _events()
    readings: list[dict] = []
    for index in range(1, 34):
        source_id = f"bin_{index:02d}"
        canonical_id = f"UGB-{index:03d}"
        sparse = index in {26, 27, 28}
        sensor_failure = index in {29, 30}
        drift = index in {31, 32, 33}
        first_step = 103 * 4 if sparse else 0
        fill = 7.0 + index % 6
        for step in range(first_step, TOTAL_DAYS * 4 + 1):
            when = START + timedelta(hours=step * 6)
            if fill >= 100.0:
                fill = 7.0 + index % 5
            else:
                base_rate = 0.105 + 0.012 * (index % 7)
                hour_factor = 1.35 if when.hour in (12, 18) else 0.75
                weekday_factor = 1.25 if when.weekday() in (4, 5) else 0.95
                monthly_factor = 1.0 + 0.08 * math.sin(2 * math.pi * when.timetuple().tm_yday / 30.5)
                event_factor = 1.75 if _event_active(canonical_id, when, events) else 1.0
                drift_factor = 2.8 if drift and when >= START + timedelta(days=128) else 1.0
                deterministic_noise = 0.08 * math.sin(step * 0.7 + index)
                increment = max(
                    0.02,
                    6.0
                    * base_rate
                    * hour_factor
                    * weekday_factor
                    * monthly_factor
                    * event_factor
                    * drift_factor
                    + deterministic_noise,
                )
                fill = min(100.0, fill + increment)
            confidence = not (
                sensor_failure and when >= START + timedelta(days=100)
            )
            observed_fill = fill
            if not confidence:
                observed_fill = min(
                    100.0,
                    max(0.0, fill + 2.5 * math.sin(step * 1.9 + index)),
                )
            readings.append(
                {
                    "timestamp": when.isoformat(),
                    "bin_id": source_id,
                    "fill_pct": round(observed_fill, 6),
                    "estimated_density": round(1.0 + (index % 9) * 0.23, 6),
                    "confidence_flag": int(confidence),
                    "ingested_at": (when + timedelta(seconds=2 + index % 4)).isoformat(),
                }
            )
    return readings, events


def main() -> None:
    config = PR2ForecastConfig.load(ROOT / "config" / "pr2_forecasting.json")
    bins = pd.read_csv(ROOT / "artifacts" / "district_bins.csv").iloc[:33].copy()
    readings, events = build_fixture()
    evaluation = rolling_origin_backtest(
        config,
        bins,
        "competition-simulation",
        readings,
        [START + timedelta(days=day, minutes=1) for day in ORIGIN_DAYS],
        events=events,
    )
    evidence = {
        "evidence_scope": "deterministic synthetic acceptance fixture; not field validation",
        "fixture": {
            "configured_bins": 33,
            "readings": len(readings),
            "start": START.isoformat(),
            "end": (START + timedelta(days=TOTAL_DAYS)).isoformat(),
            "origin_days": list(ORIGIN_DAYS),
            "regimes_injected": [
                "normal",
                "event",
                "sparse_history",
                "sensor_failure",
                "distribution_drift",
            ],
        },
        "evaluation": evaluation,
    }
    output = ROOT / "artifacts" / "pr2_forecast_adapter_evaluation.json"
    output.write_text(json.dumps(evidence, indent=2, allow_nan=False), encoding="utf-8")
    print(output)
    print(json.dumps(evaluation["overall"], indent=2, allow_nan=False))
    print("regimes:", ", ".join(evaluation["by_regime"]))


if __name__ == "__main__":
    main()
