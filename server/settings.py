"""Explicit credentials for isolated, fictional-account integration tests."""

from dataclasses import dataclass
import json
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    database: Path
    citizen_tokens: dict[str, str]
    device_token: str
    station_id: str = "RRS-001"
    device_id: str = "shared-gateway-01"
    session_seconds: int = 1200

    def __post_init__(self):
        from .contracts import StartSession

        StartSession(request_id=self.device_id, station_id=self.station_id)
        if not self.citizen_tokens or not 10 <= self.session_seconds <= 3600:
            raise ValueError("Provide fictional accounts and a 10-3600 second session lifetime")
        for citizen in self.citizen_tokens:
            StartSession(request_id=citizen, station_id=self.station_id)
            if citizen.startswith("device:"):
                raise ValueError("Citizen IDs cannot use the device action namespace")
        tokens = [self.device_token, *self.citizen_tokens.values()]
        if any(not isinstance(token, str) or len(token) < 32 or not token.isascii() for token in tokens):
            raise ValueError("Use distinct ASCII tokens of at least 32 characters")
        if len(set(tokens)) != len(tokens):
            raise ValueError("Citizen and device tokens must be distinct")

    @classmethod
    def from_file(cls, path: Path):
        raw = json.loads(path.read_text(encoding="utf-8"))
        raw["database"] = (path.resolve().parent / raw["database"]).resolve()
        return cls(**raw)
