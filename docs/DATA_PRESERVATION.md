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

PR1 uses a separate server-side planning store in its Streamlit application. Preserve that store, its schema migrations, route history and audit records. If admin browser preferences are added later, give them their own key such as `binsight-admin-v1`. Admin code must not write an object to `binsight-demo-v1`.

Shared data must pass through an explicit versioned API/adapter with one authoritative writer per domain. The separate Streamlit app cannot read citizen browser storage. Until a report API and owner-approved scope exist, citizen reports stay local; any admin example must be a separate synthetic fixture labelled as such. Do not silently import or upload existing images or overwrite a source record with an admin copy.

Keep hardware records separated by event purpose. Fill observations from both bin types belong to the telemetry and routing store. Recycling classification and session events belong to the return-station domain. Preserve `binId`, `binType` and event kind at storage and API boundaries; reject recognition events from routing and never migrate one record type into another to satisfy a route or KPI schema.

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
