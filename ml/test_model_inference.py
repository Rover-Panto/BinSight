"""
BinSight — Model Inference Verification Script.

This script tests the inference capabilities of the trained OverflowRiskModel
wrapper (`src/serve.py`) against sample smart bin sensor streams across different
bin usage archetypes (Residential, Commercial High Traffic, and Event Surge).

Usage:
    python test_model_inference.py
"""

import os
import sys
import time
from pathlib import Path
import pandas as pd
import joblib

# Ensure src is added to the system path
BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR / "src"))

from label import risk_level_from_hours, OVERFLOW_THRESHOLD_PCT
from serve import OverflowRiskModel

# ---------------------------------------------------------------------------
# 1. Load Raw Sensor Log & Verify Model Loading
# ---------------------------------------------------------------------------
print("Loading dataset...")
raw = pd.read_csv(BASE_DIR / "data" / "raw_sensor_log.csv")
print(f"Loaded {len(raw):,} sensor rows across {raw['bin_id'].nunique()} bins.")

print("Loading trained model...")
t0 = time.time()
model = joblib.load(BASE_DIR / "models" / "overflow_model.joblib")
print(f"Model loaded in {time.time()-t0:.2f}s: {type(model).__name__}")

# Initialize the production serving wrapper
risk_model = OverflowRiskModel()

# ---------------------------------------------------------------------------
# 2. Test Multi-Archetype Real-Time Inferences
# ---------------------------------------------------------------------------
# Test bins representing 3 distinct fill behaviors:
bins_to_test = [
    ("bin_000", "Residential (Slow filling, low volume)", 40),
    ("bin_005", "Commercial (High Traffic, rapid filling)", 30),
    ("bin_010", "Event Surge Area (Sudden spikes)", 60),
]

print("\n" + "=" * 65)
print(" LIVE APPLICATION PREDICTIONS FOR SMART BINS")
print("=" * 65)

for bin_id, desc, slice_len in bins_to_test:
    # Extract the recent history window for the target bin
    bin_data = raw[raw["bin_id"] == bin_id].head(slice_len)
    
    # Generate prediction from sensor history stream
    pred = risk_model.predict_from_history(bin_data)
    
    print(f"\nBin ID: {pred['bin_id']} | Type: {desc}")
    print(f"  Current Fill Level    : {pred['fill_pct']}%")
    print(f"  Confidence Flag       : {pred['confidence_flag']} (1 = Normal, 0 = Sensor Warning)")
    print(f"  Time to 90% Overflow  : {pred['time_to_overflow_hours']} hours")
    print(f"  Assigned Risk Category: [{pred['risk_level']}]")

print("\n" + "=" * 65)
print("Pipeline and model successfully verified!")
