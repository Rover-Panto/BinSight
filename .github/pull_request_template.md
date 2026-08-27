## Change

Describe the resident or operator problem and the implemented behavior.

## Data impact

- [ ] No persisted schema change
- [ ] Schema version incremented and migration added
- [ ] Existing citizen records preserved
- [ ] Admin data uses a separate storage key
- [ ] No real identity, payment, or resident data added

Storage keys or schema versions changed:

## Routing and KPI evidence

- [ ] Fixed and priority routes use the same comparison window and inputs
- [ ] KPI units, formulas, assumptions, and unavailable states are documented
- [ ] Simulation output is labelled as simulation
- [ ] Proposal targets are separate from calculated output

## Verification

- [ ] `pnpm lint`
- [ ] `pnpm test:run`
- [ ] `pnpm test:e2e`
- [ ] `pnpm build`
- [ ] Citizen login, return, payout, report, and attachment flows still pass
- [ ] Desktop, tablet, and mobile screenshots reviewed

## Documentation

- [ ] `docs/FRONTEND.md` updated for frontend changes
- [ ] `docs/PROJECT_STATE.md` updated
- [ ] `docs/DATA_PRESERVATION.md` updated when stored data changed
- [ ] Route map and KPI contracts updated when admin behavior changed
