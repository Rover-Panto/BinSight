# Simulation methods and reporting contract

## System boundary

The model is a terminating 30-day stochastic planning experiment for 33 underground bins at 11 three-bin sites serving 500 households and 20 commercial units. It includes hourly waste generation, six-hourly sensing, forecast/decision logic, road routing, travel, collection service, depot unloading, turnaround, traffic effects, payload-dependent fuel, and physical overflow while the vehicle is busy.

It does not model crew shifts, disposal-facility queues, weather, illegal dumping, mechanical failure, embodied emissions, capital cost, or measured Malaysian truck telemetry.

## Units and timing

| Quantity | Unit | Convention |
| --- | ---: | --- |
| Simulation clock | minute | SimPy processes execute through the 30-day horizon |
| Waste | kg | Non-negative hourly arrivals continue during travel/service |
| Bin volume | m³ | 4.5 per underground bin |
| Nominal bin mass capacity | kg | 4.5 × 120 kg/m³ = 540 kg |
| Road distance | m | OSRM fastest-route distance over OpenStreetMap data |
| Road duration | s | OSRM fastest-route duration before traffic multiplier |
| Truck payload | kg | 9,000 kg prototype assumption |
| Fuel | L | Driving components plus service/depot idling |
| Tailpipe CO₂ | kg | Fuel × 2.68 kg/L approximation |

Every bin starts empty. Raw metrics include the full 30 days. Post-warm-up metrics exclude the first three days for both policies, preventing either policy from gaining an advantage from the artificial empty start. Waste is removed only when service at that bin completes—not when a route is planned or a truck departs. Trips that extend beyond the horizon are recorded as unfinished rather than erased.

## Demand and capacity

Residential mean generation is 7.03 kg/household/day, from 1.90 kg/person/day and 3.7 people/household. Commercial mean generation is the editable assumption of 4.43 kg/unit/day. Total configured mean generation is 3,603.6 kg/day.

Hourly gamma draws follow residential and commercial diurnal curves, with weekend and declared event-day multipliers. The same arrival tensor is supplied to the paired fixed and smart run. A bin stores no more than 540 kg: excess mass becomes `overflow_spilled_kg`, a below-to-capacity crossing becomes an incident, and time at capacity contributes `overflow_bin_hours`.

`SITING_PLAN.md` proves the district count and checks each site's three-day reserved capacity. Loading fails if the plan no longer conserves all 500 households and 20 commercial units.

## Spatial model

OSRM's Table service provides a 12 × 12 matrix for the depot and 11 sites. Each cell is the distance or duration of the fastest road route from one ordered location to another. The code expands both matrices to 34 × 34—depot plus 33 bins—by reusing a site's row and column for its three genuinely co-located bins. It does not move the bins or invent a short road between them.

Routes are therefore vectors of matrix indices during optimization and road-coordinate polylines only during display. The map uses 11 consolidated markers, each with the state of all three bins. Public OSRM/tiles are prototype dependencies; committed matrices allow simulation reruns without refreshing the public router.

## Hidden state and sensor observations

The physical fill/mass arrays are private simulation state. At each sensing time, a separate seeded observation model creates ultrasonic and load-derived estimates with configurable:

- random noise;
- per-bin bias and drift;
- outliers;
- missing readings;
- disagreement checks; and
- confidence and uncertainty bounds.

The fixed and smart policies receive the same observation realization within a pair. Dispatch and forecast functions receive observations and observation history, not hidden mass. Hidden state is used only to generate forecast targets and measure physical outcomes. Automated leakage tests fail if a hidden field is exposed to the prediction interface.

The conservative fused estimate uses the available sensors and a one-sided 95% uncertainty bound (`z = 1.645`). A single available sensor uses a 7.5-point margin; general low-confidence/aged evidence uses 15 points. When both sensors are missing, a recent last-valid reading is aged with conservative growth; without one, the state is inspection and no collection load is invented. Missing, stale, future-dated, low-confidence, or disagreeing data is never treated as reassuring. An imminent current/aged-fill emergency may still produce `COLLECTION_REQUIRED` with operator review, but a low-confidence forecast alone cannot command a truck.

## Forecast model

The histogram gradient-boosting regressor is trained on a separate 45-day synthetic pre-period. Features contain observed fill/weight, confidence, observed growth history, site allocation, and time cycles. The target is hidden 48-hour fill growth. The last 20% of timestamps forms a chronological holdout; a naive recent-growth forecast is reported as a benchmark. Model selection does not use the 30-day evaluation outcomes.

## Collection policies

