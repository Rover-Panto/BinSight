from __future__ import annotations

import json
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime, timezone
from pathlib import Path
import shutil
import sqlite3
import tempfile
import time
from uuid import uuid4

import numpy as np
import pandas as pd

from .config import load_config, required_service_sites
from .network import load_cached_service_network
from .planning_store import PlanningStore


def configure_logging(root: str | Path) -> logging.Logger:
    """Configure one bounded local application log without duplicate handlers."""
    project_root = Path(root)
    log_dir = project_root / "data" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("binsight")
    logger.setLevel(logging.INFO)
    if not any(
        isinstance(handler, RotatingFileHandler)
        and Path(handler.baseFilename) == log_dir / "binsight-admin.log"
        for handler in logger.handlers
    ):
        handler = RotatingFileHandler(
            log_dir / "binsight-admin.log",
            maxBytes=2_000_000,
            backupCount=5,
            encoding="utf-8",
        )
        formatter = logging.Formatter(
            "%(asctime)sZ %(levelname)s %(name)s %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S",
        )
        formatter.converter = time.gmtime
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    return logger


def error_reference() -> str:
    return "ERR-" + uuid4().hex[:10].upper()


def collect_runtime_health(root: str | Path) -> dict:
    """Run deterministic local readiness checks used by startup and support."""
    project_root = Path(root).resolve()
    checks: list[dict[str, str | bool]] = []

    def record(name: str, operation) -> None:
        try:
            detail = str(operation())
            checks.append({"name": name, "ok": True, "detail": detail})
        except Exception as exc:  # readiness must report every independent failure
            checks.append(
                {"name": name, "ok": False, "detail": f"{type(exc).__name__}: {exc}"}
            )

    config_holder: dict[str, object] = {}

    def config_check() -> str:
        config = load_config(project_root / "config.json")
        config_holder["config"] = config
        return (
            f"{config.pilot.bin_count} bins / "
            f"{required_service_sites(config)} four-bin sites"
        )

    record("configuration", config_check)

    def district_check() -> str:
        config = config_holder.get("config") or load_config(project_root / "config.json")
        frame = pd.read_csv(project_root / "artifacts" / "district_bins.csv")
        if len(frame) != config.pilot.bin_count:
            raise ValueError(f"expected {config.pilot.bin_count} rows, found {len(frame)}")
        expected_materials = {
            "mixed_general_waste",
            "plastic_cups",
            "metal_cans",
            "glass_bottles",
        }
        if set(frame["material_type"]) != expected_materials:
            raise ValueError("district material contract is incomplete")
        if not (frame.groupby("site_id").size() == 4).all():
            raise ValueError("every service site must contain four bins")
        return f"{len(frame)} rows; {frame['site_id'].nunique()} sites"

    record("district", district_check)

    def matrices_check() -> str:
        config = config_holder.get("config") or load_config(project_root / "config.json")
        expected = (config.pilot.bin_count + 1, config.pilot.bin_count + 1)
        names = (
            "road_distance_matrix_m.npy",
            "road_duration_matrix_s.npy",
            "recycling_road_distance_matrix_m.npy",
            "recycling_road_duration_matrix_s.npy",
        )
        for name in names:
            matrix = np.load(project_root / "artifacts" / name)
            if matrix.shape != expected or not np.isfinite(matrix).all():
                raise ValueError(f"{name} is not a finite {expected} matrix")
        return f"four finite {expected[0]}x{expected[1]} road matrices"

    record("road_matrices", matrices_check)

    def network_check() -> str:
        config = config_holder.get("config") or load_config(project_root / "config.json")
        network = load_cached_service_network(
            project_root / "data" / "subang_jaya_osrm_network.json"
        )
        expected = required_service_sites(config) + 2
        if network.service_count != expected:
            raise ValueError(f"expected {expected} service points, found {network.service_count}")
        return f"{network.service_count} points including depot and recycling facility"

    record("road_network", network_check)

    def state_store_check() -> str:
        store = PlanningStore(project_root / "data" / "routing_plans.sqlite3")
        try:
            result = store.connection.execute("PRAGMA quick_check").fetchone()
            if result is None or str(result[0]).lower() != "ok":
                raise RuntimeError(f"SQLite quick_check failed: {result}")
        finally:
            store.close()
        return "SQLite store opened with WAL and schema checks"

    record("planning_store", state_store_check)

    def writable_check() -> str:
        data_dir = project_root / "data"
        data_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(prefix="binsight-health-", dir=data_dir):
            pass
        return "data directory is writable"

    record("local_storage", writable_check)
    ready = all(bool(item["ok"]) for item in checks)
    return {
        "status": "READY" if ready else "NOT_READY",
        "checked_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "root": str(project_root),
        "checks": checks,
    }


def create_state_backup(root: str | Path, output_dir: str | Path | None = None) -> Path:
    """Create a timestamped, locally recoverable backup of operator state."""
    project_root = Path(root).resolve()
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    destination = (
        Path(output_dir).resolve()
        if output_dir is not None
        else project_root / "data" / "backups" / timestamp
    )
    destination.mkdir(parents=True, exist_ok=False)
    database_paths = [project_root / "data" / "routing_plans.sqlite3"]
    database_paths.extend(
        sorted((project_root / "data").glob("pr2_forecast_history_*.sqlite3"))
    )
    for database in database_paths:
        if not database.exists():
            continue
        source_connection = sqlite3.connect(database)
        target_connection = sqlite3.connect(destination / database.name)
        try:
            source_connection.backup(target_connection)
        finally:
            target_connection.close()
            source_connection.close()
    for name in (
        "last_valid_sensor_readings.json",
        "mock_truck_dispatches.jsonl",
    ):
        source = project_root / "data" / name
        if source.exists():
            shutil.copy2(source, destination / name)
    for source in sorted((project_root / "data").glob("pr2_forecast_state_*.json")):
        shutil.copy2(source, destination / source.name)
    manifest = {
        "created_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "source_root": str(project_root),
        "files": sorted(path.name for path in destination.iterdir()),
    }
    (destination / "backup_manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    return destination
