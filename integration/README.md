# Integration Test Branch

Start with [the integration test plan](../docs/INTEGRATION_TEST_PLAN.md).

This branch contains the existing citizen prototype, a simulation-only return API, a candidate ledger, shared example fixtures and foundation regression checks. It does not contain PR1-4. The citizen UI still uses its mock path; the return API is not a physical deployment.

- `candidate.json`: captured PR revisions, owner decisions, demo mode and gate status; update after review, not simply after a push.
- `fixtures/`: synthetic examples for contributor tests, not deployed IDs or complete wire schemas.
- `tests/`: executable fixture/policy and readiness-tool regressions. These do not test HTTP delivery, durable credit or routing.
- `probes/review_pr4.py`: reproducible diagnostics against a reviewed PR4 source tree using a test-double model; no artifact is deserialised. Requires that source tree's Python data libraries and is not part of foundation CI.
- `probes/review_pr4_update.py`: 29 August follow-up checks for the packaged PR4 provider; mocks the loader for manifest tests and uses the reviewed model for inference checks. Requires the manifest's dependency versions. Use `--pr4-root PATH_TO_PR4 --output RESULTS.json`; exit 1 means unresolved checks. See [the review](../docs/PR4_REVIEW_2026-08-29.md).
- `return_preflight.py`: temporary real-HTTP simulation test for session, inference and credit persistence; optionally imports PR3's serializer with `--vision-root PATH_TO_PR3`. It stops its own server and does not test physical hardware.
- `check_readiness.py`: displays outstanding gates and verifies candidate commits are ancestors of the checked-out branch.

D3 confirms one physical recycling technology-demonstration bin. The existing `three_bins.json` fixture remains a three-bin synthetic scenario for producer/consumer coverage, not a physical inventory. Do not delete its IDs/history or duplicate live readings to make the physical demo look like three measured bins.

```powershell
python -m unittest discover -s integration/tests -v
python -m integration.check_readiness
python -m integration.check_readiness --require-ready
```

The last command deliberately exits unsuccessfully until the candidate is ready. The owner confirmed `demo_mode: physical`, so it now requires both software and hardware gates by default. Use `--software-only` for a labelled preflight, or `--hardware` to require hardware gates explicitly. A software-only pass does not establish physical demo readiness. The ledger cannot grant review or merge approval.
