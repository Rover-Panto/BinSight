# BinSight — Overflow-Risk ML Model: Implementation Spec

**Audience:** ML/AI engineer picking up this repo to finish integration and deployment.
**Scope of this document:** data generation, feature engineering, labeling, model training, evaluation, and the serving contract for the overflow-risk model ONLY.
**Explicitly out of scope (owned by other subsystems, not covered here):** MCU/RTOS firmware, sensor calibration hardware, the hub's route-priority logic, the dashboard UI, and the return-station (Focus D) system. This model is one input to those systems, described precisely in [§10 Serving contract](#10-serving-contract-what-the-rest-of-the-system-calls).

**Status: the pipeline in this repo has already been run end to end.** `data/` and `models/` contain real output from an actual execution (not placeholders) — a trained model is included. See `models/eval_results.json` for the numbers. Everything below is both documentation and a faithful description of code that has been executed and verified, so you can either use the included trained model directly or regenerate everything from scratch with `./run_all.sh`.

---

## Table of contents

1. [Problem definition](#1-problem-definition)
2. [Data strategy: dataset search findings + why synthetic is primary](#2-data-strategy)
3. [Repository structure](#3-repository-structure)
4. [Environment setup](#4-environment-setup)
5. [Component 1 — Synthetic simulator (`simulate.py`)](#5-component-1--synthetic-simulator-simulatepy)
6. [Component 2 — Feature engineering (`features.py`)](#6-component-2--feature-engineering-featurespy)
7. [Component 3 — Labeling (`label.py`)](#7-component-3--labeling-labelpy)
8. [Component 4 — Training & evaluation (`train.py`)](#8-component-4--training--evaluation-trainpy)
9. [Component 5 — Serving wrapper (`serve.py`)](#9-component-5--serving-wrapper-servepy)
10. [Serving contract: what the rest of the system calls](#10-serving-contract-what-the-rest-of-the-system-calls)
11. [Execution (already run once — here's how to rerun)](#11-execution-already-run-once--heres-how-to-rerun)
12. [Results obtained on the synthetic dataset](#12-results-obtained-on-the-synthetic-dataset)
13. [Retraining once real sensor logs are available](#13-retraining-once-real-sensor-logs-are-available)
14. [Optional: hyperparameter tuning](#14-optional-hyperparameter-tuning)
15. [Definition of done / acceptance checklist](#15-definition-of-done--acceptance-checklist)
16. [Known limitations and judgment calls flagged for review](#16-known-limitations-and-judgment-calls-flagged-for-review)

---

## 1. Problem definition

**Input (per bin, per reading):** `timestamp`, `bin_id`, `fill_pct` (0-100, ultrasonic-derived), `weight_kg` (load cell), `confidence_flag` (1 = good reading, 0 = sensor flagged the reading as noisy/blocked/out-of-range by the MCU).

**Output (per bin, per inference call):**
- `time_to_overflow_hours` — regression estimate of hours until `fill_pct` reaches the overflow threshold (90%, configurable — see `OVERFLOW_THRESHOLD_PCT` in `src/label.py`).
- `risk_level` — one of `Critical` (<4h), `High` (<12h), `Medium` (<24h), `Low` (≥24h), derived deterministically from `time_to_overflow_hours`. Thresholds are in `RISK_BINS` in `src/label.py`; change them there, not ad hoc elsewhere.

**Model type:** supervised regression (tree ensemble) trained on engineered features from rolling sensor history. Not a classifier trained directly on `risk_level` — the risk bucket is always derived from the regression output, not predicted independently, to keep the two outputs consistent by construction.

**Why regression + derived bucket, not a standalone classifier:** the hub's routing logic needs a continuous, rankable urgency score to prioritize which bins to visit first; the dashboard/LEDs need a discrete category. Predicting the continuous value once and bucketing it guarantees the two never disagree.

---

## 2. Data strategy

### 2.1 Public dataset search — findings

A dataset search (Kaggle, Mendeley Data, GitHub, IEEE/academic sources) turned up no ready-to-use, free, public dataset of per-bin time-series sensor readings (fill % + weight + timestamp, multiple bins, multi-week duration) suitable for directly training a time-to-overflow model. What exists:

- **Kaggle "Smart-Waste-Management-Dataset"** (viroopaksh) — an **image/object-detection** dataset for waste classification (Focus B territory), not sensor time series. Not usable here.
- **Mendeley Data "Smart Bin Insights"** (DOI 10.17632/8wc9jtndf6.1) — an academic dataset comparing regression vs. classification for bin-fill prediction, but the public listing does not expose a clear column schema or confirm multi-bin longitudinal coverage. Treat as a possible supplementary/validation source only after inspecting the actual files, not as a primary training source.
- **GoMask.ai "Smart Bin Sensor Fill Levels"** — itself a **synthetic** dataset sold on a commercial data marketplace, not a real-world collection. No advantage over generating our own synthetic data with parameters we control and can defend to judges.
- Multiple published smart-bin studies explicitly state they used **simulated data** because no fine-grained public smart-bin dataset exists at the scale they needed — this is the standard workaround in the field, not a shortcut specific to this project.

**Conclusion:** build a synthetic simulator as the primary training data source, calibrated to be physically plausible, and treat a short window of real logged data from the 3 physical prototype bins as a validation/calibration set — not as the primary training corpus. This is the approach implemented in this repo.

### 2.2 Real sensor log format

When real hub logs become available, they MUST conform to this schema so they can be fed directly into the same feature/label pipeline used for synthetic data:

```
timestamp        : ISO 8601 datetime string, e.g. "2026-09-01T14:30:00"
bin_id            : string, e.g. "bin_A01"
fill_pct          : float, 0-100 (allow slight overshoot/undershoot from sensor noise)
weight_kg         : float, >= 0
confidence_flag   : int, 1 = good reading, 0 = flagged by MCU as unreliable
```

One CSV row per reading per bin. Sort order does not matter (the pipeline sorts internally), but do not deduplicate or pre-filter `confidence_flag == 0` rows before handing the log to the pipeline — filtering happens inside feature engineering, and dropping rows upstream can create false gaps in the rolling-rate calculations.

---

## 3. Repository structure

```
binsight_ml/
├── README.md                      # quick start
├── requirements.txt
├── run_all.sh                     # one-command full pipeline rerun
├── .gitignore
├── data/
│   ├── raw_sensor_log.csv         # simulator output (already generated)
│   ├── feature_table.csv          # after features.py (already generated)
│   └── labeled_dataset.csv        # after label.py — training-ready (already generated)
├── models/
│   ├── overflow_model.joblib      # TRAINED model artifact (already trained)
│   ├── feature_columns.json       # exact ordered feature list the model expects
│   ├── eval_results.json          # baseline + model comparison metrics
│   └── feature_importance.csv     # trained model's feature importances
├── src/
│   ├── simulate.py
│   ├── features.py
│   ├── label.py
│   ├── train.py
│   └── serve.py
├── tests/
│   └── test_pipeline.py           # sanity checks — run after any retrain
└── docs/
    └── IMPLEMENTATION_SPEC.md     # this file
```

All scripts use `Path(__file__).resolve().parent.parent` to locate `data/` and `models/`, so they work correctly whether invoked as `python3 src/train.py` from the repo root or `python3 train.py` from inside `src/`.

---

## 4. Environment setup

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Or just run `./run_all.sh`, which installs dependencies and runs the full pipeline in one step.

---

## 5. Component 1 — Synthetic simulator (`simulate.py`)

Generates per-bin time series with three usage archetypes (residential, commercial, event-surge), hour-of-day and day-of-week usage patterns, sensor noise, and occasional bad readings. Fill cycles (between collection/reset events) are tracked via `cycle_id`, which the labeling step uses to compute exact time-to-overflow labels with no ambiguity, since the ground truth is known by construction.

Key parameters (in `BIN_PROFILES` and the module constants): `n_bins_per_profile=5`, `n_days=90`, `seed=42`, `OVERFLOW_THRESHOLD_PCT=90`, `STEP_MINUTES=30`. These are the only knobs the team should need to touch — see full source in `src/simulate.py`.

**Verified output (already in `data/raw_sensor_log.csv`):** 64,800 rows across 15 simulated bins (5 per profile × 90 days × 48 samples/day). Per-bin overflow cadence came out realistic without any manual tuning: residential ≈ every 72h, commercial ≈ every 13.5h, event-surge ≈ every 32h with occasional faster surge cycles.

---

## 6. Component 2 — Feature engineering (`features.py`)

Full source in `src/features.py`. Feature reference:

| Feature | Meaning |
|---|---|
| `fill_pct`, `weight_kg` | Raw calibrated sensor readings |
| `density_proxy` | `weight_kg / fill_pct` — flags contamination or unusually dense waste; also a sensor-agreement signal |
| `fill_rate_1h`, `fill_rate_6h` | Rolling rate of change — the primary predictive signal |
| `weight_rate_1h` | Same, for mass |
| `hour_sin/cos`, `dow_sin/cos`, `is_weekend` | Cyclic time encodings — daily/weekly usage rhythm |
| `hist_avg_rate_same_slot` | The bin's own learned pattern for that hour-of-day, computed only from strictly prior days (no leakage) |
| `time_since_reset_hours` | Hours since the last detected collection event |

**Verified:** zero NaNs in the output feature table (`data/feature_table.csv`) on the full 64,800-row simulated log.

---

## 7. Component 3 — Labeling (`label.py`)

Full source in `src/label.py`. For every row at time `t_i` within a bin's fill cycle, the label is the time until `fill_pct` next crosses `OVERFLOW_THRESHOLD_PCT` within that **same cycle**. Rows in a cycle that never reach the threshold before the log ends are dropped (right-censored).

**Why a loop and not `groupby(...).apply(...)`:** newer pandas versions (3.x) drop the grouping key columns from the sub-frame passed into `.apply()` unless you pass `include_groups=True`, which is not available on all versions. The explicit loop in `build_labels()` is the version-safe way to keep `bin_id`/`cycle_id` attached to the labeled rows — don't "simplify" this back to `.apply()` without checking your pandas version.

**Verified on the 64,800-row feature table:**
- 6,908 rows (10.7%) were censored and dropped, leaving 57,892 labeled rows (`data/labeled_dataset.csv`).
- Risk level distribution: Low 17,303 / High 15,559 / Medium 14,153 / Critical 10,877 — reasonably balanced.
- `time_to_overflow_hours`: mean 20.1h, median 13.5h, max 116h.

---

## 8. Component 4 — Training & evaluation (`train.py`)

**Split strategy:** split by whole `(bin_id, cycle_id)` fill-cycle, not by row. Rows within one cycle are highly correlated (same underlying trajectory) — row-level random shuffling would leak information across train/val/test. 70% of cycles → train, 15% → val, 15% → test, stratified by bin profile so all three sets see every usage archetype.

**Models trained (full source in `src/train.py`):**
- Baseline 1: naive linear extrapolation from current fill rate (no ML, no training)
- Baseline 2: linear regression on engineered features
- Model A: Random Forest Regressor (`n_estimators=300, max_depth=12, min_samples_leaf=5`)
- Model B: XGBoost (`n_estimators=300, max_depth=6, learning_rate=0.05, subsample=0.8, colsample_bytree=0.8`)

**IMPORTANT — read before retraining unattended:** the script auto-selects the model with the lowest MAE. On the run already committed to this repo, that picked **XGBoost**. But Random Forest had meaningfully better `critical_recall` (0.803 vs 0.668) — see [§12](#12-results-obtained-on-the-synthetic-dataset). Missing a Critical case means an actual overflow in production; a small MAE difference matters far less operationally. **The model currently saved in `models/overflow_model.joblib` is the auto-selected XGBoost model** — before using it in the final demo, decide whether to keep it or manually swap in the Random Forest (both are reproducible by rerunning `train.py`, which is deterministic given `SPLIT_SEED=42`). This is a judgment call for the team to make explicitly and document in the report, not something to silently automate away.

---

## 9. Component 5 — Serving wrapper (`serve.py`)

This is the only file anything outside the ML component should import. Full source in `src/serve.py`.

**Verified smoke test output (bin_005, first 30h of simulated history):**

```json
{
  "bin_id": "bin_005",
  "timestamp": "2026-01-02 05:30:00",
  "time_to_overflow_hours": 3.78,
  "risk_level": "Critical",
  "fill_pct": 62.4,
  "confidence_flag": 1
}
```

---

## 10. Serving contract: what the rest of the system calls

For whoever integrates this on the hub (Focus C):

```python
from serve import OverflowRiskModel

model = OverflowRiskModel()  # loads once at hub startup

# On each new reading (or on a schedule, e.g. every 5-15 min):
result = model.predict_from_history(bin_history_df)
# result = {
#   "bin_id": str,
#   "timestamp": str,
#   "time_to_overflow_hours": float,
#   "risk_level": "Critical" | "High" | "Medium" | "Low",
#   "fill_pct": float,
#   "confidence_flag": 0 | 1,
# }
```

**Contract notes:**
- `bin_history_df` must be raw sensor rows for a **single bin**, with **at least 24h of prior readings** at the deployed sampling interval — the feature pipeline needs that history to compute `fill_rate_6h` and `hist_avg_rate_same_slot`. Less history degrades those two features to 0 (no observed change), which the model will still handle (they were filled with 0 for cold-start rows during training) but with reduced accuracy.
- `confidence_flag == 0` in the input does **not** block prediction — the model was trained on data including flagged rows so it degrades gracefully, but the hub should surface the flag alongside the prediction (e.g., grey out or asterisk a bin's risk badge) rather than hiding it.
- If you need predictions for multiple bins at once, call `predict_from_history` once per bin (it's a lightweight tree-model call, not a bottleneck at 3-bin or even hundred-bin scale).

---

## 11. Execution (already run once — here's how to rerun)

The included `data/` and `models/` are real output from a successful run. To regenerate everything from scratch (e.g. after changing simulator parameters or adding real data):

```bash
./run_all.sh
```

Or step by step from the repo root:

```bash
python3 src/simulate.py    # -> data/raw_sensor_log.csv
python3 src/features.py    # -> data/feature_table.csv
python3 src/label.py       # -> data/labeled_dataset.csv
python3 src/train.py       # -> models/overflow_model.joblib, feature_columns.json, eval_results.json, feature_importance.csv
python3 src/serve.py       # smoke test — prints one prediction
python3 tests/test_pipeline.py   # sanity checks
```

Everything is seeded (`RNG_SEED=42`, `SPLIT_SEED=42`) so reruns are reproducible.

---

## 12. Results obtained on the synthetic dataset

From the run committed to this repo (`n_bins_per_profile=5`, `n_days=90`, `seed=42`), test set = 8,589 rows from held-out fill-cycles (exact numbers in `models/eval_results.json`):

| Model | MAE (hours) | RMSE (hours) | Risk-level accuracy | Critical recall |
|---|---|---|---|---|
| Naive extrapolation (baseline) | 25.485 | 48.847 | 0.429 | 0.714 |
| Linear regression (baseline) | 10.229 | 13.310 | 0.436 | 0.164 |
| Random Forest | 5.424 | 8.712 | **0.733** | **0.803** |
| XGBoost (auto-selected) | **5.262** | **8.207** | 0.704 | 0.668 |

**Reading this table:** both ML models roughly halve the error of the linear baseline and are ~5x better than naive extrapolation — this is the core "AI vs. no-AI" improvement claim for the judging criteria. Random Forest and XGBoost trade off slightly against each other (XGBoost lower MAE, Random Forest much better at catching true Critical cases) — see the model-selection note in §8.

Top feature importances (see `models/feature_importance.csv` for the full list): `fill_pct` (0.28), `time_since_reset_hours` (0.15), `weight_kg` (0.10), `hour_sin` (0.09), `fill_rate_6h` (0.07), `weight_rate_1h` (0.07) — the model leans most on current fill state and time-since-collection, with the engineered rate and calendar features contributing meaningfully rather than being dead weight. Worth including directly in the final report for the Technical Depth criterion.

---

## 13. Retraining once real sensor logs are available

1. Export the hub's logged readings to CSV matching the schema in §2.2, save as e.g. `data/real_sensor_log.csv`.
2. Run `features.py` and `label.py` logic on the real log exactly as on synthetic data (point the scripts at the real file, or import `build_feature_table` / `build_labels` directly in a small script).
3. **Do not simply concatenate real + synthetic rows and retrain blindly.** Instead:
   - Hold out the entire real dataset as a **final validation set** (do not train on any of it initially).
   - Train on synthetic data only (as in §8), evaluate on the real holdout, and report that number honestly alongside the synthetic-test number — two rows, clearly labeled, not blended into one misleading accuracy figure.
   - If real-data validation error is much worse than synthetic-test error, that gap is itself useful evidence: it tells you which `BIN_PROFILES` parameters in `simulate.py` need recalibrating against the real fill/weight rates you observed, rather than a sign the model is broken.
   - Only after recalibrating the simulator to better match observed real rates should you consider adding a portion of real data into the training set, keeping a separate real holdout untouched for final reporting.
4. Re-run `train.py` unchanged — it doesn't care whether `labeled_dataset.csv` came from synthetic or blended data.

---

## 14. Optional: hyperparameter tuning

The hyperparameters in `train.py` were chosen as reasonable, well-tested defaults for small-to-medium tree ensembles and were not exhaustively tuned. If time permits, a light randomized search on the Random Forest is a low-risk improvement:

```python
from sklearn.model_selection import RandomizedSearchCV

param_dist = {
    "n_estimators": [200, 300, 500],
    "max_depth": [8, 12, 16, None],
    "min_samples_leaf": [2, 5, 10],
    "max_features": ["sqrt", 0.5, 1.0],
}
search = RandomizedSearchCV(
    RandomForestRegressor(random_state=SPLIT_SEED, n_jobs=-1),
    param_distributions=param_dist, n_iter=15, cv=3,
    scoring="neg_mean_absolute_error", random_state=SPLIT_SEED, n_jobs=-1,
)
search.fit(X_train, y_train)
print(search.best_params_)
```

Treat this as a nice-to-have, not a blocker — the untuned defaults already beat both baselines by a wide margin (§12), which is what the judging criteria actually require.

---

## 15. Definition of done / acceptance checklist

- [x] `simulate.py` runs and produces `raw_sensor_log.csv` with no errors — **done, included**
- [x] `features.py` runs and produces `feature_table.csv` with zero NaNs — **done, included**
- [x] `label.py` runs, censored-row count under 15% of total rows — **done, 10.7%**
- [x] `train.py` runs and both ML models beat both baselines on test-set MAE — **done, confirmed**
- [x] `eval_results.json` and feature-importance saved for the final report — **done, included**
- [ ] Model selection (Random Forest vs XGBoost) reviewed against both MAE and critical-recall by a human — **flagged, needs your decision (§8)**
- [x] `serve.py` smoke test returns a well-formed prediction dict — **done, verified**
- [ ] Hub/integration engineer given the `OverflowRiskModel` usage snippet (§10) — **do this as part of handoff**
- [ ] Real sensor log collection started and validated against §13 before the final report deadline — **not yet possible in this environment; needs the physical prototype**

---

## 16. Known limitations and judgment calls flagged for review

- **Overflow threshold (90%) and risk-level cutoffs (4h/12h/24h) are placeholders.** They're centralized in `src/label.py` (`OVERFLOW_THRESHOLD_PCT`, `RISK_BINS`) specifically so the team can adjust them after seeing real bin behavior without touching any other file.
- **Reset detection (`drop_pct=40.0` in `add_reset_features`)** assumes a collection event causes a fill-level drop of at least 40 percentage points in one sample interval. If real collections are partial (bin not fully emptied) this threshold may need lowering — verify against real logs once available.
- **The censored-row handling (dropping cycles that never reach threshold) discards information.** For a 90-day synthetic window this only cost 10.7% of rows; for a much shorter real-data collection window, a larger fraction of cycles may be censored, shrinking the usable real-validation set. This is expected and is exactly why synthetic data is the primary training source (§2.1), not a flaw to fix.
- **Model selection logic auto-picks by MAE** but the Random Forest vs. XGBoost trade-off on critical-recall (§8, §12) is a real disagreement between the two candidates that a human should resolve, not the script. **This is the single most important open decision left in this repo.**
- **This repo has never seen real sensor data.** Every number in §12 is on synthetic data only. Treat the model as "pipeline-validated, not field-validated" until §13 is completed.
