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

The route-optimisation and KPI dashboard is planned collaborator work. It has not merged into `main` at the date above. The collaborator should follow [ADMIN_INTEGRATION.md](ADMIN_INTEGRATION.md) and [DATA_PRESERVATION.md](DATA_PRESERVATION.md).

The admin implementation should use `/admin` as its route prefix and keep admin state outside the citizen store. The first pull request must record its final route map, state model, fixtures, KPI formulas, and tests in this directory.

## Source of truth

- `web/src/model.ts`: citizen domain types and default demonstration data
- `web/src/store.tsx`: citizen persistence and migrations
- `web/src/App.tsx`: active route map
- `web/tests/`: tested browser workflows
- `BinSight_UI_Design_Language.txt`: shared visual and interaction rules
- `docs/FRONTEND.md`: frontend architecture, workflows, state, and verification rules
- `docs/`: integration contracts and current implementation status

Screenshots, chat messages, and proposal text do not override these files. Update this page in the same pull request whenever a route, storage key, schema version, or workflow changes.