**Fixed baseline.** Every bin becomes due at 06:00 after each complete three-day interval. There is no day-zero sweep of empty bins. The fixed policy uses the same depot, vehicle, trip limit, chronological execution, and road model as the smart policy. If its due load exceeds the remaining daily capacity, candidate order is preserved and excess bins are deferred and counted as unserved.

**Smart candidate.** Decisions occur at 06:00 and 18:00. Collection is required for configured fill, predicted-overflow, high-risk, or critical triggers. A 48-hour dispatch gap limits churn, while a critical 20-hour emergency may override it. Selected-site siblings are considered before other optional bins. A nearby optional bin is accepted only if it fits vehicle capacity, stays within the soft 30 km planning budget, and adds no more than 5 km to the route proxy. This is an incremental road-cost rule; it is not a 5 km radius around a critical bin.

The maximum of two trips is enforced across the entire calendar day. It is not reset at the evening decision.

## Routing and chronological execution

OR-Tools solves asymmetric, capacity-constrained depot tours using the cached road-distance matrix, up to two trips, a 9,000 kg payload, and a 250 ms solve limit. A fixed departure cost encourages consolidation. Candidate preselection uses the same upward-rounded integer demands as OR-Tools, so it cannot pass a nominally feasible load that the solver rejects by rounding.

If OR-Tools returns no solution, a deterministic fallback exactly partitions the selected bins into capacity-feasible buckets and orders each bucket by nearest road distance. Every route begins and ends at the depot.

Trip execution is sequential. For every leg, OSRM duration is multiplied by a time-of-day traffic factor. The truck then pauses eight minutes per bin; the bin is emptied at the end of that pause. At the depot it pauses 20 minutes to unload, plus 10 minutes of turnaround before another trip. Route events preserve planned and actual timestamps for map playback.

## Fuel and CO₂ model

Driving fuel is decomposed into:

1. base road fuel: distance × 0.45 L/km;
2. traffic penalty: a time-band multiplier applied to base driving fuel; and
3. payload penalty: linearly up to 15% extra fuel at full payload.

Collection and depot pauses add idle fuel at 3.0 L/hour. Total fuel is the sum of those components; CO₂ is total fuel × 2.68 kg/L. The distance rate, traffic factors, payload penalty, and idle rate are configurable prototype assumptions and must be calibrated with a real collection vehicle. The CO₂ conversion approximates the US EPA diesel factor of 10,180 g CO₂ per US gallon (about 2.69 kg/L).

## Experimental design

The independent unit is one complete paired 30-day replication. Thirty pairs are run in each condition:

| Scenario | Change from base |
| --- | --- |
| Base | Configured demand, traffic, sensing, and 9,000 kg capacity |
| High demand | Waste arrivals × 1.45 |
| Traffic | Travel/fuel traffic multiplier × 1.35 |
| Sensor failure | 18% missing and 8% outlier probability |
| Truck capacity | Payload capacity × 0.65 |

Within each replication and scenario, both policies share arrivals and sensor randomness. Across scenarios, the same base arrival seed is scaled where applicable. The production seed block is disjoint from development runs and is saved in `artifacts/seed_manifest.json`.

For lower-is-better metrics, beneficial effect = fixed − smart. For higher-is-better metrics, beneficial effect = smart − fixed. Positive is always favorable. Reports contain policy means, paired mean effect, 95% Student-t interval, 19,999-draw paired sign-flip p-value, and a Shapiro-Wilk diagnostic. Percentage change is `n/a` when the fixed mean is zero.

The intervals describe Monte Carlo uncertainty under configured assumptions only; they do not include parameter, geographic, or causal field uncertainty.

## Verification contract

- Exactly 33 bins, 11 sites, and three bins per controller.
- Exactly 500 households and 20 commercial units conserved.
- Valid site capacity and WGS84 coordinates.
- Same arrivals and observation noise in each policy pair.
- No hidden physical state in dispatch/forecast features.
- Fixed first service after the complete interval and equal warm-up treatment.
- No bin emptied before service completion.
- Daily trip count, route capacity, depot endpoints, and integer demand consistency.
- Stale/missing/disagreeing data produces safe three-state behavior.
- Eleven markers with three-bin popups and bounded maps at desktop, tablet, and mobile widths.
- Seeds, configuration, package versions, matrices, events, and results retained.

## Permitted claim

> Under the stated Subang Jaya demand, sensor, underground-bin, vehicle, traffic, and OSM-road assumptions, the modeled policy produced [effect and interval] relative to the fixed schedule across 30 paired replications.

Do not state that BinSight will reduce municipal overflow, fuel, or emissions until field inputs and outcomes are measured.
