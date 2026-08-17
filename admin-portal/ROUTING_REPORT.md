# BinSight Predictive Collection Routing Subsystem

**Technical implementation report - Focus Area C**

**Pilot scenario:** Subang Jaya, Selangor, Malaysia

**Team:** MON BLUE

**Status:** Routing design and prototype complete; final AI prediction data pending
**Prepared:** August 2026

> This report documents only the routing subsystem that has been implemented. The forecasting model is an upstream data source. Final AI predictions and field sensor records will be inserted later through the interface defined in Section 3. No field-performance claim is made from the present synthetic integration test.

## Executive summary

BinSight converts a timestamped set of current bin measurements and AI overflow-risk predictions into a capacity-feasible collection plan on Malaysian road data. The implemented Subang Jaya scenario contains 33 Dutch-style underground bins at 11 preliminary service sites, with three co-located bins monitored by one ESP32 at each site. A provisional depot near Batu Tiga/Subang Jaya is used as the start and end of every trip.

The routing sequence is: validate AI and sensor inputs; identify bins requiring collection; obtain road-network costs from OpenStreetMap through OSRM; solve a capacitated vehicle routing problem with Google OR-Tools; request route geometry; and display the result on an interactive map. Red dots show individual bins selected for collection, gray dots show bins that can wait, and each generated trip begins and ends at the depot.

The current prototype assumes a 9,000 kg truck payload and no more than two daily trips. It includes deterministic fallback routing if the optimization solver does not return a solution within its configured time limit. All 14 automated tests passed. In a fresh 30-replication synthetic holdout, the revised safety-constrained policy matched fixed three-day service at zero modeled overflow while reducing road distance, fuel, and tailpipe carbon dioxide by 5.08%. Fixed service remains the field safeguard until real sensor, AI, and operator data validate autonomous use.

## 1. Scope and system boundary

### 1.1 Included work

This report covers the following completed work:

1. Representation of the depot, 11 service sites, 33 bins, and three-bin ESP32 controller groups.
2. Definition of the data contract between the future AI forecaster and the routing system.
3. Validation and prioritization of bins that require collection.
4. Road-network distance and duration acquisition using OSRM over OpenStreetMap data.
5. Capacity-constrained route optimization using OR-Tools.
6. Deterministic fallback routing for solver timeout or failure.
7. Interactive map display and route/event data export.
8. Reproducible tests and a provisional synthetic integration study.

### 1.2 Excluded work

The report does not claim that the future AI model is accurate, that the proposed coordinates are construction-ready, or that the tested routing policy will reduce fuel or emissions in the field. Forecast training, sensor calibration, municipal approval, detailed crew scheduling, traffic prediction, disposal queueing, and excavation design remain separate work packages.

## 2. Implemented pilot model

### 2.1 Routing entities

The digital pilot contains:

- one provisional depot at latitude 3.06192, longitude 101.55272;
- 11 preliminary service sites covering SS12-SS19, USJ 1/2/4, and Bandar Sunway;
- 33 bins, arranged as three co-located bins per site;
- one ESP32 controller per site, producing three separate bin records;
- 4.5 m3 nominal volume per underground bin;
- 540 kg modeled nominal mass capacity per bin at 120 kg/m3 mixed-waste density;
- one 9,000 kg collection vehicle with a maximum of two modeled trips per day.

Three bins share a microprocessor and location, but the routing layer treats them as individual pickup decisions. If only one bin at a site requires collection, only that bin is added to the vehicle demand. Co-location gives zero or near-zero road travel between the three bin records while preserving separate fill, weight, and status values.

### 2.2 Vehicle and route assumptions

Every route starts and ends at the depot. Vehicle demand is the estimated waste weight in each selected bin, rounded upward to an integer kilogram for the solver. The total load of each trip may not exceed 9,000 kg. A fixed 15 km-equivalent departure cost encourages the solver to consolidate collection into fewer trips while still permitting two trips when capacity requires them.

The 9,000 kg payload, two-trip limit, and service-site coordinates are configurable planning assumptions. They must be replaced with operator-approved payload, axle, crane, working-time, and access constraints before deployment.

## 3. AI-to-routing input contract

### 3.1 Required fields

The confirmed future AI system will provide one record for each of the 33 bins at every routing decision time. The AI record contains exactly the seven fields below. Site coordinates, site identifiers, and controller assignments are resolved from the BinSight registry using `bin_id`; the AI does not need to send them repeatedly.

