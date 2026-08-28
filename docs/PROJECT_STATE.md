# BinSight Project State

Last verified: 28 August 2026

## Main branch

`main` contains the citizen-facing React prototype and engineering integration documentation. Proposal and submission files are kept outside Git. The web app is a local demonstration. It has no production API, database, payment connection, camera scanner, or deployed bin network.

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
| Recycling return | Two model bins measure fill and support the return flow | The same Teensy and ESP carry two independently identified fill channels. OV5647/Grove Vision AI V2 performs local classification; the same ESP relays compact recognition results and controls feedback after the server decision. |

Recycling fill readings and recycling inference events are logically independent. Firmware must contain a classifier/peripheral fault so fill reporting can continue; a shared C3 reset or power loss interrupts both streams. Fill level must not influence item acceptance. The route adapter may consume fill observations from either bin type, but must reject every classification event. See [SHARED_ESP32_GATEWAY.md](SHARED_ESP32_GATEWAY.md).

## Admin work

The route-optimisation and KPI dashboard has substantial implementation on PR #1, but has not merged into `main`. Its latest update adds predictive telemetry snapshots, trip-value routing, stored route lifecycle and expanded synthetic evaluation. PR #4 adds a separate overflow predictor that overlaps this work. Follow [the cross-PR review](PR_REVIEW_2026-08-28.md), [ADMIN_INTEGRATION.md](ADMIN_INTEGRATION.md) and [DATA_PRESERVATION.md](DATA_PRESERVATION.md).

The initial integration keeps PR1's Streamlit website under `admin-portal/` and the citizen React site under `web/`. Do not rebuild the admin site inside React. `/admin` is a possible later shared-origin deployment prefix, not a current citizen route. PR1 must document its actual navigation, planning store, fixtures, KPI formulas and tests in this directory.

## Integration Test Branch

`codex/integration-test` starts from the documentation/server-policy foundation at `68f1283`. It does not initially contain PR1-4. It adds [the integration test plan](INTEGRATION_TEST_PLAN.md), synthetic fixtures, a candidate ledger and foundation CI. Component, cross-service and hardware gates remain distinct from the existing citizen/policy checks.

The owner confirmed D1: a physical demo using the existing Teensy, shared ESP and Grove with the laptop as server. Hardware gates H01/H02 are now required by default in the readiness ledger. D2 confirms minimal admin ticket closing; main owns its report/photo/status backend and PR1 owns the operator view. Neither the shared report workflow nor the return HTTP integration is implemented yet.

D3 remains open: the owner expects one Grove per recycling bin in a future installation and is considering a split-bin demo. [The station options](RECYCLING_STATION_OPTIONS.md) compare the costs and physical/session consequences. Keep the current one-Grove budget; do not assume a second camera or a material-to-compartment mapping. Contributors keep their PR branches and report exact tested SHAs; Codex stages reviewed changes for combined testing before any owner-approved merge into `main`.

## Integration ownership

| Track | Components | Integration target |
| --- | --- | --- |
| Fill sensing for all three bins | PR #2 Teensy sensing plus the fill module in the shared ESP32-C3 firmware | PR #4 forecasting and PR #1 routing/operations through the agreed telemetry contract |
| Recycling recognition | PR #3 Grove model plus the SSCMA module in the shared ESP32-C3 firmware | `main` server, QR-bound return sessions, citizen portal and simulated payout |
| Fill/overflow forecasting | PR #4 model features, training, calibration, inference and forecast evaluation | PR #1's single prediction-consumer interface; no independent dispatcher or citizen integration |

PR #2 owns the gateway shell, Teensy transport and fill queue. PR #3 owns the Grove/SSCMA adapter and recognition queue. A focused integration change combines those modules into one ESP firmware target without sending recognition into PR #1 or fill into the return-session decision. `main` still owns the inference endpoint, QR workflow and citizen return state.

The owner confirmed PR #4 as the forecasting owner, not merely a fallback. PR #1 should remove its superseded training/prediction code after PR #4 satisfies the shared interface and integration tests. Retain required telemetry validation/cache code, routing simulation and historical data. Keep a named non-ML operational fallback for unavailable forecasts. See [the owner-confirmed split](PR_REVIEW_2026-08-28.md#owner-confirmed-split); the replacement is not yet implemented.

## Hardware sourcing baseline

The USD150 demonstrator uses one Teensy 4.1 for three fill channels, one OV5647/Grove Vision AI V2 stack for recycling inference, and one ESP32-C3 for both Wi-Fi relay functions and station feedback. The C3 receives Teensy data over hardware UART and Grove metadata over I2C. It does not run the model or make server decisions. The owned Teensy is counted at full local replacement value inside the competition ceiling.

The number of Grove modules and the split-station mechanism remain a D3 design question, not a purchase authorisation. A shared housing can contain two removable, independently measured recycling bins; it must not reduce three fill channels to two or imply three separately sorted material streams.

See [HARDWARE_BUDGET_LOCAL_SOURCING.md](HARDWARE_BUDGET_LOCAL_SOURCING.md) for the dated Malaysian listings, Selangor delivery assumptions, budget totals and purchase gates.

PR #3 now adds isolated laptop/webcam training code, pinned dependencies, a raw inference metadata class and three passing unit tests. It does not supply trained weights or tested Grove/ESP deployment. Main still needs to implement the inference/session HTTP endpoints and website integration. Follow [PR3_RECYCLING_VISION_REVIEW.md](PR3_RECYCLING_VISION_REVIEW.md) for current findings and the integration contract.

The documentation/integration branch now includes `server/recycling_policy.py`: a tested central-server decision tree that accepts stable high-confidence `plastic`, `metal` and `glass` labels and rejects every other material. It is not yet wired to an HTTP endpoint or the citizen return page. PR #3 contains no trained model artifact or dataset.

## Source of truth

- `web/src/model.ts`: citizen domain types and default demonstration data
- `web/src/store.tsx`: citizen persistence and migrations
- `web/src/App.tsx`: active route map
- `web/tests/`: tested browser workflows
- `BinSight_UI_Design_Language.txt`: shared visual and interaction rules
- `docs/FRONTEND.md`: frontend architecture, workflows, state, and verification rules
- `docs/`: integration contracts and current implementation status

Screenshots, chat messages, and proposal text do not override these files. Update this page in the same pull request whenever a route, storage key, schema version, or workflow changes.
