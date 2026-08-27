from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from .dispatch import DispatchPlan


PLANNING_STORE_SCHEMA_VERSION = 1
PLAN_STATES = {"DRAFT", "ACCEPTED", "COMPLETED", "CANCELLED"}


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _json_default(value: Any) -> Any:
    if hasattr(value, "item"):
        return value.item()
    raise TypeError(f"Cannot serialize {type(value).__name__}")


def _frame_records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    clean = frame.astype(object).where(pd.notna(frame), None)
    return clean.to_dict(orient="records")


class PlanningStore:
    """Transactional routing store, separate from telemetry and citizen data."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self.connection = sqlite3.connect(self.path, timeout=10.0)
            self.connection.row_factory = sqlite3.Row
            self.connection.execute("PRAGMA foreign_keys = ON")
            self.connection.execute("PRAGMA journal_mode = WAL")
            self._ensure_schema()
        except sqlite3.DatabaseError as exc:
            raise RuntimeError(
                f"Planning store could not be opened; the original file was preserved: {exc}"
            ) from exc

    def close(self) -> None:
        self.connection.close()

    def _ensure_schema(self) -> None:
        with self.connection:
            self.connection.execute(
                "CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
            )
            version_row = self.connection.execute(
                "SELECT value FROM metadata WHERE key='schema_version'"
            ).fetchone()
            if version_row is not None and int(version_row[0]) != PLANNING_STORE_SCHEMA_VERSION:
                raise RuntimeError(
                    f"Unsupported planning store schema version {version_row[0]}; no data was changed"
                )
            self.connection.execute(
                "INSERT OR IGNORE INTO metadata(key, value) VALUES ('schema_version', ?)",
                (str(PLANNING_STORE_SCHEMA_VERSION),),
            )
            self.connection.execute(
                """
                CREATE TABLE IF NOT EXISTS plans (
                    plan_id TEXT PRIMARY KEY,
                    idempotency_key TEXT NOT NULL UNIQUE,
                    snapshot_id TEXT NOT NULL,
                    decision_at TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    status TEXT NOT NULL CHECK(status IN ('DRAFT','ACCEPTED','COMPLETED','CANCELLED')),
                    record_version INTEGER NOT NULL,
                    source_mode TEXT NOT NULL,
                    source_event_ids_json TEXT NOT NULL,
                    snapshot_json TEXT NOT NULL,
                    plan_json TEXT NOT NULL,
                    assumptions_json TEXT NOT NULL,
                    operator_actor TEXT,
                    operator_note TEXT
                )
                """
            )
            self.connection.execute(
                """
                CREATE TABLE IF NOT EXISTS mock_dispatches (
                    dispatch_id TEXT PRIMARY KEY,
                    plan_id TEXT NOT NULL UNIQUE REFERENCES plans(plan_id),
                    created_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                )
                """
            )
            self.connection.execute(
                """
                CREATE TABLE IF NOT EXISTS service_events (
                    plan_id TEXT NOT NULL REFERENCES plans(plan_id),
                    bin_id TEXT NOT NULL,
                    serviced_at TEXT NOT NULL,
                    PRIMARY KEY (plan_id, bin_id)
                )
                """
            )
            self.connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_plans_status_decision ON plans(status, decision_at)"
            )
            self.connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_service_events_bin_time ON service_events(bin_id, serviced_at)"
            )

    def create_draft(
        self,
        plan: DispatchPlan,
        snapshot: pd.DataFrame,
        *,
        idempotency_key: str,
        assumptions: dict[str, Any],
    ) -> tuple[dict[str, Any], bool]:
        existing = self.connection.execute(
            "SELECT * FROM plans WHERE idempotency_key=?", (idempotency_key,)
        ).fetchone()
        if existing is not None:
            return self._decode(existing), False
        now = _utc_now()
        snapshot_id = str(snapshot.iloc[0].get("snapshot_id", "legacy-snapshot"))
        plan_json = json.dumps(asdict(plan), default=_json_default, sort_keys=True)
        snapshot_json = json.dumps(_frame_records(snapshot), default=_json_default, sort_keys=True)
        assumptions_json = json.dumps(assumptions, default=_json_default, sort_keys=True)
        try:
            with self.connection:
                self.connection.execute(
                    """
                    INSERT INTO plans (
                        plan_id, idempotency_key, snapshot_id, decision_at,
                        created_at, updated_at, status, record_version,
                        source_mode, source_event_ids_json, snapshot_json,
                        plan_json, assumptions_json
                    ) VALUES (?, ?, ?, ?, ?, ?, 'DRAFT', 1, ?, ?, ?, ?, ?)
                    """,
                    (
                        plan.plan_id,
                        idempotency_key,
                        snapshot_id,
                        plan.decision_at,
                        now,
                        now,
                        plan.source_mode,
                        json.dumps(list(plan.source_event_ids)),
                        snapshot_json,
                        plan_json,
                        assumptions_json,
                    ),
                )
        except sqlite3.IntegrityError:
            existing = self.connection.execute(
                "SELECT * FROM plans WHERE idempotency_key=?", (idempotency_key,)
            ).fetchone()
            if existing is None:
                raise
            return self._decode(existing), False
        return self.get_plan(plan.plan_id), True

    def _transition(
        self,
        plan_id: str,
        from_states: tuple[str, ...],
        to_state: str,
        actor: str,
        note: str = "",
    ) -> dict[str, Any]:
        if to_state not in PLAN_STATES:
            raise ValueError(f"Unknown plan state: {to_state}")
        placeholders = ",".join("?" for _ in from_states)
        with self.connection:
            cursor = self.connection.execute(
                f"""
                UPDATE plans
                SET status=?, record_version=record_version+1, updated_at=?,
                    operator_actor=?, operator_note=?
                WHERE plan_id=? AND status IN ({placeholders})
                """,
                (to_state, _utc_now(), actor, note, plan_id, *from_states),
            )
        if cursor.rowcount != 1:
            current = self.get_plan(plan_id)
            raise ValueError(
                f"Plan {plan_id} cannot move from {current['status']} to {to_state}"
            )
        return self.get_plan(plan_id)

    def accept(self, plan_id: str, actor: str, note: str = "") -> dict[str, Any]:
        return self._transition(plan_id, ("DRAFT",), "ACCEPTED", actor, note)

    def complete(self, plan_id: str, actor: str, note: str = "") -> dict[str, Any]:
        """Complete an accepted plan and durably remember which bins were emptied.

        The plan snapshot is immutable, so its normalized row order is the same
        index space used by ``served_bin_indices``. Recording the service fact in
        the same transaction prevents delayed pre-collection telemetry from
        immediately scheduling the same bin again.
        """
        row = self.connection.execute(
            "SELECT status, snapshot_json, plan_json FROM plans WHERE plan_id=?",
            (plan_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"Unknown plan_id: {plan_id}")
        if row["status"] != "ACCEPTED":
            raise ValueError(
                f"Plan {plan_id} cannot move from {row['status']} to COMPLETED"
            )
        snapshot = json.loads(row["snapshot_json"])
        plan = json.loads(row["plan_json"])
        served_indices = plan.get("route_plan", {}).get("served_bin_indices", [])
        try:
            bin_ids = [str(snapshot[int(index)]["bin_id"]) for index in served_indices]
        except (IndexError, KeyError, TypeError, ValueError) as exc:
            raise RuntimeError(
                "Accepted plan cannot be completed because its immutable bin index is invalid"
            ) from exc
        completed_at = _utc_now()
        with self.connection:
            cursor = self.connection.execute(
                """
                UPDATE plans
                SET status='COMPLETED', record_version=record_version+1, updated_at=?,
                    operator_actor=?, operator_note=?
                WHERE plan_id=? AND status='ACCEPTED'
                """,
                (completed_at, actor, note, plan_id),
            )
            if cursor.rowcount != 1:
                current = self.get_plan(plan_id)
                raise ValueError(
                    f"Plan {plan_id} cannot move from {current['status']} to COMPLETED"
                )
            self.connection.executemany(
                "INSERT INTO service_events(plan_id, bin_id, serviced_at) VALUES (?, ?, ?)",
                [(plan_id, bin_id, completed_at) for bin_id in bin_ids],
            )
        return self.get_plan(plan_id)

    def cancel(self, plan_id: str, actor: str, note: str = "") -> dict[str, Any]:
        return self._transition(plan_id, ("DRAFT", "ACCEPTED"), "CANCELLED", actor, note)

    def record_mock_dispatch(self, plan_id: str, payload: dict[str, Any]) -> tuple[dict[str, Any], bool]:
        plan = self.get_plan(plan_id)
        if plan["status"] != "ACCEPTED":
            raise ValueError("Only an accepted route can create a mock dispatch")
        existing = self.connection.execute(
            "SELECT payload_json FROM mock_dispatches WHERE plan_id=?", (plan_id,)
        ).fetchone()
        if existing is not None:
            return json.loads(existing[0]), False
        dispatch_id = str(payload["dispatch_id"])
        with self.connection:
            self.connection.execute(
                "INSERT INTO mock_dispatches VALUES (?, ?, ?, ?)",
                (dispatch_id, plan_id, _utc_now(), json.dumps(payload, default=_json_default)),
            )
        return payload, True

    def get_plan(self, plan_id: str) -> dict[str, Any]:
        row = self.connection.execute("SELECT * FROM plans WHERE plan_id=?", (plan_id,)).fetchone()
        if row is None:
            raise KeyError(f"Unknown plan_id: {plan_id}")
        return self._decode(row)

    def latest(self, limit: int = 20) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            "SELECT * FROM plans ORDER BY decision_at DESC, created_at DESC LIMIT ?",
            (max(1, int(limit)),),
        ).fetchall()
        return [self._decode(row) for row in rows]

    def latest_mock_dispatches(self, limit: int = 20) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            """
            SELECT dispatch_id, plan_id, created_at, payload_json
            FROM mock_dispatches ORDER BY created_at DESC LIMIT ?
            """,
            (max(1, int(limit)),),
        ).fetchall()
        return [
            {
                "dispatch_id": row["dispatch_id"],
                "plan_id": row["plan_id"],
                "created_at": row["created_at"],
                "payload": json.loads(row["payload_json"]),
            }
            for row in rows
        ]

    def has_mock_dispatch(self, plan_id: str) -> bool:
        return (
            self.connection.execute(
                "SELECT 1 FROM mock_dispatches WHERE plan_id=?", (plan_id,)
            ).fetchone()
            is not None
        )

    def latest_services(self) -> dict[str, dict[str, str]]:
        """Return the latest durable collection fact for every serviced bin."""
        rows = self.connection.execute(
            """
            SELECT service.bin_id, service.plan_id, service.serviced_at
            FROM service_events AS service
            JOIN (
                SELECT bin_id, MAX(serviced_at) AS serviced_at
                FROM service_events GROUP BY bin_id
            ) AS latest
              ON latest.bin_id = service.bin_id
             AND latest.serviced_at = service.serviced_at
            ORDER BY service.bin_id, service.plan_id
            """
        ).fetchall()
        return {
            str(row["bin_id"]): {
                "plan_id": str(row["plan_id"]),
                "serviced_at": str(row["serviced_at"]),
            }
            for row in rows
        }

    @staticmethod
    def _decode(row: sqlite3.Row) -> dict[str, Any]:
        result = dict(row)
        for key in (
            "source_event_ids_json",
            "snapshot_json",
            "plan_json",
            "assumptions_json",
        ):
            result[key.removesuffix("_json")] = json.loads(result.pop(key))
        return result
