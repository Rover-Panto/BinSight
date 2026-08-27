# Simulation methods and reporting contract

## System boundary

The model is a terminating 30-day stochastic planning experiment for 33 underground bins at 11 three-bin service groups serving 500 households and 20 commercial units. It includes hourly waste generation, six-hourly sensing and replanning, forecast/decision logic, road routing, travel, collection service, depot unloading, turnaround, traffic effects, payload-dependent fuel, and physical overflow while the vehicle is busy. These service groups are simulation topology, not a claim of 11 deployed controllers.

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

For bin `b` and hour `t`, non-negative arrivals are sampled as

\[
D_{b,t}\sim\operatorname{Gamma}\left(k,\mu_{b,t}/k\right)
\]

with

\[
\mu_{b,t}=B_b H_{b,t}W_{b,t}M_{b,t}A_{b,t}E_{b,t}T_{b,t}R_tL_{b,t}S.
\]

`B` is the residential/commercial base mass; `H` uses separate 24-hour residential and commercial profiles; `W` uses seven independently configured day-of-week values; `M` smoothly interpolates twelve cyclic monthly control points; `A` is a continuous annual cosine; `E` is the event multiplier; `T` is bounded long-term trend/change-point behavior; `R` and `L` are district and local persistent regimes; and `S` is an explicit scenario multiplier. Stable per-bin phase/amplitude perturbations make recurring profiles recognizable without changing the configured bin allocation. The complete hourly × weekly × monthly × annual product is normalized over a reference year so correlated factors do not silently inflate the long-run mean.

District and local regimes are mean-one lognormal AR(1) processes. Defaults are `phi=0.96, sigma=0.055` and `phi=0.90, sigma=0.075`, respectively, after a 240-hour burn-in. Scenario windows may multiply either process to represent busy/quiet multi-day periods or a localized surge. Gamma shape `k=4` controls remaining non-negative hour-level dispersion. All values are assumptions in `config.json`, not fitted municipal parameters.

Events carry type, location/target area or site, start/end, buildup, peak, decay, intensity, recurrence and `known_at_hour`. Current physical event effects influence demand; 48/168-hour calendar features become visible to the forecaster only at or after `known_at_hour`. The event-heavy scenario includes an unannounced event whose effect starts before the calendar feature becomes available. Slow trend is multiplicative and bounded below; abrupt scenario change points apply only after their declared hour and may target selected bins.

The same immutable arrival tensor and event context is supplied to both policies in a paired replication. A bin stores no more than 540 kg: excess mass becomes `overflow_spilled_kg`, a below-to-capacity crossing becomes an incident, and time at capacity contributes `overflow_bin_hours`.

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

## Forecast model and calibration

The histogram gradient-boosting models are trained on a separate 730-day synthetic pre-period. The operational 30-day experiment begins at hour zero and is never part of training, calibration or model selection. Timestamp-windowed features contain observed fill/weight availability, confidence, freshness/gaps, collection/reset signals, 6/24/168-hour observed growth, hours since service, historical bin growth, site allocation, hour/day/month/year cycles, and only calendar events known at that timestamp. Missing channels remain missing; a tuple or sentinel is never substituted for an observation. Hidden regimes and future arrivals are labels/outcomes only.

Separate regressors estimate 6-, 24-, 48- and 168-hour fill growth. A one-sided q90 48-hour model supports conservative time-to-overflow. Classifiers estimate overflow within 6 and 48 hours; the 6-hour probability is the dynamic planner's next-opportunity input when fresh, confident evidence is available. Chronological train, calibration and untouched holdout windows use a complete 168-hour purge—the longest target—so no label crosses a split. Calibration adjusts only the q90 interval. Holdout reporting includes horizon MAE versus a recent-growth baseline, time-to-overflow MAE, alert precision/recall, Brier score, probability reliability bins, q90 coverage/error, pinball loss and interval width. These are synthetic model checks, not physical accuracy evidence.

## Collection policies

**Fixed baseline.** Every bin becomes due at 06:00 after each complete three-day interval. There is no day-zero sweep of empty bins. The fixed policy uses the same depot, vehicle, trip limit, chronological execution, and road model as the smart policy. If its due load exceeds the remaining daily capacity, candidate order is preserved and excess bins are deferred and counted as unserved.

**Dynamic trip-value candidate (v2).** The simulation evaluates the same public validation and planning functions every six hours; the local controlled runner defaults to 15-minute reevaluation when explicitly started. Optional positive-value work has a 72-hour consolidation gap so repeated observations can merge work instead of launching a new truck. Because both policies start with empty bins, the first optional departure also waits that full interval. A stop is mandatory for upstream critical risk, fresh/confident conservative fill at or above 90%, or a fresh/confident calibrated probability of overflow before the next six-hour opportunity of at least 90%; mandatory work overrides the optional gap. When that classifier is unavailable, a fresh/confident q90 time-to-overflow of at most six hours is the named conservative fallback. Low-confidence evidence remains an inspection state unless independent critical evidence exists; missing/unavailable forecasts never become an infinite safe horizon.

