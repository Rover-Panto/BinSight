# PR1 and PR4 Integration Instructions

Owner instruction: 28 August 2026. **PR4 owns forecasting. PR1 owns collection decisions, routing and operational KPIs.** This document specifies work to implement; it does not claim that the branches are integrated or that PR4 is ready for deployment.

Use [the integration test branch plan](INTEGRATION_TEST_PLAN.md) for staging, owner decisions and evidence gates, and [PR4's demo acceptance conditions](PR4_REVIEW_2026-08-29.md#demo-acceptance) for the current scope. The owner clarified that this is a demonstration, not a production release. Head `28509cc` is accepted for controlled integration testing with a fixed bundle/environment. Prioritize bad-reading guards, timestamp normalization and a working route preview; defer general loader hardening and retraining automation. The original starting heads below remain historical context.

PR4 has now merged into main at `3297f43` and is present on `codex/integration-test`. PR1 remains open at `8b34c96`; its adapter is the next connection to implement. PR1 can incorporate main through its normal update process; do not merge the aggregate integration branch into the contributor branch.

Starting review heads: PR1 `c256bd44a60d12628b9f0354879e1ad90a15ec1e`; PR4 `313f76b2c8c0356f966018f591b1dec56b68a939`. Recheck the current heads and preserve newer contributor changes before editing. Resolve the [review findings](PR_REVIEW_2026-08-28.md) alongside this integration.

## 1. Connect Through a Local Python Interface

```text
PR2: Teensy/ESP telemetry -> ingestion and retained raw observations
                                    |
PR1: read-only client/cache -> validated, mapped observation snapshot
                                    |
PR4: feature preparation -> versioned forecast provider
                                    |
PR1: validate forecast -> collection policy -> route solver
                                    |
                       approval, audit, operator UI and KPIs
```

Use an importable Python package in `ml/` for the first integration. Both components run on the laptop server; no extra HTTP forecast service, database or browser request is needed. PR4 should add package metadata and relative imports, then expose one public prediction entry point. PR1 should declare the local dependency through a documented install step, not modify `sys.path` or import PR4 training scripts.

Load one trusted model bundle per worker and reuse it across planning calls. Training/retraining is a separate controlled PR4 job, not a side effect of dashboard refresh, route preview or module import. Store model artifact, manifest and evaluation together; verify model/feature versions and the artifact checksum before loading. Publish a new bundle atomically so a worker cannot mix files from different runs.

Proposed entry point for the contributors to implement and pin in contract tests:

```python
provider.predict_snapshot(
    history,
    bins=registry_metadata,
    decision_at=cutoff_utc,
    input_snapshot_id=snapshot_id,
    events=known_events,
)
```

PR4 now implements `predict_snapshot`; the exact PR1 adapter is still pending. Keep model-specific features inside PR4. PR1 supplies observations and known registry/event facts, not a second engineered feature table. For the demo, use this boundary to reject bad readings and normalize timestamps before calling the fixed provider.

## 2. Pin the Input Contract Together

| Input | Rule |
| --- | --- |
| Bin identity | Pass canonical `bin_id` plus the original hardware ID. Use PR1's explicit registry, not string guesses between `bin_01`, `bin_000` and `UGB-001`. |
| Observation identity | Retain source event/device/boot/sequence evidence when available and reference the captured input snapshot. Flag legacy identity limitations; do not invent proof of delivery. |
| Time | Keep acquisition and ingestion times separately, normalized to UTC. Both must be at or before `decision_at`. Never substitute receipt time for acquisition time. |
| Fill | Percentage with validity/quality state. Invalid or missing readings stay unavailable, not zero. |
| Weight | Calibrated kilograms when supplied, otherwise null. PR2's `estimated_density` is not weight. PR4 must support an evaluated fill-only path. |
| Sensor quality | Preserve confidence, staleness, clock status, collection/reset evidence and gaps. Sensor confidence is not model confidence. |
| Context | Use registry facts and only events known at the cutoff. Missing site attributes remain missing; no latent simulator state or future event outcomes. |

PR1 owns API access, event normalization, bin mapping, snapshot capture and any needed read-only cache. PR4 owns model-specific resampling, rate windows, reset treatment, missing-feature policy and feature validation. PR4 must validate its input independently without creating a second acquisition pipeline or writing the producer database.

Use the same normalized input shape for recorded telemetry and simulation observations. Sampling cadence can vary; require elapsed-time windows, not row offsets. The producer's current 2,000-row history limit is not a complete seasonal history; agree retained history/export or cursor support with PR2.

## 3. Agree Target Meanings Before Wiring Predictions

PR1 currently distinguishes 100% overflow from a 90% emergency-service trigger. PR4 currently labels time to 90%, and its synthetic bins reset at that threshold. Its present output cannot be renamed time-to-100% or converted by a fixed multiplier.

For the demo, preserve PR1's 100% overflow meaning and 90% service trigger, and use PR4 only for its supported 90% service-threshold estimate. Retraining for 100% overflow or calibrated probabilities is not required. Where PR1 needs unsupported capabilities, select its named non-ML fallback. A later model expansion needs matching labels and evaluation; do not rename the existing output as part of the adapter.

Each prediction must declare its target threshold, time origin and estimate meaning. A mean time-to-threshold is not a conservative upper-fill crossing. PR1 must not feed one into logic that assumes the other.

## 4. Return One Versioned Forecast Per Configured Bin

The contributors should share a schema/fixture with these meanings. Keep the forecast schema separate from PR1's existing telemetry/snapshot schema and translate it at the consumer boundary.

| Output group | Required meaning |
| --- | --- |
| Identity | Forecast schema version, prediction/batch ID, canonical bin ID and input snapshot reference. Include a result for a configured bin with insufficient evidence rather than dropping it. |
| Provenance | Model/feature version, training-data cutoff, input-data cutoff, decision time and source mode. Reject a model trained after the decision cutoff during historical replay. |
| Availability | `available`, `cold_start`, `unavailable` or `model_error`, with reason/quality flags. Missing numeric values are null, not NaN, infinity, zero or a large sentinel. |
| Threshold estimate | `time_to_overflow_hours` when justified, declared target percentage, and whether the estimate is expected or conservative. Declare the finite forecast horizon and no-crossing state explicitly. |
| Horizon predictions | Expected fill/growth and documented uncertainty bounds at the agreed 6/24/48/168-hour horizons. Distinguish fill percentage from growth in percentage points. |
| Probabilities | Calibrated overflow probability for the horizons used by routing, especially 6 and 48 hours, with their target definition. Unsupported probabilities stay null and force an explicit supported fallback. |
| Confidence/risk | Keep sensor quality and forecast confidence separate. Agree forecast risk meanings; PR1 owns operational urgency, required stops and inspection decisions. Do not just lowercase PR4's risk labels and assume their thresholds match. |

PR1's simulation currently calls `ForecastBundle.predict()` for mean/upper growth and separate 6/48-hour probability methods. PR4 returns a service-threshold estimate plus rate-based horizon projections, with probabilities explicitly unsupported. This is a capability gap, not just a naming mismatch. For the demo, use a tested, named non-ML mode where PR1 requires missing capabilities rather than expanding the model. A scalar mean prediction must not masquerade as a calibrated probability or conservative bound.

Keep horizon capability/availability checks in PR1. Do not feed an unsupported result through the old q90/probability assumptions. A finite-horizon no-crossing result does not prove the bin can never overflow.

## 5. Update Both PR1 Call Paths

| Current PR1 location | Required change |
| --- | --- |
| `binsight/pr2_forecasting.py` and `binsight/cli.py` (`forecast-pr2`) | Keep required read/validation/cache/snapshot functions; replace learned pattern fitting, feature construction and retraining with calls to the PR4 provider. The command may remain as a consumer command, not a separate trainer. |
| `binsight/simulation.py` | Replace `make_feature_row` and the old model calls with the same provider contract used for telemetry. Pass timestamped observations and known events only. Keep physical mass truth in the simulator, not in a fabricated model input. |
| `binsight/pipeline.py` | Remove automatic training/export of a competing PR1 model. Load an approved PR4 bundle and record its manifest in the experiment provenance. Keep simulation orchestration and route/KPI evaluation. |
| `binsight/dispatch.py`, `planner.py`, `planning_store.py` | Retain policy, solver, approval, audit and persistence. Add prediction-contract validation and missing-capability handling where needed. PR4 must not dispatch or modify accepted routes. |
| Admin UI and commands | Show model version, forecast/fallback state and observation age. Preserve existing workflows; do not add a duplicate ML dashboard as the operations interface. |

For unavailable/error/cold-start predictions, PR1 uses its named fill-threshold and sensor-health policy. Stale evidence requires inspection or an approved collection procedure, not a reassuring low-risk badge. Keep this fallback deterministic and independent of another ML model.

PR4 can reuse sound PR1 horizon models or calibration logic. Move ownership and tests once; do not leave two maintained copies. The owner chose the component boundary, not a promise that the current Random Forest must replace every existing forecast capability unchanged.

## 6. Verify, Then Remove the Superseded Code

1. Agree a versioned input/output fixture and one editor for shared contract changes. Document the PR dependency and installation commands; do not copy files from review snapshots into main.
2. PR4 fixes missing-weight/cold-start/gap handling, the model/manifest mismatch and evaluation leakage. Publish a reproducible, trusted model bundle with held-out evidence and a fill-only path.
3. PR1 integrates the provider for both telemetry and simulation in reviewable commits. Keep the previous model only for the transition comparison, not as a second long-term production path.
4. Run the checks below and the existing PR1 routing suite plus PR4 model/interface tests. Record new results; the earlier 97-test PR1 pass does not validate this future integration.
5. Remove the superseded active `forecast.py` training/model code and forecast-specific portions of `pr2_forecasting.py`. Update imports, commands, configuration and unused dependencies after inspecting their callers. Move useful forecast regressions to PR4, retain consumer/route regressions in PR1, and keep historical results and source data.
6. Review the integrated diff before merging. No live dispatch or claim of physical integration follows from a clean merge alone.

Required checks:

- A PR2-shaped fill-only fixture reaches PR4, returns a versioned result, and produces a PR1 route preview with unchanged bin identity and observation time.
- A synthetic three-bin snapshot preserves one general-waste and two recycling fill channels for regression coverage. D3's physical profile has one recycling technology-demonstration bin alongside general waste; do not invent an extra live bin to fill the fixture. Recognition events never enter forecasting/routing.
- First reading, irregular cadence, duplicate/replayed events, collection/reset, missing weight and partial coverage produce explicit supported states.
- Future observations, late ingestion and future-trained model state cannot affect an earlier decision. Model errors and malformed/non-finite outputs cannot become healthy low risk.
- Threshold, estimate meaning, horizon units and probability availability match between the provider and the consumer; mismatches reject or use the declared non-ML mode.
- Fixed and model-assisted policies see matched underlying arrivals and sensor-error scenarios. Their post-collection histories evolve independently, and neither sees future simulator truth. Record model version, seeds and modelled-versus-measured KPI labels.
- Approval/idempotency, stale service state, restart/replay, database migration and citizen-data preservation regressions still pass. A new forecast must not overwrite an accepted route or create duplicate dispatches.
- A clean install needs only the documented PR4 package/provider, not PR1's retired model implementation. Search remaining imports and training commands before deleting dependencies.

Do not delete telemetry/history databases, prior route records, historical simulation artifacts or citizen data during code cleanup. Retain benchmark provenance and source revisions so the team can reproduce earlier comparisons. Model ownership does not change the shared ESP, PR2 ingestion, PR3 vision or main-owned return-session/payout boundaries.
