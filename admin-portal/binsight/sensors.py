from __future__ import annotations

import json
import math
import re
import sqlite3
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "1.1"
LEGACY_SCHEMA_VERSION = "1.0"
IDENTIFIER = re.compile(r"^[A-Z0-9][A-Z0-9_-]{2,31}$")


@dataclass(frozen=True)
class ChannelCalibration:
    bin_id: str
    controller_channel: int
    bin_capacity_kg: float
    ultrasonic_empty_distance_mm: float
    ultrasonic_full_distance_mm: float
    pressure_tare_adc: float
    pressure_full_adc: float
    pressure_full_scale_kg: float


@dataclass(frozen=True)
class FusedBinReading:
    captured_at_utc: str
    controller_id: str
    sequence: int
    boot_id: str
    event_id: str
    bin_id: str
    controller_channel: int
    ultrasonic_fill_pct: float | None
    pressure_fill_pct: float | None
    fill_pct: float
    weight_kg: float | None
    sensor_confidence: float
    collected_flag: bool
    flags: tuple[str, ...]


@dataclass(frozen=True)
class IngestReceipt:
    reading: FusedBinReading
    inserted: bool
    status: str

    @property
    def event_id(self) -> str:
        return self.reading.event_id


def load_calibrations(path: str | Path) -> dict[str, ChannelCalibration]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    channels = payload.get("channels")
    if not isinstance(channels, list) or len(channels) != 3:
        raise ValueError("Calibration must define exactly three controller channels")
    calibrations = {row["bin_id"]: ChannelCalibration(**row) for row in channels}
    if len(calibrations) != 3:
        raise ValueError("Calibration bin IDs must be unique")
    for item in calibrations.values():
        if item.controller_channel not in (1, 2, 3):
            raise ValueError("Controller channels must be 1, 2, and 3")
        if item.ultrasonic_empty_distance_mm <= item.ultrasonic_full_distance_mm:
            raise ValueError("Ultrasonic empty distance must exceed full distance")
        if item.pressure_full_adc <= item.pressure_tare_adc:
            raise ValueError("Pressure full ADC must exceed the tare ADC")
        if item.bin_capacity_kg <= 0 or item.pressure_full_scale_kg <= 0:
            raise ValueError("Calibration mass values must be positive")
    if {item.controller_channel for item in calibrations.values()} != {1, 2, 3}:
        raise ValueError("Calibration must cover controller channels 1, 2, and 3")
    return calibrations


def _optional_number(value: Any, name: str, low: float, high: float) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be numeric or null")
    number = float(value)
    if not math.isfinite(number) or not low <= number <= high:
        raise ValueError(f"{name} is outside the accepted range")
    return number


def validate_controller_payload(payload: dict[str, Any]) -> dict[str, Any]:
    required = {
        "schema_version",
        "controller_id",
        "sequence",
        "captured_at_utc",
        "firmware_version",
        "bins",
    }
    if not isinstance(payload, dict) or not required.issubset(payload):
        raise ValueError("Controller payload is missing required fields")
    if payload["schema_version"] not in {SCHEMA_VERSION, LEGACY_SCHEMA_VERSION}:
        raise ValueError(f"Unsupported schema_version: {payload['schema_version']}")
    if not isinstance(payload["controller_id"], str) or not IDENTIFIER.fullmatch(
        payload["controller_id"]
    ):
        raise ValueError("controller_id has an invalid format")
    if isinstance(payload["sequence"], bool) or not isinstance(payload["sequence"], int):
        raise ValueError("sequence must be an integer")
    if payload["sequence"] < 0:
        raise ValueError("sequence must be non-negative")
    if payload["schema_version"] == SCHEMA_VERSION:
        boot_id = payload.get("boot_id")
        if not isinstance(boot_id, str) or not IDENTIFIER.fullmatch(boot_id):
            raise ValueError("boot_id is required and must use the accepted identifier format")
    else:
        boot_id = "LEGACY-UNSCOPED"
    timestamp = datetime.fromisoformat(str(payload["captured_at_utc"]).replace("Z", "+00:00"))
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise ValueError("captured_at_utc must include a timezone")
    bins = payload["bins"]
    if not isinstance(bins, list) or len(bins) != 3:
        raise ValueError("One controller payload must contain exactly three bins")
    channels: set[int] = set()
    bin_ids: set[str] = set()
    cleaned_bins = []
    for row in bins:
        if not isinstance(row, dict):
            raise ValueError("Each bin reading must be an object")
        channel = row.get("channel")
        bin_id = row.get("bin_id")
        if channel not in (1, 2, 3) or channel in channels:
            raise ValueError("Bin channels must be unique values 1, 2, and 3")
        if not isinstance(bin_id, str) or not IDENTIFIER.fullmatch(bin_id) or bin_id in bin_ids:
            raise ValueError("bin_id must be unique and use the accepted identifier format")
        pressure = _optional_number(row.get("pressure_adc"), "pressure_adc", 0, 4095)
        ultrasonic = _optional_number(
            row.get("ultrasonic_distance_mm"), "ultrasonic_distance_mm", 20, 10_000
        )
        if pressure is None and ultrasonic is None:
            raise ValueError(f"{bin_id} has no usable pressure or ultrasonic reading")
        cleaned_bins.append(
            {
                "channel": channel,
                "bin_id": bin_id,
                "pressure_adc": pressure,
                "ultrasonic_distance_mm": ultrasonic,
            }
        )
        channels.add(channel)
        bin_ids.add(bin_id)
    return dict(payload) | {
        "schema_version": SCHEMA_VERSION,
        "boot_id": boot_id,
        "captured_at_utc": timestamp.astimezone(timezone.utc).isoformat(),
        "bins": cleaned_bins,
        "legacy_identity": payload["schema_version"] == LEGACY_SCHEMA_VERSION,
    }


