# PR #2 telemetry forecasting adapter

Status: implemented for file/replay and read-only API use; physical validation remains blocked by the PR #2 producer gates.

## Purpose and boundary

`binsight/pr2_forecasting.py` converts the historical readings exposed by PR #2 into one synchronized, complete predictive snapshot for PR #1. It forecasts fill and overflow risk; it does not optimize a route. The resulting frame is passed through the existing PR #1 validator and trip-value dispatch policy, which separately decides whether a collection is operationally worthwhile.

The adapter reads PR #2 fields `timestamp`, `bin_id`, `fill_pct`, `estimated_density`, `confidence_flag`, and `ingested_at`. Acquisition time is never replaced by ingestion time. The explicit maps in `config/pr2_forecasting.json` translate `bin_01`–`bin_03` for the incomplete physical pilot and `bin_01`–`bin_44` for the competition simulation into canonical `UGB-###` IDs.

PR #2 currently returns at most 2,000 readings per bin. At the branch's two-second firmware cadence this represents only about 1.1 hours, not enough to learn the requested seasonal history. API mode therefore appends responses to a routing-owned SQLite cache. The cache is idempotent, refuses contradictory duplicates, and never writes the producer database. Field claims still require PR #2 to expose durable, correctly identified history from the actual three-channel producer.

## Cleaning and state construction

For accepted readings of bin \(b\), let \(f_{b,i}\) be fill percentage at acquisition time \(t_{b,i}\). A reading is available only when both its acquisition and ingestion timestamps are at or before the decision cutoff; this prevents a late-arriving old observation from leaking into a historical decision. Values outside the documented domains, future/unavailable-at-cutoff readings, unknown IDs, and contradictory same-bin/same-time duplicates are excluded. Exact retries are deduplicated.

A decrease of at least 30 percentage points is a collection candidate. It is a confirmed reset only when a following reading arrives within 18 hours, stays within 10 points of the low reading, and remains at least 15 points below the pre-drop value. Confirmed resets start a new segment. A single increase of at least 25 points is excluded unless the next reading sustains it. Suspected resets and isolated jumps remain visible in quality flags rather than being silently repaired.

Within one segment, the non-negative interval rate is

\[
r_{b,i}=\frac{\max(0,f_{b,i}-f_{b,i-1})}{(t_{b,i}-t_{b,i-1})/\text{hour}}.
\]

An interval has weight 1.0 when both sensors are confident and 0.25 otherwise; a gap longer than 24 hours multiplies that weight by 0.5. A gap longer than 12 hours is also recorded explicitly. A reset is never converted into negative waste generation.

## Learned pattern

The fitted base rate \(\tilde r_b\) is the weighted median interval rate, floored at 0.10 percentage points per hour. The conservative rate is the weighted 85th percentile. Multiplicative factors are learned as the cell's weighted-median rate divided by \(\tilde r_b\), clipped to 0.4–2.5:

- hour of day: when a cell has at least four intervals;
- day of week: after at least 28 days of history;
- week of month: after at least 90 days;
- month of year, representing annual seasonality: after at least 365 days and eight intervals per month cell.

The model also emits recent robust 6-hour, 24-hour and 168-hour rates, time since the last confirmed collection, typical fill added between confirmed collections, and the usable history span. Monthly or annual factors are absent until their gates are satisfied.

Known events use type, start/end time, bin applicability, proximity, intensity, expected attendance, and data quality. An event's distance multiplier is \(e^{-d/2}\). Attendance contributes a capped log multiplier. Type-specific uplift is the event/non-event median-rate ratio clipped to 1–3 when at least three historical intervals of that event type exist; otherwise the documented prior uplift is 1.35. Only events with `known_at <= decision_at` are visible. Actual attendance or other outcome fields are never read. Site and area pools allow nearby comparable bins to contribute when a bin lacks its own history.

## Fallback hierarchy

The selected model is, in order:

1. the bin's own pattern after at least 20 usable intervals spanning 14 days;
2. a service-site pool after at least 20 intervals spanning seven days;
3. an area-type pool under the same gate;
4. the bin's conservative recent rate, or the configured minimum when no usable rate exists.

Pooled and recent-rate fallbacks add quality flags and cannot set overall `confidence_flag=true`.

## Distribution forecast

Forecasts advance in six-hour steps to 168 hours. For step \(k\), the seasonal factor \(s_{b,k}\) is the product of available calendar factors and the event multiplier is \(e_{b,k}\). The expected rate blends the fitted pattern with the latest seven-day robust rate:

