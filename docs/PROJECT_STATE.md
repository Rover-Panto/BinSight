# BinSight Project State

Last verified: 17 August 2026

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

The admin portal currently opens on a route-input command surface and provides predictive-AI CSV/JSON input; collection, inspection, or no-collection decisions; OpenStreetMap/OSRM route previews; base/stress simulation results; chronological mock truck tracking; and a local mock-dispatch audit. The current operational model separates noisy observations from hidden physical state, rejects stale/future snapshots, enforces two trips across the full calendar day, and models travel/service/unloading/turnaround before a bin is emptied. Its responsive interface uses desktop/tablet tabs and a four-destination mobile bottom navigation. All operational outputs remain labelled as prototype or simulation data.

See `ADMIN_PORTAL_DESIGN_SYSTEM.md` for the implemented visual and responsive contract, and `HOW_TO_OPERATE_ADMIN_PORTAL.md` for the operator workflow and verification commands.

`COMPETITION_COMPLIANCE_AUDIT.md` records the current question-paper coverage and the unresolved physical-prototype, budget, power, presentation, camera, return-station, and proposal-consistency gaps. Digital Focus Area C completion must not be presented as full competition completion.

## Source of truth

- `web/src/model.ts`: citizen domain types and default demonstration data
- `web/src/store.tsx`: citizen persistence and migrations
- `web/src/App.tsx`: active route map
- `admin-portal/app.py`: independent operations portal entry point
- `admin-portal/binsight/dispatch.py`: predictive snapshot validation and mock dispatch contract
- `admin-portal/binsight/observations.py`: simulated sensor errors, confidence, uncertainty, and leakage boundary
- `admin-portal/binsight/maps.py` and `tracking.py`: consolidated site maps and chronological replay
- `web/tests/`: tested browser workflows
- `BinSight_UI_Design_Language.txt`: shared visual and interaction rules
- `docs/`: integration contracts and current implementation status

Screenshots, chat messages, and proposal text do not override these files. Update this page in the same pull request whenever a route, storage key, schema version, or workflow changes.