def fuse_channel(
    payload: dict[str, Any],
    row: dict[str, Any],
    calibration: ChannelCalibration,
    previous_fill_pct: float | None = None,
) -> FusedBinReading:
    if row["channel"] != calibration.controller_channel or row["bin_id"] != calibration.bin_id:
        raise ValueError("Telemetry channel/bin mapping does not match calibration")
    flags: list[str] = []
    distance = row["ultrasonic_distance_mm"]
    pressure_adc = row["pressure_adc"]
    ultrasonic_fill: float | None = None
    pressure_fill: float | None = None
    weight_kg: float | None = None

    if distance is not None:
        span = calibration.ultrasonic_empty_distance_mm - calibration.ultrasonic_full_distance_mm
        raw_fill = 100.0 * (calibration.ultrasonic_empty_distance_mm - distance) / span
        if raw_fill < -10 or raw_fill > 120:
            flags.append("ultrasonic_out_of_calibrated_range")
        ultrasonic_fill = min(100.0, max(0.0, raw_fill))
    if pressure_adc is not None:
        adc_span = calibration.pressure_full_adc - calibration.pressure_tare_adc
        weight_kg = max(
            0.0,
            (pressure_adc - calibration.pressure_tare_adc)
            / adc_span
            * calibration.pressure_full_scale_kg,
        )
        pressure_fill = min(100.0, max(0.0, 100.0 * weight_kg / calibration.bin_capacity_kg))
        if pressure_adc < calibration.pressure_tare_adc - 100:
            flags.append("pressure_below_tare")
        if weight_kg > calibration.bin_capacity_kg * 1.15:
            flags.append("pressure_over_capacity")

    available = [value for value in (ultrasonic_fill, pressure_fill) if value is not None]
    if not available:
        raise ValueError("No calibrated sensor estimate is available")
    # Routing uses the conservative estimate; both independent estimates are retained.
    fill_pct = max(available)
    if len(available) == 2:
        disagreement = abs(available[0] - available[1])
        confidence = max(0.2, 1.0 - disagreement / 60.0)
        if disagreement > 20:
            flags.append("sensor_disagreement_over_20pct")
    else:
        confidence = 0.55
        flags.append("single_sensor_fallback")
    collected = bool(
        previous_fill_pct is not None
        and previous_fill_pct - fill_pct >= 35
        and fill_pct <= 35
    )
    return FusedBinReading(
        captured_at_utc=str(payload["captured_at_utc"]),
        controller_id=str(payload["controller_id"]),
        sequence=int(payload["sequence"]),
        boot_id=str(payload["boot_id"]),
        event_id=(
            f"{payload['controller_id']}:{payload['boot_id']}:"
            f"{payload['sequence']}:{calibration.bin_id}"
        ),
        bin_id=calibration.bin_id,
        controller_channel=calibration.controller_channel,
        ultrasonic_fill_pct=ultrasonic_fill,
        pressure_fill_pct=pressure_fill,
        fill_pct=fill_pct,
        weight_kg=weight_kg,
        sensor_confidence=confidence,
        collected_flag=collected,
        flags=tuple(flags),
    )


