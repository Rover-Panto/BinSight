# Integration Baseline: 28 August 2026

This record supports [the integration test plan](INTEGRATION_TEST_PLAN.md). No contributor PR was merged for this baseline. The staging branch starts at foundation `68f1283`, descended from main `9fca9d4`. Exact captured PR revisions live in `integration/candidate.json`; new pushes require a new review.

## Captured Contributor Revisions

| PR | Head | Inspection scope |
| --- | --- | --- |
| PR1 | `d276313467fe30c81218c980e626da6624c2d78a` | Reviewed the material-aware configuration/registry/dispatch delta from `c256bd4`. Did not rerun the expanded routing suite or regenerate simulation results on this head. |
| PR2 | `e7055764b57663a9d916602d7b0e89f54df2eaa4` | Unchanged from the earlier review; [hardware findings](CLAUDE_HARDWARE_ROUTING_HANDOFF.md) still apply to this revision. |
| PR3 | `819ff37b41a78208ba1624ad0060f8bec0358346` | Unchanged from the earlier review; retain the completed scaffolding fixes and address remaining [vision/transport findings](PR3_RECYCLING_VISION_REVIEW.md). |
| PR4 | `038e262044a1bc29cee08d189c6fe4f78c970caf` | Reviewed provider/feature/training/package changes through `b7d6490`; the later commit only changes README/demo and removes old training/inference helpers. The provider and probe results below are unchanged at `038e262`. |

These revisions are candidates, not approvals. The earlier PR1 97-test pass and PR3 three-test pass apply to their earlier recorded heads, not a combined system.

## New PR4 Progress and Remaining Blockers

Completed work observed: a fill-only feature list, elapsed-time rate handling, cold-start/duplicate handling, calendar-based train/validation/test splits, validation-based model selection, manifest/checksum export, a multi-bin snapshot entry point, and removal of the old quick trainer. Four feature-builder regressions passed. The committed artifact checksum matches the manifest. These checks do not establish held-out accuracy, calibration or safe loading.

Remaining integration blockers:

1. **Hours returned as growth.** `ForecastProvider.predict()` returns the model's hours-to-threshold values as PR1's mean growth. A constant 12-hour test double produced mean growth `[12, 12]` and upper growth `[16, 16]`. These are different units and cannot replace PR1's forecast outputs. Supply actual horizon growth/bounds or return an unsupported-capability state so PR1 uses its declared non-ML mode.
2. **Uncalibrated probabilities.** Compatibility methods compute `1 - hours / horizon`, while snapshot horizons use a hand-selected normal spread around a linear rate. A constant 12-hour result becomes probability `0.75` at 48 hours. Neither calculation establishes a calibrated probability. Remove the calibration claim; validate a probability model or leave probabilities unavailable. Do not let the two caller paths disagree about forecast meaning.
3. **Target relabelling.** The manifest/labels still target 90%, but `target_threshold_pct=100` returns `available`, target 100 and the unchanged 12-hour estimate. Reject target mismatch before prediction. Retrain/relabel/evaluate for the agreed threshold; a function argument does not change the model's target.
4. **Historical leakage and stale availability.** Snapshot filtering checks observation time only. A reading received after the decision cutoff still becomes the latest fill; a January decision accepts a model whose manifest training period ends in March; old January history remains `available` for an August decision. Require acquisition AND ingestion cutoffs, machine-readable training availability/cutoffs, freshness states and strict provenance. Review target-event leakage across calendar split boundaries as well.
5. **Artifact validation order and installation.** `joblib.load()` runs before checksum validation, and a missing manifest is allowed. A mocked loader was called once before an intentionally bad hash raised. Require a trusted manifest, verify hashes/features/target/dependencies before deserialisation, and test missing/tampered bundles. A checksum is not proof that the artifact is trustworthy. The package finder includes `src*`/`tests*`, while the README promises `from ml import ForecastProvider`; verify a built wheel outside repository cwd with an explicitly supplied approved model directory. Do not rely on repo-path imports or undeclared model files.

Probe command, using an isolated source snapshot and the existing review environment:

```powershell
python integration/probes/review_pr4.py --ml-root PATH_TO_REVIEWED_PR4/ml
```

The probe imports reviewed source and substitutes a constant model; it never deserialises the contributor's artifact or measures model quality. Its output is diagnostic evidence, not a passing integration test. The feature tests used `pytest .../ml/tests/test_pipeline.py -k feature_builder -q`: **4 passed, 11 deselected**. The review environment used Python 3.13, pandas 2.3.3 and NumPy 2.3.5. Production compatibility must use the agreed package/bundle dependency versions.

## PR1 Coordination After the New Delta

The new commit adds material-aware capacities/demand, stream-aware display/routing changes, registry metadata, tests and regenerated synthetic artifacts. Do not discard these changes while integrating PR4. The earlier service-state freshness, future-trained state and lookalike-loopback URL findings live in unchanged files and still need fixes.

The physical profile now names `plastic_cups` and `glass_bottles`; the return policy also accepts `metal`. Treat these as simulation assumptions until the owner confirms D3 and the team publishes the physical station/bin mapping. Do not narrow citizen acceptance to match a routing scenario or claim the simulator's 4,500-litre capacities are measured demo-bin capacities. Preserve separate bin type, collection stream, material assumptions and physical calibration.

