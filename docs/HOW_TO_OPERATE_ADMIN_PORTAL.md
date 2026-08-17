# How to operate the admin portal

Use this guide to turn one predictive-AI snapshot into a reviewed, capacity-feasible collection plan and a local mock dispatch. The portal is a prototype: it does not authenticate an operator, contact a real vehicle, or claim measured municipal performance.

## Start the portal

From the repository root:

```powershell
.\Start-BinSight-Admin.cmd
```

Open `http://127.0.0.1:8501/`. Four destinations are available:

| Destination | Purpose |
| --- | --- |
| Route input | Validate a 33-bin snapshot and build a collection/inspection decision |
| Operations | Review base/stress simulation KPIs and representative routes |
| Mock live tracking | Replay a representative truck route and service timeline |
| Dispatch log | Review locally recorded mock dispatch payloads |

## Prepare the snapshot

Submit one row for every bin from `UGB-001` through `UGB-033`. All rows use the same timezone-aware timestamp.

| Field | Requirement | Example |
| --- | --- | --- |
| `timestamp` | ISO 8601 with timezone; shared, fresh, not materially future-dated | `2026-08-17T10:00:00+08:00` |
| `bin_id` | Every ID exactly once | `UGB-001` |
| `fill_pct` | 0–100 ultrasonic estimate, or missing under degraded-sensor handling | `82.4` |
| `weight_kg` | 0–1,500 kg load estimate, or missing under degraded-sensor handling | `442.8` |
| `time_to_overflow_hours` | Predictive estimate ≥ 0 | `30` |
| `risk_level` | `low`, `medium`, `high`, or `critical` | `high` |
| `confidence_flag` | Boolean | `true` |

```csv
timestamp,bin_id,fill_pct,weight_kg,time_to_overflow_hours,risk_level,confidence_flag
2026-08-17T10:00:00+08:00,UGB-001,82.4,442.8,30,high,true
```

The **Required input format** panel provides a blank template and a working JSON example. Upload CSV/JSON, paste JSON, or use the built-in demo.

## Read the decision

Select **Check bins and build collection route**. The result is one of three states:

- **Collection required** — at least one bin crosses a fill, overflow-time, high-risk, or critical trigger. Low-confidence urgent bins remain selected and are flagged for review.
- **Inspection required** — the system cannot safely declare the site clear because data is stale, missing, low confidence, or inconsistent, but no trustworthy urgent trigger currently requires collection.
- **No collection required** — all required fields are sufficiently trustworthy and no collection trigger is active.

The audit table shows the current reading, last-valid reading and age where used, conservative upper fill/weight, risk, reason, and selected state. Never override an inspection warning merely to create a demonstration route.

## Review a collection route

When collection is required:

1. Check selected bins, trips, road distance, planned load, and all warnings.
2. Confirm that every trip begins and ends at `DEPOT`.
3. Confirm each trip is within the 9,000 kg payload and that no more than two trips are planned for the calendar day.
4. Inspect the 11 site markers. Each popup lists all three co-located bins; the badge reports how many need attention.
5. Use the layer control to distinguish route, site status, and truck layers.
6. Treat an unavailable required bin or a capacity warning as a blocked plan requiring an operator/fleet decision.

The optional-stop rule accepts useful siblings first and then a nearby candidate only when its **incremental road-route cost** is no more than 5 km, the complete plan stays within the soft distance budget, and capacity remains feasible. It is not a 5 km circle around a critical bin.

## Record a mock dispatch

Select **Send mock route to garbage truck** only after review. The action appends one JSON line to:

```text
admin-portal/data/mock_truck_dispatches.jsonl
```

This is a local audit record only. It does not publish MQTT, send GPS coordinates, notify a driver, or call a municipal service. Open **Dispatch log** to inspect or download the payload.

## Use mock live tracking

Open **Mock live tracking** and select a scenario, policy, and representative dispatch. The map replays the saved minute-by-minute chronology:

- the truck moves along road geometry during travel;
- it pauses at each bin for the configured service duration;
- the site's state becomes completed only when service finishes;
- it returns to the depot for unloading and turnaround; and
- play/pause, reset, slider, and speed controls change only the replay.

The tracking view is not live GPS. With reduced-motion enabled, pulsing animation is removed and manual timeline controls remain available.

## Review simulation evidence

Open **Operations** and choose a scenario and metric scope:

- **Raw** includes the entire terminating 30-day run.
- **Post warm-up** excludes the first three days equally for both policies.

KPI cards and the paired table show the fixed and smart means, beneficial-direction effect, 95% interval, and sign-flip result. Positive effects are favorable; negative effects mean the smart policy was worse for that metric. Base and stress scenarios must not be averaged into one claim.

The forecast panel reports 48-hour holdout mean absolute error (MAE) in percentage points; lower is better. Simulation outcomes remain synthetic planning evidence.

## Verification

Run the Python suite from `admin-portal/`:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

With the portal running, execute both browser workflows:

```powershell
$env:NODE_PATH = (Resolve-Path ..\web\node_modules\.pnpm\node_modules).Path
$env:DASHBOARD_URL = "http://127.0.0.1:8501"
$env:BROWSER_EXECUTABLE = "C:\Program Files\Google\Chrome\Application\chrome.exe"
node .\scripts\qa_dispatch_ui.js .\artifacts\ui-qa-local
node .\scripts\qa_maps_tracking.js .\artifacts\ui-qa-maps
```

The checks cover the demo decision/dispatch workflow, 11 consolidated markers, three-bin popup contents, bounds/zoom/no-wrap behavior, tracking movement and service completion, reduced motion, browser errors, and horizontal overflow at 1440×900, 768×1024, and 390×844.

## Troubleshooting

### Project artifacts are missing

```powershell
.\.venv\Scripts\python.exe -m binsight.cli run --replications 30
```

### Snapshot rejected

Check the 33 unique IDs, shared timezone-aware timestamp, timestamp freshness, ranges, risk labels, and Boolean confidence values. Missing sensor values are permitted only through the safe degraded-data path; missing predictive fields are rejected.

### Straight route line appears

OSRM display geometry was unavailable. The stop order, distance, and duration still come from the cached road matrices; only the visual line fell back.

### Mock dispatch disabled

A required bin is unserved, daily payload/trip capacity is exceeded, or the plan has a blocking validation error. The prototype deliberately does not add a truck or bin to bypass the budget.

### Map will not pan outside Subang Jaya

This is intentional. Use **Reset map** to return to the pilot extent. The minimum/maximum zoom are also bounded.

### Playwright cannot be found

Run `pnpm install` in `web/`, set `NODE_PATH` as shown, and verify Chrome's executable path. QA captures are local artifacts and are not committed.
