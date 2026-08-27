# BinSight: Claude Review and Implementation Handoff

Prepared: 27 August 2026

Use this file as the task brief for Claude Pro or Claude Code. It contains the review findings and the owner's requested architecture. It does not claim that anyone has completed the repairs or wireless integration.

## Coordination With the Routing Contributor

Use this brief alongside [the Codex routing handoff](CODEX_ROUTING_INTEGRATION_HANDOFF.md). With both briefs in use, Claude owns hardware, USB/Wi-Fi transport, ingestion API/storage and producer-side fixes. Codex owns the `admin-portal/` adapter, prediction preparation, collection policy, planning lifecycle, operator UI and routing persistence.

Agree one event/route contract and shared fixtures before changing either side. Treat this brief's routing sections and Phase B as interface requirements to coordinate with Codex, not a second assignment to implement the same routing files. Choose one editor for each shared schema/document and exchange the tested producer/consumer versions. Do not change the other contributor's files or branch without agreement.

## 1. Instructions to Claude

Act as a senior embedded-systems and backend engineer working on BinSight. Verify the findings below against the current code, repair the hardware telemetry pipeline, and connect its readings to the existing central routing system. Preserve citizen data and existing contributor work.

Start by inspecting the repository and reporting a short implementation plan. Then work through the phases below using the repository access the owner provides. Record what you changed, which tests you ran, and what still needs hardware validation.

If you only have a chat interface and cannot access the private repository, ask for access or the relevant branch files. Do not claim to have inspected, edited, tested, committed, or deployed code you cannot access. Do not assume this handoff includes the original test harness or the repository itself.

Recheck current branch heads before applying a finding. Another contributor may have fixed it since the review. Keep working changes rather than replacing files with an older reviewed version.

### Repository and reviewed revisions

