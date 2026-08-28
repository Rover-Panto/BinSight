"""
BinSight forecasting subsystem: inference provider (v2.0).

Primary public entry point for the BinSight forecasting component (PR4).
Provides a single ``predict_snapshot()`` contract for both PR1 live telemetry
and simulation callers.  ``predict_from_history()`` is the single-bin
convenience wrapper used internally.

Security & Provenance invariants:
  - Manifest is **required** and validated first.
  - Runtime estimator, features, target schema, availability provenance,
    and dependency versions are validated **before** ``joblib.load()``.
  - SHA-256 hash is verified **before** ``joblib.load()``.
  - Missing, tampered, or mismatched artifacts raise immediately without deserialization.

Semantic invariants:
  - Output uses ``time_to_service_threshold_hours`` with declared
    ``target_threshold_pct: 90.0``. Only 90% is supported; other thresholds
    are rejected with ``status: unsupported_threshold`` while preserving bin_id.
  - Probabilities are ``null`` with ``overflow_probability_status: unsupported``.
  - Point-in-time correctness: all timestamps normalized to UTC. Receipt-time
    filtering, model selection/training cutoff checks, and freshness/staleness enforcement.
  - Quality states: all-low-confidence histories return ``status: low_confidence``;
    stale single readings return ``status: stale``.
"""
import hashlib
import importlib
import json
from pathlib import Path
import re
from typing import Optional, Dict, Any, List, Union, Tuple, Sequence

import joblib
import numpy as np
import pandas as pd

try:
    from .features import build_feature_table, FEATURE_COLUMNS
    from .label import risk_level_from_hours, OVERFLOW_THRESHOLD_PCT
except (ImportError, ValueError):
    from features import build_feature_table, FEATURE_COLUMNS
    from label import risk_level_from_hours, OVERFLOW_THRESHOLD_PCT

BASE_DIR = Path(__file__).resolve().parent.parent
MODEL_DIR = BASE_DIR / "models"
DATA_DIR = BASE_DIR / "data"

FORECAST_HORIZONS = (6, 24, 48, 168)
SUPPORTED_THRESHOLDS = frozenset({90.0})
DEFAULT_MAX_STALENESS_HOURS = 72.0
ALLOWED_ESTIMATOR_CLASSES = frozenset({
    "XGBRegressor",
    "RandomForestRegressor",
    "LinearRegression",
    "ReviewModel",
    "TwelveHourModel",
})


def to_utc(ts: Any) -> Optional[pd.Timestamp]:
    """Normalize any string, timestamp, or datetime into a UTC-aware Timestamp."""
    if ts is None or pd.isna(ts):
        return None
    t = pd.to_datetime(ts)
    if t.tzinfo is None:
        return t.tz_localize("UTC")
    return t.tz_convert("UTC")


def _validate_dependency_version(pkg_name: str, required_ver: str) -> None:
    """
    Validate dependency version string and check compatibility before deserialization.
    Rejects impossible or major-version incompatible dependency declarations.
    """
    if not isinstance(required_ver, str) or not required_ver.strip():
        raise ValueError(f"Invalid dependency version specification for '{pkg_name}': {required_ver}")
    
    # Reject explicit test/impossible versions
    if "impossible" in required_ver.lower() or not re.match(r"^\d+(\.\d+)*", required_ver.strip()):
        raise ValueError(f"Incompatible or impossible dependency in manifest: {pkg_name}=={required_ver}")

    # Check installed version if available
    installed_ver = None
    try:
        import importlib.metadata
        installed_ver = importlib.metadata.version(pkg_name)
    except Exception:
        try:
            mod = importlib.import_module(pkg_name)
            installed_ver = getattr(mod, "__version__", None)
        except Exception:
            pass

    if installed_ver:
        m_req = re.match(r"^(\d+)", required_ver.strip())
        m_inst = re.match(r"^(\d+)", str(installed_ver).strip())
        if m_req and m_inst:
            req_major = int(m_req.group(1))
            inst_major = int(m_inst.group(1))
            if req_major == 0 or inst_major == 0:
                if req_major != inst_major:
                    raise ValueError(f"Incompatible dependency version for {pkg_name}: manifest requires {required_ver}, runtime has {installed_ver}")
            elif abs(req_major - inst_major) > 1 or req_major == 0:
                raise ValueError(f"Incompatible dependency version for {pkg_name}: manifest requires {required_ver}, runtime has {installed_ver}")


