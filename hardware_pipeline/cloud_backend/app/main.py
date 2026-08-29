"""
BinSight Cloud Data Center — ingestion & validation service (FastAPI).

Scope (per the current phase of the project): intake, validate, and store
telemetry from the Teensy 4.1 edge device. No ML inference happens here yet
— that's a future cloud-hosted model that will read from this same store.

Run locally:
    pip install -r requirements.txt
    uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

Interactive API docs: http://localhost:8000/docs
"""
from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from . import crud, schemas
from .config import get_settings
from .database import Base, engine, get_db
from .security import verify_api_key, verify_signature

settings = get_settings()

# Creates binsight.db / tables on first run. For anything beyond a demo,
# swap this for an Alembic migration.
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="BinSight Cloud Data Center",
    description="Ingestion & validation backend for BinSight smart-bin telemetry.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ALLOW_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", response_model=schemas.HealthOut, tags=["ops"])
def health():
    return schemas.HealthOut(status="ok")


@app.post(
    "/api/v1/telemetry",
    response_model=schemas.IngestAck,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(verify_api_key), Depends(verify_signature)],
    tags=["ingestion"],
)
def ingest_telemetry(payload: schemas.IngestionPayload, db: Session = Depends(get_db)):
    """
    Primary ingestion endpoint — this is what Task 3 on the Teensy POSTs to.
    Pydantic has already validated the payload shape/ranges by the time this
    body runs (malformed payloads never reach here — FastAPI returns 422
    automatically). This handler only does storage + idempotency.
    """
    row, created = crud.create_reading(db, payload)
    return schemas.IngestAck(
        status="stored" if created else "duplicate_ignored",
        reading=schemas.ReadingOut.model_validate(row),
    )


@app.get("/api/v1/bins", response_model=list[str], tags=["query"])
def list_bins(db: Session = Depends(get_db)):
    return crud.list_distinct_bin_ids(db)


@app.get("/api/v1/bins/summary", response_model=list[schemas.BinSummary], tags=["query"])
def bin_summaries(db: Session = Depends(get_db)):
    """Convenience endpoint for the dashboard — one row per bin with the latest reading + stats."""
    summaries = []
    for bin_id in crud.list_distinct_bin_ids(db):
        latest = crud.get_latest_for_bin(db, bin_id)
        if latest is None:
            continue
        summaries.append(
            schemas.BinSummary(
                bin_id=bin_id,
                latest=schemas.ReadingOut.model_validate(latest),
                reading_count=crud.count_readings_for_bin(db, bin_id),
                low_confidence_count_last_20=crud.count_low_confidence_recent(db, bin_id),
            )
        )
    return summaries


@app.get("/api/v1/telemetry/{bin_id}/latest", response_model=schemas.ReadingOut, tags=["query"])
def latest_reading(bin_id: str, db: Session = Depends(get_db)):
    row = crud.get_latest_for_bin(db, bin_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"No readings found for {bin_id}")
    return row


@app.get("/api/v1/telemetry/{bin_id}/history", response_model=schemas.TelemetryHistory, tags=["query"])
def history(bin_id: str, limit: int = 200, db: Session = Depends(get_db)):
    if limit < 1 or limit > 2000:
        raise HTTPException(status_code=422, detail="limit must be between 1 and 2000")
    rows = crud.get_history_for_bin(db, bin_id, limit=limit)
    return schemas.TelemetryHistory(
        bin_id=bin_id,
        count=len(rows),
        readings=[schemas.ReadingOut.model_validate(r) for r in rows],
    )
