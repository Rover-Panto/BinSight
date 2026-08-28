"""
BinSight forecasting subsystem: inference provider (v2.0).

Primary public entry point for the BinSight forecasting component (PR4).
Provides a single ``predict_snapshot()`` contract for both PR1 live telemetry
and simulation callers.  ``predict_from_history()`` is the single-bin
convenience wrapper used internally.

Security invariants (Item 5):
  - Manifest is **required** and loaded first.
  - SHA-256 hash is verified **before** ``joblib.load()``.
  - Missing, tampered or mismatched artifacts raise immediately.

Semantic invariants (Items 1, 2, 4):
  - Output uses ``time_to_service_threshold_hours`` with declared
    ``target_threshold_pct: 90``.  Only 90% is supported; other thresholds
    are rejected with ``status: unsupported_threshold``.
  - Probabilities are ``null`` with ``overflow_probability_status: unsupported``
    until a calibrated model is trained.
  - Point-in-time correctness: receipt-time filtering, model-training cutoff
    checks, and freshness/staleness enforcement.
"""
import hashlib
import json
from pathlib import Path
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


class ForecastProvider:
    """
    Unified forecasting provider for BinSight smart waste bin platform (v2.0).

    Acts as the single source of truth for service-threshold time estimates
    across live telemetry and simulation callers.  Provides one
    ``predict_snapshot()`` entry point for both PR1 consumers.
    """

    def __init__(self, model_dir: Path = MODEL_DIR):
        """
        Initialize the model runner with strict pre-deserialization validation.

        Loading order (Item 5 — fail closed):
          1. Require manifest.json — raise if missing.
          2. Load and validate manifest fields.
          3. Verify feature_columns.json matches manifest.
          4. Compute SHA-256 of model file **before** joblib.load().
          5. Only then deserialize the model.
          6. Verify loaded model class matches manifest.
        """
        self.model_dir = Path(model_dir)
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

        # ── Step 3: Verify feature columns ────────────────────────────
        if not self.feature_columns_path.exists():
            raise FileNotFoundError(
                f"feature_columns.json not found at {self.feature_columns_path}"
            )
        with open(self.feature_columns_path, encoding="utf-8") as f:
            self.feature_columns = json.load(f)
        if self.feature_columns != self.manifest["feature_columns"]:
            raise ValueError(
                "feature_columns.json does not match manifest feature_columns"
            )

        # ── Step 4: Verify artifact hash BEFORE loading ───────────────
        if not self.model_path.exists():
            raise FileNotFoundError(
                f"Model artifact not found at {self.model_path}"
            )
        with open(self.model_path, "rb") as f:
            actual_sha256 = hashlib.sha256(f.read()).hexdigest()
        expected_sha256 = self.manifest["sha256_checksum"]
        if actual_sha256 != expected_sha256:
            raise ValueError(
                f"Model artifact SHA-256 mismatch. "
                f"Expected {expected_sha256[:16]}…, got {actual_sha256[:16]}…. "
                "Artifact may be tampered or from a different training run."
            )

        # ── Step 5: Deserialize model (hash already verified) ─────────
        self.model = joblib.load(self.model_path)

        # ── Step 6: Verify model class matches manifest ───────────────
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
            Dict containing standardized prediction record.
        """
        base = {
            "schema_version": "2.0",
            "model_version": self.model_version,
            "model_sha256": self.model_sha256,
            "target_threshold_pct": target_threshold_pct,
            "estimate_type": "expected_hours_to_service_threshold",
            "waste_type_used_as_feature": False,
        }

        # ── Item 1: Reject unsupported thresholds ─────────────────────
        if target_threshold_pct not in self.supported_thresholds:
            return {
                **base,
                "bin_id": None,
                "timestamp": None,
                "status": "unsupported_threshold",
                "reason": f"Model trained against {sorted(self.supported_thresholds)}; "
                          f"requested {target_threshold_pct}% is not supported.",
                "time_to_service_threshold_hours": None,
                "risk_level": None,
                "fill_pct": None,
                "confidence_flag": 0,
                "waste_type": None,
                "horizons": {},
            }

        if bin_history is None or len(bin_history) == 0:
            return {
                **base,
                "bin_id": None,
                "timestamp": None,
                "status": "invalid_input",
                "time_to_service_threshold_hours": None,
                "risk_level": None,
                "fill_pct": None,
                "confidence_flag": 0,
                "waste_type": None,
                "horizons": {},
            }

        # Extract bin identity
        unique_bins = (
            bin_history["bin_id"].dropna().unique()
            if "bin_id" in bin_history.columns else []
        )
        if len(unique_bins) > 1:
            target_bin = str(unique_bins[0])
            bin_history = bin_history[bin_history["bin_id"] == target_bin].copy()
        elif len(unique_bins) == 1:
            target_bin = str(unique_bins[0])
        else:
            target_bin = "unknown"

        # Preserve waste_type (Item 7)
        waste_type = None
        if "waste_type" in bin_history.columns:
            wt = bin_history["waste_type"].dropna().unique()
            if len(wt) > 0:
                waste_type = str(wt[0])

        if "fill_pct" not in bin_history.columns or "timestamp" not in bin_history.columns:
            return {
                **base,
                "bin_id": target_bin,
                "timestamp": (
                    str(bin_history["timestamp"].iloc[-1])
                    if "timestamp" in bin_history.columns else None
                ),
                "status": "missing_required_columns",
                "time_to_service_threshold_hours": None,
                "risk_level": None,
                "fill_pct": (
                    float(bin_history["fill_pct"].iloc[-1])
                    if "fill_pct" in bin_history.columns else None
                ),
                "confidence_flag": int(
                    bin_history.get("confidence_flag", pd.Series([0])).iloc[-1]
                ),
                "waste_type": waste_type,
                "horizons": {},
            }

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
                    "bin_id": target_bin,
                    "timestamp": str(latest["timestamp"].iloc[0]),
                    "status": "model_error",
                    "reason": "non-finite or negative prediction",
                    "time_to_service_threshold_hours": None,
                    "risk_level": None,
                    "fill_pct": round(float(latest["fill_pct"].iloc[0]), 1),
                    "confidence_flag": int(
                        latest.get("confidence_flag", pd.Series([0])).iloc[0]
                    ),
                    "waste_type": waste_type,
                    "horizons": {},
                }
        except Exception:
            return {
                **base,
                "bin_id": target_bin,
                "timestamp": (
                    str(bin_history["timestamp"].iloc[-1])
                    if "timestamp" in bin_history.columns else None
                ),
                "status": "model_error",
                "time_to_service_threshold_hours": None,
                "risk_level": None,
                "fill_pct": (
                    float(bin_history["fill_pct"].iloc[-1])
                    if "fill_pct" in bin_history.columns else None
                ),
                "confidence_flag": int(
                    bin_history.get("confidence_flag", pd.Series([0])).iloc[-1]
                ),
                "waste_type": waste_type,
                "horizons": {},
            }

        current_fill = float(latest["fill_pct"].iloc[0])
        rate_1h = max(0.0, float(latest["fill_rate_1h"].iloc[0]))

        # ── Item 4: No fabricated probabilities ───────────────────────
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

        status = "cold_start" if is_cold_start else "available"
        return {
            **base,
            "bin_id": target_bin,
            "timestamp": str(latest["timestamp"].iloc[0]),
            "status": status,
            "time_to_service_threshold_hours": round(hours, 2),
            "risk_level": risk_level_from_hours(hours),
            "fill_pct": round(current_fill, 1),
            "confidence_flag": int(
                latest.get("confidence_flag", pd.Series([1])).iloc[0]
            ),
            "waste_type": waste_type,
            "horizons": horizons_dict,
        }

    # ─────────────────────────────────────────────────────────────────
    #  PR1 snapshot entry point (the stable contract)
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
        PR1-to-PR4 integration entry point.

        Enforces point-in-time correctness (Item 2):
          - Filters observations with ``timestamp > decision_at``.
          - Filters observations with ``received_at > decision_at`` (when column exists).
          - Rejects if model training cutoff is after ``decision_at``.
          - Returns ``stale`` if latest observation is older than ``max_staleness_hours``.

        Args:
            history: DataFrame of sensor readings.
            bins: Configured bin IDs — every one receives a forecast record.
            decision_at: Point-in-time cutoff (UTC).
            input_snapshot_id: PR1 snapshot identifier.
            events: Known historical events (reserved).
            target_threshold_pct: Service threshold (only 90.0 supported).
            max_staleness_hours: Maximum age of latest observation before stale.

        Returns:
            Dict (single bin) or List[Dict] (multi-bin snapshot).
        """
        cutoff = pd.to_datetime(decision_at) if decision_at is not None else None

        # ── Item 2: Model-training cutoff check ───────────────────────
        if cutoff is not None and self.training_data_cutoff is not None:
            training_end = pd.to_datetime(self.training_data_cutoff)
            # Normalize tz for comparison
            cutoff_cmp = cutoff.tz_localize(None) if cutoff.tzinfo else cutoff
            training_cmp = training_end.tz_localize(None) if training_end.tzinfo else training_end
            if cutoff_cmp < training_cmp:
                model_unavailable = {
                    "schema_version": "2.0",
                    "status": "model_unavailable",
                    "reason": (
                        f"Model trained with data up to {self.training_data_cutoff}; "
                        f"decision_at {decision_at} is before training cutoff."
                    ),
                    "decision_at": str(decision_at),
                    "input_snapshot_id": input_snapshot_id,
                    "model_version": self.model_version,
                    "model_sha256": self.model_sha256,
                    "target_threshold_pct": target_threshold_pct,
                    "time_to_service_threshold_hours": None,
                    "risk_level": None,
                    "fill_pct": None,
                    "confidence_flag": 0,
                    "waste_type": None,
                    "horizons": {},
                }
                # Return one per configured bin if bins specified
                configured_bins = self._resolve_bins(bins, history)
                if configured_bins:
                    return [
                        {**model_unavailable, "bin_id": b} for b in configured_bins
                    ]
                model_unavailable["bin_id"] = None
                return model_unavailable

        # ── Item 2: Observation timestamp + receipt-time filtering ────
        if history is not None and len(history) > 0 and cutoff is not None:
            history = history.copy()
            history["timestamp"] = pd.to_datetime(history["timestamp"])
            # Normalize cutoff to match history timezone
            ts_tz = history["timestamp"].dt.tz
            if cutoff.tzinfo is not None and ts_tz is None:
                cutoff_obs = cutoff.tz_localize(None)
            elif cutoff.tzinfo is None and ts_tz is not None:
                cutoff_obs = cutoff.tz_localize(ts_tz)
            else:
                cutoff_obs = cutoff
            history = history[history["timestamp"] <= cutoff_obs]
            # Filter by received_at if column exists
            if "received_at" in history.columns:
                history["received_at"] = pd.to_datetime(history["received_at"])
                ra_tz = history["received_at"].dt.tz
                if cutoff.tzinfo is not None and ra_tz is None:
                    cutoff_ra = cutoff.tz_localize(None)
                elif cutoff.tzinfo is None and ra_tz is not None:
                    cutoff_ra = cutoff.tz_localize(ra_tz)
                else:
                    cutoff_ra = cutoff
                history = history[history["received_at"] <= cutoff_ra]

        # Resolve configured bins
        configured_bins = self._resolve_bins(bins, history)

        if not configured_bins:
            res = self._predict_single_with_staleness(
                history, cutoff, max_staleness_hours, target_threshold_pct,
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
                    "model_version": self.model_version,
                    "model_sha256": self.model_sha256,
                    "waste_type": None,
                    "horizons": {},
                    "decision_at": str(decision_at) if decision_at else None,
                    "input_snapshot_id": input_snapshot_id,
                }
            else:
                res = self._predict_single_with_staleness(
                    bin_hist, cutoff, max_staleness_hours, target_threshold_pct,
                )
                res["decision_at"] = str(decision_at) if decision_at else res.get("timestamp")
                res["input_snapshot_id"] = input_snapshot_id
            results.append(res)

        return (
            results[0]
            if len(results) == 1 and not isinstance(bins, (list, pd.DataFrame))
            else results
        )

    # ─────────────────────────────────────────────────────────────────
    #  Internal helpers
    # ─────────────────────────────────────────────────────────────────

    def _resolve_bins(
        self,
        bins: Optional[Union[Dict[str, Any], Sequence[str], pd.DataFrame]],
        history: Optional[pd.DataFrame],
    ) -> List[str]:
        """Extract the list of configured bin IDs from the various input shapes."""
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
        cutoff: Optional[pd.Timestamp],
        max_staleness_hours: float,
        target_threshold_pct: float,
    ) -> Dict[str, Any]:
        """Predict for a single bin, adding staleness check (Item 2)."""
        result = self.predict_from_history(bin_history, target_threshold_pct)

        # ── Staleness check ───────────────────────────────────────────
        if (
            cutoff is not None
            and result.get("status") == "available"
            and result.get("timestamp") is not None
        ):
            latest_ts = pd.to_datetime(result["timestamp"])
            # Normalize tz for comparison
            cutoff_s = cutoff.tz_localize(None) if cutoff.tzinfo else cutoff
            latest_s = latest_ts.tz_localize(None) if latest_ts.tzinfo else latest_ts
            age_hours = (cutoff_s - latest_s).total_seconds() / 3600.0
            if age_hours > max_staleness_hours:
                result["status"] = "stale"
                result["reason"] = (
                    f"Latest observation is {age_hours:.1f}h old "
                    f"(max {max_staleness_hours}h)."
                )

        return result


# Backward-compatible alias
OverflowRiskModel = ForecastProvider


if __name__ == "__main__":
    raw = pd.read_csv(DATA_DIR / "raw_sensor_log.csv")
    provider = ForecastProvider()

    # Test snapshot interface with multiple bins
    snapshot_res = provider.predict_snapshot(
        raw,
        bins=["bin_000", "bin_005", "bin_999_missing"],
        decision_at="2026-03-20 12:00:00",
        input_snapshot_id="SNAP-TEST-001"
    )
    print("Multi-bin snapshot result sample:")
    print(json.dumps(snapshot_res, indent=2))
