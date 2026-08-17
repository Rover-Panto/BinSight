# BinSight

BinSight is MON BLUE's engineering proposal for a smart waste-sensing system and citizen recycling hub. The concept combines instrumented bins, a beverage return station, local decision support, collection-route simulation, and a resident-facing service interface.

The repository now contains two deliberately independent applications:

- `web/`: the React citizen-facing frontend, served at `http://127.0.0.1:5173/`.
- `admin-portal/`: the Streamlit routing and operations portal, served at `http://127.0.0.1:8501/`.

They share a repository and product identity, but they do not exchange data yet. This keeps the citizen prototype stable while the routing portal is developed and reviewed separately.

## Current status

The proposal, supporting research, document-generation scripts, and responsive citizen hub frontend are present. The frontend is a self-contained prototype with simulated authentication, station-detected returns, payouts, reports, automatic public-bin routing, support services, and local persistence.

## Repository contents

- `docs/`: project state, admin integration, and data-preservation contracts
- `BinSight_UI_Design_Language.txt`: citizen and admin interface rules
- `outputs/`: current proposal documents and review material
- `scripts/`: proposal and document-generation scripts
- `work/binsight_assets/`: project-owned visual assets
- `work/research-notes/`: research and evidence notes
- `research_brief_proposal_outline.md`: proposal research brief
- `web/`: React and TypeScript citizen hub prototype
- `admin-portal/`: Python, Streamlit, OSRM/OpenStreetMap, and OR-Tools operations portal
- `Start-BinSight-Admin.cmd`: starts only the admin portal after setup
- `Start-BinSight-All.cmd`: starts both independent applications

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

The admin setup requires Python 3.12. Its virtual environment is local to `admin-portal/` and ignored by Git.

After both dependency sets are installed, use `Start-BinSight-All.cmd` to open both applications in separate local processes. Stopping one application does not stop the other.

## Planned citizen hub

The interface covers National ID and mock OTP login, beverage returns at RM0.20 per accepted item, Bank Transfer and E-Wallet payout methods, waste issue reporting, category-based disposal guidance, locations, FAQ, scripted chat, notifications, and mock contact details.

All identities, payouts, service reports, and contact details in the prototype will be simulated.

Start with `docs/PROJECT_STATE.md` before changing routes or stored data. See `CONTRIBUTING.md` for collaboration rules and `web/README.md` for local development, test, and demonstration instructions.
