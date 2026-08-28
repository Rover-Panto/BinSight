"""Durable simulation sessions; acceptance and credit commit in one transaction."""

from contextlib import contextmanager
from dataclasses import asdict
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sqlite3
import time
from uuid import uuid4

from .recycling_policy import Decision, InferenceSample, RecyclingInspection
from .settings import Settings


class Conflict(Exception):
    pass


class NotFound(Exception):
    pass


class Clock:
    def utc(self):
        return datetime.now(timezone.utc).timestamp()

    def monotonic(self):
        return time.monotonic()


def encode(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def iso(timestamp):
    return datetime.fromtimestamp(timestamp, timezone.utc).isoformat()


SCHEMA = """
CREATE TABLE stations (
    id TEXT PRIMARY KEY, device_id TEXT NOT NULL, boot_id TEXT, ready INTEGER NOT NULL DEFAULT 0,
    last_sequence INTEGER NOT NULL DEFAULT -1, last_inspection_id TEXT
);
CREATE TABLE boots (boot_id TEXT PRIMARY KEY);
CREATE TABLE sessions (
    id TEXT PRIMARY KEY, citizen_id TEXT NOT NULL, station_id TEXT NOT NULL,
    status TEXT NOT NULL, created_at REAL NOT NULL, expires_at REAL NOT NULL
);
CREATE UNIQUE INDEX one_active_station ON sessions(station_id) WHERE status = 'active';
CREATE TABLE inspections (
    id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES sessions(id),
    boot_id TEXT NOT NULL, created_at REAL NOT NULL, started_monotonic REAL NOT NULL,
    decision TEXT NOT NULL, terminal INTEGER NOT NULL DEFAULT 0
);
CREATE UNIQUE INDEX one_waiting_inspection ON inspections(session_id) WHERE terminal = 0;
CREATE TABLE events (
    id TEXT PRIMARY KEY, inspection_id TEXT NOT NULL REFERENCES inspections(id),
    boot_id TEXT NOT NULL, sequence INTEGER NOT NULL, payload TEXT NOT NULL,
    received_at REAL NOT NULL, elapsed_ms INTEGER NOT NULL,
    UNIQUE(boot_id, sequence)
);
CREATE TABLE credits (
    inspection_id TEXT PRIMARY KEY REFERENCES inspections(id),
    session_id TEXT NOT NULL REFERENCES sessions(id),
    value_cents INTEGER NOT NULL CHECK(value_cents = 20),
    created_at REAL NOT NULL
);
CREATE TABLE actions (
    actor TEXT NOT NULL, request_id TEXT NOT NULL, payload TEXT NOT NULL,
    response TEXT NOT NULL, PRIMARY KEY(actor, request_id)
);
PRAGMA user_version = 1;
"""


class ReturnStore:
    def __init__(self, settings: Settings, clock=None):
        self.settings = settings
        self.path = Path(settings.database).resolve()
        self.clock = clock or Clock()
        self._lock = None

    def open(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # OS locks release after a crash; a stale lock-file must not prevent recovery.
        self._lock = self.path.with_suffix(self.path.suffix + ".lock").open("a+b")
        try:
            self._lock.seek(0)
            if os.name == "nt":
                import msvcrt
                if self._lock.read(1) == b"":
                    self._lock.write(b"0")
                    self._lock.flush()
                self._lock.seek(0)
                msvcrt.locking(self._lock.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self._lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self._lock.close()
            self._lock = None
            raise RuntimeError("This return database already has a running server") from None
        try:
            with self.connection() as db:
                version = db.execute("PRAGMA user_version").fetchone()[0]
                tables = db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
                if version == 0 and not tables:
                    db.executescript("BEGIN IMMEDIATE;\n" + SCHEMA + "\nCOMMIT;")
                elif version != 1:
                    raise RuntimeError("Unknown return database schema; no migration was attempted")
                db.execute("PRAGMA journal_mode=WAL")
            with self.transaction() as db:
                db.execute("INSERT OR IGNORE INTO stations(id, device_id) VALUES (?, ?)",
                           (self.settings.station_id, self.settings.device_id))
                station_ids = [row[0] for row in db.execute("SELECT id FROM stations")]
                if station_ids != [self.settings.station_id]:
                    raise RuntimeError("Station configuration differs from the stored registry")
                if self._station(db)["device_id"] != self.settings.device_id:
                    raise RuntimeError("Device configuration differs from the stored registry")
                for row in db.execute("SELECT * FROM inspections WHERE terminal=0").fetchall():
                    self._finish(db, row, Decision("rejected", "server_restarted"))
                db.execute("UPDATE stations SET ready=0")
        except Exception:
            self.close()
            raise

    def close(self):
        if self._lock:
            self._lock.close()
            self._lock = None

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        try:
            yield db
        finally:
            db.close()

    @contextmanager
    def transaction(self):
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                yield db
                db.commit()
            except Exception:
                db.rollback()
                raise

    def _station(self, db):
        return db.execute("SELECT * FROM stations WHERE id=?", (self.settings.station_id,)).fetchone()

    def _owned(self, db, session_id, citizen_id):
        row = db.execute("SELECT * FROM sessions WHERE id=? AND citizen_id=?", (session_id, citizen_id)).fetchone()
        if row is None:
            raise NotFound("Session not found")
        return row

    def _action(self, db, actor, request_id, payload):
        row = db.execute("SELECT * FROM actions WHERE actor=? AND request_id=?", (actor, request_id)).fetchone()
        if row is None:
            return None
        if row["payload"] != encode(payload):
            raise Conflict("Request ID was already used for a different action")
        return json.loads(row["response"])

    def _save_action(self, db, actor, request_id, payload, response):
        db.execute("INSERT INTO actions VALUES (?, ?, ?, ?)", (actor, request_id, encode(payload), encode(response)))
        return response

    def _finish(self, db, inspection, decision):
        if inspection["terminal"]:
            return
        db.execute("UPDATE inspections SET decision=?, terminal=1 WHERE id=?", (encode(asdict(decision)), inspection["id"]))
        if decision.outcome == "accepted":
            db.execute("INSERT INTO credits VALUES (?, ?, 20, ?)", (inspection["id"], inspection["session_id"], self.clock.utc()))

    def _expire(self, db):
        now = self.clock.utc()
        expired = db.execute("SELECT id FROM sessions WHERE status='active' AND expires_at<=?", (now,)).fetchall()
        for session in expired:
            for row in db.execute("SELECT * FROM inspections WHERE session_id=? AND terminal=0", (session["id"],)).fetchall():
                self._finish(db, row, Decision("rejected", "session_expired"))
            db.execute("UPDATE sessions SET status='expired' WHERE id=?", (session["id"],))
            db.execute("UPDATE stations SET ready=0")
        for row in db.execute("SELECT * FROM inspections WHERE terminal=0").fetchall():
            elapsed = int((self.clock.monotonic() - row["started_monotonic"]) * 1000)
            if elapsed >= 5000 or elapsed < 0:
                self._finish(db, row, Decision("rejected", "inspection_timeout"))

    def _inspection_view(self, row):
        return {
            "inspection_id": row["id"], "session_id": row["session_id"],
            "created_at": iso(row["created_at"]), "expires_at": iso(row["created_at"] + 5),
            "decision": json.loads(row["decision"]), "is_simulation": True,
        }

    def _session_view(self, db, session_id):
        row = db.execute("SELECT * FROM sessions WHERE id=?", (session_id,)).fetchone()
        inspections = db.execute("SELECT * FROM inspections WHERE session_id=? ORDER BY rowid", (session_id,)).fetchall()
        cents = db.execute("SELECT COALESCE(SUM(value_cents),0) FROM credits WHERE session_id=?", (session_id,)).fetchone()[0]
        return {
            "session_id": session_id, "station_id": row["station_id"], "status": row["status"],
            "created_at": iso(row["created_at"]), "expires_at": iso(row["expires_at"]),
            "credit_cents": cents, "currency": "MYR", "is_simulation": True,
            "inspections": [self._inspection_view(item) for item in inspections],
        }

    def start_session(self, citizen_id, request):
        payload = {"action": "start_session", **request.model_dump()}
        with self.transaction() as db:
            self._expire(db)
            replay = self._action(db, citizen_id, request.request_id, payload)
            if replay:
                return self._session_view(db, replay["session_id"])
            if request.station_id != self.settings.station_id:
                raise NotFound("Station not found")
            if db.execute("SELECT 1 FROM sessions WHERE status='active'").fetchone():
                raise Conflict("Station already has an active session")
            session_id = "BS-" + uuid4().hex
            now = self.clock.utc()
            db.execute("INSERT INTO sessions VALUES (?, ?, ?, 'active', ?, ?)",
                       (session_id, citizen_id, request.station_id, now, now + self.settings.session_seconds))
            self._save_action(db, citizen_id, request.request_id, payload, {"session_id": session_id})
            return self._session_view(db, session_id)

    def get_session(self, citizen_id, session_id):
        with self.transaction() as db:
            self._owned(db, session_id, citizen_id)
            self._expire(db)
            return self._session_view(db, session_id)

    def begin_inspection(self, citizen_id, session_id, request):
        payload = {"action": "begin_inspection", "session_id": session_id}
        with self.transaction() as db:
            self._owned(db, session_id, citizen_id)
            self._expire(db)
            replay = self._action(db, citizen_id, request.request_id, payload)
            if replay:
                row = db.execute("SELECT * FROM inspections WHERE id=?", (replay["inspection_id"],)).fetchone()
                return self._inspection_view(row)
            session = self._owned(db, session_id, citizen_id)
            if session["status"] != "active":
                raise Conflict("Session is not active")
            station = self._station(db)
            if not station["ready"] or not station["boot_id"]:
                raise Conflict("Station must acknowledge an empty inspection area")
            if db.execute("SELECT 1 FROM inspections WHERE session_id=? AND terminal=0", (session_id,)).fetchone():
                raise Conflict("An inspection is already in progress")
            inspection_id = "INS-" + uuid4().hex
            db.execute("INSERT INTO inspections VALUES (?, ?, ?, ?, ?, ?, 0)",
                       (inspection_id, session_id, station["boot_id"], self.clock.utc(), self.clock.monotonic(),
                        encode(asdict(Decision("waiting", "awaiting_item")))))
            db.execute("UPDATE stations SET ready=0, last_inspection_id=?", (inspection_id,))
            self._save_action(db, citizen_id, request.request_id, payload, {"inspection_id": inspection_id})
            return self._inspection_view(db.execute("SELECT * FROM inspections WHERE id=?", (inspection_id,)).fetchone())

    def finish_session(self, citizen_id, session_id, request):
        payload = {"action": "finish_session", "session_id": session_id}
        with self.transaction() as db:
            self._owned(db, session_id, citizen_id)
            self._expire(db)
            replay = self._action(db, citizen_id, request.request_id, payload)
            if replay:
                return self._session_view(db, session_id)
            for row in db.execute("SELECT * FROM inspections WHERE session_id=? AND terminal=0", (session_id,)).fetchall():
                self._finish(db, row, Decision("rejected", "session_finished"))
            session = self._owned(db, session_id, citizen_id)
            if session["status"] == "active":
                db.execute("UPDATE sessions SET status='finished' WHERE id=?", (session_id,))
                db.execute("UPDATE stations SET ready=0")
            self._save_action(db, citizen_id, request.request_id, payload, {"session_id": session_id})
            return self._session_view(db, session_id)

    def station_state(self):
        with self.transaction() as db:
            self._expire(db)
            station = self._station(db)
            session = db.execute("SELECT id FROM sessions WHERE status='active'").fetchone()
            inspection = db.execute("SELECT * FROM inspections WHERE id=?", (station["last_inspection_id"],)).fetchone()
            return {
                "station_id": self.settings.station_id, "device_id": self.settings.device_id,
                "boot_id": station["boot_id"], "ready": bool(station["ready"]),
                "session_id": session["id"] if session else None,
                "last_inspection_id": station["last_inspection_id"],
                "inspection": self._inspection_view(inspection) if inspection else None,
                "is_simulation": True, "actuation_enabled": False,
            }

    def station_ready(self, request):
        if request.device_id != self.settings.device_id or not request.empty or not request.is_simulation:
            raise Conflict("Use the configured simulator and confirm item removal")
        payload = {"action": "station_ready", **request.model_dump()}
        with self.transaction() as db:
            self._expire(db)
            replay = self._action(db, "device:" + self.settings.device_id, request.request_id, payload)
            if replay:
                return {**replay, "duplicate": True}
            station = self._station(db)
            if request.after_inspection_id != station["last_inspection_id"]:
                raise Conflict("Removal acknowledgement does not match the latest inspection")
            new_boot = request.boot_id != station["boot_id"]
            if new_boot and db.execute("SELECT 1 FROM boots WHERE boot_id=?", (request.boot_id,)).fetchone():
                raise Conflict("A retired boot cannot re-arm the station")
            waiting = db.execute("SELECT * FROM inspections WHERE terminal=0").fetchone()
            if waiting and not new_boot:
                raise Conflict("Inspection is still in progress")
            if waiting:
                self._finish(db, waiting, Decision("rejected", "gateway_restarted"))
            if new_boot:
                db.execute("INSERT INTO boots VALUES (?)", (request.boot_id,))
                db.execute("UPDATE stations SET boot_id=?, last_sequence=-1", (request.boot_id,))
            db.execute("UPDATE stations SET ready=1")
            response = {"acknowledged": True, "after_inspection_id": request.after_inspection_id, "is_simulation": True}
            return self._save_action(db, "device:" + self.settings.device_id, request.request_id, payload, response)

    def ingest(self, sample):
        if sample.station_id != self.settings.station_id or sample.device_id != self.settings.device_id:
            raise NotFound("Device or station not found")
        if not sample.is_simulation:
            raise Conflict("Physical operation is disabled in this integration build")
        payload = sample.model_dump()
        with self.transaction() as db:
            self._expire(db)
            previous = db.execute("SELECT * FROM events WHERE id=?", (sample.event_id,)).fetchone()
            if previous:
                if previous["payload"] != encode(payload):
                    raise Conflict("Event ID was already used for different metadata")
                row = db.execute("SELECT * FROM inspections WHERE id=?", (sample.inspection_id,)).fetchone()
                return {**self._inspection_view(row), "duplicate": True}
            row = db.execute("SELECT * FROM inspections WHERE id=? AND session_id=?",
                             (sample.inspection_id, sample.session_id)).fetchone()
            if row is None:
                raise NotFound("Inspection not found")
            station = self._station(db)
            if sample.boot_id != station["boot_id"] or sample.boot_id != row["boot_id"]:
                raise Conflict("Inference belongs to another device boot")
            if row["terminal"]:
                if json.loads(row["decision"])["outcome"] == "accepted":
                    raise Conflict("Inspection already accepted; only exact event retries are acknowledged")
                return {**self._inspection_view(row), "ignored": True}
            if sample.sequence <= station["last_sequence"]:
                raise Conflict("Inference sequence is repeated or out of order")
            observed = datetime.fromisoformat(sample.observed_at).timestamp()
            now = self.clock.utc()
            if observed < row["created_at"] or observed > now + 1 or now - observed > 5:
                raise Conflict("Inference is stale or outside the inspection window")
            history = db.execute("SELECT * FROM events WHERE inspection_id=? ORDER BY rowid", (sample.inspection_id,)).fetchall()
            if len(history) >= 128:
                self._finish(db, row, Decision("rejected", "sample_limit"))
            else:
                policy = RecyclingInspection()
                for event in history:
                    old = json.loads(event["payload"])
                    policy.observe(InferenceSample(old["sequence"], old["material"], old["confidence"], old["object_count"]), event["elapsed_ms"])
                elapsed = int((self.clock.monotonic() - row["started_monotonic"]) * 1000)
                decision = policy.observe(InferenceSample(sample.sequence, sample.material, sample.confidence, sample.object_count), elapsed)
                db.execute("INSERT INTO events VALUES (?, ?, ?, ?, ?, ?, ?)",
                           (sample.event_id, sample.inspection_id, sample.boot_id, sample.sequence, encode(payload), now, elapsed))
                db.execute("UPDATE stations SET last_sequence=?", (sample.sequence,))
                if decision.outcome == "waiting":
                    db.execute("UPDATE inspections SET decision=? WHERE id=?", (encode(asdict(decision)), sample.inspection_id))
                else:
                    self._finish(db, row, decision)
            updated = db.execute("SELECT * FROM inspections WHERE id=?", (sample.inspection_id,)).fetchone()
            return {**self._inspection_view(updated), "duplicate": False}
