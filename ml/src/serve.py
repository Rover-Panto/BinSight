"""
BinSight overflow-risk model & forecasting subsystem: inference provider.

This is the primary public entry point for the BinSight forecasting component (PR4).
Provides unified forecasting for:
  1. Real hardware telemetry (PR2 edge ingestion & PR1 live operations).
  2. Multi-horizon fill & overflow probabilities (6h, 24h, 48h, 168h).
  3. Paired route/KPI simulation callers (replacing PR1's internal forecast.py).

Run from anywhere: `python3 serve.py` or `python3 src/serve.py` (runs smoke test).
"""
import hashlib
import json
import math
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


def _normal_exceedance(threshold: float, mean: float, sd: float) -> float:
    """Calculate normal cumulative exceedance probability P(X >= threshold)."""
    if sd <= 1e-9:
        return 1.0 if mean >= threshold else 0.0
    z = (threshold - mean) / sd
    return float(np.clip(0.5 * math.erfc(z / math.sqrt(2.0)), 0.0, 1.0))


class ForecastProvider:
    """
    Unified forecasting provider for BinSight smart waste bin platform.
    
    Acts as the single source of truth for overflow risk predictions, growth forecasts,
    and horizon-calibrated overflow probabilities across live telemetry and simulation.
    """

    def __init__(self, model_dir: Path = MODEL_DIR):
        """
        Initialize the model runner by loading trained model bundle and verifying checksums.
        """
        self.model_dir = Path(model_dir)
        self.model_path = self.model_dir / "overflow_model.joblib"
        self.manifest_path = self.model_dir / "manifest.json"
        
        if not self.model_path.exists():
            raise FileNotFoundError(f"Model artifact not found at {self.model_path}")
            
        self.model = joblib.load(self.model_path)
        
        with open(self.model_dir / "feature_columns.json") as f:
            self.feature_columns = json.load(f)

        if self.manifest_path.exists():
            with open(self.manifest_path) as f:
                self.manifest = json.load(f)
            # Verify SHA-256 integrity
            with open(self.model_path, "rb") as f:
                actual_sha256 = hashlib.sha256(f.read()).hexdigest()
            if self.manifest.get("sha256_checksum") != actual_sha256:
                raise ValueError("Model artifact SHA-256 checksum does not match manifest!")
        else:
            self.manifest = {}

        self.model_version = self.manifest.get("model_version", "1.1.0")
        self.model_sha256 = self.manifest.get("sha256_checksum", "")

    def predict_from_history(
        self,
        bin_history: pd.DataFrame,
        target_threshold_pct: float = OVERFLOW_THRESHOLD_PCT,
    ) -> Dict[str, Any]:
        """
        Generate overflow forecast for a single bin from its sensor history.
        
        Args:
            bin_history: DataFrame of sensor readings for ONE bin, sorted by timestamp.
            target_threshold_pct: Target fill threshold (default 90.0%).
            
        Returns:
            Dict containing standardized prediction record.
        """
        if bin_history is None or len(bin_history) == 0:
            return {
                "schema_version": "1.0",
                "bin_id": None,
                "timestamp": None,
                "status": "invalid_input",
                "time_to_overflow_hours": None,
                "risk_level": "Unavailable",
                "fill_pct": None,
                "confidence_flag": 0,
                "target_threshold_pct": target_threshold_pct,
                "model_version": self.model_version,
                "model_sha256": self.model_sha256,
                "horizons": {},
            }

        # Multi-bin check: isolate single bin if needed
        unique_bins = bin_history["bin_id"].dropna().unique() if "bin_id" in bin_history.columns else []
        if len(unique_bins) > 1:
            target_bin = str(unique_bins[0])
            bin_history = bin_history[bin_history["bin_id"] == target_bin].copy()
        elif len(unique_bins) == 1:
            target_bin = str(unique_bins[0])
        else:
            target_bin = "unknown"

        if "fill_pct" not in bin_history.columns or "timestamp" not in bin_history.columns:
            return {
                "schema_version": "1.0",
                "bin_id": target_bin,
                "timestamp": str(bin_history["timestamp"].iloc[-1]) if "timestamp" in bin_history.columns else None,
                "status": "missing_required_columns",
                "time_to_overflow_hours": None,
                "risk_level": "Unavailable",
                "fill_pct": float(bin_history["fill_pct"].iloc[-1]) if "fill_pct" in bin_history.columns else None,
                "confidence_flag": int(bin_history.get("confidence_flag", pd.Series([0])).iloc[-1]),
                "target_threshold_pct": target_threshold_pct,
                "model_version": self.model_version,
                "model_sha256": self.model_sha256,
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
                    "schema_version": "1.0",
                    "bin_id": target_bin,
                    "timestamp": str(latest["timestamp"].iloc[0]),
                    "status": "model_error",
                    "time_to_overflow_hours": None,
                    "risk_level": "Unavailable",
                    "fill_pct": round(float(latest["fill_pct"].iloc[0]), 1),
                    "confidence_flag": int(latest.get("confidence_flag", pd.Series([0])).iloc[0]),
                    "target_threshold_pct": target_threshold_pct,
                    "model_version": self.model_version,
                    "model_sha256": self.model_sha256,
                    "horizons": {},
                }
        except Exception:
            return {
                "schema_version": "1.0",
                "bin_id": target_bin,
                "timestamp": str(bin_history["timestamp"].iloc[-1]) if "timestamp" in bin_history.columns else None,
                "status": "model_error",
                "time_to_overflow_hours": None,
                "risk_level": "Unavailable",
                "fill_pct": float(bin_history["fill_pct"].iloc[-1]) if "fill_pct" in bin_history.columns else None,
                "confidence_flag": int(bin_history.get("confidence_flag", pd.Series([0])).iloc[-1]),
                "target_threshold_pct": target_threshold_pct,
                "model_version": self.model_version,
                "model_sha256": self.model_sha256,
                "horizons": {},
            }

        current_fill = float(latest["fill_pct"].iloc[0])
        rate_1h = max(0.0, float(latest["fill_rate_1h"].iloc[0]))
        
        # Calculate multi-horizon projections and calibrated probabilities
        horizons_dict = {}
        for h in FORECAST_HORIZONS:
            expected_growth = rate_1h * h
            expected_fill = min(100.0, current_fill + expected_growth)
            sd = max(1.5, 0.25 * math.sqrt(h) * (1.0 + rate_1h))
            prob_overflow = _normal_exceedance(target_threshold_pct, expected_fill, sd)
            horizons_dict[str(h)] = {
                "horizon_hours": h,
                "expected_fill_pct": round(expected_fill, 1),
                "expected_growth_pct": round(expected_growth, 1),
                "overflow_probability": round(prob_overflow, 4),
            }

        status = "cold_start" if is_cold_start else "available"
        return {
            "schema_version": "1.0",
            "bin_id": target_bin,
            "timestamp": str(latest["timestamp"].iloc[0]),
            "status": status,
            "time_to_overflow_hours": round(hours, 2),
            "risk_level": risk_level_from_hours(hours),
            "fill_pct": round(current_fill, 1),
            "confidence_flag": int(latest.get("confidence_flag", pd.Series([1])).iloc[0]),
            "target_threshold_pct": target_threshold_pct,
            "model_version": self.model_version,
            "model_sha256": self.model_sha256,
            "horizons": horizons_dict,
        }

    def predict_snapshot(
        self,
        history: pd.DataFrame,
        bins: Optional[Union[Dict[str, Any], Sequence[str], pd.DataFrame]] = None,
        decision_at: Optional[Any] = None,
        input_snapshot_id: Optional[str] = None,
        events: Optional[Any] = None,
        target_threshold_pct: float = OVERFLOW_THRESHOLD_PCT,
    ) -> Union[Dict[str, Any], List[Dict[str, Any]]]:
        """
        PR1-to-PR4 integration entry point: Generate forecast for all configured bins from a snapshot.
        
        Args:
            history: DataFrame of sensor readings at or before decision_at.
            bins: Optional list or DataFrame of configured bin IDs. If provided, guarantees
                  every configured bin receives a forecast record (even if insufficient evidence).
            decision_at: Cutoff timestamp; observations after this timestamp are strictly filtered.
            input_snapshot_id: Optional snapshot identifier from PR1 telemetry client.
            events: Optional known historical events.
            target_threshold_pct: Target overflow threshold.
            
        Returns:
            Dict (if single bin) or List of Dicts (if multi-bin snapshot).
        """
        if history is not None and len(history) > 0 and decision_at is not None:
            cutoff = pd.to_datetime(decision_at)
            history = history.copy()
            history["timestamp"] = pd.to_datetime(history["timestamp"])
            history = history[history["timestamp"] <= cutoff]

        # Extract configured bins
        if isinstance(bins, pd.DataFrame) and "bin_id" in bins.columns:
            configured_bins = list(bins["bin_id"].astype(str).unique())
        elif isinstance(bins, dict):
            configured_bins = list(bins.keys())
        elif isinstance(bins, (list, tuple)):
            configured_bins = [str(b) for b in bins]
        elif history is not None and "bin_id" in history.columns and len(history) > 0:
            configured_bins = list(history["bin_id"].dropna().unique())
        else:
            configured_bins = []

        if not configured_bins:
            # Single unknown bin fallback
            res = self.predict_from_history(history, target_threshold_pct)
            res["decision_at"] = str(decision_at) if decision_at else res.get("timestamp")
            res["input_snapshot_id"] = input_snapshot_id
            return res

        results = []
        for bin_id in configured_bins:
            bin_hist = history[history["bin_id"] == bin_id].sort_values("timestamp") if history is not None and "bin_id" in history.columns else pd.DataFrame()
            if len(bin_hist) == 0:
                res = {
                    "schema_version": "1.0",
                    "bin_id": bin_id,
                    "timestamp": None,
                    "status": "unavailable",
                    "time_to_overflow_hours": None,
                    "risk_level": "Unavailable",
                    "fill_pct": None,
                    "confidence_flag": 0,
                    "target_threshold_pct": target_threshold_pct,
                    "model_version": self.model_version,
                    "model_sha256": self.model_sha256,
                    "horizons": {},
                    "decision_at": str(decision_at) if decision_at else None,
                    "input_snapshot_id": input_snapshot_id,
                }
            else:
                res = self.predict_from_history(bin_hist, target_threshold_pct)
                res["decision_at"] = str(decision_at) if decision_at else res.get("timestamp")
                res["input_snapshot_id"] = input_snapshot_id
            results.append(res)

        return results[0] if len(results) == 1 and not isinstance(bins, (list, pd.DataFrame)) else results

    # Compatibility methods for PR1 simulation callers (ForecastBundle interface)
    def predict(self, feature_frame: pd.DataFrame) -> Tuple[np.ndarray, np.ndarray]:
        """
        PR1 simulation interface: returns (mean_growth, upper_growth) predictions.
        """
        features = feature_frame[self.feature_columns]
        mean = np.maximum(0.0, self.model.predict(features))
        upper = np.maximum(mean, mean * 1.25 + 1.0)
        return mean, upper

    def predict_overflow_probability_48h(self, feature_frame: pd.DataFrame) -> np.ndarray:
        """PR1 simulation interface: returns calibrated 48-hour overflow probability."""
        features = feature_frame[self.feature_columns]
        mean_hours = np.maximum(0.0, self.model.predict(features))
        return np.clip(1.0 - (mean_hours / 48.0), 0.0, 1.0)

    def predict_overflow_probability_6h(self, feature_frame: pd.DataFrame) -> np.ndarray:
        """PR1 simulation interface: returns calibrated 6-hour overflow probability."""
        features = feature_frame[self.feature_columns]
        mean_hours = np.maximum(0.0, self.model.predict(features))
        return np.clip(1.0 - (mean_hours / 6.0), 0.0, 1.0)


# Backward-compatible alias
OverflowRiskModel = ForecastProvider


if __name__ == "__main__":
    raw = pd.read_csv(DATA_DIR / "raw_sensor_log.csv")
    provider = ForecastProvider()
    
    # Test snapshot interface with multiple bins
    snapshot_res = provider.predict_snapshot(
        raw,
        bins=["bin_000", "bin_005", "bin_999_missing"],
        decision_at="2026-01-02 12:00:00",
        input_snapshot_id="SNAP-TEST-001"
    )
    print("Multi-bin snapshot result sample:")
    print(json.dumps(snapshot_res, indent=2))


