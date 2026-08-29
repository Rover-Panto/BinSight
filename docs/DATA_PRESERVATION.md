# Data Preservation and Migration Rules

## Current citizen storage

The citizen prototype stores its state in browser `localStorage` under `binsight-demo-v1`. The key name remains stable while the object carries an internal schema version.

Current schema: `AppData.version = 3`

Version 3 adds compressed report attachments. During startup, the migration code:

1. accepts schema versions 1, 2, and 3;
2. copies the pre-migration JSON to `binsight-demo-backup-v1` or `binsight-demo-backup-v2` when no backup exists;
3. preserves authentication, returns, payout methods, reports, notifications, and settings;
4. adds missing attachment arrays and current settings;
5. writes the migrated version through the normal store effect.

If the browser cannot create the backup, BinSight locks persistence, leaves the original key untouched, and shows a recovery warning.

Do not rename or clear `binsight-demo-v1` in feature work. Do not call `localStorage.clear()`.

## Admin storage

Use a separate key for admin fixtures and preferences. Start with `binsight-admin-v1`. Admin code must not write an object to `binsight-demo-v1`.

Shared data should pass through typed selectors or adapters. Do not let two stores write the same record. Until a backend exists, citizen reports remain citizen-owned records; the admin area may read a mapped copy for display.

The phase 1 Streamlit portal does not access browser `localStorage`. Durable route proposals and idempotent mock dispatches use the separate transactional store `admin-portal/data/routing_plans.sqlite3` (schema 1). Immutable decision snapshots and source-event references are stored with each plan. The lifecycle is draft, accepted, completed or cancelled; a new proposal never rewrites an accepted record.

Per-channel last-good observations use `admin-portal/data/last_valid_sensor_readings.json` (schema 2.0). Fill and weight are retained independently with original observation time, event ID, calibration version and source mode. The complete read/merge/write operation uses one cross-process lock and a unique temporary file followed by atomic replacement, preventing the UI and controlled runner from silently overwriting each other's channels. Corrupt, locked or unknown-version files are reported and preserved rather than reset. A stale lock may be removed only after verifying its recorded PID is no longer running. The former `mock_truck_dispatches.jsonl` remains a read-only legacy audit and is not rewritten by the new workflow.

Fill telemetry and recycling recognition/session data are separate domains. Route plans may reference accepted `fill_observation` events from either physical bin type while preserving `bin_type` and `waste_stream`. Do not reuse IDs across purposes, store a recycling class as fill, copy images/results into route snapshots, use fill to decide acceptance, or combine incompatible waste streams in one trip.

All admin runtime databases, histories, control files, Python environments, logs and UI QA captures are ignored by Git and contain prototype data only.

Do not place real resident identities, addresses, vehicle credentials, or operational telemetry in either local file. A production implementation needs authenticated storage, retention limits, access control, encryption, and an auditable deletion policy.

## Schema changes

Follow this sequence for every persisted change:

1. Add the new type without removing the old field.
2. Increment the internal schema version.
3. Accept every version still present in checked-out releases.
4. Create a backup before the first migration write.
5. Map each old field explicitly.
6. Add a migration test with representative old data.
7. Verify login state and record counts before and after migration.
8. Remove an old field only in a later, documented release.

Reject unknown future schema versions. Resetting unknown data to defaults without warning can hide a downgrade error; new admin code should surface a recovery message and leave the stored JSON untouched.

The sensor SQLite migration retains the original schema-1.0 table as `sensor_readings_legacy_v1`, copies it into reboot-safe event identities marked `LEGACY-UNSCOPED`, and does not claim that legacy rows contain a real boot identifier.

## Report images

The report form accepts JPG, PNG, and WEBP files. The browser converts each selected image to a compressed data URL before saving the report. Each stored image must remain below 900,000 characters, and each report may contain three images.

The report detail page reads the saved data URL, so attachments remain visible after submission and reload. Legacy reports with filenames but no image data continue to show filename chips.

Do not move full image data into an admin KPI record. Refer to the waste-report ID instead.

## Git merge safety

Before merging collaborator work:

```powershell
git fetch origin
git status --short
git diff main...HEAD -- web/src/model.ts web/src/store.tsx
```

Inspect every citizen model or store change. The contributor must explain each one in the pull request. Keep unrelated generated documents and local notes out of the commit.

After resolving conflicts, run:

```powershell
cd web
pnpm lint
pnpm test:run
pnpm test:e2e
pnpm build
```

Do not resolve a model or store conflict by choosing one complete side. Merge fields and migration branches deliberately, then rerun the old-data migration test.

## Recovery

When a migration fails during development:

1. Stop writing to the affected storage key.
2. Copy the current key and available `binsight-demo-backup-v*` value before editing code.
3. Record the schema version and failing commit.
4. fix the migration against a copy of the data;
5. restore only after the fixed migration passes its test.

Never paste real identity, payment, or resident data into fixtures. BinSight uses fictional demonstration records only.

For routing recovery, stop the local planner, copy `routing_plans.sqlite3` together with its `-wal` and `-shm` files when present, record the schema version, and test repair against the copy. Do not delete the database to clear an unknown version. The planner runner can be stopped with `python -m binsight.cli planner-stop` and inspected with `planner-status`.
