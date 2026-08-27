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

## Architecture invariants

BinSight has exactly two bin types:

| Bin type | Required behavior |
| --- | --- |
| General-waste bin | One demonstrator bin reports fill, weight when available, sensor health and confidence. It uses no camera and no vision model. |
| Recycling-return bin | Two demonstrator bins report fill through the shared Teensy/PR #2 relay. The separate OV5647/Grove Vision AI V2 path classifies submitted items, and the PR #3 ESP32-C3 relays recognition results without running the model. |

All three fill observations enter overflow prediction and truck-route planning through PR #2, retaining their bin type and physical `bin_id`. Recycling classification events follow PR #3 into accept/reject decisions, return sessions, simulated refunds and contamination KPIs. Do not merge fill and inference events or make either stream depend on the other.

## Change boundaries

Keep citizen and admin state separate. Changes to `web/src/model.ts`, `web/src/store.tsx`, storage keys, or migrations require an explanation and migration coverage in the pull request.

Use simulated data. Label route output, KPI values, payouts, service status, and access control accurately.

## Required checks

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

Commit each completed, verified change and push it to the contributor's remote branch. Do not leave finished work only in a local checkout. Contributors still use pull requests for merging into `main`; pushing a feature branch does not bypass review.
