# Admin Routing and KPI Integration

## Scope

The admin area will let an authorised operator inspect smart-bin status, compare a fixed collection baseline with a priority route, review route stops, and track simulation KPIs. Keep resident tasks in the existing citizen shell.

Use `/admin` as the route prefix. Recommended routes:

| Route | Purpose |
| --- | --- |
| `/admin` | Operations overview |
| `/admin/bins` | Bin status, confidence, health, and last reading |
| `/admin/routes` | Fixed-baseline and priority-route comparison |
| `/admin/routes/:id` | Route stops, assumptions, and simulated outcome |
| `/admin/kpis` | KPI definitions, comparison windows, and trends |
| `/admin/reports` | Citizen reports relevant to operations |

## Phase 1 independent-service boundary

The first collaborator integration keeps the existing Streamlit portal under `admin-portal/` and serves it at `http://127.0.0.1:8501/`. The React citizen frontend continues at `http://127.0.0.1:5173/`. This is a temporary monorepo boundary, not the final `/admin` deployment architecture.

- Either application can start, stop, test, and build without the other.
- No citizen route, mobile-navigation item, store type, or persistence migration is changed.
- No cross-application API, iframe, proxy, authentication handoff, or shared browser storage is introduced.
- The existing `/admin` route plan remains the target for a later authenticated gateway or React admin shell.
- Streamlit outputs must continue to identify simulations and mock truck dispatches accurately.

The competition simulation keeps underground-bin IDs `UGB-001` through `UGB-033`. The versioned registry explicitly maps physical `PILOT-BIN-##` hardware IDs to canonical routing IDs without renaming historical simulation records. Physical controller topology and simulated co-located service grouping are separate profiles.

The telemetry-routing 2.1 contract preserves event kind, bin type/waste stream, event/boot identity, per-bin acquisition time, receipt time, source mode, channel availability, quality, forecast status and decision provenance. Live API controls remain gated; fixtures and recorded replay use the same normalization path as the future API client. Legacy 2.0 remains general-waste-fill only.

Validated `fill_observation` events from the one general-waste and two recycling bins may enter overflow prediction and routing. Recycling-return recognition/session events have separate IDs, contracts and storage and are rejected by event kind. General-waste bins do not identify materials, and fill does not decide recycling acceptance. Route trips keep incompatible waste streams separate.

Do not add admin links to the citizen mobile navigation. Use a separate admin shell and a role gate. A mock role is acceptable for the prototype, but the interface must label it as simulated access.

## Code boundary

For a future integrated React admin shell, place admin code under `web/src/admin/`:

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
- Smart bin: `BIN-###`
- Route plan: `ROUTE-YYYYMMDD-##`
- Route run: `RUN-YYYYMMDD-##`
- KPI snapshot: `KPI-YYYYMMDD-##`

Do not use array positions as IDs. Never regenerate an existing ID during a migration.

## Proposed admin contracts

```ts
type SimulationMode = 'fixed-baseline' | 'priority-optimised'

interface BinReading {
  binId: string
  recordedAt: string
  fillPercent: number
  weightKg: number
  confidence: 'high' | 'medium' | 'low'
  health: 'online' | 'degraded' | 'offline'
  overflowRisk: 'normal' | 'watch' | 'urgent'
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

The collaborator may refine these contracts. Any change must retain the units, timestamps, stable IDs, and simulation marker or document a replacement.

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
| Fuel use | Modelled litres from base driving, traffic, payload, collection-idle, and depot-idle components |
| CO2 | Modelled kilograms from fuel use and the documented emission factor |
| Contamination | Rejected recycling items divided by inspected recycling items |
| Sensing energy | Estimated watt-hours used by the sensing schedule during the window |

Do not present proposal targets as measured results. The admin UI may show target bands, but it must separate them from simulation output and name the source of each assumption.

## Route comparison

The fixed baseline represents the same bins, depot, vehicle assumptions, and time window as the priority route. A comparison is invalid when either route uses a different service area or input window. The fixed service interval and all-bin intent are fixed, but the road path is re-solved at each departure; it is a strong heuristic comparator, not a universally perfect or proven-global-optimal path.

The priority decision exposes fill, weight/availability, forecast status, time-to-overflow/risk, confidence, age, uncertainty, retained-value provenance, probability before the next opportunity, avoided-loss value, low-fill service cost, decision reason and selection category. Preserve collection required, inspection required and no collection required; collection and inspection may both be true. Optional stops may be labelled `Defer – wait or merge` when their benefit does not cover route cost. `Dynamic priority route` is the safe label; it is not a proof of global optimality.

Plans move through `DRAFT`, `ACCEPTED`, `COMPLETED` or `CANCELLED`. A new draft never overwrites an accepted route. One accepted plan can produce at most one local mock dispatch. Active-route events freeze the current leg and create a separately auditable suffix proposal.

The current mock tracking view replays saved simulation timestamps and road geometry. It is not GPS and must never be presented as a live vehicle feed. A future driver integration needs authenticated route versioning, acknowledgement, GPS freshness, cancellation, and operator override contracts.

## Pull request evidence

The admin pull request must include:

- route screenshots at desktop and mobile widths
- one fixed-versus-priority fixture with expected totals
- unit tests for KPI formulas and zero-baseline handling
- a browser test covering the admin route comparison
- confirmation that citizen login, returns, reports, image attachments, and payout tests still pass
- updates to `PROJECT_STATE.md` and `DATA_PRESERVATION.md`
- the telemetry-routing contract, registry version and live-integration gate status
