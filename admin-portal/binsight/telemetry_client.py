from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import requests


class TelemetryClientError(RuntimeError):
    """Base class for visible telemetry-source failures."""


class TelemetryAuthenticationError(TelemetryClientError):
    pass


class TelemetryUnavailableError(TelemetryClientError):
    pass


class TelemetryPayloadError(TelemetryClientError):
    pass


@dataclass(frozen=True)
class TelemetryResponse:
    payload: dict[str, Any]
    cursor: str | None
    partial: bool


class TelemetryClient:
    """Small read-only client for the producer-owned telemetry API."""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        *,
        timeout_seconds: float = 5.0,
        verify_tls: bool = True,
        session: requests.Session | None = None,
    ) -> None:
        if not base_url.lower().startswith(("https://", "http://127.0.0.1", "http://localhost")):
            raise ValueError("Telemetry API must use HTTPS except for an explicit local host")
        if not api_key or api_key.lower().startswith(("change", "placeholder")):
            raise ValueError("A non-placeholder telemetry API key is required")
        if timeout_seconds <= 0 or timeout_seconds > 60:
            raise ValueError("timeout_seconds must be in (0, 60]")
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout_seconds = float(timeout_seconds)
        self.verify_tls = bool(verify_tls)
        self.session = session or requests.Session()

    def fetch_events(self, cursor: str | None = None) -> TelemetryResponse:
        params = {"cursor": cursor} if cursor else None
        try:
            response = self.session.get(
                f"{self.base_url}/api/v1/telemetry",
                params=params,
                headers={"X-API-Key": self.api_key, "Accept": "application/json"},
                timeout=self.timeout_seconds,
                verify=self.verify_tls,
            )
        except requests.Timeout as exc:
            raise TelemetryUnavailableError("Telemetry request timed out") from exc
        except requests.RequestException as exc:
            raise TelemetryUnavailableError(f"Telemetry network failure: {exc}") from exc
        if response.status_code in (401, 403):
            raise TelemetryAuthenticationError("Telemetry API rejected the configured credentials")
        if response.status_code == 503:
            raise TelemetryUnavailableError("Telemetry API is temporarily unavailable (HTTP 503)")
        if not response.ok:
            raise TelemetryUnavailableError(f"Telemetry API returned HTTP {response.status_code}")
        try:
            payload = response.json()
        except ValueError as exc:
            raise TelemetryPayloadError("Telemetry API did not return valid JSON") from exc
        if not isinstance(payload, dict):
            raise TelemetryPayloadError("Telemetry API response must be a JSON object")
        return TelemetryResponse(
            payload=payload,
            cursor=(str(payload["next_cursor"]) if payload.get("next_cursor") is not None else None),
            partial=bool(payload.get("partial", False)),
        )

