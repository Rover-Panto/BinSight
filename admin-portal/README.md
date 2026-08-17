# BinSight Focus Area C — Subang Jaya

This directory contains BinSight's independent operations and routing prototype. It serves a synthetic pilot of **500 households and 20 commercial units** with **33 Dutch-style 4.5 m³ underground bins at 11 sites**. Every site has three co-located bins connected to one ESP32; the competition hardware prototype represents one of those sites.

The portal is decision support, not an autonomous municipal dispatch system. Site coordinates, demand, vehicle performance, and sensor behavior are configurable planning assumptions.

## Implemented system

- ESP32 firmware for three ultrasonic and three pressure/load channels, including bounded buffering and retry logging.
- Raspberry Pi MQTT/JSON gateway, calibration, conservative sensor fusion, SQLite storage, and CSV export.
- A hidden physical fill state separated from noisy observations, with bias, drift, outliers, missing values, confidence, and freshness checks.
- A chronological 48-hour forecaster that receives observed data only; hidden state is used only to construct training labels and score simulation outcomes.
- Three operator decisions: `COLLECTION_REQUIRED`, `INSPECTION_REQUIRED`, and `NO_COLLECTION_REQUIRED`.
- Capacity-feasible OR-Tools routes over cached OSRM road distance and duration matrices, with a deterministic fallback.
- Minute-level SimPy execution with travel, per-bin service, unloading, turnaround, traffic, payload-dependent fuel, and overflow during an active trip.
- A fair fixed baseline whose first collection occurs after its configured interval, plus a three-day common warm-up report for both policies.
- Five paired scenarios: base, high demand, traffic, sensor failure, and reduced truck capacity.
- Eleven consolidated site markers, three-bin status popups, bounded Subang Jaya maps, route layers, and mock truck tracking.
- Strict 33-bin CSV/JSON intake, a local-only mock dispatch record, and a full decision audit.

## Fixed physical design

| Item | Prototype value |
| --- | --- |
| Underground bins | 33 total; 4.5 m³ each |
| Service sites | 11; exactly 3 bins per site |
| Controller topology | 1 ESP32 per 3-bin site |
| Physical competition model | 1 ESP32 and 3 bins |
| Depot | Provisional Subang Jaya/Batu Tiga point at 3.06192, 101.55272 |
| Vehicle archetype | VDL Maxxum/UGS underground-container collection system |
| Route payload assumption | 9,000 kg, maximum 2 trips per calendar day |

No bins, sites, or trucks were added by the optimization work.

## Locked finding

The corrected 30-pair base result does **not** show routine fuel savings. After the equal three-day warm-up, smart routing used 23.79% more road distance and 18.90% more fuel than the fixed schedule. Its value appears under stress: it reduced overflow incidents by 95.64% at 1.45× demand and 98.60% at 0.65× truck capacity, at the cost of more trips and fuel. Treat it as an emergency-capacity decision aid; keep fixed service as the field safeguard until a calibrated hybrid policy passes an untouched field evaluation. See [FINAL_RESULTS.md](FINAL_RESULTS.md).

## Run on Windows

From the repository root, run `Setup-BinSight-Admin.cmd` once and then `Start-BinSight-Admin.cmd`. For development from this directory:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m binsight.cli prepare
.\.venv\Scripts\python.exe -m binsight.cli run --replications 30
.\.venv\Scripts\streamlit.exe run app.py
```

Ordinary reruns use the committed road matrices. Use `--refresh-map` only when deliberately refreshing OSRM inputs.

## Predictive-AI snapshot contract

Open **Route input** and upload CSV/JSON, paste JSON, or use the built-in demo. Submit one row for each `UGB-001` through `UGB-033`.

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

Selecting **Send mock route to garbage truck** writes only to `data/mock_truck_dispatches.jsonl`. It does not contact a truck, driver app, MQTT broker, or municipal API.

## Raspberry Pi gateway

Process a saved controller payload:

```powershell
.\.venv\Scripts\python.exe -m gateway.binsight_gateway `
  --calibration hardware/controller_calibration.example.json `
  --input-json hardware/example_payload.json `
  --database data/binsight_gateway.sqlite3 `
  --export-csv data/model_readings.csv
```

For MQTT mode, set `BINSIGHT_MQTT_HOST`, `BINSIGHT_MQTT_PORT`, `BINSIGHT_MQTT_USER`, and `BINSIGHT_MQTT_PASSWORD`, then replace `--input-json ...` with `--mqtt`.

## Firmware

Open `firmware/esp32_binsight` in PlatformIO, copy `include/secrets.example.h` to `include/secrets.h`, enter Wi-Fi/MQTT settings, and calibrate all six channels. The source uses a 1,024-byte MQTT buffer; the harness verifies that a maximum three-bin payload and packet fit without truncation. PubSubClient publishes at QoS 0, so firmware retries and the local bounded queue reduce loss but do not provide broker acknowledgement. A field deployment requiring QoS 1 must use a client library with acknowledged publish support.

## Evidence and documentation

- [SITING_PLAN.md](SITING_PLAN.md) — capacity equation and preliminary coordinates.
- [METHODS.md](METHODS.md) — simulation, observation, forecast, routing, fuel, and inference method.
- [FINAL_RESULTS.md](FINAL_RESULTS.md) — locked 30-pair base and stress results.
- [ROUTING_REPORT.md](ROUTING_REPORT.md) — complete Focus Area C implementation report.
- [Final routing report (DOCX)](reports/BinSight_Routing_Subsystem_Report_Improved.docx) and [PDF](reports/BinSight_Routing_Subsystem_Report_Improved.pdf) — generated competition-facing report.
- [ROUTE_DISPLAY.md](ROUTE_DISPLAY.md) — map and tracking behavior.
- [RESEARCH_BRIEF.md](RESEARCH_BRIEF.md) — external evidence versus prototype assumptions.
- [hardware/SENSOR_CONTRACT.md](hardware/SENSOR_CONTRACT.md) — controller/gateway data contract.
- [Admin portal design system](../docs/ADMIN_PORTAL_DESIGN_SYSTEM.md) — interface tokens and QA record.
- [Operator guide](../docs/HOW_TO_OPERATE_ADMIN_PORTAL.md) — input, routing, dispatch, and troubleshooting.
- [Competition compliance audit](../docs/COMPETITION_COMPLIANCE_AUDIT.md) — question-paper coverage, proposal contradictions, and remaining deliverables.

The final experiment artifacts are in `artifacts/`, including replication-level metrics, paired effects, forecasts, routes, seeds, and run provenance.

## Reproducibility boundary

The numerical results are synthetic planning evidence, not measured Malaysian municipal performance. Normal map viewing uses third-party tiles; deployment should use a suitable hosted provider or self-hosted OSM stack and must comply with attribution and tile-use rules. Validate coordinates, bin-density calibration, vehicle fuel behavior, service time, MQTT reliability, and operator procedures in a physical pilot before operational use.
