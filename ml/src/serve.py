"""
BinSight overflow-risk model: inference wrapper.

This is the primary prediction interface for smart-bin overflow risk forecasting.
Accepts raw sensor telemetry streams (including PR2 edge-to-cloud schemas),
generates features on the fly, and outputs continuous time-to-overflow hours along with
deterministic operational risk categories.

Run from anywhere: `python3 serve.py` or `python3 src/serve.py` (runs smoke test).
"""
import json
from pathlib import Path
from typing import Optional, Dict, Any

import joblib
import numpy as np
import pandas as pd

from features import build_feature_table, FEATURE_COLUMNS  # noqa: F401
from label import risk_level_from_hours, OVERFLOW_THRESHOLD_PCT

BASE_DIR = Path(__file__).resolve().parent.parent
MODEL_DIR = BASE_DIR / "models"
DATA_DIR = BASE_DIR / "data"


class OverflowRiskModel:
    """
    Production-ready inference wrapper for smart bin overflow risk prediction.
    """
    
    def __init__(self, model_dir: Path = MODEL_DIR):
        """
        Initialize the model runner by loading trained model and expected feature schema.
        """
        self.model = joblib.load(model_dir / "overflow_model.joblib")
        with open(model_dir / "feature_columns.json") as f:
            self.feature_columns = json.load(f)
        
        manifest_path = model_dir / "manifest.json"
        if manifest_path.exists():
            with open(manifest_path) as f:
                self.manifest = json.load(f)
        else:
            self.manifest = {}

    def predict_from_history(self, bin_history: pd.DataFrame) -> Dict[str, Any]:
        """
        Generate overflow forecast for a single bin from its sensor history.
        
        Args:
            bin_history: DataFrame of sensor rows for ONE bin, sorted by timestamp.
                Supported columns: timestamp, bin_id, fill_pct, confidence_flag, (optional: estimated_density, weight_kg).
                
        Returns:
            dict containing:
                - 'bin_id' (str or None): Identifier of the bin.
                - 'timestamp' (str or None): Timestamp of latest reading.
                - 'status' (str): "ok", "cold_start", "model_error", or "invalid_input".
                - 'time_to_overflow_hours' (float or None): Estimated hours until >=90% fill.
                - 'risk_level' (str): "Critical", "High", "Medium", "Low", or "Unavailable".
                - 'fill_pct' (float or None): Current fill percentage.
                - 'confidence_flag' (int): 1 if reading is healthy, 0 if low confidence.
                - 'target_threshold_pct' (float): 90.0 (overflow threshold).
                - 'model_version' (str): Model semantic version.
        """
        if bin_history is None or len(bin_history) == 0:
            return {
                "bin_id": None,
                "timestamp": None,
                "status": "invalid_input",
                "time_to_overflow_hours": None,
                "risk_level": "Unavailable",
                "fill_pct": None,
                "confidence_flag": 0,
                "target_threshold_pct": OVERFLOW_THRESHOLD_PCT,
                "model_version": self.manifest.get("model_version", "1.1.0"),
            }

        # Multi-bin check: isolate single bin
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
                "bin_id": target_bin,
                "timestamp": str(bin_history["timestamp"].iloc[-1]) if "timestamp" in bin_history.columns else None,
                "status": "missing_required_columns",
                "time_to_overflow_hours": None,
                "risk_level": "Unavailable",
                "fill_pct": float(bin_history["fill_pct"].iloc[-1]) if "fill_pct" in bin_history.columns else None,
                "confidence_flag": int(bin_history.get("confidence_flag", pd.Series([0])).iloc[-1]),
                "target_threshold_pct": OVERFLOW_THRESHOLD_PCT,
                "model_version": self.manifest.get("model_version", "1.1.0"),
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
                    "bin_id": target_bin,
                    "timestamp": str(latest["timestamp"].iloc[0]),
                    "status": "model_error",
                    "time_to_overflow_hours": None,
                    "risk_level": "Unavailable",
                    "fill_pct": round(float(latest["fill_pct"].iloc[0]), 1),
                    "confidence_flag": int(latest.get("confidence_flag", pd.Series([0])).iloc[0]),
                    "target_threshold_pct": OVERFLOW_THRESHOLD_PCT,
                    "model_version": self.manifest.get("model_version", "1.1.0"),
                }
        except Exception:
            return {
                "bin_id": target_bin,
                "timestamp": str(bin_history["timestamp"].iloc[-1]) if "timestamp" in bin_history.columns else None,
                "status": "model_error",
                "time_to_overflow_hours": None,
                "risk_level": "Unavailable",
                "fill_pct": float(bin_history["fill_pct"].iloc[-1]) if "fill_pct" in bin_history.columns else None,
                "confidence_flag": int(bin_history.get("confidence_flag", pd.Series([0])).iloc[-1]),
                "target_threshold_pct": OVERFLOW_THRESHOLD_PCT,
                "model_version": self.manifest.get("model_version", "1.1.0"),
            }

        status = "cold_start" if is_cold_start else "ok"
        return {
            "schema_version": "1.0",
            "bin_id": target_bin,
            "timestamp": str(latest["timestamp"].iloc[0]),
            "status": status,
            "time_to_overflow_hours": round(hours, 2),
            "risk_level": risk_level_from_hours(hours),
            "fill_pct": round(float(latest["fill_pct"].iloc[0]), 1),
            "confidence_flag": int(latest.get("confidence_flag", pd.Series([1])).iloc[0]),
            "target_threshold_pct": OVERFLOW_THRESHOLD_PCT,
            "model_version": self.manifest.get("model_version", "1.1.0"),
            "model_sha256": self.manifest.get("sha256_checksum", ""),
        }

    def predict_snapshot(
        self,
        history: pd.DataFrame,
        bins: Optional[Dict[str, Any]] = None,
        decision_at: Optional[Any] = None,
        input_snapshot_id: Optional[str] = None,
        events: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """
        PR1-to-PR4 integration entry point: Generate forecast for a mapped snapshot.
        
        Args:
            history: DataFrame of sensor readings at or before decision_at.
            bins: Optional metadata mapping for registered bins.
            decision_at: Optional cutoff timestamp; filters out future observations if present.
            input_snapshot_id: Optional snapshot identifier from PR1 telemetry client.
            events: Optional known historical events.
            
        Returns:
            Dict or List of forecast dictionaries matching the PR1/PR4 contract.
        """
        if history is not None and len(history) > 0 and decision_at is not None:
            cutoff = pd.to_datetime(decision_at)
            history = history.copy()
            history["timestamp"] = pd.to_datetime(history["timestamp"])
            history = history[history["timestamp"] <= cutoff]

        result = self.predict_from_history(history)
        result["decision_at"] = str(decision_at) if decision_at else result.get("timestamp")
        result["input_snapshot_id"] = input_snapshot_id
        return result


if __name__ == "__main__":
    raw = pd.read_csv(DATA_DIR / "raw_sensor_log.csv")
    one_bin = raw[raw["bin_id"] == "bin_005"].head(60)
    model = OverflowRiskModel()
    print(json.dumps(model.predict_snapshot(one_bin, input_snapshot_id="SNAP-001"), indent=2))

