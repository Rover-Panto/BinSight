# Dynamic routing v2: matched simulation results

**Evaluation date:** 28 August 2026  
**Status:** Definitive synthetic evaluation; field/shadow validation required  
**Design:** 11 scenarios × 30 paired replications × 2 policies = 660 policy runs

## Decision

Dynamic v2 should remain in fixture/replay and shadow mode. It is a useful overflow-safety policy, but it is not yet a cost-saving replacement for the fixed schedule.

Under normal patterned demand, dynamic v2 reduced mean overflow incidents from 3.97 to 0.90 and spilled mass from 281.52 kg to 24.16 kg. It did so by increasing trips from 17.70 to 24.13, distance from 505.27 km to 718.89 km, fuel from 409.38 L to 505.84 L, and low-fill pickups from 21.73 to 32.97. The paired 95% confidence intervals exclude zero for each of those differences.

Sensor failure is the clearest stop condition: dynamic v2 increased overflow incidents from 3.57 to 9.20, spilled mass from 172.60 kg to 495.25 kg, trips from 17.77 to 37.80, distance from 506.68 km to 1,152.40 km, fuel from 410.16 L to 727.73 L, and low-fill pickups from 21.10 to 37.33. Live dispatch must therefore fail back to an approved schedule/inspection procedure when telemetry health is below the field-calibrated gate.

No result in this document is measured municipal performance. Demand, sensing, service, fuel and overflow outcomes are synthetic engineering evidence.

## Objective outcomes

| 30-day scenario / objective | Fixed | Dynamic v2 | Paired result for dynamic v2 |
| --- | ---: | ---: | --- |
| Normal: overflow incidents | 3.97 | 0.90 | 3.07 fewer; 95% CI 0.91 to 5.22 |
| Normal: spilled mass | 281.52 kg | 24.16 kg | 257.37 kg less; 95% CI 146.55 to 368.19 |
| Normal: wasted pickups | 21.73 | 32.97 | 11.23 more; 95% CI 5.09 to 17.37 more |
| Normal: trips | 17.70 | 24.13 | 6.43 more; 95% CI 5.31 to 7.55 more |
| Normal: distance | 505.27 km | 718.89 km | 213.62 km more; 95% CI 185.97 to 241.27 more |
| Normal: fuel | 409.38 L | 505.84 L | 96.46 L more; 95% CI 79.12 to 113.80 more |
| Event-heavy: wasted pickups | 34.93 | 24.83 | 10.10 fewer; 95% CI 1.17 to 19.03 |
| Event-heavy: spilled mass | 159.92 kg | 34.22 kg | 125.70 kg less; 95% CI 53.39 to 198.00 |
| Event-heavy: distance | 501.62 km | 720.25 km | 218.62 km more; 95% CI 200.72 to 236.53 more |
| Combined stress: spilled mass | 79,580.47 kg | 8,644.97 kg | 89.14% less |
| Combined stress: unserved required bins | 100.30 | 0.23 | 99.77% fewer |
| Combined stress: distance | 470.08 km | 1,626.83 km | 1,156.75 km more |
| Combined stress: fuel | 449.86 L | 1,330.16 L | 880.30 L more |
| Sensor failure: overflow incidents | 3.57 | 9.20 | 5.63 more; 95% CI 4.06 to 7.21 more |
| Sensor failure: spilled mass | 172.60 kg | 495.25 kg | 322.65 kg more; 95% CI 191.39 to 453.91 more |
| Sensor failure: distance | 506.68 km | 1,152.40 km | 645.72 km more; 95% CI 619.18 to 672.26 more |

`paired_effects.csv` contains all metrics, units, paired confidence intervals, sign-flip tests and normality diagnostics for all scenarios. The table above is a decision-focused subset rather than a post-hoc score.

## Forecast evaluation

The model trains on a 730-day synthetic pre-period. Training, probability-calibration and holdout windows are chronological. Every feature/label window is purged through the longest 168-hour target, and the latest historical target ends six hours before operations begin.

| Horizon | Model growth MAE | Naive growth MAE |
| ---: | ---: | ---: |
| 6 hours | 1.59 percentage points | 4.57 percentage points |
| 24 hours | 4.47 percentage points | 16.70 percentage points |
| 48 hours | 7.63 percentage points | 33.29 percentage points |
| 168 hours | 16.98 percentage points | 116.18 percentage points |

Additional holdout diagnostics:

- 48-hour overflow alert: 0.927 precision, 0.990 recall, Brier score 0.0212.
- 6-hour overflow alert at the 10% action threshold: 0.979 precision, 0.998 recall, Brier score 0.00514.
- Time-to-overflow MAE: 52.84 hours. This is too coarse to treat as an exact service clock.
- 90th-percentile 48-hour growth interval coverage: 82.9%, below the nominal 90%; live use requires recalibration.

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

Regime-level and decision-driver outputs are retained separately so a whole-run average cannot hide quiet, normal or surge behavior. For example, the normal scenario averaged 18.13 forecast-driven dynamic dispatches, 11.53 daily dispatch-limit blocks and 79.97 sensor-uncertainty decisions per replication.

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
