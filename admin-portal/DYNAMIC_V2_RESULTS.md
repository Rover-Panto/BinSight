# Dynamic routing v2: matched simulation results

**Evaluation date:** 28 August 2026  
**Status:** Definitive synthetic evaluation; field/shadow validation required  
**Design:** 11 scenarios × 30 paired replications × 2 policies = 660 policy runs

## Decision

Dynamic v2 should remain in fixture/replay and shadow mode. It is a useful overflow-safety policy, but it is not yet a cost-saving replacement for the fixed schedule.

Under normal patterned demand, dynamic v2 reduced mean overflow incidents from 10.33 to 3.37, spilled mass from 3,953.22 kg to 117.91 kg, and low-fill pickups from 45.20 to 24.00. It did so by increasing trips from 18.00 to 38.57, distance from 689.84 km to 1,233.11 km, and fuel from 489.09 L to 758.70 L. The paired 95% confidence intervals exclude zero for each of those differences.

Sensor failure is the clearest stop condition: dynamic v2 increased overflow incidents from 12.43 to 31.70, trips from 18.00 to 52.60, distance from 683.69 km to 1,499.85 km, and fuel from 485.04 L to 862.20 L. Spilled mass was lower on average, but its paired confidence interval includes zero, so that apparent benefit is not reliable. Live dispatch must therefore fail back to an approved schedule/inspection procedure when telemetry health is below the field-calibrated gate.

No result in this document is measured municipal performance. Demand, sensing, service, fuel and overflow outcomes are synthetic engineering evidence.

## Objective outcomes

| 30-day scenario / objective | Fixed | Dynamic v2 | Paired result for dynamic v2 |
| --- | ---: | ---: | --- |
| Normal: overflow incidents | 10.33 | 3.37 | 6.97 fewer; 95% CI 2.73 to 11.20 |
| Normal: spilled mass | 3,953.22 kg | 117.91 kg | 3,835.31 kg less; 95% CI 1,854.01 to 5,816.60 |
| Normal: wasted pickups | 45.20 | 24.00 | 21.20 fewer; 95% CI 13.57 to 28.83 |
| Normal: trips | 18.00 | 38.57 | 20.57 more; 95% CI 19.56 to 21.57 more |
| Normal: distance | 689.84 km | 1,233.11 km | 543.27 km more; 95% CI 508.35 to 578.20 more |
| Normal: fuel | 489.09 L | 758.70 L | 269.62 L more; 95% CI 249.55 to 289.68 more |
| Event-heavy: wasted pickups | 61.97 | 23.10 | 38.87 fewer; 95% CI 30.45 to 47.28 |
| Event-heavy: spilled mass | 2,499.57 kg | 141.23 kg | 2,358.33 kg less; 95% CI 831.79 to 3,884.88 |
| Event-heavy: distance | 696.75 km | 1,202.06 km | 505.31 km more; 95% CI 459.74 to 550.88 more |
| Combined stress: spilled mass | 82,887.08 kg | 26,186.73 kg | 68.41% less |
| Combined stress: unserved required bins | 109.93 | 0.00 | 100% fewer |
| Combined stress: distance | 529.02 km | 1,677.90 km | 1,148.88 km more |
| Combined stress: fuel | 488.19 L | 1,260.54 L | 772.34 L more |
| Sensor failure: overflow incidents | 12.43 | 31.70 | 19.27 more; 95% CI 14.80 to 23.73 more |
| Sensor failure: spilled mass | 4,846.23 kg | 3,082.04 kg | 1,764.19 kg less on average; 95% CI −352.21 to 3,880.60 |
| Sensor failure: distance | 683.69 km | 1,499.85 km | 816.16 km more; 95% CI 783.19 to 849.13 more |

`paired_effects.csv` contains all metrics, units, paired confidence intervals, sign-flip tests and normality diagnostics for all scenarios. The table above is a decision-focused subset rather than a post-hoc score.

## Forecast evaluation

The model trains on a 730-day synthetic pre-period. Training, probability-calibration and holdout windows are chronological. Every feature/label window is purged through the longest 168-hour target, and the latest historical target ends six hours before operations begin.

