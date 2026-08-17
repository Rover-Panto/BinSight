# BinSight Web Prototype

Responsive React and TypeScript mock frontend for the BinSight Malaysian citizen waste-services and beverage-return hub.

## Demonstration access

- National ID: any fictional value with at least six characters
- Mock OTP: `123456`
- Return value: `RM0.20` per accepted item
- Payouts, reports, contacts and service data are simulated

The entered National ID and OTP are never written to local storage. A generated demonstration user ID and login state are persisted so the user remains signed in.

Waste-report images are compressed in the browser and saved with the local demonstration report. They remain visible after submission and reload. Use fictional images only.

## Run locally

From the project folder, double-click `Start-BinSight.cmd`. It starts the localhost server and opens the site in a browser. Dependencies must already be installed.

For command-line development:

```powershell
pnpm install
pnpm dev
```

The `Account` page includes a `Stop local server` control for the development server. After stopping it, use `Start-BinSight.cmd` to start it again; a browser cannot restart a process that has already exited.

## Verification

```powershell
pnpm lint
pnpm test:run
pnpm test:e2e
pnpm build
```

Playwright covers the full login-to-payout and issue-reporting journeys at desktop and mobile sizes. The visual suite also checks the 1440x900, 768x1024 and 390x844 layouts for horizontal overflow.

## Prototype controls

Open `Account` and expand `Demo controls` to choose the next station-detected item, force an accepted or rejected result, and simulate one failed payment. `Reset demo data` restores the original sessions, reports, methods, notifications and settings.

## Stored data

The citizen store uses `binsight-demo-v1` with internal schema version 3. Startup migrations preserve older records and create a pre-migration backup for version 1 or 2 data. See `../docs/DATA_PRESERVATION.md` before changing the schema or adding the admin store.
