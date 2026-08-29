# BinSight Focus Area C — Subang Jaya

This directory contains BinSight's independent operations and routing prototype. The `competition-simulation` profile serves a synthetic district of **500 households and 20 commercial units** with **44 Dutch-style 4.5 m³ underground bins at 11 service sites**: general waste, plastic, metal and glass at every site. The separate `physical-pilot` profile still maps the real three-channel Teensy 4.1/C3 hardware producer. It is intentionally reported as partial for the four-bin demonstration until the producer contract gains a fourth channel.

The portal is decision support, not an autonomous municipal dispatch system. Site coordinates, demand, vehicle performance, and sensor behavior are configurable planning assumptions.

## Implemented system

- A retained legacy ESP32 producer/gateway reference for three ultrasonic and three pressure/load channels. The current physical handoff target is the shared three-channel Teensy 4.1/PR #2 C3 producer documented in `../docs/TELEMETRY_ROUTING_CONTRACT.md`.
- A versioned telemetry-routing 2.1 adapter (with validated 2.0 legacy normalization), explicit hardware-to-canonical registry, per-bin acquisition/receipt time, event identity, bin type/waste stream, forecast availability, quality and source-mode provenance.
- A hidden physical fill state separated from noisy observations, with bias, drift, outliers, missing values, confidence, and freshness checks.
- A patterned demand generator with normalized hourly/day/week/month/year factors, shaped events, trend/change points, persistent district/local AR(1) regimes and non-negative Gamma arrivals.
- A chronological multi-horizon forecaster trained on a separate 730-day pre-period; the 30-day operational window is excluded and hidden state is used only for labels/outcomes.
- Three operator decisions: `COLLECTION_REQUIRED`, `INSPECTION_REQUIRED`, and `NO_COLLECTION_REQUIRED`, plus a trip-value gate that can defer a non-urgent route when waiting/merging is cheaper.
- Prize-collecting OR-Tools routes over cached OSRM road distance and duration matrices. Emergency/service-level stops are mandatory; optional pickups are accepted only when their avoided-overflow value exceeds fixed-trip, distance, time, service and low-fill costs. Mass, compacted volume, route duration and daily trip limits are enforced.
- Exactly two independent specialized vehicles: one general-waste truck based at the waste depot and one three-compartment recycling truck based at the recycling facility. Either truck can dispatch while the other is active; no surge vehicle is created.
- Route-arrival deadlines include travel and all earlier stop-service time, so equal-deadline bins trigger an earlier departure instead of an extra truck. A three-day rolling optimizer assigns due work to days before same-day road ordering.
- Minute-level SimPy execution with travel, per-bin service, unloading, turnaround, traffic, payload-dependent fuel, and overflow during an active trip. Aggregate overflow exposure uses exact event times and adds every bin's duration at capacity (two bins for 30 minutes = 60 bin-minutes = 1 bin-hour).
- A fair fixed baseline whose first collection occurs after its configured interval, plus a three-day common warm-up report for both policies.
- Eleven paired scenarios spanning normal patterns, seasonal/event demand, persistent/local surges, trend/change point, traffic, sensor failure, reduced capacity and combined stress.
- Eleven consolidated site markers, four-bin status popups, a marked recycling facility, bounded keyless OpenStreetMap maps, route layers, and mock truck tracking.
- Profile-aware legacy or telemetry-routing 2.0/2.1 intake; immutable draft/accepted/completed/cancelled plans; idempotent local-only mock dispatch; and full source/decision provenance.

## Fixed physical design

| Item | Prototype value |
| --- | --- |
| Underground bins | 44 total; 4.5 m³ each |
| Service sites | 11; exactly 4 material bins per site |
| Simulation grouping | 11 service groups of 4 bins; no deployed-controller claim |
| Physical competition model | 1 Teensy 4.1/C3 producer and 3 bins |
| Depot | Provisional Subang Jaya/Batu Tiga point at 3.06192, 101.55272 |
| Recycling destination | Provisional MBSJ USJ 9 Recycling Centre at 3.04547, 101.58697 |
| Vehicle archetype | VDL Maxxum/UGS underground-container collection system |
| Fleet | 1 general-waste truck + 1 three-compartment recycling truck (1:1) |
| Route payload assumption | 9,000 kg per truck, maximum 2 trips per truck per calendar day |

The four-bin change affects the local demonstration and simulator only. It does not fabricate a fourth live hardware channel.

## Evidence status

