# BinSight

BinSight is MON BLUE's smart waste-sensing system and citizen recycling hub. The demonstrator has three physical bins: one general-waste bin and two recycling bins. All three report fill for collection routing, while computer vision belongs only to the recycling-return flow.

## Current status

The repository contains the responsive citizen hub, hardware and server integration contracts, and supporting tests. The frontend is a self-contained prototype with simulated authentication, station-detected returns, payouts, reports, automatic public-bin routing, support services, and local persistence.

## System boundary

| Bin type | Prototype hardware | Server use |
| --- | --- | --- |
| General waste | One fill-sensing channel on the shared Teensy 4.1 and PR #2 ESP32-C3 Wi-Fi relay | PR #2 integrates with PR #1 for fill history, prediction, collection priority and routing |
| Recycling return | Two independent fill channels on the same Teensy/PR #2 relay, plus a separate OV5647/Grove Vision AI V2 recognition path and PR #3 ESP32-C3 relay | Fill enters PR #1 routing through PR #2; recognition enters `main` through PR #3 for QR sessions, decisions, simulated refunds and citizen UI |

The single Teensy polls one fill sensor per physical bin and keeps a separate identity, calibration and health state for each channel. Its PR #2 ESP32-C3 relays all three fill streams. The PR #3 ESP32-C3 relays only compact recognition results from Grove; neither C3 runs the model. A vision fault must not stop recycling fill reporting, and fill level must not affect item acceptance or payout.

## Repository contents

- `docs/`: frontend reference, project state, admin integration, and data-preservation contracts
- `docs/PR3_RECYCLING_VISION_REVIEW.md`: recycling-model review and Grove-to-website integration contract
- `BinSight_UI_Design_Language.txt`: citizen and admin interface rules
- `server/`: central-server recycling decision policy and unit tests; HTTP integration remains pending
- `web/`: React and TypeScript citizen hub prototype

## Planned citizen hub

The interface covers National ID and mock OTP login, beverage returns at RM0.20 per accepted item, Bank Transfer and E-Wallet payout methods, waste issue reporting, category-based disposal guidance, locations, FAQ, scripted chat, notifications, and mock contact details.

All identities, payouts, service reports, and contact details in the prototype will be simulated.

Start with `docs/PROJECT_STATE.md` before changing routes or stored data. See `CONTRIBUTING.md` for collaboration rules and `web/README.md` for local development, test, and demonstration instructions.
