from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from .config import load_config
from .dispatch import (
    load_last_valid_readings,
    make_demo_snapshot,
    parse_snapshot_bytes,
    update_last_valid_readings_file,
)
from .pipeline import prepare_project, run_experiment
from .planner import ControlledPlanningRunner, PlanningService
from .planning_store import PlanningStore
from .registry import BinRegistry


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _planning_inputs(profile_id: str):
    root = project_root()
    config = load_config(root / "config.json")
    bins = pd.read_csv(root / "artifacts" / "district_bins.csv")
    distance = np.load(root / "artifacts" / "road_distance_matrix_m.npy")
    duration = np.load(root / "artifacts" / "road_duration_matrix_s.npy")
    if profile_id == "physical-pilot":
        bins = bins.iloc[:3].reset_index(drop=True)
        registry = BinRegistry.load(root / "config" / "bin_registry.json")
        entries = {entry.canonical_bin_id: entry for entry in registry.entries_for(profile_id)}
        bins["bin_type"] = [entries[str(value)].bin_type for value in bins["bin_id"]]
        bins["waste_stream"] = [
            entries[str(value)].waste_stream for value in bins["bin_id"]
        ]
        indices = np.array([0, 1, 2, 3])
        distance = distance[np.ix_(indices, indices)]
        duration = duration[np.ix_(indices, indices)]
    elif profile_id != "competition-simulation":
        raise ValueError(f"Unknown profile: {profile_id}")
    return config, bins, distance, duration


def _load_planning_snapshot(path: str | None, profile_id: str) -> pd.DataFrame:
    root = project_root()
    _, bins, _, _ = _planning_inputs(profile_id)
    if path is None:
        if profile_id != "competition-simulation":
            raise ValueError("The physical pilot requires an explicit telemetry fixture or replay")
        return make_demo_snapshot(bins)
    source = Path(path)
    registry = BinRegistry.load(root / "config" / "bin_registry.json")
    return parse_snapshot_bytes(
        source.read_bytes(),
        source.name,
        registry=registry,
        profile_id=profile_id,
    )


