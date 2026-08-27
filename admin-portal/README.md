# BinSight Focus Area C — Subang Jaya

This directory contains BinSight's independent operations and routing prototype. The `competition-simulation` profile serves a synthetic district of **500 households and 20 commercial units** with **33 Dutch-style 4.5 m³ underground bins at 11 service sites**. The separate `physical-pilot` profile explicitly maps one three-bin Teensy 4.1/C3 hardware producer to canonical routing IDs. Simulation service groups are not represented as 11 deployed controllers.

The portal is decision support, not an autonomous municipal dispatch system. Site coordinates, demand, vehicle performance, and sensor behavior are configurable planning assumptions.

## Implemented system

- A retained legacy ESP32 producer/gateway reference for three ultrasonic and three pressure/load channels. The current physical handoff target is the shared three-channel Teensy 4.1/PR #2 C3 producer documented in `../docs/TELEMETRY_ROUTING_CONTRACT.md`.
- A versioned telemetry-routing 2.1 adapter (with validated 2.0 legacy normalization), explicit hardware-to-canonical registry, per-bin acquisition/receipt time, event identity, bin type/waste stream, forecast availability, quality and source-mode provenance.
- A hidden physical fill state separated from noisy observations, with bias, drift, outliers, missing values, confidence, and freshness checks.
- A patterned demand generator with normalized hourly/day/week/month/year factors, shaped events, trend/change points, persistent district/local AR(1) regimes and non-negative Gamma arrivals.
- A chronological multi-horizon forecaster trained on a separate 730-day pre-period; the 30-day operational window is excluded and hidden state is used only for labels/outcomes.
- Three operator decisions: `COLLECTION_REQUIRED`, `INSPECTION_REQUIRED`, and `NO_COLLECTION_REQUIRED`, plus a trip-value gate that can defer a non-urgent route when waiting/merging is cheaper.
- Prize-collecting OR-Tools routes over cached OSRM road distance and duration matrices. Emergency/service-level stops are mandatory; optional pickups are accepted only when their avoided-overflow value exceeds fixed-trip, distance, time, service and low-fill costs. Mass, compacted volume, route duration and daily trip limits are enforced.
- Minute-level SimPy execution with travel, per-bin service, unloading, turnaround, traffic, payload-dependent fuel, and overflow during an active trip.
- A fair fixed baseline whose first collection occurs after its configured interval, plus a three-day common warm-up report for both policies.
- Eleven paired scenarios spanning normal patterns, seasonal/event demand, persistent/local surges, trend/change point, traffic, sensor failure, reduced capacity and combined stress.
- Eleven consolidated site markers, three-bin status popups, bounded Subang Jaya maps, route layers, and mock truck tracking.
- Profile-aware legacy or telemetry-routing 2.0/2.1 intake; immutable draft/accepted/completed/cancelled plans; idempotent local-only mock dispatch; and full source/decision provenance.

## Fixed physical design

| Item | Prototype value |
| --- | --- |
| Underground bins | 33 total; 4.5 m³ each |
| Service sites | 11; exactly 3 bins per site |
| Simulation grouping | 11 service groups of 3 bins; no deployed-controller claim |
| Physical competition model | 1 Teensy 4.1/C3 producer and 3 bins |
| Depot | Provisional Subang Jaya/Batu Tiga point at 3.06192, 101.55272 |
| Vehicle archetype | VDL Maxxum/UGS underground-container collection system |
| Route payload assumption | 9,000 kg, maximum 2 trips per calendar day |

No bins, sites, or trucks were added by the optimization work.

## Evidence status

The corrected 30-pair v1 result does **not** show routine fuel savings: after equal warm-up it used 23.79% more road distance and 18.90% more fuel than the fixed schedule. That result motivated dynamic trip-value policy v2; it remains historical evidence and is not a performance claim for v2. The current policy's matched simulation evidence is written to `artifacts/dynamic_v2/` and summarized separately in [DYNAMIC_V2_RESULTS.md](DYNAMIC_V2_RESULTS.md). Neither version is field evidence.

## Run on Windows

From the repository root, run `Setup-BinSight-Admin.cmd` once and then `Start-BinSight-Admin.cmd`. For development from this directory:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m binsight.cli prepare
.\.venv\Scripts\python.exe -m binsight.cli run --artifact-set dynamic_v2 --replications 30 --parallel-workers 4
.\.venv\Scripts\streamlit.exe run app.py
```

Ordinary reruns use the committed road matrices. Use `--refresh-map` only when deliberately refreshing OSRM inputs.

## Routing input contracts

Open **Route input** and upload CSV/JSON, paste JSON, or use the built-in demo. The legacy competition snapshot has one row for each `UGB-001` through `UGB-033`. The preferred telemetry-routing 2.1 envelope contains the three registered physical-pilot fill channels and carries per-bin event kind, bin type/waste stream, timing, availability, quality and forecast provenance. The one general-waste and two beverage-return recycling channels may be planned together, but generated truck trips never mix streams. Vision recognition/session events remain outside routing. See [TELEMETRY_ROUTING_CONTRACT.md](../docs/TELEMETRY_ROUTING_CONTRACT.md).

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

The read-only adapter can turn PR #2's per-bin history API or an exported JSON/CSV history into the complete predictive snapshot above. It explicitly maps hardware IDs, accumulates API history in a routing-owned cache, detects collection resets and sensor jumps, learns gated calendar/event patterns, emits probabilistic 6/24/48/168-hour fill forecasts, and validates the result before it is written. Pseudo-density remains context only and `weight_kg` stays null without calibration. See [PR2_FORECASTING_ADAPTER.md](PR2_FORECASTING_ADAPTER.md) for the equations, thresholds, fallback hierarchy, evaluation and limitations.

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
