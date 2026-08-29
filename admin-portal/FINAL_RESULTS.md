# BinSight historical v1 locked simulation results

> **Policy boundary:** these figures evaluate the retired safety-first threshold/5 km batching policy, not dynamic trip-value policy v2. They are retained to preserve the evidence trail and the failure that motivated v2. Current changed-policy output is versioned under `artifacts/dynamic_v2/` and summarized in `DYNAMIC_V2_RESULTS.md`; neither result is field evidence.

## Study lock

| Item | Value |
| --- | --- |
| Model | Minute-level 30-day terminating SimPy experiment |
| District | 500 households, 20 commercial units, 33 bins, 11 sites |
| Policies | Corrected fixed three-day baseline vs. safety-first smart candidate |
| Scenarios | Base, high demand, traffic, sensor failure, reduced truck capacity |
| Replications | 30 paired replications per scenario |
| Total policy runs | 300 |
| Arrival seed block | Base seed +1,310,000, then +101 per replication |
| Sensor seed block | Base seed +1,320,000, then +103 per replication |
| Common randomness | Same arrivals and observation errors within every policy pair |
| Final tuning boundary | Seed blocks through +1,020,000 were development/audit only |

The earlier 5.08% distance/fuel saving claim is withdrawn. It was dominated by a fixed-policy day-zero sweep of empty bins. The baseline now first collects after the full three-day interval. Raw and post-warm-up results are both retained; the primary normal-operation comparison uses the equal three-day post-warm-up values.

For lower-is-better metrics, beneficial effect = fixed − smart. For higher-is-better metrics, beneficial effect = smart − fixed. Positive is favorable. Intervals are paired 95% Student-t intervals; p-values use 19,999 paired sign flips.

## Forecast holdout

<!-- FINAL_FORECAST_START -->

The tree model used 4,752 training rows and 1,188 chronological holdout rows. Its 48-hour growth MAE was **2.484 percentage points**, versus **7.646** for the naive recent-growth benchmark: a **67.52% synthetic holdout improvement**. This validates the software against generated data only; it is not field accuracy.

<!-- FINAL_FORECAST_END -->

## Base scenario

### Post-warm-up normal-operation comparison

<!-- FINAL_BASE_POST_START -->

| Metric | Fixed mean | Smart mean | Smart result vs fixed | Beneficial effect 95% CI | Sign-flip p |
| --- | ---: | ---: | ---: | ---: | ---: |
| Overflow incidents | 0.000 | 0.067 | 0.067 more; % undefined | -0.161 to 0.028 | 0.498 |
| Spilled waste | 0.000 kg | 0.755 kg | 0.755 kg more | -1.909 to 0.399 kg | 0.500 |
| Road distance | 511.730 km | 633.448 km | **23.79% worse** | -138.773 to -104.664 km | <0.001 |
| Fuel | 413.323 L | 491.458 L | **18.90% worse** | -88.962 to -67.308 L | <0.001 |
| Tailpipe CO₂ | 1,107.706 kg | 1,317.108 kg | **18.90% worse** | -238.419 to -180.385 kg | <0.001 |
| Collection trips | 18.000 | 21.167 | **17.59% worse** | -3.964 to -2.370 | <0.001 |
| Collection stops | 297.000 | 309.600 | **4.24% worse** | -17.740 to -7.460 | <0.001 |
| Low-fill pickups | 0.567 | 72.033 | 71.467 more | -77.682 to -65.251 | <0.001 |
| Truck utilization | 63.376% | 54.292% | 9.084 points lower | -10.886 to -7.282 points | <0.001 |
| Unserved required bins | 0.000 | 0.033 | 0.033 more | -0.102 to 0.035 | 1.000 |
| Routing fallbacks | 0.000 | 0.000 | Equal | 0.000 to 0.000 | 1.000 |

The smart policy did not improve the normal-demand estimand. Its two total overflow incidents across 30 replications were rare and the paired interval includes zero, but fixed service had none. Distance, fuel, trips, stops, low-fill pickups, and utilization all favor the corrected fixed baseline.

<!-- FINAL_BASE_POST_END -->

### Raw 30-day comparison

<!-- FINAL_BASE_RAW_START -->

| Metric | Fixed mean | Smart mean | Smart result vs fixed |
| --- | ---: | ---: | ---: |
| Overflow incidents | 0.000 | 0.067 | 0.067 more |
| Road distance | 511.730 km | 664.482 km | 29.85% worse |
| Fuel | 413.323 L | 516.524 L | 24.97% worse |
| Collection trips | 18.000 | 22.300 | 23.89% worse |
| Collection stops | 297.000 | 327.367 | 10.22% worse |

The raw comparison includes smart activity during the artificial empty-start period while the corrected fixed schedule is not yet due. That is why the equal post-warm-up table above is primary. Both versions remain in the artifacts.

<!-- FINAL_BASE_RAW_END -->

## Stress scenarios

<!-- FINAL_STRESS_START -->

Primary post-warm-up means:

