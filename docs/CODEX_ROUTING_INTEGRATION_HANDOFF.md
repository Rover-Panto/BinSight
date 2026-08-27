# BinSight: Codex Routing Update and Integration Preparation

Prepared: 27 August 2026

Use this file as the implementation brief for Codex working on the routing system. Pair it with [the Claude hardware handoff](CLAUDE_HARDWARE_ROUTING_HANDOFF.md). This document requests future implementation; it does not claim that the integration or tests below already pass.

## 1. Instructions to Codex

Act as the senior engineer responsible for BinSight's central-server routing system. Inspect the current routing PR, propose a short plan, then implement the routing-side changes and integration preparation described below. Preserve the existing route engine, citizen application, simulation evidence and contributor work.

Use fixture-backed development while the hardware contributor repairs the sensing and ingestion path. Do not wait for a Wi-Fi module to implement schemas, mapping, quality handling, policy tests, the API client interface or replay-based route previews. Keep live integration disabled until the producer and consumer pass the shared contract checks.

### Repository and revisions

- Repository: [Rover-Panto/BinSight](https://github.com/Rover-Panto/BinSight).
- Routing: [PR #1, Feature/admin operations portal](https://github.com/Rover-Panto/BinSight/pull/1), branch `feature/admin-operations-portal`.
- Inspected routing head: `2e9f84ba2c2b13f93910728cdddda1589eb015ad`.
- Hardware: [PR #2, Add hardware pipeline (firmware/backend/dashboard) as a separate track](https://github.com/Rover-Panto/BinSight/pull/2), branch `feature/hardware-pipeline`.
- Reviewed hardware head: `e7055764b57663a9d916602d7b0e89f54df2eaa4`.
- Main at preparation: `9fca9d47afb805f40034da970bb47d791ba8f0b4`.
- Both implementation PRs were open and unmerged at preparation. Main and the documentation branch do not yet contain `admin-portal/` or `hardware_pipeline/`.

Fetch and inspect the latest PR revisions before editing. Record the actual starting commits. Work from the current routing implementation on a focused contributor branch or worktree; do not implement against this documentation-only branch or copy old PR files into main. If using a branch dependent on unmerged PR #1, document that dependency. Follow `CONTRIBUTING.md` and do not merge either PR into main to gain access to its code.

Check the working tree before editing. Keep unrelated edits, stored data and generated evidence intact. Ask for repository access or branch files if the environment cannot read them. Do not claim tests or edits that the environment did not perform.

## 2. Target Architecture and Ownership

The owner wants normal bins to measure waste fill and send readings over Wi-Fi to a central server. The central server makes collection decisions and calculates truck routes.

Read [the dated local hardware budget and sourcing baseline](HARDWARE_BUDGET_LOCAL_SOURCING.md). The physical prototype uses one Teensy to service three distinct general-waste bin channels and one ESP32-C3 communications module. Routing must preserve three bin identities even though the measurements share a controller and network link. The separate ESP32-S3 recycling camera is not a fill-level producer for the normal-bin route path.

```text
Bin sensors -> Teensy 4.1 -> Wi-Fi communications module
  -> Wi-Fi network -> Central telemetry ingestion and storage
  -> Routing adapter and observation-quality checks
  -> Historical features and prediction or named fallback policy
  -> Existing collection rules and route engine
  -> Operator route preview, approval and mock truck dispatch
```

Keep sensing and RTOS scheduling on the Teensy. Keep inference and routing on the server. A laptop can serve as the prototype server; no paid hosting, public deployment or real truck connection belongs in this task. The ESP32 beverage-return station remains a separate component.

### Paired handoff responsibilities

| Owner | Scope |
| --- | --- |
| Claude / hardware contributor | `hardware_pipeline/firmware/`, USB/Wi-Fi delivery, ingestion API/storage, event acknowledgements, producer-side migrations and hardware setup. |
| Codex / routing contributor | `admin-portal/binsight/`, route adapter/client, feature preparation, collection policy, planning lifecycle, routing persistence, operator UI and KPI provenance. |
| Both contributors | One versioned interface specification, bin registry meanings, quality/time semantics, fixtures and an end-to-end acceptance run. Agree a single editor for each shared file. |

The earlier Claude handoff includes routing interface requirements for context. With these two briefs in use, Codex owns the routing implementation. Do not have both agents create different adapters or competing schema definitions. Send producer-side API changes to the hardware contributor; do not alter the ingestion database directly from routing code.

## 3. Read Before Editing

Read the repository's `CONTRIBUTING.md`, `docs/PROJECT_STATE.md`, `docs/ADMIN_INTEGRATION.md`, `docs/DATA_PRESERVATION.md`, and the paired Claude handoff.

Read the current routing sources and tests:

- `admin-portal/binsight/dispatch.py`: validation, selection, conservative load calculations, history and mock dispatch.
- `admin-portal/binsight/forecast.py`: current model inputs, historical feature assumptions and synthetic training.
- `admin-portal/binsight/config.py`, `district.py`, `network.py`, `routing.py`: pilot constraints, registry, road matrix and solver boundaries.
- `admin-portal/binsight/observations.py`, `simulation.py`, `fuel.py`, `analysis.py`, `pipeline.py`: observation isolation, chronology, paired evaluation and KPI definitions.
- `admin-portal/app.py`, `binsight/cli.py`, the operator guide and current launchers: UI and process lifecycle.
- Existing tests, especially `test_dispatch.py`, `test_simulation_chronology.py`, `test_observations.py`, `test_routing.py`, `test_analysis.py`, and `test_pipeline.py`.
- `admin-portal/hardware/SENSOR_CONTRACT.md`, `gateway/`, `README.md`, `METHODS.md`, and current artifacts/provenance.

The routing code already includes tests for stale snapshots, missing sensors, conservative history, critical low-confidence bins, capacity constraints and simulation chronology. Preserve these behaviors. Earlier review findings may have changed; verify the latest code before calling an old finding unresolved. This handoff is an integration brief, not a claim that someone re-reviewed all of PR #1.

### Current interface gaps

| Current behavior | Integration consequence |
| --- | --- |
| `validate_snapshot()` requires seven predictive columns and keeps only those columns. | Extra event IDs or quality fields in JSON disappear unless the schema and consumers change together. |
| All rows share one timestamp; the validator derives one age for the entire snapshot. | Live bins have different observation times. A fresh decision time cannot refresh old observations. |
| Time-to-overflow must be finite; risk must be low/medium/high/critical. | Cold-start or unavailable predictions need an explicit supported state. |
| `update_last_valid_readings()` requires both valid fill and weight. | The current ultrasonic-only hardware never qualifies for retained fill history if weight stays null. |
| Configuration requires three bins per controller and a capacity-sized competition district. | The reviewed hardware PR models one bin per firmware instance, while the owner's budgeted target is one Teensy with three distinct sensing channels. Support the target pilot topology without weakening the full-district simulation checks. |
| The model uses weight, recent growth and site characteristics. | A current fill reading alone cannot satisfy the existing feature contract. |
| The UI calculates a route after an operator action and stores session state. | Automatic server routing must not depend on a browser tab or rerun. |
| Last-valid history uses a JSON file; dispatches use JSONL. | Adding a worker introduces concurrent-write and crash-recovery requirements. |

## 4. Implementation Requirements

### A. Agree a versioned interface first

Create a shared contract document, for example `docs/TELEMETRY_ROUTING_CONTRACT.md`, and schema/fixture files where both contributors can test them. Coordinate the exact wire fields and endpoint with the hardware contributor. Do not invent a deployed endpoint or silently change the existing `/api/v1/telemetry` contract.

Separate three representations:

1. The immutable observation as received from the telemetry producer.
2. The normalized routing observation, including mapping, age and quality.
3. The immutable decision snapshot, containing the inputs and assumptions used for one plan.

Require these meanings; choose names consistent with the code after agreement:

| Field or group | Meaning |
| --- | --- |
| `schema_version` | An explicit version with supported legacy handling and rejection of unknown future versions. |
| Event identity | Device ID, boot/session ID and sequence, or an equivalent unique producer event ID. Preserve it through retries and routing audit. |
| Hardware/canonical bin IDs | Keep the original ID and the registry mapping; use stable IDs, not array positions. |
| `observed_at` | Time of acquisition in UTC, nullable only with an explicit unsynchronized-clock state. |
| `received_at` | Server receipt time; never a substitute for a missing acquisition time. |
| `decision_at` and snapshot ID | Time and identity of the routing decision, separate from each source observation. |
| Fill and weight | Valid values with units or null; include per-channel availability and provenance. |
| Quality | Sensor confidence, stale/offline state, clock validity, filter/calibration issues and relevant event-gap indicators. |
| Source mode | Hardware, replay or synthetic; keep inferred/estimated fields distinguishable from measurements. |
| Forecast | Status, nullable time-to-overflow, method, model version and history/feature window. |
| Decision provenance | Source event IDs, registry/config/model versions, road-network version, vehicle assumptions and policy reasons. |

Support existing CSV/JSON imports through an explicit legacy adapter. For an old shared-timestamp snapshot, preserve that timestamp as the observation time of its rows. Do not invent missing event IDs as proof of producer delivery, manufacture new observations, or claim legacy data has richer quality evidence than it does.

### B. Build a registry and separate operating modes

Map `bin_01` and other hardware IDs to canonical bins, locations, service points, capacity assumptions and calibration metadata. The earlier citizen documentation uses `BIN-###`, while the route district uses `UGB-...`. Agree the mapping; do not infer physical equivalence from similar numbers.

Separate the three-bin physical prototype profile from the existing 33-bin synthetic district. Preserve the competition simulation configuration and its evidence. Do not relax its sizing checks globally just to run a one-bin transport test. A one-bin fixture can test the adapter; a configured three-bin pilot can test routing with a matching depot and road matrix.

Inspect `PilotConfig`, `validate_config()`, `required_controller_sites()`, district generation and UI labels before changing controller count. Distinguish physical controller topology from co-located service grouping; changing one must not silently change the other or alter collection capacities.

Reject unknown, duplicate or conflicting mappings. Keep a row for a known pilot bin with no reading as unknown; do not drop it from coverage. Validate coordinates, ordered IDs and matrix dimensions together. Keep hardware, replay and synthetic data distinguishable in snapshots and exports.

### C. Add a testable telemetry client and adapter

Keep the implementation in the routing package, for example `telemetry_client.py` and `telemetry_adapter.py`. Reuse existing local patterns rather than adding a separate service framework. Have the client read the telemetry API; keep it out of the citizen browser and do not let it write the ingestion database.

Provide fixture, recorded-replay and live-API input paths through the same normalization code. Use bounded request timeouts, configurable polling and visible authentication/network errors. Preserve TLS verification and keep credentials in local configuration. Do not put device secrets in a URL, browser bundle, screenshot, fixture or log.

Process observations by event identity and acquisition order. A late replay must not replace a newer accepted observation or roll back a displayed bin state. Do not use receipt time to make a replay look recent. Preserve history needed for forecast windows and keep an explicit ingestion/processing cursor where the agreed API supports one.

Build each decision from a captured set of source events. If polling multiple bins/endpoints, record a cutoff or version and source IDs so the snapshot can be reproduced. A partially failed poll must not produce an apparently complete healthy district.

Distinguish network failure, empty history, rejected data and stale retained data. Continue to show retained observations with their original age; preserve inspection state and source failure. Do not replace failed reads with the existing demo template's zero fill and low risk.

### D. Preserve per-bin time, uncertainty and last-good history

Compute each observation's age against an injected decision clock. Reject unsupported future dates and mark ambiguous legacy timestamps or unsynchronized clocks. Keep UTC for storage; document the timezone used for hour/day-of-week model features.

Set freshness thresholds from the live reporting cadence and operational policy. The simulation's six-hour sampling assumptions and twelve-hour stale setting are not automatic defaults for live hardware. Retained readings must age even while the dashboard refreshes.

Extend last-good history per channel. Retain a valid ultrasonic fill observation when weight is unavailable, with its own time, event ID and calibration version. Do not fabricate weight to pass `update_last_valid_readings()`. Keep conservative fallback assumptions separate from measurements. Validate history migrations on populated copies.

Keep fill-sensor confidence separate from weight availability. Agreement between two ultrasonic sensors does not certify a mass estimate. Apply the intended single-sensor/missing-channel uncertainty rules even when the fill confidence flag is true. Preserve disagreement detection when actual weight later becomes available.

Carry uncertainty into required-stop selection, optional and co-located pickups, ordering, capacity estimates, map badges and exports. Test stale readings that still carry a true producer confidence flag. Repeated old data must not regain trust through replay, averaging or aggregation.

### E. Support a named non-ML fallback and prepare prediction

The hardware currently supplies no overflow forecast. Add a supported forecast-unavailable state across schema validation, selection, sorting, UI, persistence and export. Do not use zero, infinity, NaN on the wire, or a large sentinel number to bypass validation. Keep finite measured values finite and invalid values rejected.

Use a documented fill-threshold fallback until suitable history and a validated model exist. A fresh high-fill bin can require collection without a forecast. A missing forecast must not turn uncertain evidence into a low-risk claim. Low-confidence or stale evidence may require inspection alongside collection; do not automatically discard a credible critical warning. Define reasons and stable tie-breaking for unknown forecasts.

Reuse the current forecasting code where appropriate, but inspect its assumptions. `make_feature_row()` treats observation positions as historical intervals; it cannot consume a burst of two-second readings as six-hour samples. Build time-windowed features using acquisition timestamps, account for gaps and collection resets, and choose a documented missing-feature policy. Do not infer household/site characteristics from a bin ID.

The existing model predicts growth over a horizon, not a measured future empty/full time. Document any conversion into time-to-overflow, uncertainty and zero-growth behavior. Keep cold-start, missing-model and model-error fallbacks explicit. A model trained on synthetic mass-derived fill is not automatically validated for irregular ultrasonic volume readings or null weight.

Evaluate forecast changes with chronological holdouts and prevent training target windows from overlapping the holdout period. Keep latent simulator state and future values out of decision features. Compare against a simple baseline, record versioned metrics and avoid tuning against the reported holdout. Mark hardware validation pending until suitable prototype logs exist.

### F. Reuse the route engine and protect the planning lifecycle

Retain `build_dispatch_plan()`, the existing OR-Tools route implementation, cached road-network handling and capacity constraints. Refactor only what the new contract needs. Keep collection required, inspection required and no collection required distinct; a bin can need collection and still require an operator warning.

Preserve truck/load limits, unserved-required-bin warnings, co-located stop behavior, daily trip accounting and dispatch blocking where a required pickup cannot fit. Do not claim a feasible load when the assumptions cannot support it. Label conservative load estimates and keep them distinct from measured `weight_kg`.

First add a load-latest/preview workflow. Then provide a controlled server-side planning runner that works without an open Streamlit tab. Extend the existing CLI/launcher structure where practical; avoid a broad infrastructure rewrite.

Make the runner opt-in for local use, with start/stop/status controls, a configurable evaluation interval, bounded retries and one writer/worker instance. Do not create operating-system startup tasks or scheduled automations. Document shutdown and do not leave test servers running after verification.

Use input identities and policy/config versions to avoid duplicate plans. Account for time: unchanged readings still become stale or cross a forecast horizon, so an unchanged event hash cannot suppress evaluation forever. Make stale/risk transitions deterministic under a test clock.

Separate draft proposals, accepted active routes, completed routes and cancelled proposals. Version changes and record the operator action. A new reading must not overwrite an accepted route or create duplicate mock dispatches. Restart/retry must not dispatch the same accepted plan twice. Maintain mock-only truck communication and keep route updates subject to operator approval.

### G. Make route records durable and auditable

Store the decision snapshot and source event references with each plan. Include chosen and excluded bins, reasons, inspection warnings, conservative loads, solver status, configuration/network/model versions and timestamps. Preserve an accepted plan even when a later snapshot changes.

Review the JSON history and JSONL dispatch writers before introducing a worker and UI writer. Use a single serialized writer, atomic file replacement where suitable, or a focused transactional routing store. Add recovery and migration tests; do not create a second uncoordinated writer for the same records.

Keep routing persistence separate from telemetry and citizen storage. Do not reset corrupt/unknown-version history to a clean default and overwrite the original. Report the problem, preserve the file and use the documented recovery path. Do not rewrite old decision evidence when a model or registry changes.

### H. Update operator views and KPI evidence

Extend the current Streamlit operations portal. Do not turn this into a React `/admin` rewrite or alter citizen navigation. Show observation age, source mode, unavailable weight/forecast, data-quality warnings, fallback/model method, route version and planning/approval state. Label draft updates separately from the active plan.

Keep existing manual CSV/JSON and synthetic-demo workflows, with their provenance. Disable or qualify live controls when the producer contract, identity, timestamp or quality gates have not passed. An API connection alone is not proof that the upstream measurements are reliable.

Preserve fair baseline/priority comparisons: the same district, depot, initial state, demand scenarios, vehicle assumptions and analysis window. Keep waste accumulating until simulated collection completes, include travel/unloading/turnaround, and apply shared daily trip limits. Use existing chronology tests as regression guards.

Use matched underlying waste arrivals and sensor-error scenarios across policies, not identical post-collection fill histories; each policy changes later fill levels. Preserve causal separation between simulator truth, sensor observations and controller decisions. Retain confidence intervals, seeds, metric definitions, completeness and modelled-versus-measured labels.

Do not infer recycling contamination or sensing energy from fill alone. Leave those KPIs unavailable without the relevant return-station or power evidence. Keep modelled fuel/CO2 separate from measured outcomes. Do not replace locked experiment artifacts during adapter work; write versioned new runs when a changed model or policy requires reevaluation.

## 5. Hardware Review Dependencies

The [Claude handoff](CLAUDE_HARDWARE_ROUTING_HANDOFF.md#4-review-findings-to-resolve) holds the ten findings and producer-side fixes. Use these as integration gates, not instructions to duplicate hardware changes in the routing branch.

| Review ID | Hardware/API concern | Routing-side preparation |
| --- | --- | --- |
| R1 | Incorrect ECHO wiring diagram | Keep physical validation pending; do not declare end-to-end hardware success from replay tests. |
| R2 | Teensy FreeRTOS build mismatch | Accept simulated/replay input for development; require a verified producer build before live acceptance. |
| R3 | Filter freezes after large fill changes | Test emptying and large-deposit traces; require producer quality/recovery evidence. |
| R4 | Invalid sensor readings become zero | Preserve unknown/missing states and do not let a nominally valid zero hide a known producer defect. |
| R5 | Backend ignores file-based API key | Test authentication failures and configuration; do not bypass authentication to make integration connect. |
| R6 | Serial diagnostics corrupt frames | Reject malformed data and show gaps/producer errors where exposed; do not silently mark a complete stream. |
| R7 | Temporary upload failures lose events | Support replay, stable event references and outage visibility; require producer retention/acknowledgement evidence. |
| R8 | Timestamp offsets disappear or collide | Enforce agreed UTC semantics and preserve ambiguity; never guess an offset to make old data pass. |
| R9 | Calibration button does not change baseline | Track calibration/version assumptions and prevent incompatible history from becoming a trusted trend. |
| R10 | Stale/unreliable bins appear healthy | Make route eligibility and operator status depend on age and quality, not only last fill. |

Also agree event identity across reboots, intentional sampling/upload cadence, drop counters and clock validity. The router cannot reliably detect every plausible-but-wrong measurement, so consumer checks do not replace firmware fixes.

## 6. Deliverable Order

1. **Contract and fixtures:** agree schema ownership, supported versions, IDs, time/quality meanings, unknown forecasts and example valid/invalid events. Record producer API needs and current missing fields.
2. **Routing preparation:** add operating profiles, registry, typed client boundary, fixture/replay adapter, per-channel history and policy tests. Keep live integration off. No hardware is required for this step.
3. **Route workflow:** add source selection, preview, immutable plan records, approval state and a controlled server runner. Preserve existing manual/demo workflows.
4. **Producer handshake:** run the same fixtures against the repaired ingestion API and routing consumer. Confirm persistence acknowledgements, identity, replay, timestamps and failure responses before a live reading drives a plan.
5. **Pilot and evidence:** run a mapped three-bin pilot, record the distinction between replay and physical measurements, then validate the Wi-Fi path with the hardware contributor. Reevaluate simulations only where the policy/model changed.

Do not block the first three steps on missing Wi-Fi hardware. Do not call the last two complete while using mocks alone. Record interface disagreements for the hardware contributor rather than applying unilateral schema changes.

## 7. Acceptance Checks

Commit focused regression tests and replay fixtures. Use an injected clock and deterministic inputs; do not require a real bin or internet service for the default test suite.

| ID | Required result |
| --- | --- |
| C01 | Current routing tests run before changes; record existing failures and preserve the safety cases. |
| C02 | Supported legacy and new schemas validate; unknown future versions and malformed/non-finite values fail without resetting data. |
| C03 | Hardware IDs map to the correct pilot; unknown/duplicate mappings and mismatched matrix order/dimensions fail. |
| C04 | The physical pilot and competition simulation use separate profiles; one-bin adapter tests do not weaken simulation sizing or topology checks. |
| C05 | Equivalent timezone offsets normalize; per-bin ages differ when observations differ; decision time does not refresh source time. |
| C06 | Future/unsynchronized/ambiguous timestamps produce the documented error or unknown state without guessing. |
| C07 | A valid fill reading with null weight updates fill-only last-good history; recovery uses its original age and provenance. |
| C08 | Missing weight stays null; conservative loads and single-channel uncertainty remain labelled and obey capacity constraints. |
| C09 | Unknown forecast is supported through validation, ordering, policy, UI and export without fake numeric sentinels. |
| C10 | Fresh high fill can trigger collection under the named fallback; missing or stale evidence does not become proof of low risk. |
| C11 | Critical low-confidence evidence remains collection-relevant with review warnings; optional and sibling pickups obey quality rules. |
| C12 | Startup failure, sustained blockage, emptying and large deposits have explicit replay outcomes; invalid samples do not create confident zero fill. |
| C13 | Rapid or irregular samples use timestamp-based feature windows; gaps, collection resets and cold start follow the documented feature policy. |
| C14 | Forecast training/holdout target windows do not overlap; future/latent data cannot enter controller features. |
| C15 | Duplicate, same-second and rebooted-device events retain their identities; old replay never replaces a newer accepted observation. |
| C16 | API authentication failures, timeouts, HTTP 503 and partial fetches create visible degraded states without fabricated complete snapshots. |
| C17 | A captured input set reproduces the plan with pinned config/network/model assumptions and stable tie-breaking. |
| C18 | Planning runs without a dashboard tab; stopping the runner stops background work and restarting does not create a second worker. |
| C19 | Repeated inputs avoid duplicate plans, while elapsed time still triggers stale/risk reevaluation. |
| C20 | New proposals leave accepted routes unchanged; approval/retry/restart cannot duplicate a mock dispatch. |
| C21 | Required-stop capacity failures block dispatch as intended; collection and inspection outcomes remain distinct and auditable. |
| C22 | Routing history/plan migrations preserve IDs and records; concurrent writes/crash recovery cannot silently replace the history with defaults. |
| C23 | Existing CSV/JSON imports, synthetic demos and route/map/tracking views retain their documented behavior and source labels. |
| C24 | Baseline/priority comparison keeps matched demand and chronology; revised outputs preserve seeds, completeness, units and provenance. |
| C25 | Unsupported contamination/energy KPIs show unavailable; fuel/CO2 and synthetic results do not appear as measured savings. |
| C26 | Producer and consumer pass shared contract fixtures, including a lost acknowledgement after storage, replay and UTC round trips. |
| C27 | Saved events for the pilot pass through ingestion, normalization, decision, route preview and an auditable mock dispatch. |
| C28 | Citizen login, returns, reports, image attachments and payout state survive; no citizen storage key changes. |
| C29 | Updated operator screens have no clipping/overlap at 1440x900, 768x1024 and 390x844. |
| C30 | Physical end-to-end Wi-Fi verification is recorded separately from replay/software tests, including outage recovery and module details. |

Run the routing suite from `admin-portal/` using its documented environment, for example `python -m pytest tests`. Run `pnpm lint`, `pnpm test:run`, `pnpm test:e2e`, and `pnpm build` from `web/` as required by `CONTRIBUTING.md`. Do not invent a passing test count or replace hard cases with happy-path fixtures. State any blocker or test not run.

Do not launch an expensive full experiment or overwrite committed artifacts as a side effect of a page refresh or unit test. Keep expensive reevaluation explicit, version its output, and document changes in results before publication.

## 8. Documentation, Git and Completion Report

Update the shared contract, routing README, operator guide, relevant sensor/gateway documentation, `docs/PROJECT_STATE.md`, `docs/ADMIN_INTEGRATION.md`, and `docs/DATA_PRESERVATION.md` in the same implementation PR. Update `docs/FRONTEND.md` if the frontend architecture or workflow changes. Keep the current Streamlit implementation distinct from the planned React `/admin` area.

Document units, source modes, clock/freshness rules, missing-channel handling, fallback policy, model features, decision/approval lifecycle, configuration, runner start/stop, schema migration, backup/restore and test procedures. Coordinate edits to shared docs with the hardware contributor.

Preserve `binsight-demo-v1`, its versioned backups and report image attachments. Do not clear browser storage, replace citizen stores, copy identity/payment data into fixtures, or merge telemetry into citizen records. Do not regenerate IDs or delete existing databases to pass tests.

Commit verified changes in reviewable groups: contract/fixtures, normalization/history, policy/forecast handling, workflow/persistence, then documentation/evidence as appropriate. Keep code and its required documentation together when splitting commits. Push the contributor branch when authorized. Do not force-push, merge/close implementation PRs or alter another contributor's branch without instruction.

Return a completion report containing:

1. Starting and resulting commits, branch/PR links, and the exact producer/consumer contract versions.
2. Changed files grouped by purpose, with preserved behavior and any migration impact.
3. Completed checks C01-C30, failures, unrun checks and reproduction commands.
4. Current producer blockers R1-R10 and the interface changes the hardware contributor still needs to supply.
5. A sample route audit showing source events, missing/estimated fields, policy reasons and mock-only dispatch.
6. Setup, start/stop, rollback and recovery instructions another contributor can follow.
7. Remaining hardware validation, model validation and deployment work; distinguish integration-ready from physically verified.

The deliverable is a tested routing-side implementation that can consume the agreed telemetry contract, plus an explicit live-integration gate. Do not claim that mocks establish physical sensor accuracy, Wi-Fi reliability, actual truck dispatch or measured municipal savings.
