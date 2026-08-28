# Latest PR Review and Integration Record

Reviewed 28 August 2026 on `codex/integration-test`. This supersedes the earlier head review for current integration decisions.

| PR | Reviewed head | Component tests | Integration status |
| --- | --- | --- | --- |
| #1 routing/admin | `8b34c9651b4b2ef4cef7abe6f45bb54c4017a3df` | 111 passed | Changes required; not staged |
| #2 fill/gateway | `84952d2b59f3636d006cbe7518f895face0774a4` | No host/firmware test suite supplied | Changes required; not staged |
| #3 vision | `819ff37b41a78208ba1624ad0060f8bec0358346` | 3 passed; PR3 serializer passed real-HTTP server preflight | Changes required; not staged |
| #4 forecast | `1143545010d89b94abfa9655a5c27a318a7145b0` | 27 passed | Changes required; not staged |

Passing component tests do not establish combined or physical readiness. PR1-4 remain outside this branch and `main`. The new main-owned return API is the only integration implementation added in this pass.

## Blocking Findings

### P1: PR2's new gateway does not target the selected ESP32-C3

`BinSight_ESP32_Gateway.ino` uses `Serial2` and GPIO16/17 for the Teensy link. Espressif's C3 documentation specifies UART0 and UART1, while Arduino ESP32 declares `Serial2` only when `SOC_UART_NUM > 2`. The selected C3 target therefore needs a board-specific `HardwareSerial(1)`/`Serial1` assignment, reviewed C3 pin choices, and a compile job for the exact board/core version. The sketch currently describes a generic separate ESP32 board, has no Grove/SSCMA module, and cannot yet be the owner-confirmed single shared C3.

