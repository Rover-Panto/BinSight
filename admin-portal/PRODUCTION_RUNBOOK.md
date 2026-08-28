# BinSight local operations runbook

## Supported operating mode

This release is a **single-laptop, localhost-only demonstration**. It binds the
Streamlit server to `127.0.0.1`, stores state on that laptop, and uses mock truck
dispatch. Do not expose port 8501 to the network or describe mock acceptance as
a live collection order.

The routing demonstration contains 11 sites and 44 bins: general waste,
plastic, metal, and glass at each site. Dry-recycling routes unload at the
provisional MBSJ USJ 9 Recycling Centre; general-waste routes unload at the
provisional waste depot.

The configured fleet is exactly two vehicles: `GENERAL-01` is based at the
waste depot and `RECYCLING-01` is a three-compartment truck based at the
recycling facility. They can dispatch independently. No third or surge vehicle
is created by the demonstration.

## First-time setup

From `admin-portal` in PowerShell:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m binsight.cli health
```

Start only when the final command reports `READY`.

## Start the website

Double-click `Start-BinSight-Admin.cmd`, or run:

```powershell
..\Start-BinSight-Admin.cmd
```

Open `http://127.0.0.1:8501`. Startup runs the same readiness checks and writes
their JSON result to `data/startup-health.json` before Streamlit launches.

## Daily readiness check

```powershell
.\.venv\Scripts\python.exe -m binsight.cli health
```

The check validates:

- the 44-bin/four-material configuration;
- base and recycling distance/duration matrices;
- depot, recycling facility, and 11 service points;
- SQLite schema, WAL mode, and quick integrity status; and
- writable local data storage.

If any check fails, leave dispatch in mock mode and resolve the reported item
before demonstrating the route.

## Back up local state

Close active demonstrations if practical, then run:

```powershell
.\.venv\Scripts\python.exe -m binsight.cli backup-state
```

The command creates a timestamped directory under `data/backups/` containing a
consistent SQLite backup plus the available JSON/JSONL planner and mock-dispatch
state. Backups, logs, and live state are deliberately excluded from Git.

## Logs and state

- Application log: `data/logs/binsight-admin.log`
- Readiness result: `data/startup-health.json`
- Planning database: `data/routing_plans.sqlite3`
- Mock dispatch ledger: `data/mock_truck_dispatches.jsonl`
- Last valid readings: `data/last_valid_sensor_readings.json`
- Planner controls: `data/planner-control/`

The application log rotates locally. When reporting a failure, retain the
timestamp, the friendly error reference shown in the UI, and the matching log
entry; do not publish tokens or machine-specific secrets.

## Recovery

1. Stop Streamlit with `Ctrl+C` in its terminal.
2. Run the readiness check.
3. If state corruption is reported, preserve the current `data/` folder and
   restore only from a known-good backup after verifying its contents.
4. Restart with `Start-BinSight-Admin.cmd` and refresh the localhost page.

Do not delete the database, dispatch ledger, or planner-control directory as a
routine troubleshooting step; they are audit state.

## Map behaviour

The map uses public OpenStreetMap tiles with a CARTO fallback and does not need
an API key. Internet access is needed for those background tiles. Site,
facility, and route overlays still render against a light fallback background
if public tiles are unavailable.

The live-tracking tab uses completed routes from the current paired 30-day
simulation. Select either specialized truck. Marker fill is forecast
interpolation for playback: grey is empty; the gauge height is the fullest bin
at that four-bin site; and the color approaches red as fill approaches 100%.
It is not a live sensor feed.

## Gates before real operations

This demonstration is not yet approved for unattended or live dispatch. Before
that scope changes:

- add and validate the fourth physical sensor channel for metal;
- confirm both unloading facilities accept the planned vehicle and materials,
  including access and operating hours;
- calibrate material density and fill-rate assumptions with field data;
- run a pre-registered, matched-seed evaluation with enough replications to
  quantify overflow, wasteful-pickup, distance, and service trade-offs;
- integrate authenticated dispatch and positive acknowledgement; and
- add operator authentication and network hardening before changing the
  localhost bind address.

The current bounded run has two paired 30-day replications in each of eleven
scenarios. It is a functional check only. It improved several overflow and
wasteful-pickup outcomes but increased distance and trips, so it does not
establish that the smart policy meets all objectives.
