from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import numpy as np
import pandas as pd

from .config import Config
from .dispatch import DispatchPlan, POLICY_VERSION, build_dispatch_plan, validate_snapshot
from .planning_store import PlanningStore
from .routing import RoutePlan


@dataclass(frozen=True)
class PlanningResult:
    plan: DispatchPlan
    snapshot: pd.DataFrame
    stored_record: dict
    created: bool


@dataclass(frozen=True)
class DynamicRouteRevision:
    active_plan_id: str
    frozen_leg_origin: str
    frozen_leg_destination: str
    completed_bin_ids: tuple[str, ...]
    remaining: PlanningResult
    start_location_semantics: str = "after frozen leg service completes"


def _persisted_plan(record: dict) -> DispatchPlan:
    payload = dict(record["plan"])
    payload["route_plan"] = RoutePlan(**payload["route_plan"])
    payload["warnings"] = tuple(payload.get("warnings", ()))
    payload["source_event_ids"] = tuple(payload.get("source_event_ids", ()))
    return DispatchPlan(**payload)


class PlanningService:
    """Browser-independent planning facade shared by UI, CLI and runner."""

    def __init__(
        self,
        config: Config,
        bins: pd.DataFrame,
        distance_matrix_m: np.ndarray,
        duration_matrix_s: np.ndarray,
        store: PlanningStore,
        *,
        network_version: str,
        model_version: str,
    ) -> None:
        self.config = config
        self.bins = bins
        self.distance_matrix_m = distance_matrix_m
        self.duration_matrix_s = duration_matrix_s
        self.store = store
        self.network_version = network_version
        self.model_version = model_version

    def evaluate(
        self,
        raw_snapshot: pd.DataFrame,
        *,
        decision_at: datetime | None = None,
        last_valid_readings: dict | None = None,
        enforce_optional_dispatch_gap: bool = True,
    ) -> PlanningResult:
        clock = (decision_at or datetime.now(timezone.utc)).astimezone(timezone.utc)
        source_mode = str(
            raw_snapshot.iloc[0].get("source_mode", "legacy")
            if not raw_snapshot.empty
            else "legacy"
        )
        live_clock_policy = source_mode in {"hardware", "replay"}
        stale_after_hours = (
            self.config.sensor.live_stale_after_minutes / 60.0
            if live_clock_policy
            else self.config.sensor.stale_after_hours
        )
        offline_after_hours = (
            self.config.sensor.live_offline_after_minutes / 60.0
            if live_clock_policy
            else None
        )
        normalized = validate_snapshot(
            raw_snapshot,
            self.bins["bin_id"],
            self.config.operations.crane_lift_limit_kg,
            now_utc=clock,
            stale_after_hours=stale_after_hours,
            future_tolerance_minutes=self.config.sensor.future_tolerance_minutes,
            offline_after_hours=offline_after_hours,
        )
        service_markers: list[str] = []
        latest_services = self.store.latest_services()
        for index, row in normalized.iterrows():
            bin_id = str(row["bin_id"])
            service = latest_services.get(bin_id)
            if service is None:
                continue
            observed_at = pd.to_datetime(row["observed_at"], utc=True)
            serviced_at = pd.to_datetime(service["serviced_at"], utc=True)
            if observed_at > serviced_at:
                continue
            service_iso = serviced_at.isoformat()
            normalized.at[index, "timestamp"] = service_iso
            normalized.at[index, "observed_at"] = service_iso
            normalized.at[index, "fill_pct"] = 0.0
            normalized.at[index, "weight_kg"] = 0.0
            normalized.at[index, "time_to_overflow_hours"] = np.nan
            normalized.at[index, "risk_level"] = "low"
            normalized.at[index, "confidence_flag"] = True
            normalized.at[index, "forecast_status"] = "stable_no_overflow"
            normalized.at[index, "forecast_method"] = "post-service-state"
            normalized.at[index, "stale_flag"] = False
            normalized.at[index, "offline_flag"] = False
            normalized.at[index, "reading_age_hours"] = max(
                0.0, (clock - serviced_at.to_pydatetime()).total_seconds() / 3600.0
            )
            normalized.at[index, "service_plan_id"] = service["plan_id"]
            normalized.at[index, "service_state_at"] = service_iso
            service_markers.append(
                f"SERVICE:{service['plan_id']}:{bin_id}:{service_iso}"
            )
        source_identity_ids = sorted(
            str(value) for value in normalized.get("event_id", pd.Series(dtype=object)).dropna()
        )
        source_identity_ids.extend(service_markers)
        source_identity_ids = sorted(source_identity_ids) or [
            str(normalized.iloc[0]["snapshot_id"])
        ]
        snapshot_material = json.dumps(
            [source_identity_ids, clock.isoformat()], separators=(",", ":")
        ).encode("utf-8")
        normalized["decision_at"] = clock.isoformat()
        normalized["snapshot_id"] = (
            "SNAP-" + hashlib.sha256(snapshot_material).hexdigest()[:20].upper()
        )
        optional_dispatch_allowed = True
        recent_dispatches = self.store.latest_mock_dispatches(1)
        if enforce_optional_dispatch_gap and recent_dispatches:
            last_dispatch_at = pd.to_datetime(
                recent_dispatches[0]["created_at"], utc=True
            ).to_pydatetime()
            elapsed_hours = (clock - last_dispatch_at).total_seconds() / 3600.0
            optional_dispatch_allowed = (
                elapsed_hours >= self.config.operations.smart_min_dispatch_gap_hours
            )
        plan = build_dispatch_plan(
            normalized,
            self.bins,
            self.distance_matrix_m,
            self.config,
            last_valid_readings,
            self.duration_matrix_s,
            optional_dispatch_allowed=optional_dispatch_allowed,
        )
        bucket_seconds = self.config.operations.dynamic_replan_interval_minutes * 60
        bucket = int(clock.timestamp()) // bucket_seconds
        assumptions = {
            "policy_version": POLICY_VERSION,
            "config_hash": hashlib.sha256(
                json.dumps(self.config.to_dict(), sort_keys=True).encode("utf-8")
            ).hexdigest(),
            "network_version": self.network_version,
            "model_version": self.model_version,
            "vehicle": {
                "mass_capacity_kg": self.config.operations.truck_capacity_kg,
                "body_volume_m3": self.config.operations.truck_body_volume_m3,
                "compaction_ratio": self.config.operations.truck_compaction_ratio,
                "max_daily_trips": self.config.operations.max_daily_trips,
            },
        }
        idempotency_material = json.dumps(
            [source_identity_ids, bucket, assumptions], sort_keys=True, separators=(",", ":")
        )
        idempotency_key = hashlib.sha256(idempotency_material.encode("utf-8")).hexdigest()
        plan = replace(
            plan,
            plan_id="PLAN-"
            + hashlib.sha256(
                f"route-plan-v2|{idempotency_key}".encode("utf-8")
            ).hexdigest()[:20].upper(),
        )
        record, created = self.store.create_draft(
            plan,
            normalized,
            idempotency_key=idempotency_key,
            assumptions=assumptions,
        )
        if not created:
            plan = _persisted_plan(record)
            normalized = pd.DataFrame(record["snapshot"])
        return PlanningResult(plan, normalized, record, created)

    def replan_remaining_after_event(
        self,
        raw_snapshot: pd.DataFrame,
        *,
        active_plan_id: str,
        frozen_leg_origin: str,
        frozen_leg_destination: str,
        completed_bin_ids: set[str],
        current_payload_kg: float = 0.0,
        current_payload_m3: float = 0.0,
        decision_at: datetime | None = None,
        last_valid_readings: dict | None = None,
    ) -> DynamicRouteRevision:
        """Freeze the in-progress leg and replan only its unserved suffix.

        The accepted plan remains immutable. The returned draft uses the frozen
        destination as a temporary start node and the real depot as its end.
        Only the current trip is revised; later depot departures are evaluated
        as separate proposals after unload/turnaround.
        """
        active = self.store.get_plan(active_plan_id)
        if active["status"] != "ACCEPTED":
            raise ValueError("Dynamic replanning requires an accepted active route")
        bin_ids = self.bins["bin_id"].astype(str).tolist()
        if frozen_leg_destination not in bin_ids:
            raise ValueError("Frozen destination is not in the configured district")
        unknown_completed = set(completed_bin_ids) - set(bin_ids)
        if unknown_completed:
            raise ValueError(f"Unknown completed bins: {sorted(unknown_completed)}")
        remaining_mass = self.config.operations.truck_capacity_kg - current_payload_kg
        remaining_volume = self.config.operations.truck_body_volume_m3 - current_payload_m3
        if remaining_mass <= 0 or remaining_volume <= 0:
            raise ValueError("No residual truck capacity remains for an active-trip revision")

        adjusted = raw_snapshot.copy()
        if "schema_version" not in adjusted.columns:
            adjusted["schema_version"] = "2.0"
            adjusted["observed_at"] = adjusted["timestamp"]
            adjusted["decision_at"] = (
                decision_at or datetime.now(timezone.utc)
            ).astimezone(timezone.utc).isoformat()
            adjusted["snapshot_id"] = f"REVISION-SOURCE-{active_plan_id}"
            adjusted["event_id"] = None
            adjusted["clock_status"] = "synchronized"
            adjusted["source_mode"] = "legacy"
            adjusted["forecast_status"] = [
                "available" if pd.notna(value) else "stable_no_overflow"
                for value in adjusted["time_to_overflow_hours"]
            ]
            adjusted["forecast_method"] = "legacy-upstream"
            adjusted["model_version"] = None
            adjusted["quality_flags"] = [tuple() for _ in range(len(adjusted))]
        finished = set(completed_bin_ids) | {frozen_leg_destination}
        mask = adjusted["bin_id"].astype(str).isin(finished)
        adjusted.loc[mask, "fill_pct"] = 0.0
        adjusted.loc[mask, "weight_kg"] = 0.0
        adjusted.loc[mask, "risk_level"] = "low"
        adjusted.loc[mask, "confidence_flag"] = True
        adjusted.loc[mask, "time_to_overflow_hours"] = np.nan
        if "forecast_status" in adjusted.columns:
            adjusted.loc[mask, "forecast_status"] = "stable_no_overflow"

        start_index = bin_ids.index(frozen_leg_destination) + 1
        distance = np.array(self.distance_matrix_m, copy=True)
        duration = np.array(self.duration_matrix_s, copy=True)
        distance[0, :] = self.distance_matrix_m[start_index, :]
        duration[0, :] = self.duration_matrix_s[start_index, :]
        distance[0, 0] = 0
        duration[0, 0] = 0
        revised_config = replace(
            self.config,
            operations=replace(
                self.config.operations,
                truck_capacity_kg=remaining_mass,
                truck_body_volume_m3=remaining_volume,
                max_daily_trips=1,
            ),
        )
        suffix_service = PlanningService(
            revised_config,
            self.bins,
            distance,
            duration,
            self.store,
            network_version=self.network_version + ":active-suffix",
            model_version=self.model_version,
        )
        result = suffix_service.evaluate(
            adjusted,
            decision_at=decision_at,
            last_valid_readings=last_valid_readings,
            enforce_optional_dispatch_gap=False,
        )
        return DynamicRouteRevision(
            active_plan_id=active_plan_id,
            frozen_leg_origin=frozen_leg_origin,
            frozen_leg_destination=frozen_leg_destination,
            completed_bin_ids=tuple(sorted(completed_bin_ids)),
            remaining=result,
        )


