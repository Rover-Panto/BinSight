# BinSight

BinSight is MON BLUE's engineering proposal for a smart waste-sensing system and citizen recycling hub. The concept combines instrumented bins, a beverage return station, local decision support, collection-route simulation, and a resident-facing service interface.

The repository now contains two deliberately independent applications:

- `web/`: the React citizen-facing frontend, served at `http://127.0.0.1:5173/`.
- `admin-portal/`: the Streamlit routing and operations portal, served at `http://127.0.0.1:8501/`.

They share a repository and product identity, but they do not exchange data yet. This keeps the citizen prototype stable while the routing portal is developed and reviewed separately.

## Two-bin architecture boundary

BinSight has exactly two bin types:

- **General waste:** one demonstrator fill/health channel on the shared Teensy 4.1 and PR #2 ESP32-C3 relay. It has no camera or material-classification model.
- **Recycling return:** two demonstrator fill channels use the same Teensy/PR #2 relay and are valid routing inputs. Their separate OV5647/Grove Vision AI V2 and PR #3 ESP32-C3 path produces recognition/session events, which routing rejects.

All three fill observations retain their physical bin type and waste stream. Fill and recognition are independent: a vision fault cannot stop recycling-fill routing, and fill cannot influence item acceptance. Incompatible general and recycling waste streams are never combined in one route trip.

The 11 three-bin groups in the competition simulation are service topology, not a claim of 11 deployed physical controllers. The physical pilot profile maps one three-channel Teensy/C3 producer explicitly.

## Current status

The proposal, supporting research, document-generation scripts, and responsive citizen hub frontend are present. The frontend is a self-contained prototype with simulated authentication, station-detected returns, payouts, reports, automatic public-bin routing, support services, and local persistence. The admin portal implements the 500-household/20-commercial-unit Focus Area C simulation, safe three-state sensor decisions, a versioned fill-telemetry boundary, dynamic trip-value routing, durable plan approval, base/stress evaluation, and mock chronological truck tracking. Physical-build, measured-power, BOM/receipt, camera-classifier, return-station-hardware, and final-presentation evidence remain open.

## Repository contents

- `docs/`: frontend reference, project state, admin integration, and data-preservation contracts
- `BinSight_UI_Design_Language.txt`: citizen and admin interface rules
- `ml/`: smart-bin overflow-risk ML pipeline, sensor simulation, feature engineering, and trained model artifacts
- `outputs/`: current proposal documents and review material
- `scripts/`: proposal and document-generation scripts
- `work/binsight_assets/`: project-owned visual assets
- `work/research-notes/`: research and evidence notes
- `research_brief_proposal_outline.md`: proposal research brief
- `web/`: React and TypeScript citizen hub prototype
- `admin-portal/`: Python, Streamlit, OSRM/OpenStreetMap, and OR-Tools operations portal
- `Start-BinSight-Admin.cmd`: starts only the admin portal after setup
- `Start-BinSight-All.cmd`: starts both independent applications

## Documentation

- [Project state](docs/PROJECT_STATE.md): current routes, boundaries, and sources of truth
- [Admin portal design system](docs/ADMIN_PORTAL_DESIGN_SYSTEM.md): visual tokens, responsive rules, states, accessibility, QA evidence, and prototype limits
- [How to operate the admin portal](docs/HOW_TO_OPERATE_ADMIN_PORTAL.md): predictive input, route review, mock dispatch, verification, and troubleshooting
- [Admin integration contract](docs/ADMIN_INTEGRATION.md): current independent-service boundary and future integration rules
- [Telemetry-to-routing contract](docs/TELEMETRY_ROUTING_CONTRACT.md): three-bin fill identity, timing, type, quality, registry and live gate
- [Routing AAR](docs/ROUTING_AAR.md): failure analysis, implemented corrections and remaining validation gates
- [Routing integration status](docs/ROUTING_INTEGRATION_STATUS.md): C01–C30 checks and R1–R10 producer blockers
- [Dynamic routing v2 results](admin-portal/DYNAMIC_V2_RESULTS.md): matched scenario outcomes, forecast diagnostics, fixed-route audit and deployment decision
- [Data preservation contract](docs/DATA_PRESERVATION.md): stored-data and migration safeguards
- [Competition compliance audit](docs/COMPETITION_COMPLIANCE_AUDIT.md): question-paper coverage, proposal gaps, and remaining deliverables
- [Focus Area C routing report (PDF)](admin-portal/reports/BinSight_Routing_Subsystem_Report_Improved.pdf): generated competition-facing implementation report

## Run the applications

Citizen frontend only:

```powershell
cd web
pnpm install
pnpm dev
```

Admin portal only, first-time setup:

```powershell
.\Setup-BinSight-Admin.cmd
.\Start-BinSight-Admin.cmd
```

The admin setup supports Python 3.12 and 3.13. Its virtual environment is local to `admin-portal/` and ignored by Git.

After both dependency sets are installed, use `Start-BinSight-All.cmd` to open both applications in separate local processes. Stopping one application does not stop the other.

## Planned citizen hub

The interface covers National ID and mock OTP login, beverage returns at RM0.20 per accepted item, Bank Transfer and E-Wallet payout methods, waste issue reporting, category-based disposal guidance, locations, FAQ, scripted chat, notifications, and mock contact details.

All identities, payouts, service reports, and contact details in the prototype will be simulated.

Start with `docs/PROJECT_STATE.md` before changing routes or stored data. See `CONTRIBUTING.md` for collaboration rules and `web/README.md` for local development, test, and demonstration instructions.