| Field | Type and unit | Routing purpose |
|---|---|---|
| `timestamp` | ISO 8601 timestamp with time-zone offset | Confirms when the prediction was produced and that records belong to the same decision snapshot. |
| `bin_id` | String, `UGB-001` to `UGB-033` | Unique pickup identifier. |
| `fill_pct` | Percentage, 0 to 100 | Current fill estimate derived from the ultrasonic sensor. |
| `weight_kg` | Kilograms | Current load-cell estimate used as vehicle-capacity demand. |
| `time_to_overflow_hours` | Hours | Predicted remaining time before the bin reaches overflow. |
| `risk_level` | `low`, `medium`, `high`, or `critical` | AI-assigned collection urgency. |
| `confidence_flag` | Boolean | States whether the AI prediction passes its confidence and data-quality checks. |

The routing service joins each record to the static bin registry. That registry supplies `site_id`, `controller_id`, latitude, longitude, and the common road service point for the three bins at a site. A future optional field, `predicted_weight_at_collection_kg`, could improve payload planning, but it is not required by the confirmed interface.

### 3.2 Example JSON record

```json
{
  "timestamp": "2026-08-16T06:00:00+08:00",
  "bin_id": "UGB-001",
  "fill_pct": 87.4,
  "weight_kg": 463.0,
  "time_to_overflow_hours": 15.5,
  "risk_level": "high",
  "confidence_flag": true
}
```

The values above are an interface example only, not a measured result.

### 3.3 Input validation and fail-safe behavior

Before optimization, the routing service checks that all expected bin identifiers are unique, timestamps are current and consistent, `fill_pct` is between 0 and 100, weights and overflow times are finite and non-negative, risk values use the agreed categories, and each `bin_id` exists in the site/controller registry. Values outside plausible bounds are flagged rather than silently corrected.

If AI values are missing, stale, invalid, or have `confidence_flag: false`, the system must not infer a safe collection cancellation. It should retain the fixed three-day schedule or require operator review. Valid current `fill_pct` and `weight_kg` measurements may still support a conservative collection decision and truck-capacity planning when the AI risk prediction is unavailable.

## 4. From prediction to collection decision

The routing service evaluates the AI snapshot at the configured decision times. Under the confirmed interface, a bin is selected for collection when at least one of the following initial rules is met:

- `risk_level` is `high` or `critical`;
- `time_to_overflow_hours` is 48 hours or less; or
- `fill_pct` is 80% or higher.

Bins marked `critical` are ranked first, followed by `high`-risk bins and bins with the shortest time to overflow. Current `fill_pct` breaks ties. The routing service uses `weight_kg`, rounded upward to an integer kilogram, as the OR-Tools demand. Until the AI supplies predicted collection-time weight, a configurable safety margin should be applied to current weight before field deployment.

The normal policy retains a 48-hour minimum gap between dispatches, but a `critical` bin with `time_to_overflow_hours` at or below 20 hours may override that gap. When the truck already visits a three-bin site, a sibling bin may be added if it is at least 50% full or predicted to overflow within 72 hours because doing so adds no road travel. Other optional bins are added only when vehicle capacity remains, the total proxy route stays within 30 km, and the bin adds no more than 5 km to that proxy route.

When `confidence_flag` is false, the AI risk prediction is not used to cancel service. The system falls back to valid current sensor measurements, the fixed three-day schedule, or operator review.

These are competition-prototype decision rules, not field-approved thresholds. The synthetic integration adapter derives `time_to_overflow_hours` and `risk_level` from the internal conservative 48-hour fill-growth forecast; Section 8 therefore validates software behavior under generated data, not the confirmed external seven-field AI interface. That intake adapter and the experiment must be rerun with real records before field-performance claims are made. If critical demand exceeds daily capacity, the production system must raise an explicit unserved-critical-bin alarm and schedule emergency capacity.

## 5. Road-network model using OpenStreetMap and OSRM

### 5.1 Service-point snapping

The depot and the 11 site anchors are sent to the OSRM Table service using the `driving` profile. OSRM returns a snapped road-network point for every location. The prototype rejects a network when any point is more than 250 m from a routable road. In the cached Subang Jaya network, the maximum snap distance is 22.1 m.

The requested site coordinate represents a planning anchor; the snapped coordinate represents the point used for routing. Neither is an approved excavation or truck-stopping position.

### 5.2 Distance matrix