class ControlledPlanningRunner:
    """Opt-in single-worker loop with explicit status and stop controls."""

    def __init__(self, control_dir: str | Path, interval_seconds: float) -> None:
        self.control_dir = Path(control_dir)
        self.control_dir.mkdir(parents=True, exist_ok=True)
        self.interval_seconds = max(1.0, float(interval_seconds))
        self.lock_path = self.control_dir / "planner.lock"
        self.stop_path = self.control_dir / "planner.stop"
        self.status_path = self.control_dir / "planner.status.json"
        self._lock_fd: int | None = None

    def _write_status(self, state: str, **extra) -> None:
        payload = {
            "state": state,
            "pid": os.getpid(),
            "updated_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        } | extra
        temporary = self.status_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        os.replace(temporary, self.status_path)

    def acquire(self) -> None:
        try:
            self._lock_fd = os.open(self.lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError as exc:
            raise RuntimeError("A planning runner already owns this control directory") from exc
        os.write(self._lock_fd, str(os.getpid()).encode("ascii"))
        if self.stop_path.exists():
            self.stop_path.unlink()
        self._write_status("STARTING")

    def request_stop(self) -> None:
        self.stop_path.write_text("stop\n", encoding="utf-8")

    def serve(self, evaluate: Callable[[], PlanningResult], *, max_iterations: int | None = None) -> int:
        self.acquire()
        iterations = 0
        try:
            self._write_status("RUNNING", iterations=iterations)
            while not self.stop_path.exists():
                result = evaluate()
                iterations += 1
                self._write_status(
                    "RUNNING",
                    iterations=iterations,
                    latest_plan_id=result.plan.plan_id,
                    latest_created=result.created,
                )
                if max_iterations is not None and iterations >= max_iterations:
                    break
                deadline = time.monotonic() + self.interval_seconds
                while time.monotonic() < deadline and not self.stop_path.exists():
                    time.sleep(min(0.25, deadline - time.monotonic()))
            self._write_status("STOPPED", iterations=iterations)
            return iterations
        finally:
            if self._lock_fd is not None:
                os.close(self._lock_fd)
                self._lock_fd = None
            if self.lock_path.exists():
                self.lock_path.unlink()
            if self.stop_path.exists():
                self.stop_path.unlink()

    def status(self) -> dict:
        if not self.status_path.exists():
            return {"state": "NOT_STARTED"}
        return json.loads(self.status_path.read_text(encoding="utf-8"))
