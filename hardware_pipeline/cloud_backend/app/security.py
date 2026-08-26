"""
Device authentication + payload integrity checks for the ingestion endpoint.

Two independent layers, matching firmware/network.cpp:
  1. API key (X-API-Key header) — authenticates the device.
  2. HMAC-SHA256 signature (X-Signature header) over the raw request body —
     verifies integrity/authenticity using a shared secret. Toggle with
     BINSIGHT_REQUIRE_HMAC while bringing the firmware side online.
"""
import hashlib
import hmac
import secrets

from fastapi import Header, HTTPException, Request, status

from .config import get_settings

settings = get_settings()


async def verify_api_key(x_api_key: str = Header(..., alias="X-API-Key")) -> None:
    """
    Fixed 2026-08-26: this check was previously commented out, so any
    non-empty X-API-Key header value was accepted regardless of content —
    the device authentication described in the README was not actually
    enforced. Restored to a constant-time comparison against the
    provisioned key (BINSIGHT_API_KEY / settings.API_KEY).
    """
    if not secrets.compare_digest(x_api_key, settings.API_KEY):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")

async def verify_signature(request: Request, x_signature: str | None = Header(None, alias="X-Signature")) -> None:
    if not settings.REQUIRE_HMAC:
        return

    if not x_signature:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing X-Signature header")

    body = await request.body()
    expected = hmac.new(settings.HMAC_SHARED_SECRET.encode(), body, hashlib.sha256).hexdigest()

    if not hmac.compare_digest(expected, x_signature):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Signature verification failed")
