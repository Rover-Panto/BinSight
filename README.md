# BinSight

BinSight is MON BLUE's smart waste-sensing system and citizen recycling hub. The physical technology demo uses one recycling-return bin alongside the general-waste sensing demonstrator. Computer vision belongs only to recycling returns. Three-channel sensing support and the existing three-bin routing fixtures remain engineering test coverage, not evidence of a second physical recycling bin.

## Current status

The repository contains the responsive citizen hub, hardware and server integration contracts, and supporting tests. PR4's forecasting package merged into `main` at `3297f43` and is now included on this integration branch. Its connection to PR1 routing is still pending. The frontend remains a self-contained prototype with simulated authentication, station-detected returns, payouts, reports, automatic public-bin routing, support services, and local persistence.

## Target System Boundary

| Bin type | Prototype hardware | Server use |
| --- | --- | --- |
| General waste | One fill-sensing channel on the shared Teensy 4.1 and ESP32-C3 gateway | PR #2 supplies telemetry; PR #4 owns forecasting; PR #1 owns collection priority, routing and KPIs |
| Recycling return | One physical bin with a Teensy fill channel and OV5647/Grove Vision AI V2 recognition through the same ESP32-C3 | Fill follows the PR #2/PR #1 route contract; recognition follows the PR #3/`main` session and decision contract |

The target design uses one Teensy to poll a fill sensor per physical bin with separate identity, calibration and health state. One ESP32-C3 receives those readings over UART, reads compact Grove recognition results over I2C, and sends both event types through independent queues. Grove runs the model; the laptop server handles routing and accept/reject decisions. Firmware must contain peripheral faults, but a shared C3 reset interrupts both paths. Fill level must not affect item acceptance or payout. This hardware integration remains under development.

The recycling demo has one collection bin, one QR station and one active return session at a time. It demonstrates recognition and accept/reject feedback, not automatic material separation. No split compartments, sorting diverter or second Grove are required. See [the confirmed station decision](docs/RECYCLING_STATION_OPTIONS.md).

PR1 should retire its duplicate forecasting after PR4's replacement passes the shared interface and integration tests. Keep routing, required telemetry validation/cache code, the non-ML operational fallback and historical records. See [the owner-confirmed split](docs/PR_REVIEW_2026-08-28.md#owner-confirmed-split).

## Repository contents

Integration coordination starts at [the test plan](docs/INTEGRATION_TEST_PLAN.md). The `codex/integration-test` branch holds the foundation checks, candidate ledger and merged PR4 package while PR1, PR2 and PR3 remain separate. This is not yet a connected or deployed system.

- `docs/`: frontend reference, project state, admin integration, and data-preservation contracts
- `docs/PR3_RECYCLING_VISION_REVIEW.md`: recycling-model review and Grove-to-website integration contract
- `docs/PR_REVIEW_2026-08-28.md`: current PR changes, defects, duplicated work and integration order
- `docs/PR1_PR4_FORECAST_INTEGRATION.md`: forecasting/routing ownership, shared interface and duplicate-code cleanup sequence
- `docs/SHARED_ESP32_GATEWAY.md`: one-board fill/recognition contract and firmware ownership
- `docs/INTEGRATION_TEST_PLAN.md`: two-site architecture, ownership, test gates and staged merge process
- `integration/`: shared fixtures, candidate-readiness checks, review probes and an isolated real-HTTP return preflight
- `BinSight_UI_Design_Language.txt`: citizen and admin interface rules
- `server/`: simulation-only return HTTP API, durable decisions/credits, backup tooling and policy tests; see [the API contract](docs/RETURN_API_V1.md)
- `ml/`: installed-package source, synthetic fill data and reviewed model for hours to the 90% service threshold; routing integration remains pending
- `web/`: React and TypeScript citizen hub prototype

The first return API slice is implemented on the test branch. PR4 is present; PR1, PR2 and PR3 remain outside this branch. The citizen app stays in mock mode; no existing records or photos are imported. See [the latest review](docs/INTEGRATION_REVIEW_LATEST.md).

## Planned citizen hub

The interface covers National ID and mock OTP login, beverage returns at RM0.20 per accepted item, Bank Transfer and E-Wallet payout methods, waste issue reporting, category-based disposal guidance, locations, FAQ, scripted chat, notifications, and mock contact details.

All identities, payouts, service reports, and contact details in the prototype will be simulated.

Start with `docs/PROJECT_STATE.md` before changing routes or stored data. See `CONTRIBUTING.md` for collaboration rules and `web/README.md` for local development, test, and demonstration instructions.
