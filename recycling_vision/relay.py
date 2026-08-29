"""Validated, image-free metadata contract for the dedicated ESP32-C3 relay."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from math import isfinite
from typing import Any

MATERIALS = frozenset({"plastic", "metal", "glass", "paper", "other"})


@dataclass(frozen=True)
class InferenceMetadata:
    schema_version: int
    event_id: str
    station_id: str
    device_id: str
    boot_id: str
    sequence: int
    session_id: str
    inspection_id: str
    observed_at: str
    source: str
    model_version: str
    material: str
    confidence: float | None
    object_count: int
    inference_ms: int
    is_simulation: bool

    def __post_init__(self) -> None:
        if type(self.schema_version) is not int or self.schema_version != 1:
            raise ValueError("unsupported schema_version")
        for field_name in ("event_id", "station_id", "device_id", "boot_id", "session_id",
                           "inspection_id", "observed_at", "source", "model_version"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field_name} must be a non-empty string")
        try:
            timestamp = datetime.fromisoformat(self.observed_at.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("observed_at must be an ISO-8601 timestamp") from exc
        if timestamp.tzinfo is None or timestamp.utcoffset() is None:
            raise ValueError("observed_at must include a timezone")
        if self.material not in MATERIALS:
            raise ValueError("unknown material; fail closed")
        if type(self.sequence) is not int or type(self.object_count) is not int or type(self.inference_ms) is not int:
            raise ValueError("sequence, object_count and inference_ms must be integers")
        if self.sequence < 0 or self.object_count < 0 or self.inference_ms < 0:
            raise ValueError("sequence, object_count and inference_ms must be non-negative")
        if self.confidence is not None and (
            isinstance(self.confidence, bool)
            or not isinstance(self.confidence, (int, float))
            or not isfinite(self.confidence)
            or not 0 <= self.confidence <= 1
        ):
            raise ValueError("confidence must be between 0 and 1")
        if type(self.is_simulation) is not bool:
            raise ValueError("is_simulation must be a boolean")

    def to_json(self) -> str:
        return json.dumps(asdict(self), separators=(",", ":"), sort_keys=True)

    @classmethod
    def from_json(cls, payload: str) -> "InferenceMetadata":
        data: dict[str, Any] = json.loads(payload)
        required = set(cls.__dataclass_fields__)
        if set(data) != required:
            raise ValueError("payload must contain exactly the relay metadata fields")
        return cls(**data)
