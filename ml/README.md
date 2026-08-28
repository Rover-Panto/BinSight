# BinSight — Overflow-Risk Machine Learning Subsystem (`ml`)

Official forecasting package for the **BinSight** smart waste management platform. Predicts continuous hours until smart bins reach overflow threshold (`time_to_overflow_hours`), projects multi-horizon fill growth (6h, 24h, 48h, 168h) with calibrated exceedance probabilities, and assigns deterministic operational risk categories (`Critical`, `High`, `Medium`, `Low`) to optimize collection routes and dispatch alerts.

---

## Key Capabilities & Highlights

- **Supervised Time-to-Overflow Forecasting**: Estimates hours until $\ge 90\%$ (or $100\%$) fill capacity using elapsed-time velocity trends and cyclical temporal embeddings.
- **PR2 Edge-to-Cloud Compatibility**: Dedicated **fill-only** feature pipeline requiring zero weight dependencies, natively processing PR2 sensor telemetry.
- **Multi-Horizon Projections & Calibrated Risk**: Computes expected fill, growth rate, and normal-exceedance overflow probabilities for 6h, 24h, 48h, and 168h horizons.
- **Leakage-Free Chronological Holdout**: Trained on 60-day history (Jan–Feb), tuned on 15-day validation set (Mar 01–16), and evaluated on an untouched 15-day holdout (Mar 16–31, 9,794 samples).
- **Hardened Prediction Interface**: Clean Python package export (`from ml import ForecastProvider`) with structured cold-start, unavailable, and model-error states.
- **Unified Artifact & Manifest Checksum**: Model architecture, hyperparameters, dependency versions, and SHA-256 artifact checksums recorded in `manifest.json`.

---

## Subsystem Layout

```
ml/
├── __init__.py                # Package exports (ForecastProvider, OverflowRiskModel)
├── pyproject.toml             # Package build specification & dependency configuration
├── data/
│   ├── raw_sensor_log.csv     # 90-day synthetic telemetry (64,800 rows across 15 bins)
│   ├── feature_table.csv      # Feature-engineered dataset (elapsed-time rates, time encodings)
│   └── labeled_dataset.csv    # Ground-truth labeled fill cycles (57,892 samples)
├── models/
│   ├── overflow_model.joblib  # Trained model artifact (XGBoost Regressor)
│   ├── manifest.json          # Unified model manifest with SHA-256 checksum & metadata
│   ├── feature_columns.json   # Feature list expected by model
│   ├── eval_results.json      # Benchmark evaluation metrics across all models
│   └── feature_importance.csv # Ranked feature importance values
├── src/
│   ├── simulate.py            # Synthetic bin sensor simulator (3 usage archetypes)
│   ├── features.py            # Elapsed-time sliding windows, cyclical encodings, reset detection
│   ├── label.py               # Cycle-aware time-to-overflow labeling & risk bucketing
│   ├── train.py               # Chronological partition, validation-based selection & manifest export
│   └── serve.py               # Production inference provider (ForecastProvider / OverflowRiskModel)
├── tests/
│   └── test_pipeline.py       # Automated test suite (15/15 tests passing)
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

### 4. Integration Usage (Local Python Import)
```python
from ml import ForecastProvider

# Initialize provider (loads model artifact and verifies SHA-256 checksum)
provider = ForecastProvider()

# A. Single-bin history forecast
result = provider.predict_from_history(bin_history_df)

# B. PR1 multi-bin snapshot forecast with cutoff filtering
snapshot_forecasts = provider.predict_snapshot(
    history=telemetry_df,
    bins=["bin_000", "bin_005", "bin_010"],
    decision_at="2026-03-16T12:00:00Z",
    input_snapshot_id="SNAP-001"
)
```

---

## Benchmark Results (Chronological Test Holdout: 9,794 samples)

| Model / Approach | MAE (hours) | RMSE (hours) | Risk Accuracy | Critical Recall |
|---|---|---|---|---|
| Naive Extrapolation (Rule-based) | 26.49 | 49.90 | 45.4% | 72.0% |
| Linear Regression | 9.50 | 12.35 | 47.8% | 15.8% |
| **Random Forest Regressor** | **4.75** | **7.83** | **77.0%** | **83.0%** |
| **XGBoost Regressor (Selected)** | **4.66** | **7.33** | **73.2%** | **65.5%** |