Evidence artifacts are accepted by the website only when their recorded configuration hash matches the active four-bin configuration. The current `artifacts/dynamic_v4/` set contains two paired 30-day replications for each of eleven scenarios and supplies the GENERAL-01 and RECYCLING-01 live-tracking replays. The sidebar's **Run 30-day experiment** control opens a compact saved month instead of recomputing the simulation in the web request: choose Day 1–30, then pause, scrub, reset, or change the shared speed while both specialized trucks remain visible. Days without dispatches show each truck idle at its own base. The playback page compares Fixed and Dynamic using the paired average for the declared `normal_patterned` scenario, rather than selecting a favorable stress case. Its monthly overflow measure is aggregate bin-time at capacity across all 44 bins and the entire 30-day horizon, calculated from the exact capacity/collection event times rather than hourly samples. It is integration verification, not a field-performance or production-deployment claim. The older 33-bin studies remain historical references and are no longer presented as current evidence.

## Run on Windows

From the repository root, run `Setup-BinSight-Admin.cmd` once and then `Start-BinSight-Admin.cmd`. For development from this directory:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m binsight.cli prepare
.\.venv\Scripts\python.exe -m binsight.cli health
.\.venv\Scripts\python.exe -m binsight.cli run --artifact-set dynamic_v4 --replications 30 --parallel-workers 4
.\.venv\Scripts\streamlit.exe run app.py
```

Ordinary reruns use the committed road matrices. Use `--refresh-map` only when deliberately refreshing OSRM inputs.

## Routing demonstration and integration contracts

The portal's **Routing demo** is deliberately demonstration-only: it loads the complete configured 44-bin scenario automatically, sets every demonstration confidence flag to true, shows a 12-row preview, and evaluates all bins when the operator runs it. UGB-001 and UGB-005 share a 6.3-hour overflow deadline so the preview visibly demonstrates one truck leaving early and reaching both stops on time. Manual CSV/JSON upload and paste controls are not exposed in the presentation UI.

The **Mock live tracking** tab replays completed routes from the current 30-day artifact. The operator can select GENERAL-01 or RECYCLING-01. Each site marker is a forecast-fill gauge for the bin(s) served by that selected truck: grey is empty, its color approaches red at 100%, and the marker resets cleanly to 0% when collection completes.

The **Operations** map shows all four bins at a service site in one circular marker divided by a cross. General, plastic, metal, and glass each occupy one fixed quarter. Each whole quarter uses the Mock live tracking grey-to-red scale and prints that bin's unchanged snapshot fill percentage; the outer ring shows the route-selection state.

The integration and command-line adapters remain documented for engineering use. The competition snapshot has one row for each `UGB-001` through `UGB-044`. The preferred telemetry-routing 2.1 envelope still contains only the three registered physical-pilot fill channels and carries per-bin event kind, bin type/waste stream, timing, availability, quality and forecast provenance. That live profile therefore cannot claim complete four-bin coverage. Vision recognition/session events remain outside routing. See [TELEMETRY_ROUTING_CONTRACT.md](../docs/TELEMETRY_ROUTING_CONTRACT.md).

```text
timestamp,bin_id,fill_pct,weight_kg,time_to_overflow_hours,risk_level,confidence_flag
```

- `timestamp`: one shared timezone-aware ISO 8601 value; no more than 12 hours old and no more than 5 minutes in the future.
- `fill_pct`: ultrasonic-derived percentage from 0 to 100; it may be missing when the other sensor and a recent last-valid reading support inspection.
- `weight_kg`: load-cell value from 0 to 1,500 kg; it may be missing under the same safe-degradation rules.
- `time_to_overflow_hours`: predictive-AI estimate greater than or equal to zero.
- `risk_level`: `low`, `medium`, `high`, or `critical`.
- `confidence_flag`: Boolean.

The dispatcher never silently converts an uncertain record into a safe record. Stale, low-confidence, missing, or disagreeing readings can produce `INSPECTION_REQUIRED`; imminent risk still produces `COLLECTION_REQUIRED` with an operator-review warning. Accepted last-valid observations are persisted locally and aged conservatively.

### PR #2 historical forecasting adapter

The read-only adapter can turn PR #2's per-bin history API or an exported JSON/CSV history into the predictive snapshot above. It explicitly maps hardware IDs, accumulates API history in a routing-owned cache, detects collection resets and sensor jumps, and validates the result before it is written. Historical replay rejects saved model state trained or populated after the simulated decision cutoff. Pseudo-density remains context only and `weight_kg` stays null without calibration. The four-bin simulation uses material-specific density and fill behavior; live PR #2 remains three-channel and incomplete until its owner updates that contract. See [PR2_FORECASTING_ADAPTER.md](PR2_FORECASTING_ADAPTER.md).

```powershell
.\.venv\Scripts\python.exe -m binsight.cli forecast-pr2 `
  --history .\path\to\pr2-history.json `
  --profile competition-simulation `
  --decision-at 2026-08-28T12:00:00+00:00 `
  --output .\data\pr2-predictive-snapshot.json
