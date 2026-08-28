# Integration Test Branch

Start with [the integration test plan](../docs/INTEGRATION_TEST_PLAN.md).

This branch contains the existing citizen prototype and server policy, a candidate ledger, shared example fixtures and foundation regression checks. It does not initially merge PR1-4 or implement the missing return API.

- `candidate.json`: captured PR revisions, owner decisions, demo mode and gate status; update after review, not simply after a push.
- `fixtures/`: synthetic examples for contributor tests, not deployed IDs or complete wire schemas.
- `tests/`: executable fixture/policy and readiness-tool regressions. These do not test HTTP delivery, durable credit or routing.
- `probes/review_pr4.py`: reproducible diagnostics against a reviewed PR4 source tree using a test-double model; no artifact is deserialised. Requires that source tree's Python data libraries and is not part of foundation CI.
- `check_readiness.py`: displays outstanding gates and verifies candidate commits are ancestors of the checked-out branch.

D3 confirms one physical recycling technology-demonstration bin. The existing `three_bins.json` fixture remains a three-bin synthetic scenario for producer/consumer coverage, not a physical inventory. Do not delete its IDs/history or duplicate live readings to make the physical demo look like three measured bins.

```powershell
python -m unittest discover -s integration/tests -v
python -m integration.check_readiness
python -m integration.check_readiness --require-ready
```

The last command deliberately exits unsuccessfully until the candidate is ready. The owner confirmed `demo_mode: physical`, so it now requires both software and hardware gates by default. Use `--software-only` for a labelled preflight, or `--hardware` to require hardware gates explicitly. A software-only pass does not establish physical demo readiness. The ledger cannot grant review or merge approval.