The OSRM Table service returns distance in metres and duration in seconds for the fastest route between every ordered pair of service points. The 12 locations are the depot plus SJ-01 through SJ-11. Examples of ordered pairs are depot to SJ-01, SJ-01 to depot, and SJ-01 to SJ-02. A matrix row means "from" and a column means "to." The diagonal contains zero-distance self-pairs. The 12-by-12 matrix therefore contains 144 cells, including 132 directed non-self pairs. Opposite directions may differ because of one-way roads and other network restrictions.

These are road-route costs, not straight-line distances. Separate 12-by-12 matrices store distance and duration. The optimizer reads these matrices as cost tables; it does not draw all 132 pairwise paths. After the stop order has been chosen, only the selected trip sequence is sent to the OSRM Route service for road-following vector geometry. For individual-bin capacity decisions, the service matrix is expanded to a 34-by-34 matrix containing the depot plus 33 bins by repeating each site's costs for its three co-located bins.

The response is cached with retrieval time and SHA-256 hash so a simulation can be reproduced even if the live map later changes. The current cache was retrieved on 3 August 2026 and has SHA-256 `3718c6c6da5de35760cde23fdc15f8a582acc269969b1b289a0463439975af27`.

### 5.3 Route geometry

After the stop order is solved, each trip is sent to the OSRM Route service with full GeoJSON geometry. This produces a polyline that follows mapped roads in the stop order. Geometry is cached separately from the distance matrix and exported to `representative_routes.geojson` for the dashboard.

OpenStreetMap data are credited on the map and are licensed under the Open Data Commons Open Database License. The public OSRM demonstration service is suitable for a competition prototype, but a production deployment should use a self-hosted or contracted routing backend with a pinned data version and service-level monitoring.

## 6. Capacity-constrained route optimization

### 6.1 Mathematical form

For the selected bins, the routing problem minimizes total road distance plus a fixed departure penalty, subject to:

- each selected bin is served exactly once;
- each active trip begins and ends at the depot;
- the sum of bin weights on a trip is no more than 9,000 kg;
- no more than two trips are used in the decision period.

This is a capacitated vehicle routing problem (CVRP). The distance callback uses the asymmetric OSRM road matrix, and the demand callback uses current estimated kilograms. OR-Tools applies parallel cheapest insertion to construct a first solution, then guided local search to improve it within a 250 ms prototype time limit. A fixed vehicle cost discourages unnecessary extra departures.

### 6.2 Deterministic fallback

If OR-Tools returns no solution within the configured time, the system uses a deterministic two-stage fallback. It first packs the selected bins into capacity-feasible trip buckets, processing heavier bins first. It then orders each bucket using nearest-neighbor road distance from the depot and returns to the depot after the last stop.

The fallback prioritizes predictability and feasibility over optimality. Each route event records `ortools`, `deterministic_fallback`, or `none`, allowing the dashboard and audit files to reveal how the route was produced. No fallback was required in the final 30-replication integration run.

### 6.3 Operational pseudocode

```text
receive one seven-field AI record for every bin
validate timestamps, IDs, fill, weight, overflow time, risk, and confidence
join each bin_id to its stored site, controller, and road service point
if confidence is false: use sensor/fixed-schedule fallback or request review

select high/critical, <=48-hour-overflow, or >=80%-full bins
allow <=20-hour emergency bins to override the normal dispatch gap
rank critical bins first, then by risk, overflow time, and current fill
add useful sibling bins at already-visited sites while capacity remains
rank other optional bins by urgency and incremental route distance
add optional bins while capacity, incremental, and total distance budgets remain

solve the CVRP using the OSRM distance matrix
if the solver fails: construct deterministic capacity-feasible routes
request road geometry for each depot-to-depot trip
publish route, selected bins, load, distance, solver method, and warnings
```

## 7. Route display and operator output

The Streamlit dashboard displays the solved route on an OpenStreetMap basemap. The visual encodings are intentionally redundant:

- solid teal line: smart route;
- dashed dark-gray line: fixed three-day route;
- green truck marker: provisional depot;
- blue site marker: residential controller site;
- orange site marker: mixed/commercial controller site;
- large red bin dot: collect now;
- small gray bin dot: can wait.

Hovering over a route shows the policy and representative simulation day. Hovering over a bin shows its unique identifier, site, and collection status. Hovering over a site shows the site label, ESP32 identifier, allocated households and businesses, and the number of bins. The layer control can hide either route or the individual-bin status layer.

![Representative BinSight route map for Subang Jaya](artifacts/route_map_preview.png)

**Figure 1.** Representative solved dispatch on OpenStreetMap. The image demonstrates routing and status display only; it is not a fixed daily route or a construction plan. Map data © OpenStreetMap contributors, ODbL.

