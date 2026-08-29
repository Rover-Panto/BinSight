# How to operate the admin portal

Use this guide to turn one telemetry snapshot into a reviewed, capacity-feasible, economically justified route proposal and a local mock dispatch. The portal is a prototype: it does not authenticate an operator, contact a real vehicle, or claim measured municipal performance.

## Start the portal

From the repository root:

```powershell
.\Start-BinSight-Admin.cmd
```

Open `http://127.0.0.1:8501/`. Four destinations are available:

| Destination | Purpose |
| --- | --- |
| Route input | Validate legacy 33-bin or versioned three-bin pilot telemetry and build a durable route proposal |
| Operations | Review base/stress simulation KPIs and representative routes |
| Mock live tracking | Replay a representative truck route and service timeline |
| Dispatch log | Review locally recorded mock dispatch payloads |

## Choose the operating profile and input

The `competition-simulation` profile uses the 33 canonical `UGB-*` bins. The `physical-pilot` profile uses the explicit three-bin mapping in `admin-portal/config/bin_registry.json`. Hardware channel IDs are never inferred from row order or generated simulation controller names.

The preferred JSON contract is telemetry-routing 2.1. It carries envelope schema/profile/source metadata and, for every fill channel, event kind, registry-matching bin type/waste stream, event identity, acquisition time, receipt time, clock status, channel availability/quality and forecast status. Version 2.0 remains a validated general-waste legacy normalization. Unknown/stale/offline values remain unknown; receipt time is never substituted for acquisition time. Use `admin-portal/tests/fixtures/telemetry_v2_valid.json` as the valid replay fixture.

Legacy competition input remains supported for demonstration:

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

## Read the decision and trip value

Select **Check bins and build collection route**. The result is one of three states:

- **Collection required** — at least one bin is a mandatory service-level/emergency stop, or the optimizer finds a positive-value optional route. Low-confidence urgent bins remain selected and are flagged for review.
- **Inspection required** — the system cannot safely declare the site clear because data is stale, missing, low confidence, or inconsistent, but no trustworthy urgent trigger currently requires collection.
- **No collection required** — no mandatory stop exists and the best feasible optional trip has non-positive net value, so the operator should wait or merge it into a later route.

The audit table shows the current reading, last-valid reading and age where used, conservative upper fill/weight, projected fill, overflow probability, forecast status, avoided-overflow benefit, low-fill cost, reason and selected state. The route summary exposes the policy/model/network versions, fixed/distance/time/service costs and net value in provisional metre-equivalent (`m-eq`) units. The low-fill term is `100 × max(0, 50 − conservative_fill)` with the current configuration. Never override an inspection warning merely to create a demonstration route.

## Review a collection route

When a route is proposed:

1. Check selected bins, trips, road distance, planned load, and all warnings.
2. Confirm that every trip begins and ends at `DEPOT`.
3. Confirm each trip is within the 9,000 kg mass limit, compacted-volume limit, duration limit and the maximum two trips per calendar day.
4. Inspect the 11 site markers. Each popup lists all three co-located bins; the badge reports how many need attention.
5. Use the layer control to distinguish route, site status, and truck layers.
6. Treat an unavailable required bin or a capacity warning as a blocked plan requiring an operator/fleet decision.

The old 5 km sibling rule is retired. The dynamic optimizer keeps service-level/emergency stops mandatory and assigns every optional stop a skip penalty equal to its avoided-overflow value. It serves that stop only when the joint route improves the objective after fixed-trip, road-distance, travel-time, service-time and low-fill costs. The wait alternative therefore competes directly with sending a truck. Exact provisional coefficients and limitations are in `admin-portal/DYNAMIC_ROUTING_MODEL.md`.

## Accept, cancel, complete and mock-dispatch a plan

Each calculation creates an immutable `DRAFT` in:

```text
admin-portal/data/routing_plans.sqlite3
```

Accept or cancel the exact plan ID after review. Only an accepted plan can be mock-dispatched, and repeated sends return the same transactional dispatch record. Completing/cancelling creates a lifecycle transition instead of rewriting the proposal. This is a local audit record only; it does not publish MQTT, send GPS coordinates, notify a driver, or call a municipal service. The old JSONL file remains read-only historical input.

## Run one plan or the controlled planner

From `admin-portal/`:

```powershell
.\.venv\Scripts\python.exe -m binsight.cli plan-once --snapshot .\tests\fixtures\telemetry_v2_valid.json --profile physical-pilot
.\.venv\Scripts\python.exe -m binsight.cli planner-start --snapshot .\tests\fixtures\telemetry_v2_valid.json --profile physical-pilot
.\.venv\Scripts\python.exe -m binsight.cli planner-status
.\.venv\Scripts\python.exe -m binsight.cli planner-stop
```

The runner is opt-in, owns a single-process lock and only creates drafts. Identical event sets within one 15-minute planning bucket resolve to the same plan; a later bucket creates a new immutable proposal. If telemetry changes after an accepted trip starts, the planner API freezes the current leg, deducts its committed capacity and can create a separate suffix draft for the remaining route. It never mutates the accepted plan.

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

The forecast panel reports a purged train/calibration/holdout evaluation, including q90 interval coverage, coverage error, pinball loss and interval width. The 48-hour purge prevents a target horizon from leaking across the boundary. Simulation outcomes remain synthetic planning evidence.

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
.\.venv\Scripts\python.exe -m binsight.cli run --artifact-set dynamic_v2 --replications 30 --parallel-workers 4
```

### Snapshot rejected

For legacy input, check 33 unique IDs, the shared timezone-aware timestamp, freshness, ranges, risk labels and Boolean confidence values. For telemetry-routing 2.1, validate the envelope/profile, `fill_observation` event kind, registered hardware/type/stream mappings, event identities, per-bin acquisition/receipt times, channel availability and forecast status. Missing sensor or forecast values remain explicit unknowns and may require inspection; they are never turned into zero or a safe forecast.

### Straight route line appears

OSRM display geometry was unavailable. The stop order, distance, and duration still come from the cached road matrices; only the visual line fell back.

### Plan acceptance or mock dispatch disabled

A required bin is unserved, a route violates mass/volume/duration/daily-trip constraints, the plan has a blocking validation error, or the plan is not in the required lifecycle state. The prototype deliberately does not add a truck or bin to bypass the budget.

### Stop or roll back the planner

Run `python -m binsight.cli planner-stop` and confirm `planner-status` is stopped. Preserve `routing_plans.sqlite3` together with its `-wal`/`-shm` files before recovery. Do not delete or reset an unknown schema. To roll back behavior, stop the runner and return to a reviewed application revision; existing immutable plan/audit data remains readable and must not be rewritten.

### Map will not pan outside Subang Jaya

This is intentional. Use **Reset map** to return to the pilot extent. The minimum/maximum zoom are also bounded.

### Playwright cannot be found

Run `pnpm install` in `web/`, set `NODE_PATH` as shown, and verify Chrome's executable path. QA captures are local artifacts and are not committed.
