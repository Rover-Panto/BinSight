# Latest PR Review and Integration Record

PR3 and PR4 were re-reviewed 29 August 2026 on `codex/integration-test`. A newer contributor push does not inherit approval from these results.

| PR | Reviewed head | Component tests | Integration status |
| --- | --- | --- | --- |
| #1 routing/admin | `8b34c9651b4b2ef4cef7abe6f45bb54c4017a3df` | 111 passed | Changes required; not staged |
| #2 fill/gateway | `84952d2b59f3636d006cbe7518f895face0774a4` | No host/firmware test suite supplied | Changes required; not staged |
| #3 vision | `dce112fe10e68089caa6e2e661bc031aa3f9a977` | 6 passed; compile passed; PR3 serializer passed real-HTTP server preflight | Focused merge-preparation changes requested; not staged |
| #4 forecast | `28509cc4e90b2c1e2c3c3c2e026244e5a6e86dee` | 32 passed again after merge; broader checks: 12 passed / 17 failed | Owner merged into main at `3297f43`; included on this branch |

Passing component tests do not establish combined or physical readiness. PR4 is now on main and this branch; PR1, PR2 and PR3 remain separate. The main-owned return API remains simulation-only on this branch. PR2 has a newer unreviewed push; its findings below apply to `84952d2`, not that newer head.

## Demo Review Bar

