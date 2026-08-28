"""Reproduce PR2/PR4 boundary failures without hardware or model deserialization."""

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
from unittest.mock import Mock, patch

import numpy as np
import pandas as pd


class ReviewModel:
    def predict(self, frame):
        return np.full(len(frame), 12.0)


def load_module(name, path, package=False):
    spec = importlib.util.spec_from_file_location(
        name, path,
        submodule_search_locations=[str(path.parent)] if package else None,
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def review_pr2(root):
    bridge = load_module("review_bridge", root / "hardware_pipeline/tools/serial_bridge.py")
    with tempfile.TemporaryDirectory(prefix="binsight-queue-probe-") as directory:
        bridge.QUEUE_FILE = str(Path(directory) / "pending.jsonl")
        bridge.enqueue_pending({"bin_id": "synthetic-bin", "fill_pct": 80})
        response = Mock(status_code=503, text="test server unavailable")
        with patch.object(bridge.requests, "post", return_value=response):
            bridge.flush_pending("http://127.0.0.1:8000", "fictional-probe-key")
        return {"queue_preserved_after_http_503": Path(bridge.QUEUE_FILE).exists()}


def review_pr1(root):
    routing = load_module("review_routing", root / "admin-portal/binsight/routing.py")
    arguments = dict(
        candidate_bin_indices=[0, 1], mandatory_bin_indices=[],
        demands_kg=np.array([10.0, 10.0]), demands_m3=np.array([1.0, 1.0]),
        full_distance_matrix_m=np.array([[0, 100, 10], [10, 0, 100], [100, 10, 0]]),
        full_duration_matrix_s=np.array([[0, 1, 2], [100, 0, 1], [1, 2, 0]]),
        skip_penalties_m_equivalent=np.array([100000.0, 100000.0]),
        truck_capacity_kg=100, truck_capacity_m3=10, max_trips=1,
        service_seconds_per_bin=0, max_route_duration_seconds=10,
        fixed_trip_cost_m_equivalent=0, travel_time_cost_m_per_minute=0,
        service_cost_m_per_minute=0, additional_service_cost_m_equivalent=np.zeros(2),
        solver_milliseconds=100,
    )
    baseline = routing.solve_value_routes(**arguments)
    optimized = routing.solve_value_routes(**arguments, post_optimize=True)
    return {
        "configured_duration_limit_seconds": 10,
        "normal_route_duration_seconds": baseline.route_duration_s,
        "post_optimized_route_duration_seconds": optimized.route_duration_s,
        "flag_is_disabled_in_committed_config": not json.loads((root / "admin-portal/config.json").read_text())["operations"]["route_post_optimization_enabled"],
    }


def review_pr4(root):
    package = load_module("review_provider_v2", root / "ml/__init__.py", package=True)
    provider_class = package.ForecastProvider
    provider = provider_class.__new__(provider_class)
    provider.model = ReviewModel()
    provider.feature_columns = package.FEATURE_COLUMNS
    provider.manifest = json.loads((root / "ml/models/manifest.json").read_text(encoding="utf-8"))
    provider.model_version = "constant-test-double"
    provider.model_sha256 = "not-a-model-artifact"
    provider.training_data_cutoff = provider.manifest["training_data_cutoff"]
    provider.supported_thresholds = {90.0}
    history = pd.DataFrame([
        {"bin_id": "bin_01", "timestamp": "2026-03-02T09:00:00Z", "fill_pct": 20.0, "confidence_flag": 1},
        {"bin_id": "bin_01", "timestamp": "2026-03-02T10:00:00Z", "fill_pct": 30.0, "confidence_flag": 1},
    ])
    unsupported = provider.predict_snapshot(history, bins=["bin_01"], decision_at="2026-03-02T11:00:00Z", target_threshold_pct=100)
    historical = provider.predict_snapshot(history, bins=["bin_01"], decision_at="2026-03-02T11:00:00Z")
    low_quality = history.assign(confidence_flag=0)
    low = provider.predict_snapshot(low_quality, bins=["bin_01"], decision_at="2026-03-02T11:00:00Z")
    cold = provider.predict_snapshot(history.head(1), bins=["bin_01"], decision_at="2026-08-28T11:00:00Z")
    result = {
        "model": "constant 12-hour test double; no artifact deserialized",
        "unsupported_threshold_bin_id": unsupported[0]["bin_id"],
        "decision_during_model_selection_period_status": historical[0]["status"],
        "all_low_confidence_status": low[0]["status"],
        "months_old_single_reading_status": cold[0]["status"],
    }
    provider.training_data_cutoff = "2026-03-02T10:30:00Z"
    for label, cutoff in (("utc", "2026-03-02T10:00:00Z"), ("myt", "2026-03-02T18:00:00+08:00")):
        result[f"equivalent_cutoff_{label}"] = provider.predict_snapshot(history, bins=["bin_01"], decision_at=cutoff)[0]["status"]
    with tempfile.TemporaryDirectory(prefix="binsight-loader-probe-") as directory:
        folder = Path(directory)
        data = b"test-double-only"
        (folder / "overflow_model.joblib").write_bytes(data)
        (folder / "feature_columns.json").write_text(json.dumps(package.FEATURE_COLUMNS), encoding="utf-8")
        manifest = dict(provider.manifest, sha256_checksum=hashlib.sha256(data).hexdigest(), estimator_class="ReviewModel", dependencies={"numpy": "0.0.0-impossible"})
        (folder / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        serving = sys.modules[provider_class.__module__]
        with patch.object(serving.joblib, "load", return_value=ReviewModel()) as loader:
            provider_class(folder)
            result["load_calls_with_incompatible_dependencies"] = loader.call_count
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pr2-root", type=Path, required=True)
    parser.add_argument("--pr4-root", type=Path, required=True)
    parser.add_argument("--pr1-root", type=Path)
    args = parser.parse_args()
    result = {"pr2": review_pr2(args.pr2_root.resolve()), "pr4": review_pr4(args.pr4_root.resolve())}
    if args.pr1_root:
        result["pr1"] = review_pr1(args.pr1_root.resolve())
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
