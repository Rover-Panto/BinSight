# BinSight Web Prototype

Responsive React and TypeScript mock frontend for the BinSight Malaysian citizen waste-services and beverage-return hub.

## Demonstration access

- National ID: any fictional value with at least six characters
- Mock OTP: `123456`
- Return value: `RM0.20` per accepted item
- Payouts, reports, contacts and service data are simulated

The entered National ID and OTP are never written to local storage. A generated demonstration user ID and login state are persisted so the user remains signed in.

## Run locally

```powershell
pnpm install
pnpm dev
```

## Verification

```powershell
pnpm lint
pnpm test:run
pnpm test:e2e
pnpm build
```

Playwright covers the full login-to-payout and issue-reporting journeys at desktop and mobile sizes. The visual suite also checks the 1440×900, 768×1024 and 390×844 layouts for horizontal overflow.

## Prototype controls

Open `Account` and expand `Demo controls` to force accepted or rejected return items and simulate one failed payment. `Reset demo data` restores the original sessions, reports, methods, notifications and settings.