## 8. Verification and provisional results

### 8.1 Software verification

The complete local test suite was run on 16 August 2026. All 14 tests passed. Routing-specific checks confirm that routes begin and end at the depot, every selected bin is served, vehicle loads remain within capacity, empty selections produce no route, and the deterministic fallback remains capacity-feasible. Simulation checks also verify overflow-deadline conversion, risk classification, and zero added road distance for a co-located optional bin.

The locked 30-replication study also recorded zero routing fallbacks. Reproducibility files include the configuration, cached OSRM network, route-event log, GeoJSON geometry, seed manifest, package versions, and replication-level metrics.

### 8.2 Synthetic integration test - not final AI evidence

The following 30-day values come from 30 paired synthetic replications. They test the connection between prediction, selection, routing, and measurement. They do not validate real sensor accuracy or future AI performance.

| Routing/safety KPI | Fixed three-day mean | Tested smart-policy mean | Interpretation |
|---|---:|---:|---|
| Road distance | 551.262 km | 523.279 km | Smart policy used 5.08% less road distance. |
| Collection trips | 19.000 | 17.600 | Smart policy used 7.37% fewer trips. |
| Collection stops | 330.000 | 282.533 | Smart policy used 14.38% fewer stops. |
| Low-fill pickups | 33.367 | 27.800 | Smart policy used 16.68% fewer low-fill pickups. |
| Mean fill at collection | 57.276% | 69.271% | Smart pickups were 11.995 percentage points fuller. |
| Overflow incidents | 0.000 | 0.000 | Both policies recorded zero modeled overflow. |

The result indicates that the emergency deadline, co-located batching, and incremental-distance rule corrected the failure observed in the first synthetic policy. Mean modeled fuel fell from 248.068 L to 235.476 L and modeled tailpipe carbon dioxide fell from 664.822 kg to 631.075 kg. These are paired scenario contrasts under synthetic assumptions, not measured municipal savings or proof that the external AI model is safe.

### 8.3 Acceptance criteria for the future AI dataset

When the final AI records are supplied, the routing evaluation should be rerun without changing the fixed-policy baseline. At minimum, the candidate system should:

1. produce a complete valid snapshot for all 33 bins at each decision time;
2. validate `time_to_overflow_hours`, `risk_level`, and `confidence_flag` on a later, untouched time window;
3. remain non-inferior to fixed collection on overflow incidents and full-bin exposure;
4. satisfy trip payload and daily-trip constraints in every dispatch;
5. report road distance, trips, stops, low-fill pickups, fuel proxy, and overflow together;
6. disclose missed critical bins, fallback use, invalid inputs, and operator overrides;
7. use paired replications or matched operating days with identical waste arrivals where possible.

Final tables should replace the synthetic figures rather than being added beside them, preventing preliminary and field results from being confused.

## 9. Sustainability relevance

The routing subsystem supports Sustainable Development Goal 11, particularly Target 11.6 on reducing the environmental impact of cities with attention to municipal waste management. It also relates to Goal 13 because road distance, fuel use, and tailpipe carbon dioxide can be monitored as routing outcomes.

These links describe design intent, not a proven field impact. The revised synthetic smart policy reduced modeled distance and emissions by 5.08% without modeled overflow, but BinSight should claim real climate benefit only if later field-calibrated results reproduce that safe reduction relative to the fixed baseline.

## 10. Limitations and next steps

The main limitations are:

- AI predictions and real pressure/ultrasonic telemetry have not yet been supplied for final evaluation.
- Site and depot coordinates are preliminary planning anchors and require municipal, utility, drainage, crane-access, and safety surveys.
- The public OSRM service and OpenStreetMap snapshot can change; the prototype cache is reproducible, but production routing needs controlled updates.
- The model does not yet include time-dependent traffic, crew shifts, service time uncertainty, crane setup, disposal unloading, vehicle breakdowns, road restrictions, or multiple depots.
- Estimated bin weight is treated as the pickup demand; sensor bias or bridging inside the bin could affect capacity feasibility.
- The optional-stop distance gate uses a fast proxy before the exact CVRP is solved.
- If critical demand exceeds available daily capacity, the production system needs an escalation and emergency-vehicle rule.

The next implementation step is to ingest the confirmed seven-field AI records together with several weeks of calibrated three-bin telemetry and operator logs, implement and lock the adapter, validate the emergency constraint, add a hard maximum-service rule, rerun the paired evaluation, and obtain field approval for the road service points.

