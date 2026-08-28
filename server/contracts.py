"""Version-one, image-free return API requests."""

from datetime import datetime, timezone
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictFloat, StrictInt, field_validator


Identifier = Annotated[str, Field(strict=True, min_length=1, max_length=80, pattern=r"^[A-Za-z0-9_.:-]+$")]


class Request(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)


class StartSession(Request):
    request_id: Identifier
    station_id: Identifier


class Action(Request):
    request_id: Identifier


class StationReady(Action):
    device_id: Identifier
    boot_id: Identifier
    after_inspection_id: Identifier | None = None
    empty: StrictBool
    is_simulation: StrictBool


class Inference(Request):
    schema_version: StrictInt
    event_id: Identifier
    station_id: Identifier
    device_id: Identifier
    boot_id: Identifier
    sequence: Annotated[StrictInt, Field(ge=0, le=2**53 - 1)]
    session_id: Identifier
    inspection_id: Identifier
    observed_at: Annotated[str, Field(min_length=1, max_length=64)]
    source: Literal["grove-vision-ai-v2"]
    model_version: Identifier
    material: Literal["plastic", "metal", "glass", "paper", "other"]
    confidence: Annotated[StrictFloat, Field(ge=0, le=1)] | None
    object_count: Annotated[StrictInt, Field(ge=0, le=100)]
    inference_ms: Annotated[StrictInt, Field(ge=0, le=5000)]
    is_simulation: StrictBool

    @field_validator("schema_version")
    @classmethod
    def version_one(cls, value):
        if value != 1:
            raise ValueError("unsupported schema version")
        return value

    @field_validator("observed_at")
    @classmethod
    def aware_time(cls, value):
        instant = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if instant.tzinfo is None or instant.utcoffset() is None:
            raise ValueError("observed_at must include a timezone")
        return instant.astimezone(timezone.utc).isoformat()
