"""
Central settings for the BinSight cloud ingestion service.

Reads from environment variables (with sane local-dev defaults) so the same
code runs unmodified whether it's launched on a laptop for the competition
demo or deployed behind a real environment-variable-configured host.
"""
import os
from functools import lru_cache


class Settings:
    # Device authentication — the Teensy firmware sends this in X-API-Key.
    API_KEY: str = os.getenv("BINSIGHT_API_KEY", "REPLACE_WITH_PROVISIONED_DEVICE_KEY")

    # Shared secret for HMAC-SHA256 payload signing (X-Signature header).
    # Set BINSIGHT_REQUIRE_HMAC=false to disable signature verification
    # during early bring-up/demo if the firmware side isn't wired up yet.
    HMAC_SHARED_SECRET: str = os.getenv("BINSIGHT_HMAC_SECRET", "REPLACE_WITH_SHARED_HMAC_SECRET")
    REQUIRE_HMAC: bool = os.getenv("BINSIGHT_REQUIRE_HMAC", "false").lower() == "true"

    # Storage
    DATABASE_URL: str = os.getenv("BINSIGHT_DATABASE_URL", "sqlite:///./binsight.db")

    # Validation bounds
    FILL_PCT_MIN: float = 0.0
    FILL_PCT_MAX: float = 100.0
    DENSITY_MIN: float = 0.0
    DENSITY_MAX: float = 50.0  # generous upper bound for the pseudo-density proxy

    # CORS — permissive for the local Streamlit dashboard during the
    # competition demo. Tighten to explicit origins for a real deployment.
    CORS_ALLOW_ORIGINS: list = ["*"]

    # Bin ID pattern enforced in schemas.py
    BIN_ID_PATTERN: str = r"^bin_[0-9]{2,}$"


@lru_cache
def get_settings() -> Settings:
    return Settings()