Owner clarification, 29 August: the target is a working physical demonstration, not production readiness. PR4 can enter integration testing with the reviewed bundle and tested dependencies. Broad model-loader hardening and retraining automation can wait. The integration adapter still needs bad-reading handling and consistent timestamps, followed by a forecast-to-route smoke test. The previous failures remain recorded; they are not all demo blockers. See [PR4's demo acceptance conditions](PR4_REVIEW_2026-08-29.md#demo-acceptance). Other components still need their own demo-scoped review; this does not approve every PR.

## Outstanding Findings

### P1: PR2's new gateway does not target the selected ESP32-C3

`BinSight_ESP32_Gateway.ino` uses `Serial2` and GPIO16/17 for the Teensy link. Espressif's C3 documentation specifies UART0 and UART1, while Arduino ESP32 declares `Serial2` only when `SOC_UART_NUM > 2`. The selected C3 target therefore needs a board-specific `HardwareSerial(1)`/`Serial1` assignment, reviewed C3 pin choices, and a compile job for the exact board/core version. The sketch currently describes a generic separate ESP32 board, has no Grove/SSCMA module, and cannot yet be the owner-confirmed single shared C3.

References: [ESP32-C3 datasheet](https://documentation.espressif.com/esp32-c3_datasheet_en.html), [Arduino ESP32 HardwareSerial declaration](https://github.com/espressif/arduino-esp32/blob/master/cores/esp32/HardwareSerial.h), PR2 `hardware_pipeline/firmware/BinSight_ESP32_Gateway/BinSight_ESP32_Gateway.ino:70`.

### P1: PR2 can still lose fill records after a server failure

`serial_bridge.post_reading()` prints HTTP 5xx without raising or returning failure. `flush_pending()` increments `sent` and removes the queue entry. The independent probe sent HTTP 503 and observed `queue_preserved_after_http_503: false`. The new ESP sketch also drops fresh frames on HTTP >=400, but its queue-flush path retries those same statuses. Fresh and queued deliveries therefore use inconsistent failure handling. Neither path has bounded nonblocking retries, durable event identity/receipt timestamps or the accepted fill contract.

The new C3 loop can block for ten seconds reconnecting, then spend up to five seconds per queued POST before reading Teensy UART. Its 20-entry RAM queue silently drops the oldest record and disappears on reset. Task 3 also sends every packet through USB and ESP, so the backend can receive duplicates. PR2 must fix the laptop queue first, then implement a bounded C3 state machine with stable event IDs, fair queues, overflow counters, explicit 4xx/dead-letter and 5xx/retry treatment, and no synchronous backlog drain ahead of UART/Grove work.

The Teensy waits only 500 ms for an uncorrelated `ACK:<status>`, while the gateway can wait five seconds for HTTP. A delayed reply can be consumed as acknowledgement of a different packet. Include the event ID in acknowledgements and distinguish queued receipt from durable server acceptance.

References: PR2 `hardware_pipeline/tools/serial_bridge.py:68`, `:109`, `:110`; gateway sketch `:117`, `:139`, `:165`; retained probe `integration/probes/review_latest.py`.

### PR4: Defer loader hardening; handle bad readings at integration

At `28509cc`, the dependency check permits adjacent major versions, skips missing versions and ignores minor/patch differences. Unknown schemas, missing or unsupported target definitions, non-runtime feature lists and invalid availability provenance still reach the loader. These remain hardening findings, but do not block the fixed demo: use the reviewed artifact, its explicit path and the tested environment; do not accept arbitrary model uploads or swap dependencies during the run.

The quality fix only catches all-zero histories. One valid 20% reading followed by a flagged 95% reading returns `available` with 0.66 hours to the service threshold. Duplicate copies of one reading also return `available`; unknown fill can leave NaN in a result. The PR1 integration adapter must select distinct, usable observations, enforce freshness from the last-good timestamp and return JSON-safe degraded records before the route demo. We can implement that boundary without requiring a broad PR4 rewrite.

### PR4: Normalize timestamps and freeze the demo model

Only temporary filtering Series are converted to UTC. Equivalent observations written in UTC and Malaysia time produce 5.05 versus 13.04 hours; mixed offsets return `model_error`. Normalize the input timestamps in the PR1 adapter before PR4 sorts and builds features, using one documented model timezone.

The new default bundle now installs and loads outside the checkout, but training writes `ml/models` while the default provider and wheel use `ml/binsight_ml/models`. For this demo, load the reviewed bundle through an explicit path and do not retrain during the run. Automated promotion is deferred.

Resolved at this head: missing packaged bundle, missing bin ID on unsupported thresholds, pre-selection historical availability, decision-cutoff timezone equivalence, all-zero confidence status and stale single-reading precedence. See [the dated PR4 review](PR4_REVIEW_2026-08-29.md) for exact line references, fixes, environment and retained evidence.

PR4 still supports only expected hours to a 90% service threshold, not calibrated probabilities. PR1's separate forecaster and missing capability-aware adapter remain integration work. Do not reinterpret hours as growth or delete the existing predictor before live/replay adapter tests pass.

### P2: PR1's optional post-optimizer can invalidate route duration

The latest PR1 delta correctly recomputes routes and keeps its new structural optimizer disabled by default. It only protects arrival times for mandatory bins, however, and does not re-check the route-duration constraint. A retained two-bin probe started with a feasible three-second route under a ten-second limit; post-optimization shortened distance but returned a 104-second route. Keep the flag off. Before enabling it, reject any candidate that violates duration, capacity, destination/unload order, protected deadlines or value constraints, and add asymmetric-matrix regression tests for each invariant.

PR1 also still hard-codes four material bins per simulated service site while declaring three physical controller bins. Preserve the district experiment as a simulation profile; add a separate physical registry for the confirmed one general-waste and one recycling demonstrator rather than calling the four-stream district a physical layout.

References: PR1 `admin-portal/binsight/routing.py:33`, `:571`; `config.json` has `route_post_optimization_enabled: false`; probe retained in `integration/probes/review_latest.py`.

### P2: PR3 has a laptop artifact, not the Grove integration

PR3's strict metadata serializer now interoperates with the main-owned simulation API and its six tests pass. The branch adds a checksum-recorded `.pt` artifact, but labels it laptop-only. Dataset source/licence, training provenance and held-out evidence remain incomplete. The branch still has no Grove-compatible Vela artifact, SSCMA reader, shared-gateway recognition module, deployment class-map check or removal signal. Its relay header still says dedicated C3 even though PR3 will use PR2's physical relay. Keep the serializer and tests, align the wording with the shared gateway, and document or remove the committed artifact before merge.

Broad `plastic`, `metal` and `glass` labels do not prove beverage-container eligibility. Until the dataset/evaluation establishes that narrower meaning, describe the demo as material recognition and accept/reject policy, not verified beverage return. Grove export, shared-firmware integration and physical tests remain pre-demo gates; they do not block merging a clearly labelled, isolated software scaffold after the focused fixes.

## Implemented Integration Slice

`server/` now provides loopback-only, simulation-only return sessions, inspections, authenticated PR3 metadata ingestion, server-timed confidence/stability decisions, SQLite persistence, one 20-sen credit per accepted inspection, event/action idempotency, restart interruption, device-boot tracking, removal re-arm and verified backup/restore. It rejects physical mode and exposes no actuator or payment endpoint.

`python -m integration.return_preflight --vision-root PATH_TO_PR3` imported PR3's real serializer, sent four samples over a real temporary HTTP server, accepted one metal item, rejected paper, deduplicated the accepted retry, stored four events and one 20-sen credit, then stopped its own process. Server tests cover concurrent retries, wrong owners/stations/boots, stale time, strict types, old schemas and live backup. Citizen lint/unit/build/browser tests remain green; uploaded report images still survive reload.

This is partial G06/G07/G09/G10/G12 evidence. QR/login/browser transport, simulated payout linkage, shared report workflow, combined C3 firmware and physical gates remain open. `main` and all existing browser records/photos were unchanged.

## Next Integration Order

1. PR2 fixes loss semantics and replaces the generic blocking sketch with one compile-tested shared C3 shell. Keep fill UART and recognition I2C in independent bounded tasks/queues.
2. PR3 resolves the laptop artifact provenance, updates the dedicated-relay wording, and reports its six-test result. The current serializer already passes the main return preflight. Grove export, the SSCMA adapter and the exact combined C3 build remain required before the physical demo.
3. PR4 staging is complete through main merge `3297f43`. Next add usable-reading guards and timestamp normalization in the PR1 adapter, then run a forecast-to-route smoke test before deleting PR1's duplicate predictor. Defer broad loader hardening and retraining automation.
4. PR1 keeps the post-optimizer disabled, adds a physical demo registry and consumes the installed PR4 provider with a named non-ML fallback.
5. Main adds a feature-flagged citizen client/QR handoff and versioned return-data migration, then the report API and PR1 ticket controls.
6. Run G01-G13 on the exact staged heads, then H01-H02 on the bench. Merge focused PRs to `main` only after owner approval.

## Verification Commands

```powershell
python -m unittest discover -s server/tests -v
python -m unittest discover -s integration/tests -v
python -m integration.return_preflight
python integration/probes/review_latest.py --pr1-root PATH_TO_PR1 --pr2-root PATH_TO_PR2 --pr4-root PATH_TO_PR4
python integration/probes/review_pr4_update.py --pr4-root PATH_TO_PR4 --output pr4-review-results.json
```

The older `review_latest.py` is historical evidence against its recorded heads. `review_pr4_update.py` retains the broader PR4 diagnostics; its nonzero exit records unresolved checks, including deferred hardening. Do not treat all of those checks as demo staging requirements or relabel them as passed.

From `web/`: `pnpm lint`, `pnpm test:run`, `pnpm build`, and `pnpm test:e2e`. From PR1: its full `pytest` suite. From PR3: `python -m unittest recycling_vision.test_relay -v`. From PR4: `pytest ml/tests -q`.
