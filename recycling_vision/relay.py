"""Validated, image-free metadata contract for the dedicated ESP32-C3 relay."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
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
        if self.schema_version != 1:
            raise ValueError("unsupported schema_version")
        if self.material not in MATERIALS:
            raise ValueError("unknown material; fail closed")
        if self.sequence < 0 or self.object_count < 0 or self.inference_ms < 0:
            raise ValueError("sequence, object_count and inference_ms must be non-negative")
        if self.confidence is not None and not 0 <= self.confidence <= 1:
            raise ValueError("confidence must be between 0 and 1")

    def to_json(self) -> str:
        return json.dumps(asdict(self), separators=(",", ":"), sort_keys=True)

    @classmethod
    def from_json(cls, payload: str) -> "InferenceMetadata":
        data: dict[str, Any] = json.loads(payload)
        required = set(cls.__dataclass_fields__)
        if set(data) != required:
            raise ValueError("payload must contain exactly the relay metadata fields")
        return cls(**data)
