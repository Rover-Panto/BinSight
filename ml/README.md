# BinSight — Overflow-Risk Machine Learning Subsystem (`ml`) v2.0

Official forecasting package for the **BinSight** smart waste management platform. Predicts continuous hours until smart bins reach the **service threshold** (`time_to_service_threshold_hours` at 90% fill), projects multi-horizon fill growth (6h, 24h, 48h, 168h), and assigns deterministic operational risk categories (`Critical`, `High`, `Medium`, `Low`) to optimize collection routes and dispatch alerts.

> **Note**: The model is trained and evaluated against **90% fill** (service threshold). It does **not** currently support 100% physical overflow prediction. Requesting `target_threshold_pct=100` returns `status: unsupported_threshold`.

---

## Key Capabilities & Highlights

- **Supervised Time-to-Service-Threshold Forecasting**: Estimates hours until ≥90% fill capacity using elapsed-time velocity trends and cyclical temporal embeddings.
- **PR2 Edge-to-Cloud Compatibility**: Dedicated **fill-only** feature pipeline requiring zero weight dependencies, natively processing PR2 sensor telemetry.
- **Multi-Horizon Projections**: Computes expected fill and growth rate for 6h, 24h, 48h, and 168h horizons. Overflow probabilities are explicitly `null` / `unsupported` until a calibrated probability model is trained.
- **Leakage-Free Chronological Holdout with Label Purging**: Trained on 60-day history (Jan–Feb), tuned on 15-day validation set (Mar 01–16), and evaluated on an untouched 15-day holdout (Mar 16–31). Training/validation rows whose threshold-crossing label event falls after their split boundary are purged.
- **Point-in-Time Correctness**: Enforces observation timestamp + receipt-time filtering at `decision_at`, rejects model use before its training cutoff, and returns `stale` status for old data.
- **Fail-Closed Artifact Loading**: Manifest is required. SHA-256 hash is verified **before** `joblib.load()`. Missing, tampered, or mismatched artifacts raise immediately.
- **Hardened Prediction Interface**: Clean Python package export (`from binsight_ml import ForecastProvider`) with structured `cold_start`, `unavailable`, `stale`, `model_unavailable`, `model_error`, and `unsupported_threshold` states.
- **Four-Bin Waste Type Support**: Accepts and preserves `waste_type` (general, plastic, metal, glass) in input/output. Current model does **not** use `waste_type` as a feature; per-waste-type evaluation should be reported separately.
- **Unified Artifact & Manifest Checksum**: Model architecture, hyperparameters, dependency versions, training-data cutoff, label-purge counts, and SHA-256 artifact checksums recorded in `manifest.json`.

---

## Subsystem Layout

```
ml/
├── __init__.py                # In-repo backward-compat package exports
├── binsight_ml/
│   └── __init__.py            # Installable package: from binsight_ml import ForecastProvider
├── pyproject.toml             # Package build specification & dependency configuration
├── data/
│   ├── raw_sensor_log.csv     # 90-day synthetic telemetry (64,800 rows across 15 bins)
│   ├── feature_table.csv      # Feature-engineered dataset (elapsed-time rates, time encodings)
│   └── labeled_dataset.csv    # Ground-truth labeled fill cycles with crossing_timestamp
├── models/
│   ├── overflow_model.joblib  # Trained model artifact (XGBoost Regressor)
│   ├── manifest.json          # Unified model manifest with SHA-256, training cutoff & purge counts
│   ├── feature_columns.json   # Feature list expected by model
│   ├── eval_results.json      # Benchmark evaluation metrics across all models
│   └── feature_importance.csv # Ranked feature importance values
├── src/
│   ├── simulate.py            # Synthetic bin sensor simulator (3 usage archetypes)
│   ├── features.py            # Elapsed-time sliding windows, cyclical encodings, reset detection
│   ├── label.py               # Cycle-aware time-to-threshold labeling & risk bucketing
│   ├── train.py               # Chronological partition, label-purge, validation selection & manifest
│   └── serve.py               # Production inference provider (ForecastProvider v2.0)
├── tests/
│   └── test_pipeline.py       # Automated test suite (27/27 tests passing)
├── docs/
│   └── IMPLEMENTATION_SPEC.md # Full technical and architectural specification
├── demo_app.py                # Interactive scenario demonstration & live prediction visualizer
├── requirements.txt           # Python package dependencies
└── run_all.sh                 # End-to-end pipeline execution script
```

