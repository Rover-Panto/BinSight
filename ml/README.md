# BinSight — Overflow-Risk ML Component

Predicts, per smart bin, how many hours until it reaches overflow capacity (`time_to_overflow_hours`) and assigns a deterministic operational `risk_level` (`Critical`, `High`, `Medium`, `Low`) based on ultrasonic and load-cell sensor telemetry streams.

---

## Key Capabilities & Highlights

- **Supervised Time-to-Overflow Regression**: Predicts continuous hours until >=90% bin capacity using rolling trends and time-of-day features.
- **Deterministic Operational Risk Bucketing**: Converts continuous estimates into actionable dispatch alerts (`Critical` <4h, `High` <12h, `Medium` <24h, `Low` ≥24h).
- **Leakage-Free Temporal Split**: Evaluated on complete, independent fill-cycles across 3 distinct usage archetypes (Residential, Commercial, Event Surge).
- **Production Inference Wrapper**: Simple single-method integration (`OverflowRiskModel.predict_from_history`) for backend / IoT hub services.

---

## Repository Layout & Script Summary

```
BinSight/
├── data/
│   ├── raw_sensor_log.csv         # 90-day synthetic telemetry (64,800 rows across 15 bins)
│   ├── feature_table.csv          # Feature-engineered dataset (rolling rates, time encodings)
│   └── labeled_dataset.csv        # Ground-truth labeled fill cycles (57,892 samples)
├── models/
│   ├── overflow_model.joblib      # Trained machine learning model artifact
│   ├── feature_columns.json       # Ordered feature list expected by model
│   ├── eval_results.json          # Benchmark evaluation metrics across all models
│   └── feature_importance.csv     # Ranked feature importance values
├── src/
│   ├── simulate.py                # Synthetic bin sensor simulator (3 usage archetypes)
│   ├── features.py                # Rolling rates, cyclical time encodings, reset detection
│   ├── label.py                   # Cycle-aware time-to-overflow labeling & risk bucketing
│   ├── train.py                   # Model training, cycle-stratified split & comparative evaluation
│   └── serve.py                   # Production inference class (OverflowRiskModel)
├── tests/
│   └── test_pipeline.py           # Automated sanity and contract verification tests
├── docs/
│   └── IMPLEMENTATION_SPEC.md     # Complete technical specification and architectural spec
├── demo_app.py                    # Interactive demo script showing live predictions
├── quick_train_rf.py              # Standalone fast Random Forest training script
├── test_model_inference.py        # Smoke testing inference across multiple archetypes
├── requirements.txt               # Python package dependencies
└── run_all.sh                     # End-to-end pipeline rerun script
```

---

## Quick Start & Usage

### 1. Environment Setup
```bash
pip install -r requirements.txt
```

### 2. Run Sanity Checks & Test Suite
```bash
python tests/test_pipeline.py
```

### 3. Run Live Interactive Demo
```bash
python demo_app.py
```

### 4. Integration into Hub / Backend Services
```python
import sys
from pathlib import Path
sys.path.insert(0, "src")

from serve import OverflowRiskModel

# Initialize model once at service startup
model = OverflowRiskModel()

# Pass recent DataFrame of sensor readings for a bin (sorted by timestamp)
prediction = model.predict_from_history(bin_history_df)

# Output structure:
# {
#   "bin_id": "bin_005",
#   "timestamp": "2026-01-02 05:30:00",
#   "time_to_overflow_hours": 3.78,
#   "risk_level": "Critical",
#   "fill_pct": 62.4,
#   "confidence_flag": 1
# }
```

---

## Benchmark Results

Evaluated on 8,589 held-out cycle test samples:

| Model / Approach | MAE (hours) | RMSE (hours) | Accuracy | Critical Recall |
|---|---|---|---|---|
| Naive Extrapolation (Rule-based) | 25.49 | 48.85 | 42.9% | 71.4% |
| Linear Regression | 10.23 | 13.31 | 43.6% | 16.4% |
| **Random Forest Regressor** | **5.42** | **8.71** | **73.3%** | **80.3%** |
| **XGBoost Regressor** | **5.26** | **8.21** | **70.4%** | **66.8%** |

*Note*: Both machine learning models cut error by ~50% compared to linear regression and ~80% compared to rule-based extrapolation. See `docs/IMPLEMENTATION_SPEC.md` for full metrics and analysis.