class SensorStore:
    def __init__(self, database_path: str | Path, calibrations: dict[str, ChannelCalibration]):
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.calibrations = calibrations
        self.connection = sqlite3.connect(self.database_path)
        self._ensure_schema()

    def _create_current_table(self) -> None:
        self.connection.execute(
            """
            CREATE TABLE IF NOT EXISTS sensor_readings (
                event_id TEXT NOT NULL PRIMARY KEY,
                captured_at_utc TEXT NOT NULL,
                controller_id TEXT NOT NULL,
                boot_id TEXT NOT NULL,
                sequence INTEGER NOT NULL,
                bin_id TEXT NOT NULL,
                controller_channel INTEGER NOT NULL,
                ultrasonic_fill_pct REAL,
                pressure_fill_pct REAL,
                fill_pct REAL NOT NULL,
                weight_kg REAL,
                sensor_confidence REAL NOT NULL,
                collected_flag INTEGER NOT NULL,
                flags_json TEXT NOT NULL,
                UNIQUE (controller_id, boot_id, sequence, bin_id)
            )
            """
        )

    def _ensure_schema(self) -> None:
        exists = self.connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='sensor_readings'"
        ).fetchone()
        if not exists:
            self._create_current_table()
            self.connection.commit()
            return
        columns = {
            row[1] for row in self.connection.execute("PRAGMA table_info(sensor_readings)")
        }
        if {"event_id", "boot_id"}.issubset(columns):
            return
        archive_name = "sensor_readings_legacy_v1"
        if self.connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (archive_name,)
        ).fetchone():
            raise RuntimeError(
                "Cannot migrate sensor_readings: preserved legacy archive already exists"
            )
        with self.connection:
            self.connection.execute(
                f"ALTER TABLE sensor_readings RENAME TO {archive_name}"
            )
            self._create_current_table()
            self.connection.execute(
                f"""
                INSERT OR IGNORE INTO sensor_readings (
                    event_id, captured_at_utc, controller_id, boot_id, sequence,
                    bin_id, controller_channel, ultrasonic_fill_pct,
                    pressure_fill_pct, fill_pct, weight_kg, sensor_confidence,
                    collected_flag, flags_json
                )
                SELECT controller_id || ':LEGACY-UNSCOPED:' || sequence || ':' || bin_id,
                       captured_at_utc, controller_id, 'LEGACY-UNSCOPED', sequence,
                       bin_id, controller_channel, ultrasonic_fill_pct,
                       pressure_fill_pct, fill_pct, weight_kg, sensor_confidence,
                       collected_flag, flags_json
                FROM {archive_name}
                """
            )
        self.connection.commit()

    def close(self) -> None:
        self.connection.close()

    def _previous_fill(self, bin_id: str) -> float | None:
        row = self.connection.execute(
            "SELECT fill_pct FROM sensor_readings WHERE bin_id = ? "
            "ORDER BY captured_at_utc DESC LIMIT 1",
            (bin_id,),
        ).fetchone()
        return float(row[0]) if row else None

    def ingest(self, payload: dict[str, Any]) -> list[IngestReceipt]:
        clean = validate_controller_payload(payload)
        receipts: list[IngestReceipt] = []
        for row in clean["bins"]:
            calibration = self.calibrations.get(row["bin_id"])
            if calibration is None:
                raise ValueError(f"No calibration exists for {row['bin_id']}")
            reading = fuse_channel(clean, row, calibration, self._previous_fill(row["bin_id"]))
            cursor = self.connection.execute(
                "INSERT OR IGNORE INTO sensor_readings VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    reading.event_id,
                    reading.captured_at_utc,
                    reading.controller_id,
                    reading.boot_id,
                    reading.sequence,
                    reading.bin_id,
                    reading.controller_channel,
                    reading.ultrasonic_fill_pct,
                    reading.pressure_fill_pct,
                    reading.fill_pct,
                    reading.weight_kg,
                    reading.sensor_confidence,
                    int(reading.collected_flag),
                    json.dumps(reading.flags),
                ),
            )
            inserted = cursor.rowcount == 1
            receipts.append(
                IngestReceipt(
                    reading=reading,
                    inserted=inserted,
                    status="stored" if inserted else "duplicate_already_stored",
                )
            )
        self.connection.commit()
        return receipts

    def export_model_csv(self, path: str | Path) -> None:
        output = Path(path)
        output.parent.mkdir(parents=True, exist_ok=True)
        rows = self.connection.execute(
            "SELECT captured_at_utc, event_id, bin_id, fill_pct, weight_kg, sensor_confidence, "
            "collected_flag FROM sensor_readings ORDER BY captured_at_utc, event_id"
        ).fetchall()
        import csv

        with output.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(
                [
                    "timestamp_utc",
                    "event_id",
                    "bin_id",
                    "fill_pct",
                    "weight_kg",
                    "sensor_confidence",
                    "collected_flag",
                ]
            )
            writer.writerows(rows)


def reading_to_dict(reading: FusedBinReading | IngestReceipt) -> dict[str, Any]:
    if isinstance(reading, IngestReceipt):
        return asdict(reading.reading) | {
            "inserted": reading.inserted,
            "storage_status": reading.status,
        }
    return asdict(reading)
