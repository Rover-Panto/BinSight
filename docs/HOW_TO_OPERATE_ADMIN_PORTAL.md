# How to Operate the Admin Portal

Use this guide to turn one complete predictive-AI snapshot into a reviewed, capacity-feasible collection route and a local mock dispatch. For colors, layouts, states, and implementation details, see the [Admin Portal Design System Reference](ADMIN_PORTAL_DESIGN_SYSTEM.md).

## Prerequisites

- Windows with Python 3.12.
- The repository checked out locally.
- The admin portal installed with `Setup-BinSight-Admin.cmd`.
- All committed artifacts present under `admin-portal/artifacts/`.

Start the portal from the repository root:

```powershell
.\Start-BinSight-Admin.cmd
```

Open `http://127.0.0.1:8501/`. The **Route input** destination should be selected first and should show **Waiting for a bin snapshot**.

## Prepare the predictive snapshot

Submit exactly one row for each bin from `UGB-001` through `UGB-033`. Every row must use the same ISO 8601 timestamp with a timezone.

| Field | Type and constraint | Example |
| --- | --- | --- |
| `timestamp` | ISO 8601 timestamp with timezone; identical in all 33 rows | `2026-08-17T10:00:00+08:00` |
| `bin_id` | Each ID `UGB-001` to `UGB-033` exactly once | `UGB-001` |
| `fill_pct` | Number from 0 to 100 | `82.4` |
| `weight_kg` | Number from 0 to 1,500 | `442.8` |
| `time_to_overflow_hours` | Number greater than or equal to zero | `30` |
| `risk_level` | `low`, `medium`, `high`, or `critical` | `high` |
| `confidence_flag` | Boolean `true` or `false` | `true` |

CSV example:

```csv
timestamp,bin_id,fill_pct,weight_kg,time_to_overflow_hours,risk_level,confidence_flag
2026-08-17T10:00:00+08:00,UGB-001,82.4,442.8,30,high,true
```

The **Required input format** panel in the portal provides a blank 33-bin CSV and a complete working JSON example.

## Build and review a route

1. Select one input method: **Upload CSV or JSON**, **Paste JSON**, or **Use built-in demo**.

2. Provide the data. The built-in demo is useful for a presentation because it includes critical, high-risk, co-located, nearby, and low-confidence examples.

3. Select **Check bins and build collection route**.

4. Read the decision state:

   - **Bin collection required** means at least one bin is high/critical risk, is predicted to overflow within 48 hours, or is at least 65% full.
   - **No collection required** means no current bin crosses those configured triggers, so the portal does not create a truck route.

5. If collection is required, review all four summary values: selected bins, truck trips, road distance, and planned load.

6. Inspect the route map and selection table. Red bins are required; amber bins are useful co-located pickups; teal bins are efficient nearby pickups; gray bins can wait.

7. Resolve every warning before mock dispatch:

   - A low-confidence reading requires operator review.
   - A measured weight above 540 kg indicates a nominal-capacity issue.
   - High fill with near-zero weight indicates a likely sensor problem.
   - Required bins beyond daily truck capacity block the mock-send control.

8. Confirm each trip starts and ends at `DEPOT` and remains within the 9,000 kg truck payload. The planner permits at most two trips for the snapshot.

## Record a mock dispatch

Select **Send mock route to garbage truck** only after reviewing the map, warnings, and loads.

The button writes one JSON line to:

```text
admin-portal/data/mock_truck_dispatches.jsonl
```

It does not contact a truck, driver, municipal system, MQTT broker, or external API. A successful action displays the mock vehicle `MOCK-TRUCK-01` and a generated dispatch ID.

Open **Dispatch log** to review the record, download the latest JSON payload, or inspect the full payload in the page.

## Review simulation evidence

Open **Operations** to inspect the current 30-day simulation artifacts:

- KPI cards report change relative to the fixed policy in each metric's beneficial direction.
- The map compares representative fixed and smart road routes.
- Red dots identify individual bins selected in the representative smart event.
- Forecast validation reports tree-model and naive-model mean absolute error (MAE); lower is better.
- The paired table shows fixed and smart means, confidence-interval bounds, and paired sign-flip p-values.

Treat these values as configured simulation evidence, not measured field performance.

## Verification

Run the Python test suite from `admin-portal/`:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

To repeat the browser workflow, first start the portal. Install the citizen-app Node dependencies, then expose pnpm's Playwright package to the standalone QA script:

```powershell
$qaOutput = ".\artifacts\ui-qa-local"
New-Item -ItemType Directory -Force -Path $qaOutput | Out-Null
$env:NODE_PATH = (Resolve-Path ..\web\node_modules\.pnpm\node_modules).Path
$env:DASHBOARD_URL = "http://127.0.0.1:8501"
$env:BROWSER_EXECUTABLE = "C:\Program Files\Google\Chrome\Application\chrome.exe"
node .\scripts\qa_dispatch_ui.js $qaOutput
```

The script checks the demo route, mock send, dispatch log, Operations page, browser errors, and horizontal overflow at 1440x900, 768x1024, and 390x844. It restores the dispatch log after the run.

## Troubleshooting

### The page asks for project artifacts

Generate them from `admin-portal/`:

```powershell
.\.venv\Scripts\python.exe -m binsight.cli run --replications 30
```

### The snapshot is rejected

- Confirm there are exactly 33 rows.
- Remove duplicate bin IDs and add any missing ID.
- Use one identical timestamp in every row.
- Include an explicit timezone such as `+08:00` or `Z`.
- Keep fill, weight, and overflow-time values inside their accepted ranges.
- Use only the four risk labels and Boolean confidence values.

### The route preview uses straight lines

OSRM route geometry was unavailable. The displayed stop order and distance still come from the cached OSM road matrix; the preview line alone has fallen back.

### No route was created

If the state is **No collection required**, the submitted values did not cross a required-service trigger. Check the snapshot values; do not raise them merely to force a route outside a demonstration.

### Mock dispatch is disabled

At least one required bin could not fit within the configured daily capacity. Review the warning and adjust real fleet availability or operating constraints before treating the plan as dispatchable.

### The browser QA script cannot find Playwright

Run `pnpm install` in `web/`, then set `NODE_PATH` exactly as shown in the verification command. Node.js must also be available on `PATH`. If Chrome is installed elsewhere, change `BROWSER_EXECUTABLE` to that executable; alternatively install Playwright's Chromium browser and omit the variable.
