# Integration Test Branch

Start with [the integration test plan](../docs/INTEGRATION_TEST_PLAN.md).

This branch contains the existing citizen prototype and server policy, a candidate ledger, shared example fixtures and foundation regression checks. It does not initially merge PR1-4 or implement the missing return API.

- `candidate.json`: captured PR revisions and gate status; update after review, not simply after a push.
- `fixtures/`: synthetic examples for contributor tests, not deployed IDs or complete wire schemas.
- `tests/`: executable fixture/policy and readiness-tool regressions. These do not test HTTP delivery, durable credit or routing.
- `probes/review_pr4.py`: reproducible diagnostics against a reviewed PR4 source tree using a test-double model; no artifact is deserialised. Requires that source tree's Python data libraries and is not part of foundation CI.
- `check_readiness.py`: displays outstanding gates and verifies candidate commits are ancestors of the checked-out branch.

```powershell
python -m unittest discover -s integration/tests -v
python -m integration.check_readiness
python -m integration.check_readiness --require-ready
```

The last command deliberately exits unsuccessfully until the software candidate is ready. Use `--hardware` to include physical gates. The ledger cannot grant review or merge approval.
