# Contributing to BinSight

## Branches

Create a focused branch from the latest `main`. Use names such as `feature/admin-operations`, `fix/report-images`, or `docs/data-contracts`.

Do not force-push `main`. Submit admin routing and KPI work through a pull request.

## Before coding

Read:

- [Project state](docs/PROJECT_STATE.md)
- [Frontend reference](docs/FRONTEND.md)
- [Admin integration](docs/ADMIN_INTEGRATION.md)
- [Data preservation](docs/DATA_PRESERVATION.md)
- [UI design language](BinSight_UI_Design_Language.txt)
- [Web prototype instructions](web/README.md)

Check `git status --short` before editing. Do not delete, stage, or reformat files that belong to another contributor's unfinished work.

## Change boundaries

Keep citizen and admin state separate. Changes to `web/src/model.ts`, `web/src/store.tsx`, storage keys, or migrations require an explanation and migration coverage in the pull request.

Keep fill and recognition domains separate. The shared Teensy/PR #2 ESP32-C3 reports independently identified fill for one general-waste and two recycling bins; all three may enter routing. The OV5647/Grove Vision AI V2 and PR #3 ESP32-C3 produce recycling recognition/session events, which must never enter routing. Do not adapt classification into fill, use fill to decide item acceptance, or combine incompatible waste streams in one truck trip.

Treat the 11 three-bin simulation groups as service topology. Physical controller topology belongs to the explicit three-channel pilot registry and must not be inferred from simulation names or row positions.

Use simulated data. Label route output, KPI values, payouts, service status, and access control accurately.

## Required checks

Run from `admin-portal/` for routing, sensor, simulation, firmware-contract, report, or admin UI changes:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

When maps/tracking or route input changes, run both `scripts/qa_dispatch_ui.js` and `scripts/qa_maps_tracking.js` against the local Streamlit service.

Run from `web/`:

```powershell
pnpm lint
pnpm test:run
pnpm test:e2e
pnpm build
```

Attach screenshots when a pull request changes a user-facing page. Check 1440x900, 768x1024, and 390x844 layouts for clipping, overlap, and horizontal overflow.

## Documentation

Update documentation in the same pull request as the code. At minimum:

- update `docs/FRONTEND.md` for frontend architecture, workflow, state, or test changes;
- update `docs/PROJECT_STATE.md` for route or workflow changes;
- update `docs/DATA_PRESERVATION.md` for stored-data changes;
- document every KPI formula, unit, assumption, and simulation flag;
- record any new storage key and internal schema version.

Code and documentation should describe the same behavior at merge time.

## Publishing work

Every completed implementation update must include its affected documentation and tests in the same commit. Stage explicit intended paths, inspect the staged diff, use a descriptive commit message, and push the active feature branch unless the task owner explicitly asks for a local-only change. Never preserve a known-stale result claim merely to avoid changing a report.

Do not leave finished work only in a local checkout. Contributors still use pull requests for merging into `main`; pushing a feature branch does not bypass review.
