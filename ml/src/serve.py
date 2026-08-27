"""
BinSight overflow-risk model: inference wrapper.

This is the ONLY file the hub/integration engineer needs to import.
It defines the exact input/output contract described in docs/IMPLEMENTATION_SPEC.md (Section 10).

Run from anywhere: `python3 serve.py` or `python3 src/serve.py` (runs a smoke test).
"""
import json
from pathlib import Path

import joblib
import pandas as pd

from features import build_feature_table, FEATURE_COLUMNS  # noqa: F401 (re-exported for convenience)
from label import risk_level_from_hours

BASE_DIR = Path(__file__).resolve().parent.parent
MODEL_DIR = BASE_DIR / "models"
DATA_DIR = BASE_DIR / "data"


class OverflowRiskModel:
    """
    Production-ready inference wrapper for smart bin overflow risk prediction.
    
    This class loads the trained regression model artifact and feature definitions,
    accepts a window of recent sensor readings for a bin, generates features,
    and returns both the continuous hours-to-overflow and operational risk category.
    """
    
    def __init__(self, model_dir: Path = MODEL_DIR):
        """
        Initialize the model runner by loading trained model and expected feature schema.
        
        Args:
            model_dir: Directory containing 'overflow_model.joblib' and 'feature_columns.json'.
        """
        self.model = joblib.load(model_dir / "overflow_model.joblib")
        with open(model_dir / "feature_columns.json") as f:
            self.feature_columns = json.load(f)

    def predict_from_history(self, bin_history: pd.DataFrame) -> dict:
        """
        Generate overflow forecast for a single bin from its recent sensor history.
        
        Args:
            bin_history: DataFrame of raw sensor rows for ONE bin, sorted by timestamp.
                Required columns: timestamp, bin_id, fill_pct, weight_kg, confidence_flag.
                Must include sufficient history (recommended >= 24h) to compute rolling rates.
                
        Returns:
            dict containing:
                - 'bin_id' (str): Identifier of the bin.
                - 'timestamp' (str): Timestamp of the most recent reading.
                - 'time_to_overflow_hours' (float): Estimated hours until >=90% fill.
                - 'risk_level' (str): One of ['Critical', 'High', 'Medium', 'Low'].
                - 'fill_pct' (float): Current fill level percentage.
                - 'confidence_flag' (int): 1 if sensor reading is reliable, 0 if noisy.
        """
        feat = build_feature_table(bin_history)
        latest = feat.iloc[[-1]]
        X = latest[self.feature_columns]
        hours = float(self.model.predict(X)[0])
        hours = max(hours, 0.0)
        return {
            "bin_id": str(latest["bin_id"].iloc[0]),
            "timestamp": str(latest["timestamp"].iloc[0]),
            "time_to_overflow_hours": round(hours, 2),
            "risk_level": risk_level_from_hours(hours),
            "fill_pct": round(float(latest["fill_pct"].iloc[0]), 1),
            "confidence_flag": int(latest["confidence_flag"].iloc[0]),
        }


if __name__ == "__main__":
    # Smoke test using a slice of the simulated log
    raw = pd.read_csv(DATA_DIR / "raw_sensor_log.csv")
    one_bin = raw[raw["bin_id"] == "bin_005"].head(60)  # first 30 hours of history
    model = OverflowRiskModel()
    print(json.dumps(model.predict_from_history(one_bin), indent=2))