## 11. Reproducibility record

The completed routing work is contained in:

- `binsight/network.py` - OSRM requests, snapping, matrices, caching, and route geometry;
- `binsight/routing.py` - OR-Tools CVRP and deterministic fallback;
- `binsight/simulation.py` - selection policy, dispatch logic, metrics, and route events;
- `app.py` - interactive route and bin-status map;
- `config.json` - depot, bins, truck, thresholds, and solver settings;
- `data/subang_jaya_sites.json` - 11 preliminary site anchors;
- `data/subang_jaya_osrm_network.json` - cached road-network response;
- `artifacts/representative_routes.geojson` - displayed route geometry;
- `artifacts/representative_route_events.json` - stop order and solver audit;
- `artifacts/run_provenance.json` and `artifacts/seed_manifest.json` - reproducibility metadata;
- `tests/test_routing.py` - capacity and fallback tests.
- `tests/test_simulation.py` - deadline, risk, distance-proxy, and batching tests.

The routing core is ready to be connected to the later AI dataset through the adapter contract in Section 3; the seven-field intake adapter still has to be implemented and tested. Until that dataset passes the safety criteria in Section 8.3, the fixed three-day collection schedule remains the operational safeguard.

## References

1. Open Source Routing Machine Project. *OSRM HTTP API, v5.24.0*. Route and Table service documentation. https://project-osrm.org/docs/v5.24.0/api/ (accessed 16 August 2026).
2. Google for Developers. *OR-Tools: Capacity Constraints - Capacitated Vehicle Routing Problem*. https://developers.google.com/optimization/routing/cvrp (accessed 16 August 2026).
3. OpenStreetMap Foundation. *Copyright and License*. https://www.openstreetmap.org/copyright (accessed 16 August 2026).
4. United Nations Department of Economic and Social Affairs. *Sustainable Development Goal 11*. https://sdgs.un.org/goals/goal11 (accessed 16 August 2026).
5. United Nations Department of Economic and Social Affairs. *Sustainable Development Goal 13*. https://sdgs.un.org/goals/goal13 (accessed 16 August 2026).
6. Southeast Asia Engineering Design Competition 2026. *Degree Level Question Paper - Smart, Efficient and AI-Based Waste Management*, Focus Area C and D2 requirements. User-provided competition brief.

## Appendix A. Site-to-controller schedule

| Site | Area | Controller | Bin IDs |
|---|---|---|---|
| SJ-01 | SS12 residential cluster | ESP32-001 | UGB-001 to UGB-003 |
| SJ-02 | SS13 residential cluster | ESP32-002 | UGB-004 to UGB-006 |
| SJ-03 | SS14 residential cluster | ESP32-003 | UGB-007 to UGB-009 |
| SJ-04 | SS15 commercial-residential cluster | ESP32-004 | UGB-010 to UGB-012 |
| SJ-05 | SS17 residential cluster | ESP32-005 | UGB-013 to UGB-015 |
| SJ-06 | SS18 residential cluster | ESP32-006 | UGB-016 to UGB-018 |
| SJ-07 | SS19 residential cluster | ESP32-007 | UGB-019 to UGB-021 |
| SJ-08 | USJ 1 mixed-use cluster | ESP32-008 | UGB-022 to UGB-024 |
| SJ-09 | USJ 2 residential cluster | ESP32-009 | UGB-025 to UGB-027 |
| SJ-10 | USJ 4 residential cluster | ESP32-010 | UGB-028 to UGB-030 |
| SJ-11 | Bandar Sunway mixed-use cluster | ESP32-011 | UGB-031 to UGB-033 |

## Appendix B. Route output contract

Each solved dispatch should publish:

| Field | Meaning |
|---|---|
| `decision_timestamp_utc` | Snapshot that triggered the route. |
| `route_id` and `trip_number` | Unique route/trip identifiers. |
| `solver_method` | `ortools`, `deterministic_fallback`, or `none`. |
| `stop_sequence` | Depot, ordered bin IDs, depot. |
| `selected_bin_ids` | All bins assigned to the dispatch. |
| `unserved_critical_bin_ids` | Critical bins requiring escalation. |
| `estimated_load_kg` | Sum of current weights on the trip. |
| `distance_km` and `duration_s` | OSRM route outputs. |
| `route_geometry_geojson` | Road-following line for the map. |
| `warnings` | Invalid inputs, stale prediction, false confidence flag, capacity issue, or fallback use. |
