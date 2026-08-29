# BinSight Project State

Last verified: 29 August 2026 for PR4; other component reviews retain their 28 August baseline.

## Main branch

`main` contains the citizen-facing React prototype, PR4's forecasting package and engineering integration documentation. The owner merged PR4 at `3297f431e44e4b751aa158757659867cbc980654` on 29 August Malaysia time. Proposal and submission files are kept outside Git. The web app is a local demonstration. It has no production API, database, payment connection, camera scanner, or deployed bin network.

The citizen app currently supports:

- National ID entry with mock OTP verification
- Persistent demonstration login
- Return sessions at RM0.20 per accepted container
- Station-detected can or bottle results controlled through hidden demo settings
- Bank Transfer and E-Wallet payout simulations
- Waste issue reports with locally stored image attachments
- Broad waste-stream guidance, locations, FAQ, scripted chat, and contact details
- Automatic public-bin collection wording with no resident timetable
- Local server stop control and `Start-BinSight.cmd` restart launcher

The mock return value remains RM0.20. [The return-deposit assessment](RETURN_DEPOSIT_POLICY.md) recommends treating it as a simulated refundable container deposit that follows the marked container, not as a tax or unrestricted recycling reward. Citizen wording and the physical eligibility check still need that policy integration.

## Current routes

| Route | Purpose |
| --- | --- |
| `/` | Citizen task hub |
| `/return` and `/return/:id` | Beverage-return sessions |
| `/payout/:id` | Simulated payout selection and receipt |
| `/report` | New waste issue |
| `/reports` and `/reports/:id` | Citizen report tracking |
| `/guide` | Waste-stream guidance |
| `/locations` | Demonstration drop-off locations |
| `/bulky-pickup` | Simulated bulky-item request |
| `/faq`, `/chat`, `/contact` | Resident support |
| `/notifications`, `/history`, `/account` | Citizen records and settings |

There is no collection-schedule route. BinSight describes public-bin servicing as demand-led and automatically routed.

## Two Bin Types

BinSight has two and only two bin types. Keep this distinction in firmware, APIs, storage, routing, dashboards, proposal text and demonstrations.

| Bin type | Physical role | Processing boundary |
| --- | --- | --- |
| General waste | One model bin measures fill and, where fitted, weight | The shared Teensy 4.1 schedules sensing; the single ESP32-C3 relays telemetry for overflow prediction and routing. No camera or vision model is used for this bin. |
| Recycling return | One physical bin demonstrates fill sensing and the return flow | The same Teensy and ESP carry its identified fill channel. One OV5647/Grove Vision AI V2 performs local classification; the same ESP relays compact recognition results and controls feedback after the server decision. |

Recycling fill readings and recycling inference events are logically independent. Firmware must contain a classifier/peripheral fault so fill reporting can continue; a shared C3 reset or power loss interrupts both streams. Fill level must not influence item acceptance. The route adapter may consume fill observations from either bin type, but must reject every classification event. See [SHARED_ESP32_GATEWAY.md](SHARED_ESP32_GATEWAY.md).

## Admin and Decision-Support Work

The route-optimisation and KPI dashboard has substantial implementation on PR #1, but has not merged into `main`. Its latest update adds predictive telemetry snapshots, trip-value routing, stored route lifecycle and expanded synthetic evaluation. PR #4's forecast provider is now on main; PR1's adapter and retirement of duplicate prediction code are still pending. Follow [the cross-PR review](PR_REVIEW_2026-08-28.md), [ADMIN_INTEGRATION.md](ADMIN_INTEGRATION.md) and [DATA_PRESERVATION.md](DATA_PRESERVATION.md).

The initial integration keeps PR1's Streamlit website under `admin-portal/` and the citizen React site under `web/`. Do not rebuild the admin site inside React. `/admin` is a possible later shared-origin deployment prefix, not a current citizen route. PR1 must document its actual navigation, planning store, fixtures, KPI formulas and tests in this directory.

## Integration Test Branch

`codex/integration-test` started from the documentation/server-policy foundation at `68f1283` and now includes main's PR4 merge `3297f43`. PR1, PR2 and PR3 are not staged. The branch also contains [the integration test plan](INTEGRATION_TEST_PLAN.md), synthetic fixtures, a candidate ledger and foundation CI. Component, cross-service and hardware gates remain distinct from the existing citizen/policy checks.

The owner confirmed D1: a physical demo using the existing Teensy, shared ESP and Grove with the laptop as server. Hardware gates H01/H02 are now required by default in the readiness ledger. D2 confirms minimal admin ticket closing; main owns its report/photo/status backend and PR1 owns the operator view. The shared report workflow remains pending. A simulation-only return HTTP API now exists on this test branch, with durable sessions, decisions and credits; see [RETURN_API_V1.md](RETURN_API_V1.md). The citizen UI is not connected to it.

D3 is confirmed: one recycling bin as a technology demonstration, using one Grove/camera and one QR station with one active session at a time. No split compartments, sorting diverter or second physical recycling station are required. Accepted plastic, metal and glass go into the same collection bin; the ledger retains their material labels. [The station decision](RECYCLING_STATION_OPTIONS.md) supersedes the earlier split-bin recommendation. Contributors keep their PR branches and report exact tested SHAs; Codex stages reviewed changes for combined testing before any owner-approved merge into `main`.

