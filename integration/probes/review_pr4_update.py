"""Review a PR4 checkout without changing it. Exit 1 means review checks failed."""

import argparse
from copy import deepcopy
import hashlib
import importlib
import importlib.metadata
import json
import math
from pathlib import Path
import platform
import subprocess
import sys
import tempfile
from unittest.mock import patch


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pr4-root", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    root = args.pr4_root.resolve()
    sys.path.insert(0, str(root / "ml"))
    package = importlib.import_module("binsight_ml")
    serve = importlib.import_module(package.ForecastProvider.__module__)
    pd = importlib.import_module("pandas")
    bundle = root / "ml" / "binsight_ml" / "models"
    manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
    results = []

    def check(name, run, predicate):
        try:
            actual = run()
            passed = bool(predicate(actual))
        except Exception as exc:
            actual = {"error": type(exc).__name__, "message": str(exc)}
            passed = False
        results.append({"check": name, "passed": passed, "actual": actual})

    def guard(change=lambda m: None, runtime_changes=None, feature_override=None):
        candidate = deepcopy(manifest)
        change(candidate)
        runtime = dict(manifest["dependencies"])
        runtime.update(runtime_changes or {})
        features = feature_override or manifest["feature_columns"]
        payload = b"review-placeholder-not-a-pickle"
        candidate["sha256_checksum"] = hashlib.sha256(payload).hexdigest()
        # No pickle is loaded in guard tests. The allowed class name isolates pre-load checks.
        model_stub = type("XGBRegressor", (), {})()

        def version(name):
            if name not in runtime or runtime[name] is None:
                raise importlib.metadata.PackageNotFoundError(name)
            return runtime[name]

        with tempfile.TemporaryDirectory(prefix="binsight-pr4-guard-") as folder:
            path = Path(folder)
            (path / "overflow_model.joblib").write_bytes(payload)
            (path / "manifest.json").write_text(json.dumps(candidate), encoding="utf-8")
            (path / "feature_columns.json").write_text(json.dumps(features), encoding="utf-8")
            error = None
            with (
                patch.object(serve.joblib, "load", return_value=model_stub) as loader,
                patch("importlib.metadata.version", side_effect=version),
                patch("importlib.import_module", side_effect=ModuleNotFoundError("review missing package")),
            ):
                try:
                    serve.ForecastProvider(path)
                except Exception as exc:
                    error = type(exc).__name__ + ": " + str(exc)
            return {"load_calls": loader.call_count, "error": error}

    def refused(result):
        return result["load_calls"] == 0 and result["error"] is not None

    check("matching_metadata_reaches_loader", guard, lambda r: r["load_calls"] == 1 and r["error"] is None)
    check("numpy_major_mismatch_rejected", lambda: guard(runtime_changes={"numpy": "1.26.4"}), refused)
    check("xgboost_patch_mismatch_rejected", lambda: guard(runtime_changes={"xgboost": "3.4.0"}), refused)
    check("missing_dependency_rejected", lambda: guard(runtime_changes={"numpy": None}), refused)
    check("incomplete_dependency_manifest_rejected", lambda: guard(lambda m: m.update(dependencies={"numpy": m["dependencies"]["numpy"]})), refused)
    check("malformed_dependency_version_rejected", lambda: guard(lambda m: m["dependencies"].update(numpy="2.5.1garbage")), refused)
    check("unknown_schema_rejected", lambda: guard(lambda m: m.update(schema_version="99")), refused)
    check("missing_target_definition_rejected", lambda: guard(lambda m: m.pop("target_definitions")), refused)
    check("unsupported_target_definition_rejected", lambda: guard(lambda m: m["target_definitions"].update(service_threshold_pct=100.0, supported_thresholds=[100.0])), refused)
    check("runtime_feature_mismatch_rejected", lambda: guard(lambda m: m.update(feature_columns=["not_a_runtime_feature"]), feature_override=["not_a_runtime_feature"]), refused)
    check("missing_availability_provenance_rejected", lambda: guard(lambda m: [m.pop(k, None) for k in ("training_data_cutoff", "selection_data_cutoff", "model_availability_after", "trained_at")]), refused)
    check("availability_before_selection_rejected", lambda: guard(lambda m: m.update(model_availability_after="2026-02-01T00:00:00Z")), refused)
    check("unknown_estimator_rejected", lambda: guard(lambda m: m.update(estimator_class="UnreviewedRegressor")), refused)
    check("test_doubles_not_in_production_allowlist", lambda: sorted(serve.ALLOWED_ESTIMATOR_CLASSES), lambda r: not ({"ReviewModel", "TwelveHourModel"} & set(r)))

    # The inference checks use the reviewed, checksum-verified shipped bundle.
    provider = package.ForecastProvider()

    def history():
        return pd.DataFrame([
            {"bin_id": "general-1", "timestamp": "2026-03-20T09:00:00Z", "received_at": "2026-03-20T09:00:01Z", "fill_pct": 20.0, "confidence_flag": 1},
            {"bin_id": "general-1", "timestamp": "2026-03-20T10:00:00Z", "received_at": "2026-03-20T10:00:01Z", "fill_pct": 30.0, "confidence_flag": 1},
        ])

    def snapshot(frame=None, **kwargs):
        options = {"bins": ["general-1"], "decision_at": "2026-03-20T11:00:00Z", "input_snapshot_id": "review-only"}
        options.update(kwargs)
        return provider.predict_snapshot(history() if frame is None else frame, **options)

    def record(frame=None, **kwargs):
        value = snapshot(frame, **kwargs)
        return value[0] if isinstance(value, list) else value

    baseline = record()
    check("normal_history_available", lambda: baseline, lambda r: r["status"] == "available")
    check("unsupported_threshold_preserves_bin", lambda: record(target_threshold_pct=100), lambda r: r["bin_id"] == "general-1" and r["status"] == "unsupported_threshold")
    check("selection_window_unavailable", lambda: record(decision_at="2026-03-02T12:00:00Z"), lambda r: r["status"] == "model_unavailable")
    check("decision_offset_equivalence", lambda: record(decision_at="2026-03-20T19:00:00+08:00"), lambda r: r["status"] == baseline["status"] and r["time_to_service_threshold_hours"] == baseline["time_to_service_threshold_hours"])

    local = history()
    local["timestamp"] = ["2026-03-20T17:00:00+08:00", "2026-03-20T18:00:00+08:00"]
    local["received_at"] = ["2026-03-20T17:00:01+08:00", "2026-03-20T18:00:01+08:00"]
    check("observation_offset_equivalence", lambda: record(local), lambda r: r["status"] == baseline["status"] and r["time_to_service_threshold_hours"] == baseline["time_to_service_threshold_hours"] and r["horizons"] == baseline["horizons"])
    mixed = history()
    mixed.loc[1, "timestamp"] = local.loc[1, "timestamp"]
    check("mixed_observation_offsets", lambda: record(mixed), lambda r: r["status"] == "available" and r["time_to_service_threshold_hours"] == baseline["time_to_service_threshold_hours"])

    check("all_low_confidence_degraded", lambda: record(history().assign(confidence_flag=0)), lambda r: r["status"] == "low_confidence")
    faulty = history()
    faulty.loc[1, ["fill_pct", "confidence_flag"]] = [95.0, 0]
    check("latest_low_confidence_not_available", lambda: record(faulty), lambda r: r["status"] != "available")
    unknown = history()
    unknown.loc[1, "fill_pct"] = float("nan")
    check("unknown_fill_not_available", lambda: record(unknown), lambda r: r["status"] != "available")
    check("unknown_fill_record_json_safe", lambda: json.dumps(record(unknown), allow_nan=False), lambda r: bool(r))
    duplicates = pd.concat([history().iloc[[0]]] * 2, ignore_index=True)
    check("duplicate_only_history_cold_start", lambda: record(duplicates), lambda r: r["status"] == "cold_start")
    check("single_old_reading_stale", lambda: record(history().iloc[[0]], decision_at="2026-08-29T12:00:00Z"), lambda r: r["status"] == "stale")
    late = history()
    late.loc[1, "received_at"] = "2026-03-20T12:00:00Z"
    check("late_receipt_excluded", lambda: record(late), lambda r: r["fill_pct"] == 20.0)
    check("missing_configured_bin_identified", lambda: snapshot(bins=["general-1", "recycling-1"]), lambda r: len(r) == 2 and r[1]["bin_id"] == "recycling-1" and r[1]["status"] == "unavailable")
    check("probabilities_remain_unsupported", lambda: baseline["horizons"], lambda r: all(v["overflow_probability"] is None and v["overflow_probability_status"] == "unsupported" for v in r.values()))

    versions = {name: importlib.metadata.version(name) for name in manifest["dependencies"]}
    report = {
        "source_head": subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip(),
        "python": platform.python_version(),
        "runtime_dependencies": versions,
        "manifest_dependencies": manifest["dependencies"],
        "exact_manifest_runtime": versions == manifest["dependencies"],
        "model_sha256": provider.model_sha256,
        "passed": sum(r["passed"] for r in results),
        "failed": sum(not r["passed"] for r in results),
        "checks": results,
    }

    def json_safe(value):
        if isinstance(value, float) and not math.isfinite(value):
            return str(value)
        if isinstance(value, dict):
            return {k: json_safe(v) for k, v in value.items()}
        if isinstance(value, list):
            return [json_safe(v) for v in value]
        return value

    rendered = json.dumps(json_safe(report), indent=2, default=str, allow_nan=False)
    if args.output:
        args.output.write_text(rendered + "\n", encoding="utf-8")
        print(json.dumps({k: report[k] for k in ("source_head", "exact_manifest_runtime", "passed", "failed")}))
        for result in results:
            print(("PASS " if result["passed"] else "FAIL ") + result["check"])
    else:
        print(rendered)
    return int(report["failed"] > 0)


if __name__ == "__main__":
    raise SystemExit(main())