PR1 and PR4 should integrate both live-telemetry and simulation consumers before PR1 deletes superseded forecast code. Keep PR1's read/validation/cache logic, route lifecycle and a deterministic fill/health fallback. Freeze a reviewed provider version for the combined test; do not import a moving branch during a run.

## Foundation Verification

Local checks on the integration preparation tree:

| Check | Result |
| --- | --- |
| `python -m unittest discover -s server/tests -v` | 16 passed |
| `python -m unittest discover -s integration/tests -v` | 12 passed, including ten policy fixture scenarios in subtests |
| `python -m integration.check_readiness --require-ready` | Expected exit 1: candidates unstaged, reviews/owner decisions and integration gates outstanding |
| `pnpm lint` in `web/` | Passed |
| Initial `pnpm test:run` | Thread-worker startup timed out on Windows; 3 tests completed, so this was not a successful run |
| `pnpm test:run --pool=forks` | 7 passed; the test configuration now uses one process-based worker |
| Final `pnpm test:run` after configuration change | 7 passed with the documented command |
| `pnpm build` | Passed |
| `pnpm test:e2e` | 7 passed, 1 intentional duplicate visual-project skip; desktop/mobile journeys and three-size visual captures |

No browser layout changes were made. Browser tests covered return/payout, report submission and image persistence after reload. Reviewed the desktop report attachment, tablet home and mobile return captures. The visual test captures desktop/tablet/mobile through its desktop project; its separate mobile project deliberately skips that same capture test.

Both jobs in [foundation CI run 33165774817](https://github.com/Rover-Panto/BinSight/actions/runs/33165774817) passed at commit `f682befddc4d371c229cbea61057638e773e666e`: server policy/fixtures and citizen lint/unit/build/browser regression. GitHub completed the run on 28 August 2026 at 11:06 UTC. G01 remains partial in the candidate ledger because the coordinator must repeat regression checks after staging the contributor code.

This success is not evidence for the missing HTTP/session backend, the unmerged routing/provider connection or physical hardware. Do not claim those gates passed from this table.

## Contributor Handoffs Published

Each comment names the component owner, completed work to retain, required changes, dependencies, test gates and the exact-head evidence requested before staging:

- [PR1: routing, admin and PR4 consumer integration](https://github.com/Rover-Panto/BinSight/pull/1#issuecomment-5451752713), addressed to the PR author and latest contributor.
- [PR2: three-channel sensing, ingestion and shared C3 shell](https://github.com/Rover-Panto/BinSight/pull/2#issuecomment-5451753256).
- [PR3: Grove model, recognition module and main-owned return connection](https://github.com/Rover-Panto/BinSight/pull/3#issuecomment-5451753726).
- [PR4: forecast-provider corrections and route integration](https://github.com/Rover-Panto/BinSight/pull/4#issuecomment-5451754205).

Contributors should reply with their updated commit SHA and test evidence. The coordinator then reviews that revision before including it in a combined candidate. These comments do not approve a merge or change the PR base branches.

## Owner Follow-up and Main Work

After the foundation handoff, the owner confirmed D1: a physical Teensy/ESP/Grove demo with the laptop as server, using the existing local setup. D2 now includes minimal ticket-closing controls in PR1, with report/photo/status APIs and durable history owned by main. D3 remains pending: the owner expects one Grove per recycling bin in a future installation and asked for split-bin ideas. See [the layout comparison](RECYCLING_STATION_OPTIONS.md). No material-to-compartment map or second vision stack has been approved.

The candidate now declares `demo_mode: physical`. The readiness command requires H01/H02 by default; `--software-only` is a labelled preflight, not physical demo approval. Follow-up verification on this decision-update tree: integration tests **17 passed**, server-policy tests **16 passed**, and `git diff --check` passed. Both default and software-only `--require-ready` checks correctly returned exit 1 for the outstanding candidate work; the default included H01/H02. These results supplement, not replace, the earlier foundation evidence. Frontend files and stored records were not changed in this follow-up.

Both jobs in [follow-up CI run 33167295593](https://github.com/Rover-Panto/BinSight/actions/runs/33167295593) passed at `6fbf13373244607fe1f3a76bfe913d9f7d25f7b0`: server policy/fixtures and citizen lint/unit/build/browser regression. Hardware and cross-service gates remain outstanding.

The owner-decision update was posted to all four PRs with their responsibilities and links to the revised plan:

- [PR1: minimal ticket controls, main-owned report backend and pending bin mapping](https://github.com/Rover-Panto/BinSight/pull/1#issuecomment-5451975656).
- [PR2: physical demo evidence, three fill channels and the shared gateway](https://github.com/Rover-Panto/BinSight/pull/2#issuecomment-5451976409).
- [PR3: deployed Grove evidence, configurable station identity and pending mechanics](https://github.com/Rover-Panto/BinSight/pull/3#issuecomment-5451979788).
- [PR4: physical-data integration evidence with forecast ownership unchanged](https://github.com/Rover-Panto/BinSight/pull/4#issuecomment-5451980454).

Remote PR1-4 heads still matched the captured revisions when publishing this decision update. No PR was merged or marked ready. Main integration still owns the return API, durable decision/credit storage, station/session authentication, shared report/attachment/status API, citizen client and migrations, safe runtime controls and combined gateway assembly. No camera stream, real payment service or public deployment was added.
