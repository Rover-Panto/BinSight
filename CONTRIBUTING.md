# Contributing to BinSight

## Branches

Create a focused branch from the latest `main`. Use names such as `feature/admin-operations`, `fix/report-images`, or `docs/data-contracts`.

Do not force-push `main`. Submit admin routing and KPI work through a pull request.

For PR1-4 integration, read [the test plan](docs/INTEGRATION_TEST_PLAN.md). `codex/integration-test` is coordinator-managed staging, not a replacement PR base. Keep changes on your existing feature branch and report the tested commit SHA. Do not merge the aggregate staging branch into feature branches or merge into `main` before review and owner approval.

## Before coding

Read:

- [Project state](docs/PROJECT_STATE.md)
- [Frontend reference](docs/FRONTEND.md)
- [Admin integration](docs/ADMIN_INTEGRATION.md)
- [Integration test plan and gates](docs/INTEGRATION_TEST_PLAN.md)
- [Data preservation](docs/DATA_PRESERVATION.md)
- [UI design language](BinSight_UI_Design_Language.txt)
- [Web prototype instructions](web/README.md)

Check `git status --short` before editing. Do not delete, stage, or reformat files that belong to another contributor's unfinished work.

## Architecture invariants

BinSight has exactly two bin types:

| Bin type | Required behavior |
| --- | --- |
| General-waste bin | One demonstrator bin reports fill, weight when available, sensor health and confidence through the shared Teensy/ESP32-C3 gateway. It uses no camera and no vision model. |
| Recycling-return bin | One physical technology-demonstration bin reports fill through that same gateway. OV5647/Grove Vision AI V2 classifies submitted items, and the same ESP32-C3 relays compact recognition results without running the model. |

Fill observations enter overflow prediction and truck-route planning through the PR #2 contract, retaining their bin type and `bin_id`. Keep three-channel capability and existing three-bin fixtures for tests; label replay/synthetic channels and never duplicate a live reading to invent another physical bin. Recycling classification events follow the PR #3 contract into accept/reject decisions, return sessions and simulated refunds. They support rejection-rate diagnostics, not measured contamination without ground truth. One ESP carries both contracts, but they require separate tasks, queues, sequence spaces and server handlers.

## Change boundaries

Keep citizen and admin state separate. Changes to `web/src/model.ts`, `web/src/store.tsx`, storage keys, or migrations require an explanation and migration coverage in the pull request.

Use simulated data. Label route output, KPI values, payouts, service status, and access control accurately.

## Required checks

Run from the root for the shared integration foundation:

```powershell
python -m unittest discover -s server/tests -v
python -m unittest discover -s integration/tests -v
python -m integration.check_readiness
```

Foundation checks do not validate unmerged subsystems. Attach component tests and the applicable integration gate evidence, including skipped hardware checks, to each PR. The test plan defines those gates.

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
