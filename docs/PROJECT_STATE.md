# BinSight Project State

Last verified: 27 August 2026

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

## Two-bin architecture

BinSight has two and only two bin types. Keep this distinction in firmware, APIs, storage, routing, dashboards, proposal text and demonstrations.

| Bin type | Physical role | Processing boundary |
| --- | --- | --- |
| General waste | One model bin measures fill and, where fitted, weight | The shared Teensy 4.1 schedules its sensing; the PR #2 ESP32-C3 relays telemetry for overflow prediction and routing. No camera or vision model is used. |
| Recycling return | Two model bins measure fill and support the return flow | The same Teensy and PR #2 C3 carry two independently identified fill channels into routing. OV5647/Grove Vision AI V2 performs local classification for the return flow; the separate PR #3 C3 relays compact recognition results and controls feedback. |

Recycling fill readings and recycling inference events are independent. A classifier fault must not stop fill reporting, and fill level must not influence item acceptance. The route adapter may consume fill observations from either bin type, but must reject every classification event.

## Admin work

The route-optimisation and KPI dashboard is planned collaborator work. It has not merged into `main` at the date above. The collaborator should follow [ADMIN_INTEGRATION.md](ADMIN_INTEGRATION.md) and [DATA_PRESERVATION.md](DATA_PRESERVATION.md).

The admin implementation should use `/admin` as its route prefix and keep admin state outside the citizen store. The first pull request must record its final route map, state model, fixtures, KPI formulas, and tests in this directory.

## Integration ownership

| Track | Components | Integration target |
| --- | --- | --- |
| Fill sensing for all three bins | PR #2 shared Teensy sensing and its dedicated ESP32-C3 relay | PR #1 prediction, routing and operations portal |
| Recycling recognition | PR #3 Grove model and its dedicated ESP32-C3 inference relay | `main` server, QR-bound return sessions, citizen portal and simulated payout |

PR #2 owns recycling-bin fill telemetry but must not implement Grove recognition, the inference endpoint, QR workflow or citizen return state. PR #3 must not send recognition events into PR #1's routing adapter. The tracks may share a physical recycling bin, but not event schemas, queues or decision logic.

## Hardware sourcing baseline

The USD150 demonstrator uses one Teensy 4.1 for three fill channels: one general-waste bin and two recycling bins. One PR #2 ESP32-C3 relays all three fill streams. The return flow uses one OV5647 camera and Grove Vision AI V2 for local inference, plus a separate PR #3 ESP32-C3 for recognition delivery and station control. Only recycling uses vision, and neither C3 runs the model. The owned Teensy is counted at full local replacement value inside the competition ceiling.

See [HARDWARE_BUDGET_LOCAL_SOURCING.md](HARDWARE_BUDGET_LOCAL_SOURCING.md) for the dated Malaysian listings, Selangor delivery assumptions, budget totals and purchase gates.

PR #3 adds a laptop/webcam YOLO training prototype but does not yet implement the Grove export, ESP32-C3 result relay, server decision contract or website integration. It must not merge unchanged. Follow [PR3_RECYCLING_VISION_REVIEW.md](PR3_RECYCLING_VISION_REVIEW.md) for the required class map, high-confidence decision gate, no-camera web boundary, data contract, merge order and acceptance checks.

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
