"""SQLAlchemy ORM models — the storage layer for ingested telemetry."""
from sqlalchemy import Column, Integer, String, Float, DateTime, UniqueConstraint, Index
from sqlalchemy.sql import func

from .database import Base


class Reading(Base):
    """
    One row per (bin_id, timestamp) sensor reading, as received from the
    Teensy 4.1's Task 3 transmission handler.

    A unique constraint on (bin_id, timestamp) makes ingestion idempotent:
    if the MCU retries a send that actually succeeded (e.g. it never saw
    the response), the duplicate is absorbed rather than double-counted.
    """
    __tablename__ = "readings"

    id = Column(Integer, primary_key=True, index=True)

    timestamp = Column(DateTime(timezone=True), nullable=False)       # from the payload (sensor time)
    bin_id = Column(String(32), nullable=False, index=True)
    fill_pct = Column(Float, nullable=False)
    estimated_density = Column(Float, nullable=False)
    confidence_flag = Column(Integer, nullable=False)                  # 0 or 1

    ingested_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("bin_id", "timestamp", name="uq_bin_timestamp"),
        Index("ix_bin_timestamp", "bin_id", "timestamp"),
    )
