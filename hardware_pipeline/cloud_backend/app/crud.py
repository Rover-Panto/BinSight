"""Database access functions — kept separate from the route handlers in main.py."""
from sqlalchemy import func
from sqlalchemy.orm import Session

from . import models, schemas


def create_reading(db: Session, payload: schemas.IngestionPayload) -> tuple[models.Reading, bool]:
    """
    Inserts a reading. Returns (row, was_newly_created).

    If a row with the same (bin_id, timestamp) already exists (the MCU
    retried a send that actually succeeded), the existing row is returned
    instead of raising — ingestion is idempotent by design.
    """
    existing = (
        db.query(models.Reading)
        .filter(models.Reading.bin_id == payload.bin_id, models.Reading.timestamp == payload.timestamp)
        .first()
    )
    if existing:
        return existing, False

    row = models.Reading(
        timestamp=payload.timestamp,
        bin_id=payload.bin_id,
        fill_pct=payload.fill_pct,
        confidence_flag=payload.confidence_flag,
        # [Removed 2026-08-28] estimated_density / estimated_weight_proxy
        # — both fields are gone from the payload and the model.
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row, True


def get_latest_for_bin(db: Session, bin_id: str) -> models.Reading | None:
    return (
        db.query(models.Reading)
        .filter(models.Reading.bin_id == bin_id)
        .order_by(models.Reading.timestamp.desc())
        .first()
    )


def get_history_for_bin(db: Session, bin_id: str, limit: int = 200) -> list[models.Reading]:
    return (
        db.query(models.Reading)
        .filter(models.Reading.bin_id == bin_id)
        .order_by(models.Reading.timestamp.desc())
        .limit(limit)
        .all()[::-1]  # chronological order for charting
    )


def list_distinct_bin_ids(db: Session) -> list[str]:
    rows = db.query(models.Reading.bin_id).distinct().all()
    return sorted(r[0] for r in rows)


def count_readings_for_bin(db: Session, bin_id: str) -> int:
    return db.query(func.count(models.Reading.id)).filter(models.Reading.bin_id == bin_id).scalar() or 0


def count_low_confidence_recent(db: Session, bin_id: str, window: int = 20) -> int:
    recent = (
        db.query(models.Reading.confidence_flag)
        .filter(models.Reading.bin_id == bin_id)
        .order_by(models.Reading.timestamp.desc())
        .limit(window)
        .all()
    )
    return sum(1 for (flag,) in recent if flag == 0)
