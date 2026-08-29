"""
Pydantic schemas — the validation boundary between the Teensy MCU and the
cloud service. The IngestionPayload model enforces the *exact* structure
specified for the edge-to-cloud contract:

    {
      "timestamp": "2026-08-19T19:31:45Z",
      "bin_id": "bin_01",
      "fill_pct": 75.5,
      "confidence_flag": 1
    }

[Removed 2026-08-28] estimated_density and estimated_weight_proxy are
both gone from the contract — the firmware no longer estimates either
(not just the manual button classification that used to feed the density
baseline). See hardware_pipeline/README.md's "Known changes" entry for
2026-08-28 for the full removal across firmware, schema, model, and
dashboard.

model_config below uses extra="forbid" — a Teensy still running OLDER
firmware that sends the now-removed fields will get a 422 from this
endpoint. Flash the updated firmware (this same change) before relying on
ingestion.
"""
from datetime import datetime
from typing import List, Literal

from pydantic import BaseModel, Field, field_validator, ConfigDict

from .config import get_settings

settings = get_settings()


class IngestionPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")  # reject unexpected fields outright

    timestamp: datetime = Field(..., description="ISO-8601 UTC timestamp of the sensor reading")
    bin_id: str = Field(..., pattern=settings.BIN_ID_PATTERN, description="e.g. 'bin_01'")
    fill_pct: float = Field(..., ge=settings.FILL_PCT_MIN, le=settings.FILL_PCT_MAX)
    confidence_flag: Literal[0, 1]
    # [Removed 2026-08-28] estimated_density and estimated_weight_proxy
    # fields — see module docstring above.

    @field_validator("timestamp")
    @classmethod
    def timestamp_must_be_timezone_aware(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError("timestamp must include timezone info (e.g. trailing 'Z')")
        return v


class ReadingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    timestamp: datetime
    bin_id: str
    fill_pct: float
    confidence_flag: int
    ingested_at: datetime


class IngestAck(BaseModel):
    status: Literal["stored", "duplicate_ignored"]
    reading: ReadingOut


class BinSummary(BaseModel):
    bin_id: str
    latest: ReadingOut
    reading_count: int
    low_confidence_count_last_20: int


class HealthOut(BaseModel):
    status: Literal["ok"]
    service: str = "binsight-cloud-backend"


class TelemetryHistory(BaseModel):
    bin_id: str
    count: int
    readings: List[ReadingOut]