\[
\hat r_{b,k}=\alpha_b(\tilde r_b s_{b,k}e_{b,k})+(1-\alpha_b)r^{recent}_b,
\]

where \(\alpha_b=0.65\) for own history, 0.60 for a pool, and 0 for the recent-rate fallback. The expected fill is

\[
\mu_{b,h}=f_{b,0}+\sum_{k\le h/6}6\hat r_{b,k}.
\]

Each new valid reading immediately changes current fill, recent rates, and a recency-weighted seven-day residual MAE. Seasonal parameters retrain separately on the controlled policy below. Step variance accumulates the larger of minimum process error, online residual error, and half the conservative-versus-expected rate gap. Low-confidence or stale evidence adds variance. The published conservative band is

\[
[L_{b,h},U_{b,h}]=[\mu_{b,h}-z\sigma_{b,h},\mu_{b,h}+z\sigma_{b,h}],\quad z=1.28155,
\]

clipped to the physical 0–100% output domain. Under the normal approximation, the overflow probability is

\[
P(F_{b,h}\ge100)=1-\Phi\left(\frac{100-\mu_{b,h}}{\sigma_{b,h}}\right).
\]

`time_to_overflow_hours` is the first conservative upper-bound crossing of 100%, linearly interpolated between adjacent six-hour steps. If no crossing occurs in seven days, the conservative terminal slope extrapolates the time instead of returning a reassuring sentinel.

## Adaptation and drift

Every invocation recomputes the current trajectory, recent rates, and online residual error from readings at or before the decision cutoff. A saved model whose training timestamp or training-data cutoff is later than the simulated decision time is rejected and rebuilt from evidence available at that decision; this prevents a historical replay from borrowing a model created in its future. The fitted pattern retrains when either:

- at least 168 hours have elapsed and at least 48 new usable readings exist; or
- the seven-day median rate differs from the preceding 21-day reference by at least a factor of two and at least 12 new readings exist.

After collection, current fill begins from the confirmed post-service reading while the learned pattern remains. Each output records model family/version, training cutoff, actual data cutoff, and drift state. Model versions are hashes of deterministic cleaned training material.

## Risk and confidence

The configurable initial policy is:

- `critical`: confirmed current fill is at least 90%, probability of overflow within six hours is at least 0.50, or conservative time to overflow is at most six hours;
- `high`: 48-hour overflow probability is at least 0.50 or conservative crossing is within 48 hours;
- `medium`: seven-day probability is at least 0.30, crossing is within seven days, or overall confidence is false;
- `low`: none of the above.

Overall confidence requires a confident sensor, reading age at most 12 hours, the bin's own sufficient history, 48-hour interval width at most 35 points, six-hour residual MAE at most 12 points, event-data quality at least 0.7, no active drift, and no unconfirmed jump/reset. Readings older than 60 hours are marked offline. Missing bins are emitted as unavailable, medium risk, low confidence, and null fill—never as zero.

`estimated_density` is retained only as `estimated_density_context`. It is not a feature, never becomes `weight_kg`, and the output states `estimated_density_used=false`. `weight_kg` remains null until a documented physical calibration exists; PR #1 then applies its labelled conservative capacity fallback.

## Evaluation evidence

`scripts/evaluate_pr2_forecasting_adapter.py` runs chronological rolling origins against a deterministic acceptance fixture containing normal, event, sparse-history, sensor-failure, and distribution-drift regimes. It censors fill scoring after a collection because observed post-collection fill is not the counterfactual no-service trajectory. The full artifact is `artifacts/pr2_forecast_adapter_evaluation.json`; it is synthetic acceptance evidence, not field validation.

| Horizon | Adapter MAE | Current-fill MAE | Last-rate MAE | Central-band coverage |
| --- | ---: | ---: | ---: | ---: |
| 6 h | 0.935 pp | 1.521 pp | 0.891 pp | 95.4% |
| 24 h | 1.352 pp | 4.946 pp | 2.326 pp | 87.9% |
| 48 h | 2.140 pp | 9.500 pp | 4.242 pp | 81.4% |
| 168 h | 3.509 pp | 26.174 pp | 9.004 pp | 66.3% |

At 48 hours the fixture produces 0.933 precision, 0.737 recall, 0.0308 Brier score, 6.7% false-trigger rate, and 26.3% missed-overflow rate. Time-to-overflow MAE is 10.98 hours. Calibration bins and all required regime slices are stored in the artifact.

