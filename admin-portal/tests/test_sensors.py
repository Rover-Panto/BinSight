import json
from pathlib import Path

import pytest

from binsight.sensors import SensorStore, fuse_channel, load_calibrations, validate_controller_payload


ROOT = Path(__file__).resolve().parents[1]


def _payload():
    return json.loads((ROOT / "hardware" / "example_payload.json").read_text(encoding="utf-8"))


def test_three_channel_payload_and_conservative_fusion():
    clean = validate_controller_payload(_payload())
    calibrations = load_calibrations(ROOT / "hardware" / "controller_calibration.example.json")
    reading = fuse_channel(clean, clean["bins"][0], calibrations["UGB-001"])
    assert reading.ultrasonic_fill_pct == pytest.approx(56.4103, rel=1e-4)
    assert reading.pressure_fill_pct == pytest.approx(51.6667, rel=1e-4)
    assert reading.fill_pct == reading.ultrasonic_fill_pct
    assert 0 < reading.sensor_confidence <= 1


def test_payload_requires_exactly_three_unique_channels():
    payload = _payload()
    payload["bins"] = payload["bins"][:2]
    with pytest.raises(ValueError, match="exactly three"):
        validate_controller_payload(payload)


def test_store_deduplicates_and_exports_model_schema(tmp_path):
    calibrations = load_calibrations(ROOT / "hardware" / "controller_calibration.example.json")
    store = SensorStore(tmp_path / "readings.sqlite3", calibrations)
    try:
        first = store.ingest(_payload())
        duplicate = store.ingest(_payload())
        assert len(first) == 3
        assert len(duplicate) == 3
        count = store.connection.execute("SELECT COUNT(*) FROM sensor_readings").fetchone()[0]
        assert count == 3
        output = tmp_path / "model.csv"
        store.export_model_csv(output)
        assert output.read_text(encoding="utf-8").splitlines()[0] == (
            "timestamp_utc,bin_id,fill_pct,weight_kg,sensor_confidence,collected_flag"
        )
    finally:
        store.close()
