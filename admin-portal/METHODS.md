# Simulation methods and reporting contract

## System boundary

The model is a terminating 30-day planning experiment for 33 underground bins at 11 three-bin controller sites serving exactly 500 households and 20 commercial units. It includes stochastic waste generation, six-hourly noisy observations, dispatch decisions, vehicle payload, OSM-road routing, collections, and physical overflow. It excludes traffic, crew-hour rules, queueing at disposal facilities, unloading time, precipitation, illegal dumping, mechanical failure, embodied emissions, and capital cost.

## Units and configuration

| Quantity | Unit | Locked convention |
|---|---:|---|
| Clock | hour | 0 through 719; events at hour 720 are outside the horizon |
| Waste | kg | non-negative hourly arrival |
| Bin volume | m3 | 4.5 per underground bin |
| Bin mass capacity | kg | 4.5 x assumed 120 kg/m3 = 540 |
| Site usable capacity | kg | 3 x 540 x 80% = 1,296 |
| Road distance | metre | OSRM fastest-route road distance over OSM data |
| Truck payload | kg | conservative 9,000 kg model assumption |
| Fuel | litre | road km x 0.45 L/km assumption |
| Tailpipe CO2 | kg | fuel x 2.68 kg CO2/L assumption |

All bins start empty. This initial condition is part of the estimand, so no warm-up period is discarded. Remaining contents at hour 720 are reported as `uncollected_kg_at_horizon`.

## Demand and capacity

Residential demand is 7.03 kg/household/day, derived from 1.90 kg/person/day and 3.7 persons/household. Commercial demand is the editable 4.43 kg/unit/day assumption. Total mean generation is 3,603.6 kg/day.

Eleven sites are required by the district calculation in `SITING_PLAN.md`. `load_site_plan` also validates every site separately against its 1,296 kg three-day reserved capacity. The program fails rather than silently accept an overloaded site allocation.

## Spatial model

The OSRM service table contains the depot plus 11 sites. Requested WGS84 coordinates are retained for provenance; routing uses the snapped road-service coordinates. The 12 x 12 site matrix is expanded to a 34 x 34 depot-plus-bin matrix by repeating each site's row/column for its three co-located bins. Route geometries are fetched only for representative routes and cached.

OSRM table distance is the distance of its fastest road route, not a straight-line or necessarily geometrically shortest path. Public OSRM availability is outside the model; cached inputs support ordinary reruns.

## Stochastic arrivals and sensors

Hourly arrivals are gamma-distributed around residential and commercial diurnal curves. Weekend and declared event-day factors modify the mean. The gamma draw is non-negative. Excess above physical 540 kg capacity is not stored: the bin is capped and the excess becomes `overflow_spilled_kg`. An incident is a crossing from below capacity to above capacity; every hour at capacity contributes one `overflow_bin_hour`.

The simulation adds independent Gaussian observation error with a configurable 2 percentage-point standard deviation every six hours. Arrival and noise arrays are generated before policy execution. Both policies in a replication receive exactly the same arrays; different replications use different seeds.

## Forecast model

The predictor is a histogram gradient-boosting regressor trained on a separate 45-day synthetic pre-period. Features include current fill, recent fill history, time cycles, and residential/commercial allocation. The final 20% of timestamps form a chronological holdout. A naive rolling-growth forecast is reported beside model MAE. The prediction target is 48-hour fill growth; an upper estimate is used for risk selection.

## Collection policies

**Fixed baseline:** at 06:00 every third day, every bin is selected. The baseline is road-routed and capacity constrained, so the smart alternative is not compared with an intentionally inefficient route.

**Smart candidate:** at 06:00 and 18:00, conservative 48-hour growth is converted into a predicted time to overflow and a `low`/`medium`/`high`/`critical` risk level. A 48-hour minimum dispatch gap limits repeated departures, but a critical bin inside the 20-hour emergency horizon overrides that gap. High and critical bins are mandatory subject to daily capacity. When a selected bin causes a site visit, useful siblings at the same three-bin site are included first because their road increment is zero. Other medium-risk bins are admitted only if the capacity-aware route proxy stays within 30 km and the bin adds no more than 5 km. Critical routes may exceed the soft budget rather than discard imminent-risk waste.

The final results show this candidate should not autonomously replace the fixed schedule. It remains in the code to expose the trade-off and support the next safety-constrained design.

## Routing

OR-Tools solves capacity-constrained depot tours using up to two daily trips, a 9,000 kg payload, asymmetric OSM-road distances, and a 250 ms solve limit. A fixed vehicle-departure cost encourages consolidation.

If OR-Tools returns no solution within the time limit, a deterministic fallback first packs bins by descending demand into capacity-feasible trips, then orders each trip by nearest road distance. The `routing_fallbacks` KPI records every such dispatch. The final 30-replication run used the fallback zero times for both policies.

## Experimental design and inference

The independent experimental unit is one complete paired 30-day replication, not an hour or a bin. Thirty pairs use a production seed block disjoint from exploratory development. For each KPI:

- lower-is-better beneficial effect = fixed minus smart;
- higher-is-better beneficial effect = smart minus fixed.

Positive effects are always favorable. The project reports policy means, paired mean effect, a 95% Student-t interval across the 30 differences, a 19,999-draw two-sided sign-flip p-value, and a Shapiro-Wilk diagnostic. If the fixed mean is zero, percentage change is undefined and is reported as `n/a`; the absolute difference remains available.

The intervals quantify Monte Carlo uncertainty only. Parameter uncertainty, geographic sampling error, and causal field effects are not included.

## Verification contract

- Configuration requires exactly three bins per controller and 33 bins total.
- Site counts conserve exactly 500 households and 20 commercial units.
- District and each individual site pass the declared capacity formula.
- All requested coordinates are valid WGS84 and snap within 250 m of a drive service.
- Waste arrivals are non-negative and reproducible for a fixed seed.
- Each route starts and ends at the depot, serves every selected bin once, and respects payload.
- Fixed and smart policies share arrivals and sensor noise within each pair.
- Replication IDs/counts match before paired analysis.
- Cached service inputs, package versions, configuration, and seeds are retained.
- The controller payload contains exactly three bins with unique channels and message IDs.

## Permitted claim

Use this wording pattern:

> Under the stated Subang Jaya waste, underground-bin, sensor, vehicle, and OSM-road assumptions, the modeled policy produced [effect and interval] relative to the fixed schedule across 30 paired replications.

Do not state that BinSight will reduce municipal fuel, emissions, or overflow until the inputs and outcomes are validated with field measurements.
