# BinSight

BinSight is MON BLUE's engineering proposal for a smart waste-sensing system and citizen recycling hub. The concept combines instrumented bins, a beverage return station, local decision support, collection-route simulation, and a resident-facing service interface.

## Current status

The proposal, supporting research, document-generation scripts, and responsive citizen hub frontend are present. The frontend is a self-contained prototype with simulated authentication, station-detected returns, payouts, reports, automatic public-bin routing, support services, and local persistence.

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

## Planned citizen hub

The interface covers National ID and mock OTP login, beverage returns at RM0.20 per accepted item, Bank Transfer and E-Wallet payout methods, waste issue reporting, category-based disposal guidance, locations, FAQ, scripted chat, notifications, and mock contact details.

All identities, payouts, service reports, and contact details in the prototype will be simulated.

Start with `docs/PROJECT_STATE.md` before changing routes or stored data. See `CONTRIBUTING.md` for collaboration rules and `web/README.md` for local development, test, and demonstration instructions.