```

Use `--api-base` instead of `--history` for the PR #2 API and set `BINSIGHT_PR2_API_KEY`. API mode persists model state and the append-only local history cache under `data/`; it never writes the producer database.

Every proposal is first stored as an immutable `DRAFT` in `data/routing_plans.sqlite3`. An operator must accept or cancel it. Sending an accepted mock route creates at most one transactional mock-dispatch record for that plan. It does not contact a truck, driver app, MQTT broker, or municipal API. The old JSONL file remains read-only historical audit input.

## Planner commands

```powershell
.\.venv\Scripts\python.exe -m binsight.cli plan-once --snapshot .\tests\fixtures\telemetry_v2_valid.json --profile physical-pilot
.\.venv\Scripts\python.exe -m binsight.cli planner-start --snapshot .\tests\fixtures\telemetry_v2_valid.json --profile physical-pilot
.\.venv\Scripts\python.exe -m binsight.cli planner-status
.\.venv\Scripts\python.exe -m binsight.cli planner-stop
```

The periodic planner is opt-in and single-worker. It proposes drafts; it never auto-accepts or sends a route. Repeated identical input inside one 15-minute planning bucket is idempotent. A telemetry event during an accepted trip can freeze the active leg and produce a separate residual-capacity suffix draft without mutating the accepted plan.

## Raspberry Pi gateway

Process a saved controller payload:

```powershell
.\.venv\Scripts\python.exe -m gateway.binsight_gateway `
  --calibration hardware/controller_calibration.example.json `
  --input-json hardware/example_payload.json `
  --database data/binsight_gateway.sqlite3 `
  --export-csv data/model_readings.csv
```

For MQTT mode, set `BINSIGHT_MQTT_HOST`, `BINSIGHT_MQTT_PORT`, `BINSIGHT_MQTT_USERNAME`, and `BINSIGHT_MQTT_PASSWORD`, then replace `--input-json ...` with `--mqtt`.

## Legacy firmware reference

`firmware/esp32_binsight` and the Raspberry Pi gateway remain an executable legacy-reference path, now using schema 1.1 boot/event identity so a reboot cannot cause valid readings to be discarded as duplicates. They are not the current physical producer architecture. Hardware PR #2 must emit the routing handoff contract from the Teensy 4.1/C3 path and pass the shared fixture/schema checks.

## Evidence and documentation

- [SITING_PLAN.md](SITING_PLAN.md) — capacity equation and preliminary coordinates.
- [PRODUCTION_RUNBOOK.md](PRODUCTION_RUNBOOK.md) — localhost startup, health, backup, logs and recovery.
- [METHODS.md](METHODS.md) — simulation, observation, forecast, routing, fuel, and inference method.
- [DYNAMIC_ROUTING_MODEL.md](DYNAMIC_ROUTING_MODEL.md) — exact v2 objective, provisional weights, constraints and deferral rule.
- [PR2_FORECASTING_ADAPTER.md](PR2_FORECASTING_ADAPTER.md) — PR #2 history bridge, mathematical forecast, online adaptation and acceptance evidence.
- [FINAL_RESULTS.md](FINAL_RESULTS.md) — locked 30-pair base and stress results.
- [ROUTING_REPORT.md](ROUTING_REPORT.md) — complete Focus Area C implementation report.
- [Historical v1 routing report (DOCX)](reports/BinSight_Routing_Subsystem_Report_Improved.docx) and [PDF](reports/BinSight_Routing_Subsystem_Report_Improved.pdf) — retained generated evidence for the retired threshold/legacy-topology version; not current v2 documentation.
- [ROUTE_DISPLAY.md](ROUTE_DISPLAY.md) — map and tracking behavior.
- [RESEARCH_BRIEF.md](RESEARCH_BRIEF.md) — external evidence versus prototype assumptions.
- [hardware/SENSOR_CONTRACT.md](hardware/SENSOR_CONTRACT.md) — controller/gateway data contract.
- [Admin portal design system](../docs/ADMIN_PORTAL_DESIGN_SYSTEM.md) — interface tokens and QA record.
- [Operator guide](../docs/HOW_TO_OPERATE_ADMIN_PORTAL.md) — input, routing, dispatch, and troubleshooting.
- [Competition compliance audit](../docs/COMPETITION_COMPLIANCE_AUDIT.md) — question-paper coverage, proposal contradictions, and remaining deliverables.

The final experiment artifacts are in `artifacts/`, including replication-level metrics, paired effects, forecasts, routes, seeds, and run provenance.

## Reproducibility boundary

The numerical results are synthetic planning evidence, not measured Malaysian municipal performance. Normal map viewing uses third-party tiles; deployment should use a suitable hosted provider or self-hosted OSM stack and must comply with attribution and tile-use rules. Validate coordinates, bin-density calibration, vehicle fuel behavior, service time, MQTT reliability, and operator procedures in a physical pilot before operational use.