---

## Quick Start & Usage

### 1. Environment Setup
```bash
pip install -r requirements.txt
```

### 2. Run Test Suite
```bash
python tests/test_pipeline.py
```

### 3. Run Live Interactive Demo
```bash
python demo_app.py
```

### 4. Integration Usage (Installed Package)
```bash
# Install as editable package
pip install -e ./ml
```

```python
from binsight_ml import ForecastProvider

# Initialize provider (validates manifest + hash before loading model)
provider = ForecastProvider(model_dir="path/to/ml/models")

# A. Single-bin history forecast
result = provider.predict_from_history(bin_history_df)
# result["time_to_service_threshold_hours"]  → hours to 90% fill
# result["target_threshold_pct"]             → 90.0
# result["status"]                           → "available" | "cold_start" | ...

# B. PR1 multi-bin snapshot forecast with point-in-time cutoff
snapshot_forecasts = provider.predict_snapshot(
    history=telemetry_df,
    bins=["bin_general", "bin_plastic", "bin_metal", "bin_glass"],
    decision_at="2026-03-16T12:00:00Z",
    input_snapshot_id="SNAP-001"
)
```

### 5. Output Contract (v2.0 Schema)
```json
{
  "schema_version": "2.0",
  "bin_id": "bin_general",
  "timestamp": "2026-03-16T11:30:00",
  "status": "available",
  "time_to_service_threshold_hours": 8.45,
  "target_threshold_pct": 90.0,
  "estimate_type": "expected_hours_to_service_threshold",
  "risk_level": "High",
  "fill_pct": 62.4,
  "confidence_flag": 1,
  "waste_type": "general",
  "waste_type_used_as_feature": false,
  "model_version": "2.0.0",
  "model_sha256": "881eec29de12...",
  "horizons": {
    "6":   {"expected_fill_pct": 74.4, "expected_growth_pct_points": 12.0, "overflow_probability": null, "overflow_probability_status": "unsupported"},
    "24":  {"expected_fill_pct": 100.0, "expected_growth_pct_points": 48.0, "overflow_probability": null, "overflow_probability_status": "unsupported"},
    "48":  {"expected_fill_pct": 100.0, "expected_growth_pct_points": 96.0, "overflow_probability": null, "overflow_probability_status": "unsupported"},
    "168": {"expected_fill_pct": 100.0, "expected_growth_pct_points": 336.0, "overflow_probability": null, "overflow_probability_status": "unsupported"}
  }
}
```

### Status Values
| Status | Meaning |
|---|---|
| `available` | Valid forecast produced |
| `cold_start` | Only 1 observation — forecast produced but with limited confidence |
| `unavailable` | Configured bin has no data |
| `stale` | Latest observation is too old (> 72h by default) |
| `model_unavailable` | Decision time is before model's training-data cutoff |
| `model_error` | Non-finite or negative prediction |
| `unsupported_threshold` | Requested threshold not trained (e.g. 100% when model is 90%) |
| `invalid_input` | Empty or null input |
| `missing_required_columns` | Required columns absent |

---

## Benchmark Results (Chronological Test Holdout, Label-Purged)

| Model / Approach | MAE (hours) | RMSE (hours) | Risk Accuracy | Critical Recall |
|---|---|---|---|---|
| Naive Extrapolation (Rule-based) | 26.49 | 49.90 | 45.4% | 72.0% |
| Linear Regression | 9.49 | 12.36 | 47.9% | 16.1% |
| **Random Forest Regressor** | **4.79** | **7.92** | **76.7%** | **83.2%** |
| **XGBoost Regressor (Selected)** | **4.70** | **7.42** | **73.0%** | **64.5%** |

### Known Limitations
- **waste_type not used as feature**: A single model is applied across all waste types. Per-waste-type evaluation should be examined for hidden performance disparities.
- **Overflow probabilities unsupported**: All `overflow_probability` fields are `null` until a calibrated probability model is trained and evaluated.
- **90% service threshold only**: The model cannot be used for 100% physical overflow prediction without retraining against that target.