This forecast evaluation does not replace the fixed-versus-dynamic route experiment. The adapter feeds the already tested PR #1 dispatch policy but does not change its objective or claim that better fill MAE automatically lowers route distance. The current route evidence in `DYNAMIC_V2_RESULTS.md` still says dynamic v2 is a safety policy, not yet a cost-saving replacement for the fixed schedule; a new paired route comparison needs retained PR #2/shadow data.

The self-evaluation exposes the main weaknesses rather than hiding them: the literal last-interval rate is marginally better at six hours (0.891 versus 0.935 points), interval coverage degrades to 66.3% at seven days, drift examples are substantially harder than normal/event cases, and 48-hour recall misses about one quarter of observed overflow events. The next justified improvements are calibration on real retained PR #2 history, a more responsive drift-specific variance/update rule, and evaluation of a censored survival/TTO model. Those changes should not be tuned against this acceptance fixture and claimed as general performance.

### Acceptance trace

| Required check | Executable evidence |
| --- | --- |
| Collection reset and non-negative generation | `test_collection_reset_is_confirmed_and_never_becomes_negative_generation` |
| Rate/growth windows and interpolated crossing | `test_output_is_deterministic_and_threshold_crossing_is_interpolated` |
| Event uplift and no future outcome feature | `test_known_event_increases_distribution_without_using_future_event_outcome` |
| Missing, stale, low-confidence evidence and explicit ID map | `test_missing_stale_low_confidence_and_id_mapping_are_explicit` |
| Isolated ultrasonic jump cannot create a critical alert | `test_single_unconfirmed_ultrasonic_jump_cannot_create_critical_alert` |
| No future sensor data and no density-to-weight conversion | `test_future_reading_is_excluded_density_never_becomes_weight_and_forecast_updates` |
| Online residual update and controlled retraining | `test_online_residual_updates_each_reading_and_scheduled_retrain_is_controlled` |
| Collection resets trajectory but retains learned pattern | `test_confirmed_collection_resets_trajectory_but_keeps_learned_pattern` |
| Determinism for fixed history/model/event inputs | `test_output_is_deterministic_and_threshold_crossing_is_interpolated` |
| Complete routable 44-bin snapshot and PR #1 validation | `test_realistic_pr2_history_produces_valid_routable_44_bin_snapshot` |
| Strict JSON command output | `test_forecast_cli_writes_strict_json_snapshot` |
| Chronological baselines, leakage guard and required metrics | `test_rolling_origin_evaluation_is_chronological_and_compares_all_baselines` |
| Read-only PR #2 API shape and cross-bin refusal | `test_client_reads_pr2_history_and_rejects_cross_bin_payloads` |
| Append-only cache idempotency and conflict refusal | `test_routing_owned_history_cache_is_idempotent_and_never_overwrites_conflicts` |

The complete admin/routing suite passes 111 tests. The only emitted warnings are three SWIG deprecation warnings from imported OR-Tools dependencies.

## Commands

From `admin-portal`:

```powershell
.\.venv\Scripts\python.exe -m binsight.cli forecast-pr2 `
  --history .\path\to\pr2-history.json `
  --profile competition-simulation `
  --decision-at 2026-08-28T12:00:00+00:00 `
  --output .\data\pr2-predictive-snapshot.json

$env:BINSIGHT_PR2_API_KEY = "..."
.\.venv\Scripts\python.exe -m binsight.cli forecast-pr2 `
  --api-base https://producer.example `
  --profile physical-pilot `
  --decision-at 2026-08-28T12:00:00+00:00 `
  --output .\data\pr2-predictive-snapshot.json

.\.venv\Scripts\python.exe -m scripts.evaluate_pr2_forecasting_adapter
```

API mode defaults to routing-owned state and cache files under `data/`. Secrets are read from `BINSIGHT_PR2_API_KEY`, never from command output or committed configuration.

## Known limitations and live gate

- The current PR #2 branch is a one-bin/two-second prototype even though the latest owner comment defines three routable fill channels. Its API history cap cannot independently provide weekly, monthly, or annual learning windows.
- The probability shape is an interpretable normal approximation. Its central band is not considered calibrated until it is tested on retained hardware history.
- Confirming a collection reset requires one later reading, deliberately trading up to one sampling interval of caution for resistance to an ultrasonic drop-out.
- Event uplift uses the documented prior until enough comparable event intervals exist.
- No weight calibration exists, so payload capacity remains conservative and labelled.
- Live integration and physical performance claims remain disabled until PR #2 passes identity, replay, clock, outage, quality, and three-channel producer acceptance.
