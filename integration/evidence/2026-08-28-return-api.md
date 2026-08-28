# Return API Integration Evidence

Date: 28 August 2026. Branch: `codex/integration-test`. Main remained at `9fca9d47afb805f40034da970bb47d791ba8f0b4`. No PR1-4 merge was performed.

## Reviewed Components

- PR1: `8b34c9651b4b2ef4cef7abe6f45bb54c4017a3df`.
- PR2: `84952d2b59f3636d006cbe7518f895face0774a4`.
- PR3: `819ff37b41a78208ba1624ad0060f8bec0358346`.
- PR4: `1143545010d89b94abfa9655a5c27a318a7145b0`.

Use [the review](../../docs/INTEGRATION_REVIEW_LATEST.md) for findings and contributor fixes. These SHAs are reviewed with changes required, not approved or staged.

## Local Results

| Check | Result | Scope |
| --- | --- | --- |
| PR1 full pytest suite | 111 passed, 3 dependency deprecation warnings | Latest routing/admin head in an isolated worktree |
| PR3 unittest suite | 3 passed | Metadata serializer only |
| PR4 pytest suite | 27 passed | Contributor component tests, not independent accuracy validation |
| Main server tests | 42 passed | API, policy, persistence, concurrency, restart, strict input and backup/restore |
| Integration foundation | 17 passed | Fixtures and fail-closed readiness ledger |
| Citizen lint | Passed | No citizen source changes |
| Citizen unit tests | 7 passed | Existing mock flow |
| Citizen production build | Passed | Existing frontend |
| Citizen browser tests | 7 passed, 1 intentionally skipped mobile visual-only case | Desktop/mobile returns, reports and retained uploaded photos |
| Real HTTP preflight with PR3 serializer | Passed | Temporary server/database, simulated metadata, no camera/hardware |
| Readiness with required physical gates | Expected exit 1, NOT READY | Missing/still-failing gates retained |

The server tests use temporary databases and fictional credentials. No existing browser storage, report images, payment methods, route history or telemetry store was read or migrated. The preflight uses an unused loopback port and stops its own server. It leaves no recurring service running.

Environment: Windows, Python 3.13. Main dependencies are pinned in `server/requirements.txt`. The isolated PR environment used pandas 2.3.3, NumPy 2.3.5, scikit-learn 1.9.0, XGBoost 3.4.1 and joblib 1.5.2. These do not all match PR4's manifest; that mismatch is a review finding, not a validated model runtime. PR4's contributor tests load the checked artifact. Independent boundary probes use a constant test double and do not deserialize it.

## HTTP Result

PR3's actual `InferenceMetadata.to_json()` supplied the requests. Three matching metal samples at exactly 0.70 produced one accepted inspection. Replaying the final sample returned a duplicate acknowledgement. After a device removal acknowledgement, a paper sample rejected. Finishing left four stored events, one credit row and `credit_cents: 20`.

Separate server tests verified a rejected item can be followed by another inspection only after device re-arm; a held item cannot start another inspection; concurrent retries cannot double-credit; a server/device restart interrupts pending work; and an injected failure after decision/credit writes rolls the transaction back before a successful retry. The live SQLite backup restored the same credit in an isolated copy and refused an overwrite.

This is software/transport evidence only. No Grove model inference, physical UART/I2C, camera, servo, QR/login handoff, browser API client, payout transfer, route dispatch or shared report workflow was tested by the HTTP preflight.

## Independent Counterexamples

```json
{
  "pr1_duration_limit_seconds": 10,
  "pr1_normal_duration_seconds": 3,
  "pr1_post_optimized_duration_seconds": 104,
  "pr1_post_optimizer_enabled_by_default": false,
  "pr2_queue_preserved_after_http_503": false,
  "pr4_unsupported_threshold_bin_id": null,
  "pr4_decision_during_model_selection": "available",
  "pr4_all_low_confidence_history": "available",
  "pr4_months_old_single_reading": "cold_start",
  "pr4_equivalent_utc_cutoff": "model_unavailable",
  "pr4_equivalent_malaysia_cutoff": "available",
  "pr4_load_calls_with_incompatible_dependencies": 1
}
```

PR4 built a wheel and imported from an installed target outside the repository using Python isolated mode. The default model bundle was absent there; callers need an explicit approved bundle path or a packaged bundle. No inference with an unverified installed artifact was attempted.

## Reproduce

```powershell
python -m pip install -r server/requirements.txt
python -m unittest discover -s server/tests -v
python -m unittest discover -s integration/tests -v
python -m integration.return_preflight --vision-root PATH_TO_PR3
python integration/probes/review_latest.py --pr1-root PATH_TO_PR1 --pr2-root PATH_TO_PR2 --pr4-root PATH_TO_PR4
python -m integration.check_readiness --require-ready
```

The boundary probes also require the isolated PR dependencies, including pandas, NumPy, OR-Tools, requests, pyserial and python-dotenv. They print counterexamples, not a passing acceptance suite. Keep all model, firmware and combined-system gates open until fixes are reviewed on new exact SHAs.
