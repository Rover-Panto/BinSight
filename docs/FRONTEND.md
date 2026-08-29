# Frontend Reference

Last verified: 27 August 2026

## Stack

- React 19 and TypeScript
- Vite development and production builds
- React Router for citizen routes
- Lucide icons
- Barlow for interface text and JetBrains Mono for technical references
- Vitest and Testing Library for component tests
- Playwright for browser workflows and responsive screenshots

The frontend lives under `web/`. It is a local demonstration with simulated identity, payouts, service data, and bin activity.

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

Admin pages belong under `web/src/admin/` and use a separate shell and store. See [ADMIN_INTEGRATION.md](ADMIN_INTEGRATION.md).

The current operator implementation remains the independent Streamlit service on port 8501. It now displays source mode, observation age, forecast availability, data-quality warnings, trip-value inputs and immutable plan lifecycle. This does not add a React citizen route, shared browser storage or citizen navigation item.

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

### Waste report

The resident selects an issue, location, observation time, description, safety flag, and up to three images. The browser converts JPG, PNG, and WEBP files into compressed local attachments. The report detail page keeps them visible after submission and reload.

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
