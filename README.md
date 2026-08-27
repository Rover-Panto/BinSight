# BinSight

BinSight is MON BLUE's engineering proposal for a smart waste-sensing system and citizen recycling hub. The prototype has two bin types: general-waste bins that measure fill for collection routing, and a recycling-return station that classifies deposited items. Computer vision belongs only to the recycling-return station.

## Current status

The proposal, supporting research, document-generation scripts, and responsive citizen hub frontend are present. The frontend is a self-contained prototype with simulated authentication, station-detected returns, payouts, reports, automatic public-bin routing, support services, and local persistence.

## System boundary

| Bin type | Prototype hardware | Server use |
| --- | --- | --- |
| General waste | Three fill-sensing channels controlled by one Teensy 4.1, with one ESP32-C3 Wi-Fi relay | PR #2 integrates with PR #1 for fill history, prediction, collection priority and routing |
| Recycling return | OV5647 camera and Grove Vision AI V2, with its own ESP32-C3 result relay | PR #3 integrates with `main` for QR sessions, accept/reject records, simulated refunds and citizen UI |

General-waste bins have no camera and perform no item classification. The recycling-return station is the only BinSight device that requires or runs the vision model. The two ESP32-C3 boards have separate firmware, identities and data contracts; neither runs the model.

## Repository contents

- `docs/`: frontend reference, project state, admin integration, and data-preservation contracts
- `docs/PR3_RECYCLING_VISION_REVIEW.md`: recycling-model review and Grove-to-website integration contract
- `BinSight_UI_Design_Language.txt`: citizen and admin interface rules
- `outputs/`: current proposal documents and review material
- `scripts/`: proposal and document-generation scripts
- `server/`: central-server recycling decision policy and unit tests; HTTP integration remains pending
- `work/binsight_assets/`: project-owned visual assets
- `work/research-notes/`: research and evidence notes
- `research_brief_proposal_outline.md`: archived early research notes; not the current architecture source
- `web/`: React and TypeScript citizen hub prototype

## Planned citizen hub

The interface covers National ID and mock OTP login, beverage returns at RM0.20 per accepted item, Bank Transfer and E-Wallet payout methods, waste issue reporting, category-based disposal guidance, locations, FAQ, scripted chat, notifications, and mock contact details.

All identities, payouts, service reports, and contact details in the prototype will be simulated.

Start with `docs/PROJECT_STATE.md` before changing routes or stored data. See `CONTRIBUTING.md` for collaboration rules and `web/README.md` for local development, test, and demonstration instructions.