| Horizon | Model growth MAE | Naive growth MAE |
| ---: | ---: | ---: |
| 6 hours | 1.57 percentage points | 4.44 percentage points |
| 24 hours | 4.44 percentage points | 16.36 percentage points |
| 48 hours | 7.61 percentage points | 32.62 percentage points |
| 168 hours | 17.47 percentage points | 113.92 percentage points |

Additional holdout diagnostics:

- 48-hour overflow alert: 0.930 precision, 0.993 recall, Brier score 0.0185.
- 6-hour overflow alert at the 10% action threshold: 0.974 precision, 0.999 recall, Brier score 0.00486.
- Time-to-overflow MAE: 57.17 hours. This is too coarse to treat as an exact service clock.
- 90th-percentile 48-hour growth interval coverage: 84.6%, below the nominal 90%; live use requires recalibration.

These values validate the synthetic forecasting pipeline, not real-world generalization. The high alert metrics and underestimated upper-tail coverage can coexist because they measure different questions.

## Demand and scenario coverage

The paired demand process includes normalized hourly residential/commercial profiles, day-of-week effects, smoothly wrapped monthly and annual seasonality, persistent district/local autocorrelation, recurring and unannounced events with build-up/peak/decay, trends and abrupt changes. Both policies receive the same latent arrivals, event realizations and observation noise for each paired replication.

The definitive scenarios are:

1. normal patterned demand;
2. high seasonal demand;
3. event-heavy demand;
4. persistent multi-day surge;
5. localized surge;
6. gradual upward trend;
7. abrupt behavior change;
8. sensor failure;
9. reduced truck capacity;
10. traffic disruption; and
11. combined demand and operational stress.

Regime-level and decision-driver outputs are retained separately so a whole-run average cannot hide quiet, normal or surge behavior. For example, the normal scenario averaged 24.63 forecast-driven dynamic dispatches, 27.03 daily dispatch-limit blocks and 84.10 sensor-uncertainty decisions per replication.

## Does the fixed path make sense?

The fixed comparator is strong but not universal or mathematically perfect:

- its service intent and three-day timing are fixed, but the stop order is re-optimized at each scheduled departure using the same cached OSRM matrices as dynamic v2;
- it preserves waste stream, payload, daily trip, depot return and duplicate-stop constraints;
- its solver is time-bounded and heuristic, so it has no global-optimality certificate;
- it cannot anticipate an event, react early to a localized surge, or safely infer missing telemetry;
- the 11-scenario suite is deliberately broad but cannot enumerate every road closure, demand shift, hardware fault or operational response; and
- the definitive fixed-route audit records all schedule, depot, duplicate and capacity checks, plus the exact limitation statement.

The evidence supports a hybrid field strategy: retain the fixed schedule as the approved fallback; operate dynamic v2 in shadow mode; require healthy, calibrated telemetry; and dispatch dynamically only after prospective field criteria show that the safety gain justifies the incremental trip cost.

## Reproducibility artifacts

All files below are under `artifacts/dynamic_v2/`:

- `run_provenance.json` — versions, assumptions, worker count and run identity;
- `seed_manifest.json` — 330 paired demand/sensor seed records and hashes;
- `replication_metrics.csv` — 660 policy-run rows;
- `policy_summary.csv` and `paired_effects.csv` — aggregates and paired inference;
- `demand_regime_metrics.csv` and `demand_regime_summary.csv` — quiet/normal/surge results;
- `decision_driver_summary.csv` — forecast, capacity, dispatch-limit and uncertainty drivers;
- `forecast_evaluation.json` and `fill_forecaster.joblib` — holdout diagnostics and locked model;
- `synthetic_forecast_training_data.csv.gz` — compressed synthetic modelling data;
- `fixed_baseline_route_audit.json` — schedule/path/constraint audit;
- `representative_route_events.json` and `representative_routes.geojson` — replayable route evidence.

The integrity check requires exactly 660 metric rows, 330 complete policy pairs, 11 scenarios, 30 replications per policy/scenario, finite numeric metrics, unique paired seeds, a 168-hour purge and passing fixed-route checks.