References: [ESP32-C3 datasheet](https://documentation.espressif.com/esp32-c3_datasheet_en.html), [Arduino ESP32 HardwareSerial declaration](https://github.com/espressif/arduino-esp32/blob/master/cores/esp32/HardwareSerial.h), PR2 `hardware_pipeline/firmware/BinSight_ESP32_Gateway/BinSight_ESP32_Gateway.ino:70`.

### P1: PR2 can still lose fill records after a server failure

`serial_bridge.post_reading()` prints HTTP 5xx without raising or returning failure. `flush_pending()` increments `sent` and removes the queue entry. The independent probe sent HTTP 503 and observed `queue_preserved_after_http_503: false`. The new ESP sketch also drops fresh frames on HTTP >=400, but its queue-flush path retries those same statuses. Fresh and queued deliveries therefore use inconsistent failure handling. Neither path has bounded nonblocking retries, durable event identity/receipt timestamps or the accepted fill contract.

The new C3 loop can block for ten seconds reconnecting, then spend up to five seconds per queued POST before reading Teensy UART. Its 20-entry RAM queue silently drops the oldest record and disappears on reset. Task 3 also sends every packet through USB and ESP, so the backend can receive duplicates. PR2 must fix the laptop queue first, then implement a bounded C3 state machine with stable event IDs, fair queues, overflow counters, explicit 4xx/dead-letter and 5xx/retry treatment, and no synchronous backlog drain ahead of UART/Grove work.

The Teensy waits only 500 ms for an uncorrelated `ACK:<status>`, while the gateway can wait five seconds for HTTP. A delayed reply can be consumed as acknowledgement of a different packet. Include the event ID in acknowledgements and distinguish queued receipt from durable server acceptance.

References: PR2 `hardware_pipeline/tools/serial_bridge.py:68`, `:109`, `:110`; gateway sketch `:117`, `:139`, `:165`; retained probe `integration/probes/review_latest.py`.

### P1: PR4 can load a model before validating its runtime provenance

The manifest requires a `dependencies` object but the provider never checks those versions before `joblib.load`. The probe supplied an impossible NumPy version and observed one deserialization call. The wheel builds and imports outside the repository, but it does not package a default model bundle. The contributor must validate schema, target definition, runtime feature list, estimator allow-list, dependency versions and model availability time before deserialization, then either package the reviewed bundle or require an explicit bundle path.

The manifest says validation selected the model through 15 March and records `trained_at` on 28 August, but runtime availability uses a 28 February training-data cutoff. A 2 March historical decision returned `available`. Normalize all decision/training/receipt timestamps to UTC and reject decisions before the latest evidence used for model selection. The current `tz_localize(None)` logic returned different states for the same instant written as UTC and Malaysia time.

### P1: PR4 output cannot yet drive PR1 routes safely

Configured bins lose `bin_id` on unsupported-threshold responses. Low-confidence histories still return `available`; months-old single-reading histories remain `cold_start` instead of stale. PR4 supports hours to a 90% service threshold and explicitly has no calibrated horizon probabilities. PR1 still owns and runs a separate 1,903-line pattern forecaster. PR1 must not reinterpret hours as growth or invent probabilities. Add one adapter that returns one identified capability/state record per configured bin; route with current validated fill plus a named non-ML fallback when capability is missing. Retire the duplicate forecaster only after that adapter and historical replay tests pass.

References: PR4 `ml/src/serve.py:85`, `:121`, `:172`, `:358`, `:361`, `:505`; PR1 `admin-portal/binsight/pr2_forecasting.py:795`; retained probe output.

### P2: PR1's optional post-optimizer can invalidate route duration

The latest PR1 delta correctly recomputes routes and keeps its new structural optimizer disabled by default. It only protects arrival times for mandatory bins, however, and does not re-check the route-duration constraint. A retained two-bin probe started with a feasible three-second route under a ten-second limit; post-optimization shortened distance but returned a 104-second route. Keep the flag off. Before enabling it, reject any candidate that violates duration, capacity, destination/unload order, protected deadlines or value constraints, and add asymmetric-matrix regression tests for each invariant.

PR1 also still hard-codes four material bins per simulated service site while declaring three physical controller bins. Preserve the district experiment as a simulation profile; add a separate physical registry for the confirmed one general-waste and one recycling demonstrator rather than calling the four-stream district a physical layout.

References: PR1 `admin-portal/binsight/routing.py:33`, `:571`; `config.json` has `route_post_optimization_enabled: false`; probe retained in `integration/probes/review_latest.py`.

### P2: PR3 is a transport skeleton, not the Grove integration

PR3's metadata serializer now interoperates with the main-owned simulation API. The branch still contains no trained/exported artifact, held-out evidence, Grove/SSCMA reader, shared-C3 queue, model hash/class map deployment check or removal signal. Its relay header still says dedicated C3. Keep the serializer and tests, update the shared-board wording, and supply a pinned Grove artifact plus a C++ adapter that returns metadata without owning sessions, credits, fill parsing or network policy.

Broad `plastic`, `metal` and `glass` labels do not prove beverage-container eligibility. Until the dataset/evaluation establishes that narrower meaning, describe the demo as material recognition and accept/reject policy, not verified beverage return.

## Implemented Integration Slice

`server/` now provides loopback-only, simulation-only return sessions, inspections, authenticated PR3 metadata ingestion, server-timed confidence/stability decisions, SQLite persistence, one 20-sen credit per accepted inspection, event/action idempotency, restart interruption, device-boot tracking, removal re-arm and verified backup/restore. It rejects physical mode and exposes no actuator or payment endpoint.

`python -m integration.return_preflight --vision-root PATH_TO_PR3` imported PR3's real serializer, sent four samples over a real temporary HTTP server, accepted one metal item, rejected paper, deduplicated the accepted retry, stored four events and one 20-sen credit, then stopped its own process. Server tests cover concurrent retries, wrong owners/stations/boots, stale time, strict types, old schemas and live backup. Citizen lint/unit/build/browser tests remain green; uploaded report images still survive reload.

This is partial G06/G07/G09/G10/G12 evidence. QR/login/browser transport, simulated payout linkage, shared report workflow, combined C3 firmware and physical gates remain open. `main` and all existing browser records/photos were unchanged.

## Next Integration Order

1. PR2 fixes loss semantics and replaces the generic blocking sketch with one compile-tested shared C3 shell. Keep fill UART and recognition I2C in independent bounded tasks/queues.
2. PR3 supplies the reviewed Grove artifact and SSCMA adapter. Run the main return preflight with recorded metadata, then on the exact combined C3 build.
3. PR4 fixes pre-load provenance and point-in-time/output contracts. Add a PR1 adapter contract test before deleting PR1's duplicate predictor.
4. PR1 keeps the post-optimizer disabled, adds a physical demo registry and consumes the installed PR4 provider with a named non-ML fallback.
5. Main adds a feature-flagged citizen client/QR handoff and versioned return-data migration, then the report API and PR1 ticket controls.
6. Run G01-G13 on the exact staged heads, then H01-H02 on the bench. Merge focused PRs to `main` only after owner approval.

## Verification Commands

```powershell
python -m unittest discover -s server/tests -v
python -m unittest discover -s integration/tests -v
python -m integration.return_preflight
python integration/probes/review_latest.py --pr1-root PATH_TO_PR1 --pr2-root PATH_TO_PR2 --pr4-root PATH_TO_PR4
```

From `web/`: `pnpm lint`, `pnpm test:run`, `pnpm build`, and `pnpm test:e2e`. From PR1: its full `pytest` suite. From PR3: `python -m unittest recycling_vision.test_relay -v`. From PR4: `pytest ml/tests -q`.