For optional bin `i`, the model estimates avoided overflow loss `B_i` from a provisional 180,000 m-equivalent value multiplied by the greater of the calibrated 6-hour probability and the calibrated 48-hour probability amortized over its eight six-hour planning opportunities. This consolidation term can make an already-eligible medium/high-risk stop worth adding to a justified route, but it cannot make the stop mandatory. A 90,000 m-equivalent emergency term applies above the 10% planning tolerance. A documented q90/risk proxy is used only when classifiers are unavailable. Optional eligibility requires a fresh central fill of at least 45%, unless observable time-to-overflow says service is due before the next 72-hour batch. A fresh uncertain/high-conservative-fill bin may join a scheduled site only when that site already has two confident eligible bins or mandatory service; it cannot bootstrap a route from uncertainty alone. Low-fill collection cost is `100 × max(0, 50 − central_fused_fill_i)`. Route cost combines a 15,000 m-equivalent fixed trip charge, road metres, 120 m-equivalent per travel minute, 120 m-equivalent per service minute and low-fill costs. The prize-collecting solver maximizes served benefit minus these costs; it dispatches only for a mandatory stop or positive net value. Coefficients are explicit, configurable engineering priors—not learned monetary values.

The physical profile preserves `bin_type` and `waste_stream`. Mixed general waste and beverage-return recycling may be evaluated together, but no vehicle trip is allowed to mix incompatible streams; each stream receives a separate route subject to the shared daily trip budget.

The maximum of two trips is enforced across the entire calendar day. It is not reset at the evening decision.

## Routing and chronological execution

OR-Tools solves asymmetric prize-collecting depot tours using cached road distance and duration matrices, up to two trips, a 9,000 kg payload, compacted vehicle-volume capacity, 480-minute route duration and a 250 ms/solution-limit prototype search. Mandatory stops cannot be dropped. Optional stops have disjunction penalties equal to avoided loss, so waiting competes with route operation in the same objective. Candidate preselection uses the same upward-rounded integer mass and volume demands as OR-Tools, so it cannot pass a nominally feasible load that the solver rejects by rounding.

If OR-Tools returns no solution for mandatory work, a deterministic fallback exactly partitions required bins into dual-capacity-feasible buckets and orders each bucket by nearest road distance. Optional non-positive work is deferred instead of forcing a fallback trip. Every route begins and ends at the depot.

Every proposal records the policy/model/network/config versions, source event IDs, per-bin decision inputs, objective components and dropped nodes. It is stored immutably as `DRAFT`; operator acceptance, completion or cancellation are separate transitions. A repeated event set in one planning bucket is idempotent. On an active-route event, the current leg is frozen, its committed capacity is deducted, and any changed suffix is a new draft linked to the accepted plan.

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
| Normal patterned | Configured patterns, regimes, events, sensing and capacity; fixed service is expected to remain competitive |
| High-demand seasonal | December calendar plus configured high-demand multiplier |
| Event-heavy | More frequent/intense recurring events plus one unseen event |
| Persistent multi-day surge | District regime ×1.55 on days 7–16 |
| Localized surge | Local regime ×1.80 for selected bins on days 9–20 |
| Gradual upward trend | Accelerated bounded trend for adaptation testing |
| Abrupt behavior change | Demand ×1.45 after day 12 |
| Traffic disruption | Travel/fuel traffic multiplier ×1.35 |
| Sensor failure | 18% missing and 8% outlier probability |
| Reduced truck capacity | Payload/body capacity ×0.65 |
| Combined stress | Seasonal/event/regime/change, traffic, sensing and capacity changes together |

Within each replication and scenario, both policies share the exact arrival matrix, event context and sensor randomness. Across scenarios, the same replication seed drives comparable base stochastic regimes while declared scenario transformations differ. Development/tuning used the +1,310,000/+1,320,000 blocks. The locked v2 evaluation begins at base seed +1,610,000 for arrivals and +1,620,000 for sensors, is disjoint from development runs, and is saved with arrival hashes in `artifacts/dynamic_v2/seed_manifest.json`.

For lower-is-better metrics, beneficial effect = fixed − smart. For higher-is-better metrics, beneficial effect = smart − fixed. Positive is always favorable. Reports contain policy means, paired mean effect, 95% Student-t interval, 19,999-draw paired sign-flip p-value, and a Shapiro-Wilk diagnostic. Percentage change is `n/a` when the fixed mean is zero.

The intervals describe Monte Carlo uncertainty under configured assumptions only; they do not include parameter, geographic, or causal field uncertainty.

## Verification contract

- Exactly 33 bins and 11 three-bin service groups in the competition simulation; exactly the explicitly registered three physical bins in the pilot profile.
- Exactly 500 households and 20 commercial units conserved.
- Valid site capacity and WGS84 coordinates.
- Same arrivals and observation noise in each policy pair.
- Hour/day/week/month/year factors preserve intended patterns and the normalized long-run mean; December-to-January is cyclic.
- District/local regimes persist; event targeting, buildup/decay and knowledge-time boundaries are deterministic and tested.
- No hidden physical state in dispatch/forecast features.
- Fixed first service after the complete interval and equal warm-up treatment.
- No bin emptied before service completion.
- Daily trip count, mass/volume capacity, route duration, depot endpoints, mandatory-service coverage and integer demand consistency.
- Stale/missing/disagreeing data produces safe three-state behavior.
- Unknown forecasts, future events, duplicate/replayed events and controller reboots preserve identity and cannot silently create a safe reading.
- Forecast train/calibration/holdout boundaries retain a full 168-hour target-horizon purge, exclude the operational window and report multi-horizon/q90/probability checks.
- Plan lifecycle, idempotency, single-runner ownership and active-route suffix revision remain auditable.
- Eleven markers with three-bin popups and bounded maps at desktop, tablet, and mobile widths.
- Seeds, configuration, package versions, matrices, events, and results retained.

## Permitted claim

> Under the stated Subang Jaya demand, sensor, underground-bin, vehicle, traffic, and OSM-road assumptions, the modeled policy produced [effect and interval] relative to the fixed schedule across 30 paired replications.

Do not state that BinSight will reduce municipal overflow, fuel, or emissions until field inputs and outcomes are measured.