- Repository: [Rover-Panto/BinSight](https://github.com/Rover-Panto/BinSight)
- Hardware PR: [#2, Add hardware pipeline (firmware/backend/dashboard) as a separate track](https://github.com/Rover-Panto/BinSight/pull/2)
- Hardware branch: `feature/hardware-pipeline`
- Reviewed hardware commit: `e7055764b57663a9d916602d7b0e89f54df2eaa4`
- Routing PR: [#1, Feature/admin operations portal](https://github.com/Rover-Panto/BinSight/pull/1)
- Routing branch: `feature/admin-operations-portal`
- Inspected routing commit: `2e9f84ba2c2b13f93910728cdddda1589eb015ad`
- Main at handoff: `9fca9d47afb805f40034da970bb47d791ba8f0b4`
- Both PRs were open and unmerged when this file was prepared. PR #2 had no attached automated check results.

Read `CONTRIBUTING.md`, `docs/PROJECT_STATE.md`, `docs/DATA_PRESERVATION.md`, and `docs/ADMIN_INTEGRATION.md` before editing. Read each PR's own README and setup instructions. Treat older proposed contracts as proposals; reconcile them with the current implementations.

## 2. Owner's Architecture Decision

The owner wants the bin to read its sensors and send measurements over Wi-Fi to a central server. The server stores readings, evaluates collection need, predicts overflow, and calculates routes for garbage trucks.

```text
Normal smart bin
  Ultrasonic sensors -> Teensy 4.1 with RTOS
      -> Wi-Fi communications module
      -> Wi-Fi access point
      -> Network connection to the central server

Central BinSight server
  Authenticated ingestion -> Stored observations
      -> Quality checks and historical features
      -> Prediction or explicitly labelled fallback policy
      -> Collection decisions and existing route planner
      -> Operator dashboard and mock truck dispatch
```

Keep routing and model inference on the server. Keep sensor acquisition, bounded filtering, health reporting, and transmission buffering at the bin. A laptop can host the server for the prototype; the design should allow a separate host later. Do not buy hosting, expose services to the public internet, or connect real municipal systems as part of this task.

Teensy 4.1 has no built-in Wi-Fi. Retain it as the normal-bin controller and propose a communications module, such as an ESP32 connected over UART. An ESP32 in this role handles communication; it does not replace the Teensy sensing controller. Keep the separate ESP32 beverage-return station out of this change.

Confirm the available module, firmware/toolchain, serial pins, power supply and budget before implementing board-specific Wi-Fi firmware. If those details are unavailable, proceed with the protocol, server adapter, mocks and USB development path. Mark physical Wi-Fi support as pending. An HTTP upload test or laptop Wi-Fi connection does not prove standalone wireless operation at the bin.

Manufacturer references: [Teensy 4.1 interfaces](https://www.pjrc.com/store/teensy41.html), [ESP32 communications capabilities](https://www.espressif.com/en/products/socs/esp32).

## 3. Current Implementation and Boundaries

PR #2 adds 29 files under `hardware_pipeline/`. It changes no citizen frontend files. Its current path is:

```text
Two ultrasonic sensors on one bin -> Teensy -> USB serial
  -> Python serial bridge on a laptop
  -> FastAPI backend with SQLite
  -> Streamlit telemetry dashboard and CSV export
```

One firmware instance represents one bin. The second ultrasonic sensor cross-checks the first. The firmware configures sensing, filtering and transmission tasks at 200 ms, 500 ms and 2 seconds. Buttons supply waste-type hints and a calibration request.

The wire payload contains `timestamp`, `bin_id`, `fill_pct`, `estimated_density`, and `confidence_flag`. The density value uses an arbitrary relative scale influenced by button choice and fill rate. It is not measured weight, physical density, or automatic material classification. No load cell or watchdog recovery implementation exists in this PR. Its dashboard uses fill thresholds rather than an ML overflow model.

PR #1 contains the route planner, a Streamlit operations portal, simulation and forecast code, plus a different ESP32/MQTT hardware track. Reconcile that competing hardware design in the documentation. Do not maintain two conflicting definitions of the normal smart bin or delete a contributor's work without agreement.

Use these ownership boundaries:

| Area | Responsibility |
| --- | --- |
| `hardware_pipeline/firmware/` | Teensy sensing, filtering, calibration, health and transport interface |
| `hardware_pipeline/tools/` | USB development bridge and transport test utilities |
| `hardware_pipeline/cloud_backend/` | Telemetry API, validation, persistence and ingestion acknowledgements |
| `admin-portal/binsight/` | Server-side telemetry adapter, forecast features, collection policy and existing route engine |
| `admin-portal/app.py` | Operator workflow and route preview |
| `docs/` | Shared contracts, ownership, migration, operation and verification records |
| `web/` | Citizen app; no redesign or storage migration in this task |

## 4. Review Findings to Resolve

The original review recommended changes before merging PR #2. P1 findings block reliance on the current implementation. Resolve the P2 findings before using its readings for routing. The linked line numbers refer to the reviewed commit, not future revisions.

### R1. [P1] Unsafe ECHO voltage-divider diagram

Source: [SETUP_AND_WIRING_GUIDE.md:158](https://github.com/Rover-Panto/BinSight/blob/e7055764b57663a9d916602d7b0e89f54df2eaa4/hardware_pipeline/SETUP_AND_WIRING_GUIDE.md#L158).

The diagram connects the sensor's ECHO output straight to GND alongside the resistor path. Following it shorts the output when high and risks sensor damage. The prose below describes the intended circuit.

Correct the diagram so ECHO connects through R1 to the Teensy input tap, and only the tap connects through R2 to GND. Align the diagram, prose and pin table. Have the hardware operator check the circuit before applying power. Do not report a physical wiring check based only on editing the diagram.

### R2. [P1] Inconsistent Teensy FreeRTOS dependency

Sources: [tasks.h:21](https://github.com/Rover-Panto/BinSight/blob/e7055764b57663a9d916602d7b0e89f54df2eaa4/hardware_pipeline/firmware/BinSight_Teensy41/tasks.h#L21), [setup guide:48](https://github.com/Rover-Panto/BinSight/blob/e7055764b57663a9d916602d7b0e89f54df2eaa4/hardware_pipeline/SETUP_AND_WIRING_GUIDE.md#L48).

The sketch includes `arduino_freertos.h`; `tasks.h` requests `Arduino_FreeRTOS.h`. The documented `tsandmann/freertos-teensy` dependency supplies the former. Its upstream build instructions also require a supported platform/core or the documented Teensyduino package, rather than an arbitrary repository ZIP.

Use one compatible port throughout. Pin a working Teensy 4.1 build configuration and dependencies, correct the setup instructions, and add a clean-target compile check. Check task-creation failures and stack use during bring-up. Do not substitute an AVR FreeRTOS library.

References: [upstream build and thread-safety notes](https://github.com/tsandmann/freertos-teensy), [public header declaration](https://github.com/tsandmann/freertos-teensy/blob/master/library.properties).

### R3. [P1] Fill filter can freeze after a collection or large deposit

Source: [filters.h:34](https://github.com/Rover-Panto/BinSight/blob/e7055764b57663a9d916602d7b0e89f54df2eaa4/hardware_pipeline/firmware/BinSight_Teensy41/filters.h#L34).

The filter rejects changes above 25 percentage points and retains the same reference value. Sustained valid readings beyond that threshold cannot establish a new baseline. A host test initialized the actual filter at 80%, then supplied 100 readings of 5%; the output stayed at 80%.

Implement bounded reacquisition after a stable, credible sequence and handle collection resets. Define the recovery bound in samples or seconds. Keep spike rejection, but do not freeze valid measurements. Propagate filter rejection/recovery into output quality; agreement between raw sensors does not make a frozen filtered value trustworthy.

### R4. [P1] Invalid sensor readings become a fabricated zero

Source: [tasks.cpp:134](https://github.com/Rover-Panto/BinSight/blob/e7055764b57663a9d916602d7b0e89f54df2eaa4/hardware_pipeline/firmware/BinSight_Teensy41/tasks.cpp#L134).

The invalid branch calls `fillFilter.process(0.0f, ...)` despite a comment claiming to hold the last good value. In host probes, five invalid substitutions moved 20% to 0%. An invalid startup substitution followed by 100 valid 80% readings remained at 0% because of R3.

Exclude invalid samples from filter updates. Represent unavailable fill as unavailable. Retain a last-good observation separately with its original time and age; do not present it as a fresh measurement. Add a versioned schema change where null/unknown support requires it.

### R5. [P1] Backend ignores the documented `.env` configuration

Sources: [config.py:14](https://github.com/Rover-Panto/BinSight/blob/e7055764b57663a9d916602d7b0e89f54df2eaa4/hardware_pipeline/cloud_backend/app/config.py#L14), [setup guide:61](https://github.com/Rover-Panto/BinSight/blob/e7055764b57663a9d916602d7b0e89f54df2eaa4/hardware_pipeline/SETUP_AND_WIRING_GUIDE.md#L61).

The guide tells users to create `cloud_backend/.env`. The backend only reads process environment variables, and the launch command does not load the file. The bridge does load its `.env`. A test using matching file-based keys still received HTTP 401 because the backend retained its placeholder key.

Load the explicitly located configuration before settings initialization, or document and test `uvicorn --env-file .env`. Fail startup on missing/placeholder credentials. Verify this from a fresh shell with no exported key. Keep secrets out of Git and logs.

### R6. [P2] Serial diagnostics can interrupt telemetry frames

Sources: [network.cpp:25](https://github.com/Rover-Panto/BinSight/blob/e7055764b57663a9d916602d7b0e89f54df2eaa4/hardware_pipeline/firmware/BinSight_Teensy41/network.cpp#L25), [tasks.cpp:70](https://github.com/Rover-Panto/BinSight/blob/e7055764b57663a9d916602d7b0e89f54df2eaa4/hardware_pipeline/firmware/BinSight_Teensy41/tasks.cpp#L70).

Debug output takes the serial mutex; the telemetry writer does not. The sensing task can preempt the separate prefix, JSON and newline writes. A controlled host interleaving produced a `BINSIGHT:[Task1] ...` line and detached JSON, which the bridge would discard.

Use one serial writer or a shared lock around complete frames for all writers. Bound diagnostic work so it does not stall sensing. Test debug-enabled parsing and transport separation. The original probe demonstrated a possible interleaving, not a measured failure rate on hardware.

### R7. [P2] HTTP failures discard readings

Sources: [serial_bridge.py:85](https://github.com/Rover-Panto/BinSight/blob/e7055764b57663a9d916602d7b0e89f54df2eaa4/hardware_pipeline/tools/serial_bridge.py#L85), [serial_bridge.py:52](https://github.com/Rover-Panto/BinSight/blob/e7055764b57663a9d916602d7b0e89f54df2eaa4/hardware_pipeline/tools/serial_bridge.py#L52).

The bridge logs connection errors or HTTP 503 and advances to the next frame. It has no replay queue. Tests confirmed that the first of two readings disappeared after a temporary failure. The MCU's USB-write success does not acknowledge server storage.

Retain events until the server confirms storage or an identical duplicate. Add a durable host queue to the USB path and define durable buffering for the wireless path. Retry transient failures with bounded backoff; retain permanent validation failures in an inspectable error queue. Cap storage, expose queue age/drop counts, and document behavior when full. Do not promise unlimited or lossless retention.

### R8. [P2] SQLite timestamp handling corrupts identity and ordering

Sources: [schemas.py:35](https://github.com/Rover-Panto/BinSight/blob/e7055764b57663a9d916602d7b0e89f54df2eaa4/hardware_pipeline/cloud_backend/app/schemas.py#L35), [models.py:21](https://github.com/Rover-Panto/BinSight/blob/e7055764b57663a9d916602d7b0e89f54df2eaa4/hardware_pipeline/cloud_backend/app/models.py#L21).

The API accepts offsets without UTC normalization. The configured SQLite datetime mapping drops the timezone. Tests stored `10:00+08:00` and `02:00Z` as different events, but treated `10:00+08:00` and `10:00Z` as duplicates. The response omitted the UTC indicator.

Normalize new input to UTC and return timezone-aware timestamps. Choose an explicit storage representation and add migration tests. Existing naive timestamps have ambiguous provenance: do not assume an offset and shift historical records without evidence. Preserve them, record the ambiguity and agree a recovery policy.

### R9. [P2] Calibration button reports success without changing anything

Source: [tasks.cpp:81](https://github.com/Rover-Panto/BinSight/blob/e7055764b57663a9d916602d7b0e89f54df2eaa4/hardware_pipeline/firmware/BinSight_Teensy41/tasks.cpp#L81).

The long-press handler prints a re-zeroing message but leaves the geometry constants and filter state unchanged.

Implement a validated empty-baseline update, reject invalid calibration attempts, and reset dependent filter/rate state. Document persistence across restarts and record calibration version/time. If calibration cannot yet run, label the control as unavailable and document manual configuration instead of claiming success. Test a bin whose empty distance is not 80 cm.

### R10. [P2] Dashboard treats old or unreliable readings as reassuring

Sources: [streamlit_app.py:108](https://github.com/Rover-Panto/BinSight/blob/e7055764b57663a9d916602d7b0e89f54df2eaa4/hardware_pipeline/dashboard/streamlit_app.py#L108), [streamlit_app.py:122](https://github.com/Rover-Panto/BinSight/blob/e7055764b57663a9d916602d7b0e89f54df2eaa4/hardware_pipeline/dashboard/streamlit_app.py#L122).

The dashboard counts bins with historical readings as active and sets the risk badge from fill alone. An unplugged bin with an old 20% reading remains active and green. Separate confidence warnings do not correct that status.

Show sensor observation age, offline/stale status and inspection-required states. Keep page refresh time separate from sensor time. Define freshness thresholds against the configured reporting interval and use them in the adapter as well as the UI. Verify stale, clock-invalid and low-confidence cases.

## 5. Data Integrity Work Beyond the Ten Findings

Address these before introducing replay and live routing:

- **Event identity:** the firmware creates several samples per second but emits second-resolution packaging timestamps. It does not serialize `sequence_id` or convert the captured `millis_timestamp`. Add reboot-safe identity, such as device ID, boot/session ID and monotonic sequence. Timestamp alone is not a sufficient duplicate key.
- **Conflicting retries:** acknowledge the same event ID and content once. Reject or quarantine a reused ID with different content. Make duplicate handling transactional, including concurrent submissions. Do not silently replace historical observations.
- **Throughput:** sampling runs at 5 Hz while transmission removes one packet per 2-second cycle. With the current bounded queue, dropping packets is normal operation. Define sampling, aggregation and upload cadences separately, preserve required evidence, and record intentional reductions and dropped events.
- **Clock state:** keep acquisition time, receipt time and monotonic sample time separate. Report unsynchronized clocks. Do not stamp stale queued observations with the current time during retry.
- **Watchdog behavior:** if implementing the proposal's recovery claim, monitor progress of the required tasks and report restart cause. A watchdog feed from an unrelated timer does not demonstrate task health. Measure recovery and queue behavior on the board.
- **Backups:** test migrations and restore on copies. Keep raw observations, derived predictions, route snapshots and dispatch records distinct and linked by IDs. Use database-safe backup methods and document retention.

## 6. Server Integration Contract

The existing routing entry points live in `admin-portal/binsight/dispatch.py`: `validate_snapshot()` and `build_dispatch_plan()`. Keep the existing route engine. Add a small adapter near it, for example `admin-portal/binsight/telemetry_adapter.py`, that reads the telemetry API rather than writing into its database.

The current routing snapshot requires:

```text
timestamp, bin_id, fill_pct, weight_kg,
time_to_overflow_hours, risk_level, confidence_flag
```

It currently expects a complete configured district with one shared timestamp; the supplied district has 33 `UGB-...` bins. It accepts null fill/weight but requires a finite time-to-overflow. The validator selects known columns, so adding an extra quality field to JSON alone will not make the router use it.

### Contract changes to implement and document

| Concern | Required treatment |
| --- | --- |
| Schema version | Introduce an explicit version where fields or meanings change; preserve or migrate existing clients and stored records. |
| Bin identity | Map hardware IDs such as `bin_01` to a stable registry entry, location and geometry. Do not assume `BIN-###` and `UGB-...` identify the same physical bin. |
| Observation identity | Preserve source event ID, device, boot/session and sequence through ingestion, prediction and routing audit. |
| Time | Keep per-bin observation time separate from route decision time and server receipt time. Preserve age and clock quality. |
| Fill | Use a validated measurement or explicit unavailable state. Keep any retained last-good estimate labelled and aged. |
| Weight | Use `null` without a real measurement. The existing router has conservative missing-weight/inspection behavior; document its assumptions. Never reinterpret relative density as kilograms. |
| Forecast | Record method, model version, input window and quality. Support unknown time-to-overflow without zero or large-number sentinels. |
| Risk | Define the mapping between fill, forecast, uncertainty and collection policy; do not rename a threshold badge as ML output. |
| Provenance | Identify hardware, replay and synthetic observations and distinguish measured, predicted and modelled values. |
| Reproducibility | Save an immutable decision snapshot, source event IDs, policy/model versions and vehicle/network assumptions with each route. |

Update validation, selection rules and tests together when adding unknown forecasts or per-bin timestamps. Preserve operator review for stale/missing data; do not let missing information become evidence that collection is unnecessary. Do not refresh all observation timestamps to satisfy the current same-time snapshot rule.

### Prediction and early operation

The existing `admin-portal/binsight/forecast.py` model uses fill, weight, confidence, historical growth and site characteristics. Its training data comes from the simulator. Do not assume it is validated for physical bins or feed it rapid samples as though they represent the expected historical intervals.

Build historical features using actual timestamps and a documented time window. Exclude invalid observations, handle collection resets, define cold-start behavior and validate any missing-feature treatment. Evaluate against held-out prototype logs when enough data exists. Keep synthetic evaluation separate from physical validation.

Until then, implement a named fill-threshold fallback with explicit forecast-unavailable status. Preserve the route engine's capacity and inspection constraints. This fallback is not a trained forecast.

### Pilot size

First connect a saved hardware-style log to one mapped bin and verify the state changes. Then use a small configured pilot with its own matching depot, locations, capacities and road matrix. If demonstrating the existing 33-bin district, label each non-hardware bin as simulated and keep those results out of claims about measured field performance. Do not copy one sensor stream across the district.

## 7. Wireless Delivery and Route Updates

Prefer authenticated HTTPS against the existing ingestion backend for the first wireless implementation. Add another messaging protocol only if it solves a documented requirement; the current HTTP backend does not require an MQTT rewrite.

- Use a module with a verified compatible firmware stack, adequate power supply and TLS support. Document the UART framing and acknowledgements between Teensy and the module.
- Validate server certificates and keep credentials in provisioning/local configuration. Do not disable verification or commit working credentials. Keep unsecured development settings explicit and isolated from remote deployment.
- A local UART or network acknowledgement is not proof of database storage. Define the acknowledgement point, durable queue owner and replay behavior across Wi-Fi loss, server restart, module restart and bin power loss.
- Send reports at a configured interval, with bounded event-triggered updates for significant fill or health changes. Do not upload every fast sensor poll without a throughput and power justification.
- Require Wi-Fi coverage at each bin and a network path to the server. Do not claim city-wide coverage based on a desk test.
- Keep the USB path as a development transport using the same event contract. Test that USB and wireless ingestion produce equivalent stored events.

Add an operator action to load the latest validated observations and preview a route before enabling automatic evaluation. Run subsequent route calculations on the server, independently of whether an operator has a dashboard tab open. Avoid repeated work when the input snapshot has not changed.

Rate-limit replanning and version proposed routes. Keep an accepted active route separate from new proposals; do not send competing instructions to a driver on each sensor update. Keep vehicle dispatch simulated until the owner authorizes a real integration.

If adding KPI output, retain the same district, depot, vehicle assumptions and time window for baseline/priority comparisons. Use matched waste-generation scenarios in simulation, since different collection policies change later fill levels. Label modelled fuel and CO2, record completeness, and do not present proposal targets or simulated savings as measured outcomes.

## 8. Implementation Phases and Git Workflow

### Phase A: Repair the hardware pipeline

Verify and resolve R1-R10. Add regression tests, a reproducible firmware build and corrected setup instructions. Address event identity, storage migration and queue behavior before treating historical data as reliable. Keep these repairs focused on PR #2's track.

### Phase B: Connect the central server

Agree and version the contract. Add the registry, adapter, timestamp/quality handling and supported unknown-forecast state. Reuse the existing planner. Demonstrate saved-log ingestion, route preview and audit records before live updates.

### Phase C: Add Wi-Fi and controlled automation

After confirming the module, implement the transport and test reconnection, replay, power interruption and end-to-end storage acknowledgement. Add server-side route evaluation and operator controls. Keep hardware tests pending when the equipment is unavailable; do not let that block independent server tests.

### Branch discipline

Follow `CONTRIBUTING.md`. Use a focused feature/fix branch; update a collaborator's existing branch only with their agreement. Keep repair and integration changes in separate reviewable commits or PRs. If integration depends on both unmerged PRs, record the dependency and base revisions; do not assume those files exist on `main` or duplicate them by copying an old snapshot.

Stage only task-owned files, run the relevant checks, commit completed work and push the contributor branch when you have repository access and permission to push. Do not force-push, merge into `main`, close PRs, or discard another contributor's changes without the owner's instruction.

## 9. Protect Existing Data and Documentation

- Leave citizen state in `binsight-demo-v1` and preserve its versioned backups and migration behavior. Do not call `localStorage.clear()`.
- Preserve citizen login, returns, payout methods, reports, notifications, settings and stored image attachments. Do not move image data into route or KPI records.
- Keep admin preferences separate from citizen storage. Keep telemetry and routing databases under their existing owners until a tested migration says otherwise.
- Test database changes against populated old-schema copies. Check row counts, IDs, values and restore behavior. Do not recreate or delete a database to make a migration pass.
- Use fictional demonstration data. Do not upload real identity, payment, Wi-Fi credentials or resident records to chat, fixtures or Git.
- Update `hardware_pipeline/README.md` and `SETUP_AND_WIRING_GUIDE.md` for the corrected build and transports.
- Update `docs/PROJECT_STATE.md`, `docs/ADMIN_INTEGRATION.md`, `docs/DATA_PRESERVATION.md`, and the routing README/sensor contract to describe what the implementation now does. Distinguish current USB support, pending/verified Wi-Fi, and the competing older hardware track.
- Update `docs/FRONTEND.md` only if frontend behavior or architecture changes. State that the Streamlit operations portal is separate from the planned React `/admin` module unless you implement an approved integration. Do not redesign the citizen frontend in this task.
- Document the new wire contract, units, time handling, schema version, provisioning, backup/restore, startup/shutdown and remaining limitations. Remove obsolete ZIP-only setup assumptions when documenting repository checkout paths.

## 10. Acceptance Tests

Add these as committed tests or recorded hardware procedures. Report each as passed, failed or not run, with the command/environment or test evidence.

| ID | Scenario and required result |
| --- | --- |
| T01 | Clean checkout builds for the pinned Teensy 4.1 toolchain. |
| T02 | Corrected divider matches the checked circuit; a hardware operator verifies it before power-on. |
| T03 | Stable 80% followed by stable 5% converges within the documented recovery bound. |
| T04 | A genuine large fill increase recovers; a single spike does not become the accepted baseline. |
| T05 | Startup timeout followed by valid 80% readings recovers without a false confident zero. |
| T06 | Invalid readings after 20% do not create fresh zero-fill observations; age and quality remain visible. |
| T07 | Calibration changes the configured baseline, resets dependent state, rejects bad readings and follows the documented restart policy. |
| T08 | Debug output cannot corrupt a telemetry frame; queues and transport failures do not stall sensing. |
| T09 | Fresh-shell setup uses the file-based key; invalid/missing keys and placeholder server configuration fail as documented. |
| T10 | Equivalent UTC/offset timestamps round-trip consistently; different instants remain distinct. |
| T11 | Two acquisitions in one second both survive; retries, concurrent submissions and device reboots do not duplicate or overwrite events. |
| T12 | Connection failure, HTTP 503 and an acknowledgement lost after storage trigger replay; each accepted event remains once. |
| T13 | Process/power restart preserves the promised queue contents; capacity exhaustion creates a visible, documented result. |
| T14 | Stale, disconnected, clock-invalid and low-confidence bins show unknown/inspection states, not a confident empty state. |
| T15 | Measured fill, unavailable weight and unavailable forecast pass the intended policy without fabricated kilograms or overflow times. |
| T16 | Pilot ID coverage, depot and road-matrix dimensions match; reject unmapped/duplicate IDs and unintended synthetic substitutions. |
| T17 | A saved-log end-to-end run records ingestion, derived decision inputs, selected stops and an auditable mock dispatch. |
| T18 | Rising fill changes collection eligibility; a verified emptying updates the next plan; stale data cannot masquerade as a fresh snapshot. |
| T19 | New proposals do not overwrite an accepted active route, and repeated input does not create duplicate dispatches. |
| T20 | Populated old databases migrate/restore without changing original IDs or losing records; citizen data and images remain intact. |
| T21 | Physical Wi-Fi test uses the actual bin/module and central server, exercises reconnection and validates TLS; a mock does not satisfy this test. |

Run the existing routing tests after adapter, policy or schema changes. Run the citizen checks required by `CONTRIBUTING.md` from `web/`: `pnpm lint`, `pnpm test:run`, `pnpm test:e2e`, and `pnpm build`. Record any environment blocker instead of claiming a pass. Add screenshots at the documented desktop/tablet/mobile sizes if changing a visible page.

## 11. Evidence From the Original Review

The reviewer inspected all 29 PR #2 files and used isolated copies for tests. The tracked citizen project stayed unchanged.

- A multi-assertion backend control passed: valid storage, exact retry handling, wrong-key rejection, fill range validation and history count.
- Nine targeted Python cases produced one pass and eight failed desired-behavior assertions. Those failures covered `.env` loading/401, three timestamp cases, two temporary HTTP failures and a same-second event-identity probe. Several cases concern the same defect; this is not a count of eight independent backend bugs.
- The reviewer compiled the actual filter and serial writer in a desktop C++ harness with a minimal Arduino stub. The filter results described in R3/R4 came from that code.
- The serial probe used controlled preemption. The reviewer did not measure its frequency on a Teensy.
- The reviewer did not complete a full MCU target build, physical wiring/ultrasonic tests, Wi-Fi tests or browser-rendered Streamlit verification. Treat those as outstanding work.
- The routing contract review covered the current integration boundary. It was not a complete re-review of PR #1.

Recreate focused regression tests in the repository. Do not rely on temporary paths from the review machine or weaken tests to match defective behavior.

## 12. Required Completion Report

Return a report with:

1. Current source commits and a disposition for R1-R10: fixed, already fixed, or unresolved with evidence.
2. Changed files and the reason for each change, grouped into repairs and integration.
3. The final event/route contracts, migration details and data ownership rules.
4. Test commands and results, including a separate list of untested physical behaviors.
5. Startup, shutdown, provisioning and recovery instructions another contributor can follow.
6. Hardware/module and power-budget decisions, or the exact missing information that prevents the Wi-Fi phase.
7. Commit/branch/PR references and the remaining review items before merge.

Do not call the system deployed, lossless, production-ready or proven without evidence. Do not claim genuine truck dispatch or real savings from a simulated demonstration. Leave a reviewable implementation with accurate documentation and explicit limitations.
