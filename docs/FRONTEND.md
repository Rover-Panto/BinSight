# Frontend Reference

Architecture documentation updated: 28 August 2026. See the integration baseline for current test evidence.

## Stack

- React 19 and TypeScript
- Vite development and production builds
- React Router for citizen routes
- Lucide icons
- Barlow for interface text and JetBrains Mono for technical references
- Vitest and Testing Library for component tests
- One process-based Vitest worker for repeatable Windows and CI runs
- Playwright for browser workflows and responsive screenshots

The frontend lives under `web/`. It is a local demonstration with simulated identity, payouts, service data, and bin activity.

## Product boundary

The interface represents one general-waste and two recycling bins. All three report fill and health through the PR #2 contract for automatic collection routing. The same ESP32-C3 also relays PR #3 Grove recognition events, but only the server's recognition decision determines item acceptance; fill status never does.

Keep the distinction visible without asking the citizen to categorise the item manually. Return pages describe a station inspection. Routing and fill status belong to the operations side. Do not display recycling classification as general-waste telemetry or suggest that general-waste bins identify their contents.

## File map

| Path | Responsibility |
| --- | --- |
| `web/src/App.tsx` | Route registration and global status banners |
| `web/src/components/AppShell.tsx` | Citizen desktop and mobile navigation |
| `web/src/components/UI.tsx` | Shared headings, fields, notices, modals, badges, and empty states |
| `web/src/model.ts` | Citizen domain types, fixtures, and formatting helpers |
| `web/src/store.tsx` | Citizen actions, persistence, schema migration, and storage status |
| `web/src/pages/AuthPages.tsx` | National ID and mock OTP flow |
| `web/src/pages/HomeAccountPages.tsx` | Home, notifications, account, payout methods, and history |
| `web/src/pages/ReturnPages.tsx` | Return inspection, payout selection, and receipt |
| `web/src/pages/ServicePages.tsx` | Reports, disposal guidance, locations, and bulky pickup |
| `web/src/pages/SupportPages.tsx` | FAQ, scripted chat, and contacts |
| `web/src/index.css` | Design tokens, components, responsive rules, and accessibility states |
| `web/tests/` | Browser workflows and visual checks |

The first integration preserves PR1's separate Streamlit application in `admin-portal/`. It does not add admin pages to the citizen React router. Both applications exchange data through owned backend/provider contracts, not shared browser storage. See [ADMIN_INTEGRATION.md](ADMIN_INTEGRATION.md) and [the integration test plan](INTEGRATION_TEST_PLAN.md).

## Citizen navigation

Desktop navigation exposes Home, Return, Report, My Reports, Dispose, Services, and Account. Mobile navigation exposes Home, Return, Report, Dispose, and Account.

The top bar holds chat, notifications, and account access. Do not repeat page titles or breadcrumbs there.

The citizen route list is maintained in [PROJECT_STATE.md](PROJECT_STATE.md). Update that file whenever a route is added, removed, or renamed.

## State and persistence

The citizen store uses `binsight-demo-v1` with `AppData.version = 3`. The stable key preserves existing login and demonstration records while internal migrations update the object shape.

The store owns:

- generated demonstration identity and login state
- return sessions and simulated payouts
- payout methods
- waste reports and compressed image attachments
- notifications and user settings

Do not write admin fixtures or route simulation output to the citizen key. Follow [DATA_PRESERVATION.md](DATA_PRESERVATION.md) for every stored-data change.

## Main workflows

### Return

The resident starts a session and inserts one container at a time. The station determines the simulated item type and accepted or rejected result. Accepted items add RM0.20. The resident then chooses Bank Transfer or E-Wallet and receives a simulated receipt.

The planned hardware integration receives decision metadata from the laptop server after Grove Vision AI V2 classifies the item, the shared ESP32-C3 relays the result and the server applies the confidence gate. The browser must not access or display the station camera. Keep mock behavior behind a return-station client until the server contract is available, then place the API implementation behind the same interface. See [PR3_RECYCLING_VISION_REVIEW.md](PR3_RECYCLING_VISION_REVIEW.md).

### Waste report

The resident selects an issue, location, observation time, description, safety flag, and up to three images. The browser converts JPG, PNG, and WEBP files into compressed local attachments. The report detail page keeps them visible after submission and reload.

Reports currently stay in that browser. Admin report management is pending owner decision D2. Connecting it requires a report/photo/status API and an explicit migration/import design; do not claim Streamlit can already see these records or automatically upload old local images.

### Disposal guidance

The resident describes an item or chooses a broad waste stream. The UI returns a likely destination or an uncertain-result path. Do not replace this with a fixed item catalogue.

### Public-bin collection

Citizen pages describe public-bin collection as automatic and priority-based. Do not add a resident collection timetable.

## Design rules

Use [BinSight_UI_Design_Language.txt](../BinSight_UI_Design_Language.txt) as the full visual reference. Core requirements:

- Put the resident's immediate task first.
- Use graphite structural surfaces, Monash-inspired blue actions, green success states, and cool concrete content backgrounds.
- Keep radii between 4 and 6 pixels.
- Use Lucide icons and accessible names for icon-only controls.
- Avoid greetings, marketing language, AI terminology, fixed waste catalogues, and unnecessary labels.
- Keep simulated outcomes and prototype limits explicit.

## Responsive checks

Review every changed screen at:

- 1440x900 desktop
- 768x1024 tablet
- 390x844 mobile

Check horizontal overflow, text clipping, navigation overlap, fixed controls, modal height, and touch targets. Use screenshots; code inspection alone does not verify layout.

## Frontend change checklist

Every frontend change must include the relevant documentation in the same commit:

- update this file for architecture, workflow, state, or test changes;
- update `PROJECT_STATE.md` for routes and implemented capabilities;
- update `DATA_PRESERVATION.md` for schemas, storage keys, migrations, and attachments;
- update `ADMIN_INTEGRATION.md` for admin routes, shared contracts, routing, or KPI behavior;
- update `BinSight_UI_Design_Language.txt` when design tokens or interaction rules change;
- update `web/README.md` when setup, controls, or verification commands change.

After verification, commit and push the complete code-and-documentation change to the contributor's branch. Work that exists only in a local checkout is not ready for review.
