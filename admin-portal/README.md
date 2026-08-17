# BinSight Focus Area C - Subang Jaya

This directory is the independent operations and routing portal inside the shared BinSight repository. It does not import the React citizen store, write to `binsight-demo-v1`, or require the citizen frontend to be running.

From the repository root, run `Setup-BinSight-Admin.cmd` once and then `Start-BinSight-Admin.cmd`. Direct Python and Streamlit commands below remain supported for development.

BinSight is a reproducible Focus Area C prototype for **500 households and 20 commercial units in Subang Jaya, Selangor**. It combines three-bin ESP32 sensing, a Raspberry Pi gateway, fill forecasting, OpenStreetMap-road routing, and a paired 30-day discrete-event simulation.

## Final design decision

- **33 Dutch-style 4.5 m3 underground bins**.
- **11 sites**, each with exactly **3 bins and 1 ESP32**.
- Physical competition prototype: **1 ESP32 + 3 bins**.
- Provisional depot: Subang Jaya/Batu Tiga waste-transfer feature at 3.06192, 101.55272.
- Vehicle archetype: VDL Maxxum/UGS underground-container collection system; 22 m3 body and 1,500 kg lift reference, with a conservative 9,000 kg route-payload assumption.

Read [SITING_PLAN.md](SITING_PLAN.md) first for the sizing equation, exact preliminary locations, and construction checks.

## What is implemented

- Validated configuration and exact three-bin controller topology.
- Demand-balanced, capacity-checked plan for all 11 sites.
- Cached OSRM matrix over OpenStreetMap roads and representative route geometries.
- Synthetic but locally scaled hourly waste generation.
- Chronological fill-growth forecasting with a naive benchmark.
- Fixed and smart collection policies using common random numbers.
- Capacity-constrained OR-Tools routing with a recorded deterministic fallback.
- 30 paired replications, confidence intervals, and paired sign-flip tests.
- Streamlit/Folium dashboard.
- Predictive-AI CSV/JSON snapshot input with strict 33-bin validation.
- Operator-facing collection decision, OSM route preview, and local mock-truck dispatch log.
- ESP32 PlatformIO firmware for three ultrasonic plus three pressure channels.
- Raspberry Pi MQTT/JSON gateway, calibration, conservative sensor fusion, SQLite, and CSV export.

## Important operational result

The revised safety-constrained smart policy matched fixed service at **zero modeled overflow** in a fresh 30-replication holdout while reducing road distance, fuel, and tailpipe CO2 by **5.08%**, trips by **7.37%**, and stops by **14.38%**. It uses a 20-hour emergency overflow horizon, allows critical bins to override the normal dispatch gap, bundles useful co-located bins, and limits optional pickups by incremental road distance. These are synthetic planning results, not authorization for autonomous municipal control; real telemetry and operator validation are still required.

## Run on Windows

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m binsight.cli prepare
.\.venv\Scripts\python.exe -m binsight.cli run --replications 30
.\.venv\Scripts\streamlit.exe run app.py
```

The cached road-service matrix makes normal reruns independent of the public OSRM service. Use `--refresh-map` only when you deliberately want to refresh the OSM routing data.

## Predictive AI input and mock dispatch

Open the **AI input & dispatch** tab in the Streamlit app. Upload CSV/JSON, paste JSON, or use the built-in working demo. A downloadable 33-bin CSV template is available in the tab.

The required fields are:

```text
timestamp,bin_id,fill_pct,weight_kg,time_to_overflow_hours,risk_level,confidence_flag
```

- Submit exactly one row for each `UGB-001` through `UGB-033`.
- Use one ISO 8601 timestamp with a timezone for the whole snapshot.
- `fill_pct` is 0–100 and `weight_kg` is 0–1,500 kg.
- `time_to_overflow_hours` is zero or greater.
- `risk_level` is `low`, `medium`, `high`, or `critical`.
- `confidence_flag` is `true` or `false`.

The prototype can then create a capacity-feasible route and record a mock send to `MOCK-TRUCK-01` in `data/mock_truck_dispatches.jsonl`. This is deliberately local-only; no real vehicle or municipal service is contacted.

## Raspberry Pi gateway

Process a saved controller payload:

```powershell
.\.venv\Scripts\python.exe -m gateway.binsight_gateway `
  --calibration hardware/controller_calibration.example.json `
  --input-json hardware/example_payload.json `
  --database data/binsight_gateway.sqlite3 `
  --export-csv data/model_readings.csv
```

For MQTT mode, set `BINSIGHT_MQTT_HOST`, `BINSIGHT_MQTT_PORT`, `BINSIGHT_MQTT_USER`, and `BINSIGHT_MQTT_PASSWORD`, then replace `--input-json ...` with `--mqtt`. See [hardware/SENSOR_CONTRACT.md](hardware/SENSOR_CONTRACT.md) and [hardware/WIRING.md](hardware/WIRING.md).

## ESP32 firmware

Open `firmware/esp32_binsight` in PlatformIO, copy `include/secrets.example.h` to `include/secrets.h`, enter the Wi-Fi/MQTT settings, and calibrate every channel. PlatformIO was not installed on the analysis workstation, so the firmware source was statically inspected but not falsely reported as compiled on hardware.

## Key files

- `../docs/ADMIN_PORTAL_DESIGN_SYSTEM.md` - UI tokens, layouts, states, accessibility, QA evidence, and limitations.
- `../docs/HOW_TO_OPERATE_ADMIN_PORTAL.md` - operator workflow, input contract, verification, and troubleshooting.
- `SITING_PLAN.md` - count, capacity proof, and locations.
- `ROUTE_DISPLAY.md` - route-map legend and captured dashboard preview.
- `RESEARCH_BRIEF.md` - evidence and assumptions.
- `METHODS.md` - model and statistical method.
- `FINAL_RESULTS.md` - locked holdout results and decision.
- `DEVELOPMENT_LOG.md` - tuning history and safeguards.
- `config.json` - all scenario values and policy thresholds.
- `app.py` - dashboard.
- `binsight/` - model, forecasting, routing, simulation, and sensor fusion.
- `firmware/esp32_binsight/` - three-bin controller firmware.
- `gateway/` - Raspberry Pi ingestion service.
- `artifacts/` - final tables, model, routes, and provenance.

## Reproducibility boundary

The model is a planning experiment, not a claim of measured municipal performance. Site coordinates are preliminary; commercial generation, waste density, vehicle payload, compaction, and fuel rate remain configurable assumptions. Public OSRM is appropriate for the prototype, but deployment should pin a Malaysian OSM extract and self-host the routing backend.
