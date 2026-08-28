from __future__ import annotations

from dataclasses import dataclass
import ipaddress
from typing import Any
from urllib.parse import quote, urlparse

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
        parsed = urlparse(base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("Telemetry API URL must include an HTTP(S) scheme and host")
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("Telemetry API URL cannot embed credentials, query strings, or fragments")
        is_loopback = parsed.hostname.lower() == "localhost"
        if not is_loopback:
            try:
                is_loopback = ipaddress.ip_address(parsed.hostname).is_loopback
            except ValueError:
                is_loopback = False
        if parsed.scheme != "https" and not is_loopback:
            raise ValueError("Telemetry API must use HTTPS except for an exact loopback host")
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

    def fetch_pr2_history(self, source_bin_id: str, *, limit: int = 2000) -> list[dict[str, Any]]:
        """Read one PR #2 history without writing to the producer database."""
        if not source_bin_id.strip():
            raise ValueError("source_bin_id cannot be blank")
        if limit < 1 or limit > 2000:
            raise ValueError("PR #2 history limit must be in 1..2000")
        encoded = quote(source_bin_id, safe="")
        try:
            response = self.session.get(
                f"{self.base_url}/api/v1/telemetry/{encoded}/history",
                params={"limit": limit},
                headers={"X-API-Key": self.api_key, "Accept": "application/json"},
                timeout=self.timeout_seconds,
                verify=self.verify_tls,
            )
        except requests.Timeout as exc:
            raise TelemetryUnavailableError(
                f"PR #2 history request timed out for {source_bin_id}"
            ) from exc
        except requests.RequestException as exc:
            raise TelemetryUnavailableError(
                f"PR #2 history network failure for {source_bin_id}: {exc}"
            ) from exc
        if response.status_code in (401, 403):
            raise TelemetryAuthenticationError("PR #2 API rejected the configured credentials")
        if response.status_code == 404:
            return []
        if response.status_code == 503:
            raise TelemetryUnavailableError("PR #2 API is temporarily unavailable (HTTP 503)")
        if not response.ok:
            raise TelemetryUnavailableError(
                f"PR #2 history API returned HTTP {response.status_code} for {source_bin_id}"
            )
        try:
            payload = response.json()
        except ValueError as exc:
            raise TelemetryPayloadError("PR #2 history API did not return valid JSON") from exc
        if not isinstance(payload, dict) or not isinstance(payload.get("readings"), list):
            raise TelemetryPayloadError("PR #2 history response must contain a readings array")
        readings: list[dict[str, Any]] = []
        for position, raw in enumerate(payload["readings"]):
            if not isinstance(raw, dict):
                raise TelemetryPayloadError(
                    f"PR #2 history reading {position} for {source_bin_id} is not an object"
                )
            row = dict(raw)
            if str(row.get("bin_id") or "") != source_bin_id:
                raise TelemetryPayloadError(
                    f"PR #2 history for {source_bin_id} contained bin_id {row.get('bin_id')}"
                )
            readings.append(row)
        return readings

    def fetch_pr2_histories(
        self, source_bin_ids: list[str] | tuple[str, ...], *, limit: int = 2000
    ) -> list[dict[str, Any]]:
        readings: list[dict[str, Any]] = []
        for source_bin_id in source_bin_ids:
            readings.extend(self.fetch_pr2_history(source_bin_id, limit=limit))
        return readings
