"""Inspect a reviewed PR4 source tree with a stub model; never unpickle its artifact.

Run with the reviewed Python environment and --ml-root pointing to an isolated
PR4 checkout. This diagnostic is not the future provider contract test suite.
"""

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

import numpy as np
import pandas as pd


class TwelveHourModel:
    def predict(self, frame):
        return np.full(len(frame), 12.0)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ml-root", required=True, type=Path)
    args = parser.parse_args()
    root = args.ml_root.resolve()
    spec = importlib.util.spec_from_file_location(
        "binsight_review_ml", root / "__init__.py", submodule_search_locations=[str(root)],
    )
    package = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = package
    spec.loader.exec_module(package)
    provider = package.ForecastProvider.__new__(package.ForecastProvider)
    provider.model = TwelveHourModel()
    provider.feature_columns = package.FEATURE_COLUMNS
    provider.manifest = json.loads((root / "models/manifest.json").read_text(encoding="utf-8"))
    provider.model_version = "review-stub-not-a-trained-model"
    provider.model_sha256 = "review-stub"

    history = pd.DataFrame([
        {"bin_id": "bin_01", "timestamp": "2026-01-02T09:00:00Z", "received_at": "2026-01-02T09:00:01Z", "fill_pct": 20.0, "confidence_flag": 1},
        {"bin_id": "bin_01", "timestamp": "2026-01-02T10:00:00Z", "received_at": "2026-01-02T10:00:01Z", "fill_pct": 30.0, "confidence_flag": 1},
    ])
    features = package.build_feature_table(history)
    mean, upper = provider.predict(features)
    result = {
        "model": "constant 12-hour test double; no artifact deserialised",
        "fill_only_feature_values_finite": bool(np.isfinite(features[package.FEATURE_COLUMNS].to_numpy()).all()),
        "compatibility_mean_growth_from_12_hour_output": mean.tolist(),
        "compatibility_upper_growth": upper.tolist(),
        "compatibility_probability_48h": provider.predict_overflow_probability_48h(features).tolist(),
    }
    requested = provider.predict_from_history(history, target_threshold_pct=100.0)
    result["requested_100_with_90_trained_manifest"] = {
        key: requested.get(key) for key in ("status", "target_threshold_pct", "time_to_overflow_hours")
    }
    historical = provider.predict_snapshot(history, decision_at="2026-01-02T11:00:00Z")
    result["historical_request_before_manifest_training_end"] = historical.get("status")
    late = history.copy()
    late.loc[1, "received_at"] = "2026-01-02T12:00:00Z"
    received = provider.predict_snapshot(late, decision_at="2026-01-02T11:00:00Z")
    result["latest_fill_with_receipt_after_cutoff"] = received.get("fill_pct")
    stale = provider.predict_snapshot(history, decision_at="2026-08-28T11:00:00Z")
    result["old_history_status"] = stale.get("status")

    serving = sys.modules[package.ForecastProvider.__module__]
    with tempfile.TemporaryDirectory(prefix="binsight-manifest-probe-") as directory:
        model_dir = Path(directory)
        (model_dir / "overflow_model.joblib").write_bytes(b"test-double-only")
        (model_dir / "feature_columns.json").write_text(json.dumps(package.FEATURE_COLUMNS), encoding="utf-8")
        (model_dir / "manifest.json").write_text(json.dumps({"sha256_checksum": "0" * 64}), encoding="utf-8")
        with patch.object(serving.joblib, "load", return_value=TwelveHourModel()) as load:
            try:
                package.ForecastProvider(model_dir)
            except ValueError:
                pass
            result["load_calls_before_bad_checksum_rejected"] = load.call_count

    artifact = root / "models/overflow_model.joblib"
    result["committed_artifact_checksum_matches_manifest"] = (
        hashlib.sha256(artifact.read_bytes()).hexdigest() == provider.manifest["sha256_checksum"]
    )
    print(json.dumps(result, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
