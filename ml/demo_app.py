"""
BinSight Interactive Application & Model Demonstration Script.

Tests the model on real-world scenarios and demonstrates live overflow risk forecasting,
validation testing, and evaluation metrics comparison for team presentations and demos.

Usage:
    python demo_app.py
"""
import sys
import json
from pathlib import Path
import pandas as pd
import numpy as np

# Ensure src is in python path
BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR / "src"))

from serve import OverflowRiskModel
from features import FEATURE_COLUMNS

def print_banner(title: str) -> None:
    """Print formatted terminal section banner."""
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)

def run_tests() -> None:
    """
    Run pipeline sanity tests to verify data integrity, feature computation,
    and model inference contracts.
    """
    print_banner("1. RUNNING MODEL PIPELINE SANITY TESTS")
    from tests.test_pipeline import (
        test_raw_log_exists_and_well_formed,
        test_feature_table_has_no_nans,
        test_labeled_dataset_has_valid_labels,
        test_model_artifacts_and_manifest_exist_and_agree,
        test_model_beats_baselines,
        test_feature_builder_handles_pr2_payload_without_weight,
        test_feature_builder_handles_single_reading_cold_start,
        test_feature_builder_handles_duplicate_timestamps,
        test_feature_builder_handles_irregular_sampling_and_gaps,
        test_serve_wrapper_returns_valid_prediction,
        test_serve_wrapper_handles_empty_and_invalid_inputs
    )
    
    tests = [
        ("Raw Sensor Log Validation", test_raw_log_exists_and_well_formed),
        ("Feature Table NaN Check", test_feature_table_has_no_nans),
        ("Labeled Dataset Target Validity", test_labeled_dataset_has_valid_labels),
        ("Model Artifacts & Manifest SHA-256", test_model_artifacts_and_manifest_exist_and_agree),
        ("Model vs Baselines Benchmark", test_model_beats_baselines),
        ("PR2 Telemetry Compatibility", test_feature_builder_handles_pr2_payload_without_weight),
        ("Single Reading Cold Start", test_feature_builder_handles_single_reading_cold_start),
        ("Duplicate Timestamps Guard", test_feature_builder_handles_duplicate_timestamps),
        ("Irregular Gaps Rate Recovery", test_feature_builder_handles_irregular_sampling_and_gaps),
        ("Inference Contract Output", test_serve_wrapper_returns_valid_prediction),
        ("Invalid & Empty Input Handling", test_serve_wrapper_handles_empty_and_invalid_inputs),
    ]
    
    passed = 0
    for name, test_fn in tests:
        try:
            test_fn()
            print(f"  [PASS] {name}")
            passed += 1
        except Exception as e:
            print(f"  [FAIL] {name}: {e}")
            
    print(f"\n  Result: {passed}/{len(tests)} tests passed successfully.")

def demonstrate_scenarios() -> None:
    """
    Demonstrate live inference on three realistic smart bin archetypes:
    - Archetype 1: Residential Bin (slow filling, predictable rhythm)
    - Archetype 2: Commercial High-Usage Bin (fast filling, midday peaks)
    - Archetype 3: Event Surge Bin (sudden spikes requiring urgent dispatch)
    """
    print_banner("2. LIVE APPLICATION DEMO: SMART BIN OVERFLOW FORECASTING")
    
    raw_df = pd.read_csv(BASE_DIR / "data" / "raw_sensor_log.csv")
    raw_df["timestamp"] = pd.to_datetime(raw_df["timestamp"])
    
    model = OverflowRiskModel()
    
    # Archetype 1: Residential Bin (Slow filling)
    res_bin = raw_df[raw_df["bin_id"] == "bin_000"].sort_values("timestamp")
    # Take a 48-hour slice when fill is around 40-50%
    res_slice = res_bin.iloc[20:70]
    res_pred = model.predict_from_history(res_slice)
    
    print("\n--- Scenario A: Residential Smart Bin (bin_000) ---")
    print(f"  Current Fill Level    : {res_pred['fill_pct']}%")
    print(f"  Sensor Status         : {'HEALTHY (1)' if res_pred['confidence_flag'] == 1 else 'UNRELIABLE (0)'}")
    print(f"  Predicted Time-to-90% : {res_pred['time_to_overflow_hours']:.1f} hours")
    print(f"  Assigned Risk Category: [{res_pred['risk_level']}] (Schedule routine collection)")
    
    # Archetype 2: Commercial High-Usage Bin (Fast filling)
    comm_bin = raw_df[raw_df["bin_id"] == "bin_005"].sort_values("timestamp")
    # Take a slice when fill is rising rapidly towards 70%
    comm_slice = comm_bin.iloc[10:55]
    comm_pred = model.predict_from_history(comm_slice)
    
    print("\n--- Scenario B: Commercial High-Traffic Bin (bin_005) ---")
    print(f"  Current Fill Level    : {comm_pred['fill_pct']}%")
    print(f"  Sensor Status         : {'HEALTHY (1)' if comm_pred['confidence_flag'] == 1 else 'UNRELIABLE (0)'}")
    print(f"  Predicted Time-to-90% : {comm_pred['time_to_overflow_hours']:.1f} hours")
    print(f"  Assigned Risk Category: [{comm_pred['risk_level']}] (Queue for next collection route)")
    
    # Archetype 3: Event Surge Bin (Festival / Sudden Rush)
    surge_bin = raw_df[raw_df["bin_id"] == "bin_010"].sort_values("timestamp")
    # Find a cycle where fill is high and rising fast
    high_fill_idx = surge_bin[surge_bin["fill_pct"] > 75].index
    if len(high_fill_idx) > 0:
        target_idx = high_fill_idx[0]
        pos = surge_bin.index.get_loc(target_idx)
        surge_slice = surge_bin.iloc[max(0, pos-48):pos+1]
    else:
        surge_slice = surge_bin.iloc[30:80]
        
    surge_pred = model.predict_from_history(surge_slice)
    
    print("\n--- Scenario C: Event Area Smart Bin during Surge (bin_010) ---")
    print(f"  Current Fill Level    : {surge_pred['fill_pct']}%")
    print(f"  Sensor Status         : {'HEALTHY (1)' if surge_pred['confidence_flag'] == 1 else 'UNRELIABLE (0)'}")
    print(f"  Predicted Time-to-90% : {surge_pred['time_to_overflow_hours']:.1f} hours")
    print(f"  Assigned Risk Category: [{surge_pred['risk_level']}] (IMMEDIATE DISPATCH REQUIRED)")

    print_banner("3. MODEL EVALUATION SUMMARY & COMPARISON")
    with open(BASE_DIR / "models" / "eval_results.json") as f:
        eval_data = json.load(f)
    
    print("  Comparison on 8,589 held-out cycle test samples:")
    print(f"  {'Model':<32} {'MAE (h)':<10} {'RMSE (h)':<10} {'Accuracy':<10} {'Critical Recall'}")
    print("  " + "-" * 75)
    for res in eval_data["results"]:
        marker = " *" if res["model"] == eval_data["selected_model"] else ""
        print(f"  {res['model']+marker:<32} {res['MAE_hours']:<10.2f} {res['RMSE_hours']:<10.2f} {res['risk_level_accuracy']:<10.1%} {res['critical_recall']:<10.1%}")
    print("\n  * Selected model artifact")
    print("=" * 70 + "\n")

if __name__ == "__main__":
    run_tests()
    demonstrate_scenarios()