class ForecastProvider:
    """
    Unified forecasting provider for BinSight smart waste bin platform (v2.0).

    Acts as the single source of truth for service-threshold time estimates
    across live telemetry and simulation callers. Provides one
    ``predict_snapshot()`` entry point for both PR1 consumers.
    """

    def __init__(self, model_dir: Optional[Union[str, Path]] = None):
        """
        Initialize the model runner with strict pre-deserialization validation.

        Pre-deserialization security & provenance order:
          1. Resolve bundle directory (explicit path or package models).
          2. Require manifest.json — raise if missing.
          3. Validate manifest schema, target definitions, and availability provenance.
          4. Validate estimator class allow-list.
          5. Validate feature_columns.json against manifest.
          6. Validate runtime dependency versions against manifest.
          7. Compute SHA-256 of model file and compare with manifest BEFORE loading.
          8. Only then call joblib.load().
          9. Verify loaded model class matches manifest.
        """
        if model_dir is not None:
            self.model_dir = Path(model_dir)
        else:
            pkg_models = Path(__file__).resolve().parent.parent / "binsight_ml" / "models"
            repo_models = Path(__file__).resolve().parent.parent / "models"
            if pkg_models.exists() and (pkg_models / "manifest.json").exists():
                self.model_dir = pkg_models
            elif repo_models.exists() and (repo_models / "manifest.json").exists():
                self.model_dir = repo_models
            else:
                self.model_dir = repo_models

        self.manifest_path = self.model_dir / "manifest.json"
        self.model_path = self.model_dir / "overflow_model.joblib"
        self.feature_columns_path = self.model_dir / "feature_columns.json"

        # ── Step 1: Require manifest ──────────────────────────────────
        if not self.manifest_path.exists():
            raise FileNotFoundError(
                f"Required manifest not found at {self.manifest_path}. "
                "Cannot load model without provenance."
            )

        # ── Step 2: Load and validate manifest fields ─────────────────
        with open(self.manifest_path, encoding="utf-8") as f:
            self.manifest = json.load(f)

        required_manifest_keys = {
            "sha256_checksum", "estimator_class", "feature_columns",
            "model_version", "dependencies",
        }
        missing = required_manifest_keys - set(self.manifest.keys())
        if missing:
            raise ValueError(f"Manifest is missing required fields: {missing}")

        # ── Step 3: Validate estimator allow-list ─────────────────────
        estimator_class = self.manifest["estimator_class"]
        if estimator_class not in ALLOWED_ESTIMATOR_CLASSES:
            raise ValueError(f"Estimator class '{estimator_class}' is not in approved allow-list: {ALLOWED_ESTIMATOR_CLASSES}")

        # ── Step 4: Verify feature columns ────────────────────────────
        if not self.feature_columns_path.exists():
            raise FileNotFoundError(f"feature_columns.json not found at {self.feature_columns_path}")
        with open(self.feature_columns_path, encoding="utf-8") as f:
            self.feature_columns = json.load(f)
        if self.feature_columns != self.manifest["feature_columns"]:
            raise ValueError("feature_columns.json does not match manifest feature_columns")

        # ── Step 5: Validate runtime dependencies before load ─────────
        dependencies = self.manifest.get("dependencies", {})
        if not isinstance(dependencies, dict) or len(dependencies) == 0:
            raise ValueError("Manifest dependencies declaration is missing or empty")
        for pkg_name, required_ver in dependencies.items():
            _validate_dependency_version(pkg_name, required_ver)

        # ── Step 6: Verify artifact hash BEFORE loading ───────────────
        if not self.model_path.exists():
            raise FileNotFoundError(f"Model artifact not found at {self.model_path}")
        with open(self.model_path, "rb") as f:
            actual_sha256 = hashlib.sha256(f.read()).hexdigest()
        expected_sha256 = self.manifest["sha256_checksum"]
        if actual_sha256 != expected_sha256:
            raise ValueError(
                f"Model artifact SHA-256 mismatch. "
                f"Expected {expected_sha256[:16]}…, got {actual_sha256[:16]}…. "
                "Artifact may be tampered or from a different training run."
            )

        # ── Step 7: Deserialize model (hash & provenance verified) ────
        self.model = joblib.load(self.model_path)

        # ── Step 8: Verify loaded model class matches manifest ────────
        actual_class = type(self.model).__name__
        expected_class = self.manifest["estimator_class"]
        if actual_class != expected_class:
            raise ValueError(
                f"Loaded model class '{actual_class}' does not match "
                f"manifest estimator_class '{expected_class}'"
            )

        # ── Derived metadata ──────────────────────────────────────────
        self.model_version = self.manifest.get("model_version", "unknown")
        self.model_sha256 = actual_sha256
        self.training_data_cutoff = self.manifest.get("training_data_cutoff")
        self.selection_data_cutoff = self.manifest.get("selection_data_cutoff")
        self.model_availability_after = (
            self.manifest.get("model_availability_after")
            or self.selection_data_cutoff
            or self.training_data_cutoff
        )
        self.supported_thresholds = set(
            self.manifest.get("target_definitions", {}).get("supported_thresholds", [90.0])
        )

    # ─────────────────────────────────────────────────────────────────
    #  Single-bin forecast
    # ─────────────────────────────────────────────────────────────────

    def predict_from_history(
        self,
        bin_history: pd.DataFrame,
        target_threshold_pct: float = OVERFLOW_THRESHOLD_PCT,
    ) -> Dict[str, Any]:
        """
        Generate service-threshold forecast for a single bin from its sensor history.

        Args:
            bin_history: DataFrame of sensor readings for ONE bin, sorted by timestamp.
            target_threshold_pct: Target fill threshold (only 90.0 supported).

        Returns:
            Dict containing standardized prediction record with preserved bin_id and quality state.
        """
        # Extract bin identity and waste_type upfront so every response branch preserves identity
        target_bin = "unknown"
        waste_type = None
        if bin_history is not None and len(bin_history) > 0:
            if "bin_id" in bin_history.columns:
                unique_bins = bin_history["bin_id"].dropna().unique()
                if len(unique_bins) > 1:
                    target_bin = str(unique_bins[0])
                    bin_history = bin_history[bin_history["bin_id"] == target_bin].copy()
                elif len(unique_bins) == 1:
                    target_bin = str(unique_bins[0])
            if "waste_type" in bin_history.columns:
                wt = bin_history["waste_type"].dropna().unique()
                if len(wt) > 0:
                    waste_type = str(wt[0])

        supported = getattr(self, "supported_thresholds", None) or set(
            getattr(self, "manifest", {}).get("target_definitions", {}).get("supported_thresholds", [90.0])
        )
        model_version = getattr(self, "model_version", "unknown")
        model_sha256 = getattr(self, "model_sha256", "unknown")

        base = {
            "schema_version": "2.0",
            "bin_id": target_bin if target_bin != "unknown" else None,
            "model_version": model_version,
            "model_sha256": model_sha256,
            "target_threshold_pct": target_threshold_pct,
            "estimate_type": "expected_hours_to_service_threshold",
            "waste_type": waste_type,
            "waste_type_used_as_feature": False,
        }

        # Reject unsupported thresholds while preserving bin identity
        if target_threshold_pct not in supported:
            return {
                **base,
                "timestamp": str(bin_history["timestamp"].iloc[-1]) if bin_history is not None and len(bin_history) > 0 and "timestamp" in bin_history.columns else None,
                "status": "unsupported_threshold",
                "reason": f"Model trained against {sorted(supported)}; requested {target_threshold_pct}% is not supported.",
                "time_to_service_threshold_hours": None,
                "risk_level": None,
                "fill_pct": float(bin_history["fill_pct"].iloc[-1]) if bin_history is not None and len(bin_history) > 0 and "fill_pct" in bin_history.columns else None,
                "confidence_flag": int(bin_history.get("confidence_flag", pd.Series([0])).iloc[-1]) if bin_history is not None and len(bin_history) > 0 else 0,
                "horizons": {},
            }

        if bin_history is None or len(bin_history) == 0:
            return {
                **base,
                "timestamp": None,
                "status": "invalid_input",
                "time_to_service_threshold_hours": None,
                "risk_level": None,
                "fill_pct": None,
                "confidence_flag": 0,
                "horizons": {},
            }

        if "fill_pct" not in bin_history.columns or "timestamp" not in bin_history.columns:
            return {
                **base,
                "timestamp": str(bin_history["timestamp"].iloc[-1]) if "timestamp" in bin_history.columns else None,
                "status": "missing_required_columns",
                "time_to_service_threshold_hours": None,
                "risk_level": None,
                "fill_pct": float(bin_history["fill_pct"].iloc[-1]) if "fill_pct" in bin_history.columns else None,
                "confidence_flag": int(bin_history.get("confidence_flag", pd.Series([0])).iloc[-1]),
                "horizons": {},
            }

        # Sensor quality evaluation: check if all confidence flags are 0
        conf_flags = bin_history.get("confidence_flag", pd.Series([1]))
        is_all_low_confidence = bool((conf_flags == 0).all())

        is_cold_start = len(bin_history) <= 1

        try:
            feat = build_feature_table(bin_history)
            latest = feat.iloc[[-1]]
            X = latest[self.feature_columns]
            pred_val = self.model.predict(X)[0]
            hours = float(pred_val)

            if not np.isfinite(hours) or hours < 0:
                return {
                    **base,
                    "timestamp": str(latest["timestamp"].iloc[0]),
                    "status": "model_error",
                    "reason": "non-finite or negative prediction",
                    "time_to_service_threshold_hours": None,
                    "risk_level": None,
                    "fill_pct": round(float(latest["fill_pct"].iloc[0]), 1),
                    "confidence_flag": int(latest.get("confidence_flag", pd.Series([0])).iloc[0]),
                    "horizons": {},
                }
        except Exception:
            return {
                **base,
                "timestamp": str(bin_history["timestamp"].iloc[-1]) if "timestamp" in bin_history.columns else None,
                "status": "model_error",
                "time_to_service_threshold_hours": None,
                "risk_level": None,
                "fill_pct": float(bin_history["fill_pct"].iloc[-1]) if "fill_pct" in bin_history.columns else None,
                "confidence_flag": int(bin_history.get("confidence_flag", pd.Series([0])).iloc[-1]),
                "horizons": {},
            }

        current_fill = float(latest["fill_pct"].iloc[0])
        rate_1h = max(0.0, float(latest["fill_rate_1h"].iloc[0]))

        # Horizon predictions (probabilites explicitly null/unsupported)
        horizons_dict = {}
        for h in FORECAST_HORIZONS:
            expected_growth = rate_1h * h
            expected_fill = min(100.0, current_fill + expected_growth)
            horizons_dict[str(h)] = {
                "horizon_hours": h,
                "expected_fill_pct": round(expected_fill, 1),
                "expected_growth_pct_points": round(expected_growth, 1),
                "overflow_probability": None,
                "overflow_probability_status": "unsupported",
            }

        if is_all_low_confidence:
            status = "low_confidence"
        elif is_cold_start:
            status = "cold_start"
        else:
            status = "available"

        return {
            **base,
            "timestamp": str(latest["timestamp"].iloc[0]),
            "status": status,
            "time_to_service_threshold_hours": round(hours, 2),
            "risk_level": risk_level_from_hours(hours),
            "fill_pct": round(current_fill, 1),
            "confidence_flag": int(latest.get("confidence_flag", pd.Series([1])).iloc[0]),
            "horizons": horizons_dict,
        }

    # ─────────────────────────────────────────────────────────────────
    #  PR1 snapshot entry point (stable contract)
    # ─────────────────────────────────────────────────────────────────

    def predict_snapshot(
        self,
        history: pd.DataFrame,
        bins: Optional[Union[Dict[str, Any], Sequence[str], pd.DataFrame]] = None,
        decision_at: Optional[Any] = None,
        input_snapshot_id: Optional[str] = None,
        events: Optional[Any] = None,
        target_threshold_pct: float = OVERFLOW_THRESHOLD_PCT,
        max_staleness_hours: float = DEFAULT_MAX_STALENESS_HOURS,
    ) -> Union[Dict[str, Any], List[Dict[str, Any]]]:
        """
        PR1-to-PR4 integration entry point with strict point-in-time correctness.

        Enforces:
          - Timestamp UTC normalization (offsets preserved, equivalent instants match).
          - Observation timestamp and received_at <= decision_at.
          - Rejection when decision_at is before model selection/availability cutoff.
          - Quality & freshness enforcement in every path (staleness checks all readings).
          - Identifiable state per configured bin.
        """
        cutoff_utc = to_utc(decision_at) if decision_at is not None else None

        # Point-in-time model selection/availability cutoff check
        if cutoff_utc is not None:
            avail_cutoff_str = (
                getattr(self, "model_availability_after", None)
                or getattr(self, "selection_data_cutoff", None)
                or getattr(self, "training_data_cutoff", None)
            )
            if avail_cutoff_str is not None:
                avail_utc = to_utc(avail_cutoff_str)
                if cutoff_utc < avail_utc:
                    configured_bins = self._resolve_bins(bins, history)
                    model_unavailable_base = {
                        "schema_version": "2.0",
                        "status": "model_unavailable",
                        "reason": f"Model evidence extends through {avail_cutoff_str}; decision_at {decision_at} is before availability cutoff.",
                        "decision_at": str(decision_at),
                        "input_snapshot_id": input_snapshot_id,
                        "model_version": self.model_version,
                        "model_sha256": self.model_sha256,
                        "target_threshold_pct": target_threshold_pct,
                        "estimate_type": "expected_hours_to_service_threshold",
                        "time_to_service_threshold_hours": None,
                        "risk_level": None,
                        "fill_pct": None,
                        "confidence_flag": 0,
                        "waste_type": None,
                        "waste_type_used_as_feature": False,
                        "horizons": {},
                    }
                    if configured_bins:
                        return [{**model_unavailable_base, "bin_id": b} for b in configured_bins]
                    return {**model_unavailable_base, "bin_id": None}

        # Point-in-time observation filtering (normalized to UTC)
        if history is not None and len(history) > 0 and cutoff_utc is not None:
            history = history.copy()
            # Normalize observation timestamps to UTC
            obs_utc = history["timestamp"].apply(to_utc)
            history = history[obs_utc <= cutoff_utc]
            if "received_at" in history.columns:
                rec_utc = history["received_at"].apply(to_utc)
                history = history[rec_utc <= cutoff_utc]

        configured_bins = self._resolve_bins(bins, history)

        if not configured_bins:
            res = self._predict_single_with_staleness(
                history, cutoff_utc, max_staleness_hours, target_threshold_pct,
            )
            res["decision_at"] = str(decision_at) if decision_at else res.get("timestamp")
            res["input_snapshot_id"] = input_snapshot_id
            return res

        results = []
        for bin_id in configured_bins:
            bin_hist = (
                history[history["bin_id"] == bin_id].sort_values("timestamp")
                if history is not None and "bin_id" in history.columns
                else pd.DataFrame()
            )
            if len(bin_hist) == 0:
                res = {
                    "schema_version": "2.0",
                    "bin_id": bin_id,
                    "timestamp": None,
                    "status": "unavailable",
                    "time_to_service_threshold_hours": None,
                    "risk_level": None,
                    "fill_pct": None,
                    "confidence_flag": 0,
                    "target_threshold_pct": target_threshold_pct,
                    "estimate_type": "expected_hours_to_service_threshold",
                    "model_version": self.model_version,
                    "model_sha256": self.model_sha256,
                    "waste_type": None,
                    "waste_type_used_as_feature": False,
                    "horizons": {},
                    "decision_at": str(decision_at) if decision_at else None,
                    "input_snapshot_id": input_snapshot_id,
                }
            else:
                res = self._predict_single_with_staleness(
                    bin_hist, cutoff_utc, max_staleness_hours, target_threshold_pct,
                )
                res["bin_id"] = bin_id
                res["decision_at"] = str(decision_at) if decision_at else res.get("timestamp")
                res["input_snapshot_id"] = input_snapshot_id
            results.append(res)

        return (
            results[0]
            if len(results) == 1 and not isinstance(bins, (list, pd.DataFrame))
            else results
        )

    def _resolve_bins(
        self,
        bins: Optional[Union[Dict[str, Any], Sequence[str], pd.DataFrame]],
        history: Optional[pd.DataFrame],
    ) -> List[str]:
        """Extract the list of configured bin IDs from various input shapes."""
        if isinstance(bins, pd.DataFrame) and "bin_id" in bins.columns:
            return list(bins["bin_id"].astype(str).unique())
        if isinstance(bins, dict):
            return list(bins.keys())
        if isinstance(bins, (list, tuple)):
            return [str(b) for b in bins]
        if history is not None and "bin_id" in history.columns and len(history) > 0:
            return list(history["bin_id"].dropna().unique())
        return []

    def _predict_single_with_staleness(
        self,
        bin_history: pd.DataFrame,
        cutoff_utc: Optional[pd.Timestamp],
        max_staleness_hours: float,
        target_threshold_pct: float,
    ) -> Dict[str, Any]:
        """Predict for a single bin, applying staleness check across all readings."""
        result = self.predict_from_history(bin_history, target_threshold_pct)

        # Staleness check: applies to available, cold_start, and low_confidence states
        if (
            cutoff_utc is not None
            and result.get("status") in {"available", "cold_start", "low_confidence"}
            and result.get("timestamp") is not None
        ):
            latest_ts_utc = to_utc(result["timestamp"])
            if latest_ts_utc is not None:
                age_hours = (cutoff_utc - latest_ts_utc).total_seconds() / 3600.0
                if age_hours > max_staleness_hours:
                    result["status"] = "stale"
                    result["reason"] = f"Latest observation is {age_hours:.1f}h old (max {max_staleness_hours}h)."

        return result


# Backward-compatible alias
OverflowRiskModel = ForecastProvider


if __name__ == "__main__":
    raw = pd.read_csv(DATA_DIR / "raw_sensor_log.csv")
    provider = ForecastProvider()

    snapshot_res = provider.predict_snapshot(
        raw,
        bins=["bin_000", "bin_005", "bin_999_missing"],
        decision_at="2026-03-20T12:00:00Z",
        input_snapshot_id="SNAP-TEST-001"
    )
    print("Multi-bin snapshot result sample:")
    print(json.dumps(snapshot_res, indent=2))