| Scenario | Overflow incidents fixed → smart | Spilled kg fixed → smart | Distance km fixed → smart | Fuel L fixed → smart |
| --- | ---: | ---: | ---: | ---: |
| High demand (×1.45) | 62.667 → 2.733 | 3,006.703 → 58.828 | 511.080 → 860.166 | 415.874 → 661.606 |
| Traffic (×1.35) | 0.000 → 0.133 | 0.000 → 1.402 | 511.760 → 632.777 | 505.581 → 610.646 |
| Sensor failure | 0.000 → 0.167 | 0.000 → 2.874 | 511.431 → 1,190.298 | 413.039 → 832.330 |
| Truck capacity (×0.65) | 7.133 → 0.100 | 2,099.685 → 1.498 | 552.411 → 731.525 | 438.026 → 550.231 |

Key paired effects:

- **High demand:** smart reduced overflow incidents by 95.64% (effect 59.933; 95% CI 57.945 to 61.921; p<0.001) and spill by 98.04%, but used 68.30% more distance and 59.09% more fuel.
- **Reduced capacity:** smart reduced overflow incidents by 98.60% (effect 7.033; 95% CI 6.474 to 7.592; p<0.001), spill by 99.93%, and unserved required bins from 9.900 to 0.633 (93.60% better), but used 32.42% more distance and 25.62% more fuel.
- **Traffic:** smart provided no safety advantage because fixed already had zero overflow; it used 23.65% more distance and 20.78% more fuel.
- **Sensor failure:** smart averaged 0.167 incidents versus zero for fixed (paired interval -0.339 to 0.006; p=0.124), while distance increased 132.74% and fuel 101.51%. It also generated far more inspection events. This scenario exposes the need for a real inspection-resolution workflow rather than repeated automated routing.

Raw 30-day totals lead to the same direction. For example, high-demand raw overflow was 64.267 fixed versus 2.767 smart, while raw distance was 511.080 versus 927.294 km. All raw values remain in `paired_effects.csv`.

<!-- FINAL_STRESS_END -->

## Interpretation

<!-- FINAL_INTERPRETATION_START -->

1. **Do not claim routine fuel savings.** The corrected normal-demand result conclusively favors fixed service for distance and fuel under the configured assumptions.

2. **The smart policy is an emergency-capacity strategy.** It is valuable when demand rises sharply or effective payload falls, where fixed service overflows. The price is more trips, road distance, fuel, and stops.

3. **Inspection and collection must remain distinct.** Severe data failure causes many inspection states. Automatically dispatching every uncertain bin would be safe-looking but operationally wasteful; ignoring uncertainty would be unsafe. A human/remote inspection process is missing from the simulation.

4. **Co-located/optional batching is retained.** Development trials that tightened sibling and optional pickups reduced low-fill stops but produced more separate trips and higher fuel. Shorter emergency horizons saved fuel but caused materially more overflow. The locked 48-hour gap, 20-hour emergency horizon, and 5 km incremental rule are therefore a safety-first compromise, not a cost optimum.

5. **Next optimization should be a hybrid controller.** Under calibrated field data, retain the efficient fixed schedule in normal conditions and activate forecast-driven emergency routing only when a validated demand/capacity regime warrants it. Pre-register thresholds on development data and evaluate the hybrid on a later untouched period.

<!-- FINAL_INTERPRETATION_END -->

## Model decision

The historical smart candidate was accepted only as **research evidence and an operator decision-support precursor**, not as an autonomous replacement for fixed collection. It is now superseded in software by dynamic trip-value v2. Adoption still requires a prospective field trial showing that overflow protection, inspection workflow, distance, fuel, calibration and false-pickup costs satisfy pre-registered operator thresholds.

The recommended field sequence is:

1. keep the fixed three-day schedule as the operational safeguard;
2. run BinSight in shadow mode using calibrated sensor/AI snapshots;
3. resolve inspection states through an operator workflow;
4. measure actual overflow, kilometres, litres, service/idle time, sensor outages, and false alerts; and
5. tune a hybrid rule only on a development period, then evaluate it on a later untouched period.

## Reproducibility files

- `artifacts/replication_metrics.csv` — one row per policy/replication/scenario.
- `artifacts/policy_summary.csv` — policy means and intervals.
- `artifacts/paired_effects.csv` — paired effects, intervals, sign-flip and Shapiro diagnostics.
- `artifacts/seed_manifest.json` — exact scenario and paired seeds.
- `artifacts/run_provenance.json` — packages, study type, scenario definitions, and scope.
- `artifacts/forecast_evaluation.json` — chronological holdout result.
- `artifacts/representative_route_events.json` — chronological route/service events.
- `artifacts/representative_routes.geojson` — representative display roads.

## Claim boundary

> Under the stated Subang Jaya demand, sensing, underground-bin, vehicle, traffic, and OSM-road assumptions, BinSight produced the reported paired simulation effects. These results are synthetic planning evidence and do not establish municipal fuel, emissions, or overflow performance.
