# BinSight Project State

Last verified: 28 August 2026

## Main branch

`main` contains the citizen-facing React prototype and the proposal material. The web app is a local demonstration. It has no production API, database, payment connection, camera scanner, or deployed bin network.

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

## Admin work

The `feature/admin-operations-portal` branch adds the collaborator's routing and KPI prototype under `admin-portal/`. In this first integration stage it runs as an independent Streamlit service on port 8501 while the citizen React application remains on port 5173.

The applications do not exchange data yet. The admin portal does not import or write the citizen store, and the existing citizen route map remains unchanged. A later integration can expose an authenticated `/admin` gateway or shared API after the data contract and role model are agreed.

The admin portal opens on a route-input command surface and supports legacy predictive CSV/JSON plus the versioned telemetry-routing 2.1 replay contract. A separate read-only adapter now converts PR #2 historical fill readings into complete 6/24/48/168-hour probabilistic snapshots with explicit ID mapping, reset/outlier handling, hierarchical fallbacks, controlled retraining and model provenance. It provides collection, inspection, defer/wait, or no-collection decisions; OpenStreetMap/OSRM route previews; versioned simulation evidence; chronological mock tracking; and a durable draft/accept/complete/cancel plan audit. The dynamic trip-value model jointly chooses optional pickups and routes while keeping emergency/service-level stops mandatory. It enforces mass, compacted volume, waste-stream compatibility, route duration and shared daily trips, and exposes avoided loss, route cost and net value.

Telemetry observations, routing plans and citizen records remain separate. Live hardware input is disabled until the producer branch passes identity, UTC, replay, acknowledgement, quality and outage contract checks. Fixture/replay success is not physical Wi-Fi or sensor validation.

BinSight has two bin types across three demonstrator bins. One general-waste and two recycling bins provide independent fill/health channels through the shared Teensy and PR #2 ESP32-C3; all three fill streams may enter routing. Only recycling uses OV5647/Grove Vision AI V2 and the separate PR #3 ESP32-C3 recognition path. Recognition/session events cannot enter routing, general-waste has no vision model, and fill cannot decide item acceptance.

See `ADMIN_PORTAL_DESIGN_SYSTEM.md` for the implemented visual and responsive contract, and `HOW_TO_OPERATE_ADMIN_PORTAL.md` for the operator workflow and verification commands.

`COMPETITION_COMPLIANCE_AUDIT.md` records the current question-paper coverage and the unresolved physical-prototype, budget, power, presentation, camera, return-station, and proposal-consistency gaps. Digital Focus Area C completion must not be presented as full competition completion.

## Source of truth

- `web/src/model.ts`: citizen domain types and default demonstration data
- `web/src/store.tsx`: citizen persistence and migrations
- `web/src/App.tsx`: active route map
- `admin-portal/app.py`: independent operations portal entry point
- `admin-portal/binsight/dispatch.py`: predictive snapshot validation and mock dispatch contract
- `admin-portal/binsight/telemetry_adapter.py` and `registry.py`: versioned producer-event normalization and stable hardware/canonical IDs
- `admin-portal/binsight/pr2_forecasting.py`: PR #2 history cleaning, online adaptation, probabilistic forecasting, snapshot alignment and rolling-origin evaluation
- `admin-portal/binsight/planner.py` and `planning_store.py`: browser-independent evaluation, controlled runner and immutable route lifecycle
- `admin-portal/binsight/routing.py`: prize-collecting mass/volume/time route solver
- `admin-portal/binsight/observations.py`: simulated sensor errors, confidence, uncertainty, and leakage boundary
- `admin-portal/binsight/maps.py` and `tracking.py`: consolidated site maps and chronological replay
- `web/tests/`: tested browser workflows
- `BinSight_UI_Design_Language.txt`: shared visual and interaction rules
- `docs/FRONTEND.md`: frontend architecture, workflows, state, and verification rules
- `docs/`: integration contracts and current implementation status
- `docs/TELEMETRY_ROUTING_CONTRACT.md`: producer/consumer version 2.1 interface and live gate

Screenshots, chat messages, and proposal text do not override these files. Update this page in the same pull request whenever a route, storage key, schema version, or workflow changes.