The latest review covers PR1 `8b34c96`, PR2 `84952d2`, PR3 `dce112f` and PR4 `28509cc`. PR2 has a newer push awaiting review. PR3's six relay tests, compilation and main return preflight pass; focused artifact-provenance and shared-gateway wording changes remain before a merge recommendation. After the owner's demo-only clarification, PR4 was accepted and merged as a component with the reviewed bundle and tested environment. Its 32 tests and fresh wheel install pass. The adapter must still handle bad readings and normalize timestamps before a route smoke test; general loader hardening and retraining automation are deferred. PR1, PR2 and PR3 remain unmerged. See [the current review](INTEGRATION_REVIEW_LATEST.md) and [demo acceptance conditions](PR4_REVIEW_2026-08-29.md#demo-acceptance).

## Integration ownership

| Track | Components | Integration target |
| --- | --- | --- |
| Fill sensing for configured bins | PR #2 Teensy sensing plus the fill module in the shared ESP32-C3 firmware; retain three-channel test capability | PR #4 forecasting and PR #1 routing/operations through the agreed telemetry contract |
| Recycling recognition | PR #3 Grove model plus the SSCMA module in the shared ESP32-C3 firmware | `main` server, QR-bound return sessions, citizen portal and simulated payout |
| Fill/overflow forecasting | PR #4 model features, training, calibration, inference and forecast evaluation | PR #1's single prediction-consumer interface; no independent dispatcher or citizen integration |

PR #2 owns the gateway shell, Teensy transport and fill queue. PR #3 owns the Grove/SSCMA adapter and recognition queue. A focused integration change combines those modules into one ESP firmware target without sending recognition into PR #1 or fill into the return-session decision. `main` still owns the inference endpoint, QR workflow and citizen return state.

The owner confirmed PR #4 as the forecasting owner, not merely a fallback. PR #1 should remove its superseded training/prediction code after PR #4 satisfies the shared interface and integration tests. Retain required telemetry validation/cache code, routing simulation and historical data. Keep a named non-ML operational fallback for unavailable forecasts. See [the owner-confirmed split](PR_REVIEW_2026-08-28.md#owner-confirmed-split); the replacement is not yet implemented.

## Hardware sourcing baseline

The USD150 demonstrator uses one Teensy 4.1 with configurable fill channels, one OV5647/Grove Vision AI V2 stack for the single recycling bin, and one ESP32-C3 for both Wi-Fi relay functions and station feedback. The C3 receives Teensy data over hardware UART and Grove metadata over I2C. It does not run the model or make server decisions. The owned Teensy is counted at full local replacement value inside the competition ceiling.

Retain three-channel sensing capability and the existing three-bin routing fixtures as engineering tests. Mark additional channels as simulated or unavailable; never copy a physical reading to invent another bin. The dated budget still reserves a third sensing channel as spare/bench equipment, not another physical recycling station. This smaller demo does not establish three-physical-bin submission compliance. No proposal, saved citizen record or simulation history was changed by D3.

See [HARDWARE_BUDGET_LOCAL_SOURCING.md](HARDWARE_BUDGET_LOCAL_SOURCING.md) for the dated Malaysian listings, Selangor delivery assumptions, budget totals and purchase gates.

PR #3 now adds isolated laptop/webcam training code, pinned dependencies, a strict raw-inference metadata class, six passing unit tests and a checksum-recorded laptop-only `.pt` artifact. The artifact still needs documented provenance/licence or removal before merge. PR3 does not yet supply a Grove-compatible model or tested Grove/shared-ESP deployment. The test branch implements the inference/session HTTP endpoints in simulation mode; website and physical integration remain pending. Follow [PR3_RECYCLING_VISION_REVIEW.md](PR3_RECYCLING_VISION_REVIEW.md) for current findings and the integration contract.

The documentation/integration branch now includes `server/recycling_policy.py`: a tested central-server decision tree that accepts stable high-confidence `plastic`, `metal` and `glass` labels and rejects every other material. The new return API calls this policy and persists its outcomes. The citizen return page still uses its existing mock path. PR #3 contains a laptop-only candidate artifact but no dataset or Grove-deployable artifact.

## Machine Learning Subsystem (`ml/`)

The merged forecasting package and synthetic sensor simulation pipeline are located in `ml/`:
- **Model capability**: Predicts `time_to_service_threshold_hours` at 90% fill using fill/rate/calendar features. Weight is not required. Horizon probabilities remain unsupported; this is not a 100% physical-overflow model.
- **Interface**: `from binsight_ml import ForecastProvider`, then `predict_snapshot(...)`. The PR1 routing adapter is not implemented at its reviewed head `8b34c96`.
- **Verification**: The 32 component tests and fresh package install passed. The recorded synthetic holdout MAE is 4.696 hours; this is not field-measured accuracy. Use the fixed reviewed model for the demo and keep the documented input/time guards at the integration boundary.

## Source of truth

- `web/src/model.ts`: citizen domain types and default demonstration data
- `web/src/store.tsx`: citizen persistence and migrations
- `web/src/App.tsx`: active route map
- `web/tests/`: tested browser workflows
- `BinSight_UI_Design_Language.txt`: shared visual and interaction rules
- `docs/FRONTEND.md`: frontend architecture, workflows, state, and verification rules
- `docs/`: integration contracts and current implementation status

Screenshots, chat messages, and proposal text do not override these files. Update this page in the same pull request whenever a route, storage key, schema version, or workflow changes.
