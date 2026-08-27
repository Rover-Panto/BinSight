# Admin Routing and KPI Integration

## Scope

The admin area will let an authorised operator inspect fill status across the three-bin demonstrator, compare a fixed collection baseline with a priority route, review route stops, and track simulation KPIs. Keep resident tasks in the existing citizen shell.

BinSight has two bin types across three physical bins. PR #2 produces fill telemetry for one general-waste and two recycling bins; all three are eligible routing inputs. PR #3 produces recycling item-classification and return-session events. Keep fill separate from vision decisions even when both refer to the same recycling bin.

Use `/admin` as the route prefix. Recommended routes:

| Route | Purpose |
| --- | --- |
| `/admin` | Operations overview |
| `/admin/bins` | Bin status, confidence, health, and last reading |
| `/admin/routes` | Fixed-baseline and priority-route comparison |
| `/admin/routes/:id` | Route stops, assumptions, and simulated outcome |
| `/admin/kpis` | KPI definitions, comparison windows, and trends |
| `/admin/reports` | Citizen reports relevant to operations |

Do not add admin links to the citizen mobile navigation. Use a separate admin shell and a role gate. A mock role is acceptable for the prototype, but the interface must label it as simulated access.

## Code boundary

Place admin code under `web/src/admin/`:

```text
web/src/admin/
  components/
  pages/
  model.ts
  store.tsx
  fixtures.ts
```

Do not replace `web/src/model.ts` or `web/src/store.tsx`. The citizen store contains returns, reports, payout methods, notifications, settings, and image attachments. Admin fixtures and admin UI state should use a separate storage key such as `binsight-admin-v1`.

Move a type into `web/src/shared/` only when both applications use the same meaning, units, and lifecycle. Record the move in the pull request and provide a migration when stored data changes.

## Shared identifiers

Use stable IDs across citizen and admin records:

- Waste report: `WR-####`
- Return session: `BS-####`
- General-waste hardware channel: producer ID such as `bin_01`, mapped through the registry to its existing canonical route ID
- Recycling-return station: `RRS-###`
- Route plan: `ROUTE-YYYYMMDD-##`
- Route run: `RUN-YYYYMMDD-##`
- KPI snapshot: `KPI-YYYYMMDD-##`

Do not use array positions as IDs. Never regenerate an existing ID during a migration.

## Proposed admin contracts

```ts
type SimulationMode = 'fixed-baseline' | 'priority-optimised'
type BinType = 'general-waste' | 'recycling-return'

interface GeneralWasteBinReading {
  binId: string
  binType: 'general-waste'
  recordedAt: string
  fillPercent: number
  weightKg: number | null
  confidence: 'high' | 'medium' | 'low'
  health: 'online' | 'degraded' | 'offline'
  overflowRisk: 'normal' | 'watch' | 'urgent'
}

interface RecyclingReturnEvent {
  stationId: string
  binType: 'recycling-return'
  recordedAt: string
  materialClass: 'plastic' | 'metal' | 'glass' | 'non-recyclable' | 'unknown'
  accepted: boolean
  confidence: number | null
  inferenceSource: 'grove-vision-ai-v2'
  isSimulation: true
}

interface RecyclingFillReading {
  binId: string
  binType: 'recycling-return'
  recordedAt: string
  fillPercent: number
  confidence: 'high' | 'medium' | 'low'
  health: 'online' | 'degraded' | 'offline'
  source: 'teensy-fill-sensor'
}

interface RoutePlan {
  id: string
  mode: SimulationMode
  generatedAt: string
  stopBinIds: string[]
  distanceKm: number
  estimatedFuelLitres: number
  estimatedCo2Kg: number
  isSimulation: true
}

interface KpiSnapshot {
  id: string
  periodStart: string
  periodEnd: string
  baselineRouteIds: string[]
  priorityRouteIds: string[]
  overflowIncidents: number
  unnecessaryTrips: number
  routeDistanceKm: number
  estimatedFuelLitres: number
  estimatedCo2Kg: number
  contaminationRatePercent: number | null
  sensingEnergyWh: number | null
  isSimulation: true
}
```

The collaborator may refine these contracts. Any change must retain the bin-type boundary, units, timestamps, stable IDs, and simulation marker or document a replacement. A route snapshot accepts validated fill readings from both bin types and rejects recycling inference events. The classifier must not supply, modify or validate `fillPercent`.

## KPI rules

Every KPI card and chart must show:

- metric name and unit
- measurement window
- fixed-baseline value
- priority-route value
- absolute change
- percentage change when the baseline is non-zero
- data completeness or unavailable state
- `Simulation` status

Use these definitions:

| KPI | Definition |
| --- | --- |
| Overflow incidents | Count of bins that reached the overflow threshold during the comparison window |
| Unnecessary trips | Stops where the bin remained below the agreed collection threshold |
| Route distance | Sum of simulated route-leg distance in kilometres |
| Fuel use | Modelled litres based on route distance and the documented vehicle assumption |
| CO2 | Modelled kilograms from fuel use and the documented emission factor |
| Contamination | Rejected recycling items divided by items inspected by the recycling-return station; never infer this from general-waste fill data |
| Sensing energy | Estimated watt-hours used by the sensing schedule during the window |

Do not present proposal targets as measured results. The admin UI may show target bands, but it must separate them from simulation output and name the source of each assumption.

## Route comparison

The fixed baseline represents the same three bins, depot, vehicle assumptions, and time window as the priority route. A comparison is invalid when either route uses a different service area or input window. Preserve each bin's waste stream and do not assign incompatible waste streams to one vehicle unless the simulation explicitly defines that capability.

The priority score should expose its input fields. At minimum, record fill level, time-to-overflow or risk, confidence, report urgency, and data freshness. Do not label a route as optimal unless the implementation proves optimality for the stated objective and constraints. `Priority route` is the safe default label.

## Pull request evidence

The admin pull request must include:

- route screenshots at desktop and mobile widths
- one fixed-versus-priority fixture with expected totals
- unit tests for KPI formulas and zero-baseline handling
- a browser test covering the admin route comparison
- confirmation that citizen login, returns, reports, image attachments, and payout tests still pass
- updates to `PROJECT_STATE.md` and `DATA_PRESERVATION.md`