def _evaluate_once(snapshot_path: str | None, profile_id: str):
    root = project_root()
    config, bins, distance, duration = _planning_inputs(profile_id)
    raw = _load_planning_snapshot(snapshot_path, profile_id)
    store = PlanningStore(root / "data" / "routing_plans.sqlite3")
    service = PlanningService(
        config,
        bins,
        distance,
        duration,
        store,
        network_version="subang-jaya-osrm-v1",
        model_version="hist-gradient-boosting-multihorizon-q90-overflow-v3",
    )
    history_path = root / "data" / "last_valid_sensor_readings.json"
    history = load_last_valid_readings(history_path)
    result = service.evaluate(
        raw,
        decision_at=datetime.now(timezone.utc),
        last_valid_readings=history,
    )
    update_last_valid_readings_file(result.snapshot, bins, config, history_path)
    store.close()
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="BinSight Focus C OSM routing simulation")
    subparsers = parser.add_subparsers(dest="command", required=True)
    prepare = subparsers.add_parser("prepare", help="Download/cache OSM and build district")
    prepare.add_argument("--refresh-map", action="store_true")
    run = subparsers.add_parser("run", help="Run paired 30-day experiment")
    run.add_argument("--refresh-map", action="store_true")
    run.add_argument("--replications", type=int, default=None)
    run.add_argument(
        "--parallel-workers",
        type=int,
        default=1,
        help="Run independent policy pairs in 1-8 local worker processes",
    )
    run.add_argument(
        "--artifact-set",
        default=None,
        help="Write changed-policy evidence to a versioned artifacts subdirectory",
    )
    preview = subparsers.add_parser("plan-once", help="Create one durable route proposal")
    preview.add_argument("--snapshot", default=None, help="CSV/JSON snapshot or telemetry replay")
    preview.add_argument(
        "--profile",
        choices=("competition-simulation", "physical-pilot"),
        default="competition-simulation",
    )
    serve = subparsers.add_parser("planner-serve", help="Run the opt-in planner in the foreground")
    serve.add_argument("--snapshot", default=None)
    serve.add_argument(
        "--profile",
        choices=("competition-simulation", "physical-pilot"),
        default="competition-simulation",
    )
    serve.add_argument("--interval-seconds", type=float, default=900.0)
    serve.add_argument("--max-iterations", type=int, default=None)
    start = subparsers.add_parser("planner-start", help="Start one local background planner")
    start.add_argument("--snapshot", default=None)
    start.add_argument(
        "--profile",
        choices=("competition-simulation", "physical-pilot"),
        default="competition-simulation",
    )
    start.add_argument("--interval-seconds", type=float, default=900.0)
    subparsers.add_parser("planner-stop", help="Request a clean planner shutdown")
    subparsers.add_parser("planner-status", help="Show local planner status")
    args = parser.parse_args()
    if args.command == "prepare":
        config, service_network, _, bins, _, _ = prepare_project(
            project_root(), args.refresh_map
        )
        print(
            f"Prepared {config.pilot.label}: {service_network.service_count} OSM-routed "
            f"service points, {len(bins)} bins."
        )
        return
    if args.command == "run":
        result = run_experiment(
            project_root(),
            args.refresh_map,
            args.replications,
            artifact_set=args.artifact_set,
            parallel_workers=args.parallel_workers,
        )
        print(f"Completed. Results: {result['artifacts_dir']}")
        print(result["effects"][["metric", "beneficial_change_pct_vs_fixed"]].to_string(index=False))
        return
    if args.command == "plan-once":
        result = _evaluate_once(args.snapshot, args.profile)
        print(
            json.dumps(
                {
                    "plan_id": result.plan.plan_id,
                    "created": result.created,
                    "status": result.stored_record["status"],
                    "decision_state": result.plan.decision_state,
                    "dispatch_reason": result.plan.route_plan.dispatch_reason,
                    "selected_bins": result.plan.selected_count,
                    "distance_km": result.plan.route_plan.distance_m / 1000.0,
                    "net_value_m_equivalent": result.plan.route_plan.net_value_m_equivalent,
                },
                indent=2,
            )
        )
        return
    control_dir = project_root() / "data" / "planner-control"
    runner = ControlledPlanningRunner(control_dir, getattr(args, "interval_seconds", 900.0))
    if args.command == "planner-serve":
        runner.serve(
            lambda: _evaluate_once(args.snapshot, args.profile),
            max_iterations=args.max_iterations,
        )
        return
    if args.command == "planner-stop":
        runner.request_stop()
        print("Planner stop requested.")
        return
    if args.command == "planner-status":
        print(json.dumps(runner.status(), indent=2))
        return
    if args.command == "planner-start":
        if runner.lock_path.exists():
            raise RuntimeError(
                "A planner lock already exists; inspect planner-status and stop the active "
                "runner before starting another. Remove a stale lock only after verifying "
                "that its recorded PID is not running."
            )
        runner.status_path.unlink(missing_ok=True)
        command = [
            sys.executable,
            "-m",
            "binsight.cli",
            "planner-serve",
            "--profile",
            args.profile,
            "--interval-seconds",
            str(args.interval_seconds),
        ]
        if args.snapshot:
            command.extend(["--snapshot", str(Path(args.snapshot).resolve())])
        log_path = control_dir / "planner.log"
        control_dir.mkdir(parents=True, exist_ok=True)
        log_handle = log_path.open("a", encoding="utf-8")
        creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        process = subprocess.Popen(
            command,
            cwd=project_root(),
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            creationflags=creationflags,
            start_new_session=os.name != "nt",
        )
        log_handle.close()
        deadline = time.monotonic() + 5.0
        status = {"state": "NOT_STARTED"}
        while time.monotonic() < deadline:
            if runner.status_path.exists():
                status = runner.status()
                if status.get("state") in {"STARTING", "RUNNING"}:
                    break
            time.sleep(0.1)
        if status.get("state") not in {"STARTING", "RUNNING"}:
            raise RuntimeError(
                f"Planner did not report a running state. Inspect {log_path}"
            )
        print(
            f"Planner started locally with worker PID {status.get('pid')} "
            f"({status.get('state')}). Log: {log_path}"
        )
        return


if __name__ == "__main__":
    main()
