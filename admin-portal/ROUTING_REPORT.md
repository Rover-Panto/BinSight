# BinSight predictive collection routing subsystem

**Focus Area C technical implementation report**

**Pilot:** Subang Jaya, Selangor

**Team:** MON BLUE

**Status:** Reproducible digital prototype; physical and municipal validation pending
**Date:** 17 August 2026

## Executive summary

BinSight converts a complete 33-bin predictive snapshot into a safe operator decision and, when collection is required, a capacity-feasible route over OpenStreetMap-derived roads. The pilot represents 500 households and 20 commercial units using 33 Dutch-style 4.5 m³ underground bins at 11 sites. Each site has three genuinely co-located bins controlled by one ESP32. No extra bins, sites, or trucks were added during optimization.

The implemented chain is:

1. three ultrasonic and three pressure/load channels are sampled by one ESP32;
2. a Raspberry Pi gateway validates, calibrates, stores, and exports readings;
3. noisy observations—not hidden simulated fill—enter the 48-hour forecaster and decision logic;
4. the operator receives `COLLECTION_REQUIRED`, `INSPECTION_REQUIRED`, or `NO_COLLECTION_REQUIRED` with reasons;
5. selected bins are packed into at most two 9,000 kg daily trips and ordered by OR-Tools using cached OSRM road costs;
6. SimPy executes travel, service, unloading, and turnaround chronologically; and
7. the portal displays 11 consolidated site markers, road routes, and a mock truck replay.

The earlier claim of 5.08% lower route distance was withdrawn. It came from an unfair day-zero fixed collection of empty bins. The corrected baseline first collects after its complete interval and both policies use the same three-day post-warm-up reporting rule. The final experiment reports base and stress scenarios separately and does not hide metrics where the smart policy is worse.

> BinSight is decision support. Mock dispatch does not contact a vehicle, and simulation evidence is not measured municipal performance.

## 1. Scope and fixed design

This report covers only the Focus Area C sensing-to-routing subsystem. It does not claim completion of the proposal's camera classifier or physical QR return station.

| Design item | Implemented value |
| --- | --- |
| Service population | 500 households + 20 commercial units |
| Evaluation horizon | 30 days |
| Underground bins | 33 × 4.5 m³ |
| Sites/controllers | 11 sites; 1 ESP32 + 3 bins per site |
| Physical model unit | 1 ESP32 + 3 instrumented bins |
| Depot | Provisional Batu Tiga/Subang Jaya point, 3.06192, 101.55272 |
| Truck archetype | VDL Maxxum/UGS family, 22 m³ body assumption |
| Route payload | 9,000 kg assumption |
| Daily trips | Maximum 2 across the whole calendar day |

The 33-bin sizing follows `SITING_PLAN.md`:

`ceil(3,603.6 kg/day × 3 days × 1.25 reserve ÷ 1,296 kg/site) = 11 sites`

where a site has `3 × 4.5 m³ × 120 kg/m³ × 80% = 1,296 kg` usable design capacity.

## 2. Sensor and predictive-data boundary

### 2.1 Controller message

The ESP32 publishes one atomic JSON message for all three channels on:

```text
binsight/v1/telemetry/<controller_id>
```

The firmware uses a 1,024-byte MQTT buffer. Its maximum tested three-bin JSON is 555 bytes and the complete packet is 616 bytes. Serialization length is checked; publication is attempted three times with backoff; up to four unsent messages remain in a bounded RAM queue; and logs identify failure stages.

PubSubClient publishes at QoS 0. Retry/queue behavior reduces transient loss but does not provide broker acknowledgement or power-loss durability. A field system requiring QoS 1 must use a client with acknowledged publishing and retain gateway deduplication.

### 2.2 Route-input contract

The external predictive AI supplies:

```text
timestamp,bin_id,fill_pct,weight_kg,time_to_overflow_hours,risk_level,confidence_flag
```

Exactly one row is required for each `UGB-001` through `UGB-033`. The shared timestamp must include a timezone, be no more than 12 hours old, and be no more than five minutes in the future. Ranges, duplicate/missing IDs, risk labels, confidence values, and sensor disagreement are validated.

Missing sensor values may enter the degraded-data path, but missing predictive risk/time fields are rejected. A last-valid observation can be aged conservatively. If no trustworthy evidence exists, the result is inspection—not an invented safe zero or an invented full-bin truck load.

### 2.3 Three decisions

| Decision | Meaning |
| --- | --- |
| Collection required | At least one trustworthy/current or emergency trigger requires a route; uncertainty remains visible |
| Inspection required | Data quality prevents a safe no-collection decision, but evidence does not justify automatic collection |
| No collection required | Snapshot is sufficiently trustworthy and no service trigger is active |

Low-confidence urgent readings are never silently discarded. The route input retains them with a warning; the simulator allows only conservative emergency current/aged-fill evidence to override a low-confidence forecast.

## 3. Hidden state, observations, and forecast

The simulation maintains physical mass privately. At each six-hour observation, a separately seeded model produces ultrasonic and load-cell values with random noise, per-bin bias, drift, missing readings, outliers, and disagreement. Both policies in a pair receive the same error realization.

High-confidence observations receive a one-sided 95% margin (`z = 1.645`). A single available sensor uses a 7.5-point margin; general low-confidence/aged evidence uses 15 points. When both sensors are absent, a recent valid record is aged at 0.75 percentage points/hour plus its margin. With no valid record, inspection is required.

The histogram gradient-boosting regressor uses observed fill/weight, confidence, observed history, allocation, and time cycles. Its target is hidden 48-hour fill growth. A 45-day synthetic pre-period is split chronologically: the last 20% is holdout. Automated leakage guards reject feature names indicating hidden/true/future/target state.

<!-- FORECAST_RESULTS -->

The final model used 4,752 training rows and 1,188 chronological holdout rows. Its 48-hour MAE was **2.484 percentage points**, versus **7.646** for the naive benchmark, a 67.52% synthetic improvement. This is generated-data software validation, not measured forecast accuracy.

## 4. Road locations and matrices

OSRM runs over OpenStreetMap data. Its Table service returns duration and distance for every ordered pair of supplied coordinates. Distance is the length of the fastest route, not straight-line distance and not necessarily the geometrically shortest path.

The service matrix begins as 12 × 12:

- index 0: depot;
- indices 1–11: service sites.

It expands to 34 × 34 for individual-bin capacity decisions:

- index 0: depot;
- indices 1–33: bins.

Each site's costs are repeated for its three co-located bins. This expansion is executable code in `binsight/network.py`; it does not move markers or create a fictional road. Same-site bin-to-bin road cost is zero because one truck stop/crane position serves the site.

The matrices are vectors of numeric costs used by the optimizer. Road polylines are requested only for display/replay and cached separately. A geometry failure can therefore fall back to straight display segments without changing the solved stop order or reported matrix distance.

## 5. Collection selection

The fixed baseline marks every bin due at 06:00 after each full three-day interval. It has no day-zero empty-bin sweep.

The smart policy evaluates at 06:00 and 18:00. High/critical fill or predicted-overflow triggers become required candidates. Critical evidence inside the 20-hour horizon can override the usual 48-hour dispatch gap. Co-located siblings are considered next, followed by confident medium-risk bins whose addition stays within:

- available truck capacity;
- the soft 30 km route budget; and
- no more than 5 km incremental road-route cost.

The 5 km rule is not a radius around a critical bin. It compares the capacity-aware proxy route before and after adding one optional stop.

## 6. Capacity-constrained route solving

Candidate priority is preserved while each demand is rounded upward exactly as OR-Tools will consume it. Preselection explicitly packs candidates into the remaining trips. This prevents a floating-point total from passing preselection and then failing the integer vehicle-capacity constraint.

OR-Tools solves asymmetric depot tours with:

- the cached 34 × 34 distance matrix;
- a 9,000 kg payload per trip;
- no more than two daily trips;
- a 250 ms solve limit; and
- a fixed departure cost encouraging consolidation.

Every produced route starts and ends at `DEPOT`. If the solver returns no solution within the limit, a deterministic fallback exactly partitions bins into capacity-feasible buckets and orders each bucket by nearest road cost. Excess required bins are reported as unserved rather than silently dropped.

## 7. Chronological execution

Routes are not instantaneous. The minute-level SimPy process performs:

1. travel using OSRM duration and a departure-time traffic multiplier;
2. eight minutes of service at each bin;
3. emptying only at service completion;
4. 20 minutes of depot unloading; and
5. 10 minutes of turnaround before a later trip.

Waste generation continues during every activity. Overflow can therefore occur while a truck is en route or collecting. The two-trip count is shared by morning and evening; if a trip must wait for the next day, that wait is retained in the event timeline. Trips unfinished at the 30-day boundary are reported.

## 8. Fuel and CO₂

Total fuel is the sum of:

| Component | Prototype formula |
| --- | --- |
| Base driving | Road km × 0.45 L/km |
| Traffic penalty | Base driving × configured time-band increment |
| Payload penalty | Up to 15% of base fuel at full payload |
| Collection idle | Service hours × 3.0 L/hour |
| Depot idle | Unload/turnaround idle hours × 3.0 L/hour |

Tailpipe CO₂ is fuel × 2.68 kg/L. The US EPA gives 10,180 g CO₂ per US gallon of diesel (about 2.69 kg/L), so 2.68 is a close prototype approximation. All fuel-performance values require real truck calibration.

## 9. Map and mock tracking

All maps use 11 consolidated markers. Each popup lists the three bin IDs and their fill, weight, time to overflow, risk, confidence, decision reason, and state. The attention badge shows `n/3`; the highest-priority state determines the marker style. No visual offset is applied.

The map is restricted to the Subang Jaya pilot bounds, zoom 13–18, no tile wrapping, with a reset control and switchable route/site/truck layers. Smart routes use a cyan line with dark underlay; fixed routes use a restrained dashed comparison.

Mock tracking converts the representative route timeline and geometry into interpolated truck frames. The truck moves during travel and pauses during service/unloading/turnaround. A site becomes completed only after service completion. Play/pause, reset, timeline, and speed controls operate locally; reduced-motion mode removes pulsing animation.

![Representative BinSight route map for Subang Jaya](artifacts/route_map_preview.png)

**Figure 1.** Representative simulation route. Coordinates are planning anchors, not construction-ready locations.

## 10. Experiment and statistical analysis

Thirty paired replications are run for each scenario, giving 300 policy runs:

| Scenario | Configured change |
| --- | --- |
| Base | Declared demand, traffic, sensing, and capacity |
| High demand | Arrivals × 1.45 |
| Traffic | Traffic duration/fuel effect × 1.35 |
| Sensor failure | 18% missing + 8% outlier probability |
| Truck capacity | Capacity × 0.65 |

Fixed and smart policies share arrivals and observation noise within every pair. Raw metrics use all 30 days; post-warm-up metrics remove the first three days for both. Scenario results remain separate.

For lower-is-better metrics, beneficial effect = fixed − smart. For higher-is-better metrics, beneficial effect = smart − fixed. Positive is favorable. Each effect includes a 95% Student-t interval and a 19,999-draw paired sign-flip p-value. These measure Monte Carlo uncertainty under configured assumptions only.

## 11. Locked results and interpretation

<!-- LOCKED_RESULTS_START -->

The untouched final seed block begins at base +1,310,000 for arrivals and +1,320,000 for sensors. Artifacts contain 300 policy runs, 30 pairs per scenario, and 150 seed records.

Primary equal three-day post-warm-up base means:

| Metric | Fixed | Smart | Interpretation |
| --- | ---: | ---: | --- |
| Overflow incidents | 0.000 | 0.067 | Rare smart incidents; paired interval includes zero |
| Spilled waste | 0.000 kg | 0.755 kg | Paired interval includes zero |
| Road distance | 511.730 km | 633.448 km | Smart **23.79% worse**; p<0.001 |
| Fuel | 413.323 L | 491.458 L | Smart **18.90% worse**; p<0.001 |
| Tailpipe CO₂ | 1,107.706 kg | 1,317.108 kg | Smart **18.90% worse**; p<0.001 |
| Trips | 18.000 | 21.167 | Smart **17.59% worse**; p<0.001 |
| Stops | 297.000 | 309.600 | Smart **4.24% worse**; p<0.001 |
| Low-fill pickups | 0.567 | 72.033 | Smart made 71.467 more; p<0.001 |

The beneficial distance effect (fixed − smart) was -121.719 km (95% CI -138.773 to -104.664); fuel was -78.135 L (95% CI -88.962 to -67.308). Normal-demand fuel savings are therefore not supported.

Stress post-warm-up means show a different safety/cost trade-off:

| Scenario | Overflow fixed → smart | Distance fixed → smart | Fuel fixed → smart |
| --- | ---: | ---: | ---: |
| High demand ×1.45 | 62.667 → 2.733 | 511.080 → 860.166 km | 415.874 → 661.606 L |
| Traffic ×1.35 | 0.000 → 0.133 | 511.760 → 632.777 km | 505.581 → 610.646 L |
| Sensor failure | 0.000 → 0.167 | 511.431 → 1,190.298 km | 413.039 → 832.330 L |
| Truck capacity ×0.65 | 7.133 → 0.100 | 552.411 → 731.525 km | 438.026 → 550.231 L |

Smart reduced high-demand overflow by 95.64% and reduced-capacity overflow by 98.60%, but it consumed substantially more distance/fuel in every scenario. Under reduced capacity it also cut unserved required bins from 9.900 to 0.633. Under sensor failure it did not beat fixed safety and produced excessive inspection/routing activity.

The implemented smart policy is therefore an **emergency-capacity decision-support candidate**, not a routine replacement. A future field-calibrated hybrid should retain fixed service in a validated normal regime and activate predictive emergency routing only when a verified demand/capacity state warrants the cost.

<!-- LOCKED_RESULTS_END -->

## 12. Verification

Forty-eight automated tests cover configuration, siting, sensors, leakage, firmware payload size, safe input states, routing/capacity, chronology, fuel, statistics, map consolidation/bounds, tracking, and pipeline scenarios.

Browser QA covers:

- route-input demo and local mock dispatch;
- desktop 1440×900, tablet 768×1024, and mobile 390×844 without horizontal overflow;
- exactly 11 site markers and three popup rows per site;
- map bounds, zoom 13–18, no wrap, reset, and route containment;
- truck movement, pause/resume, completion timing, and reset; and
- reduced-motion behavior with zero browser console/page errors.

## 13. Known limitations and next work

- Inputs and outcomes are synthetic; sensor/vehicle parameters are not field calibrated.
- Coordinates are preliminary and require permission, utility, access, drainage, flood, and crane-safety surveys.
- The public map/router stack is prototype infrastructure without an SLA; production should use an appropriate provider or self-hosted Malaysian extract.
- MQTT publication is QoS 0 and the ESP32 queue is volatile.
- Mock dispatch/tracking has no authentication, driver acknowledgement, GPS, cancellation, or municipal API.
- Severe sensor failure may protect overflow at the cost of inspections and extra collection; an operator inspection workflow is required.
- The current smart policy is not an automatic replacement for the fixed schedule unless field validation proves the required safety/cost trade-off.
- Competition-wide gaps remain: physical build/photos, measured power, materials statement, BOM/receipts, cost-benefit, city-scale budget, deck/video, and proposal consistency.

## 14. UN Sustainable Development Goal alignment

- **SDG 11 — Sustainable Cities and Communities, Target 11.6.** BinSight models municipal-waste collection capacity and overflow risk. The high-demand and reduced-capacity scenarios show how predictive routing could support service resilience, but the result is synthetic and does not establish a measured reduction in Subang Jaya's environmental impact.
- **SDG 13 — Climate Action, Target 13.2.** The prototype includes route distance, decomposed fuel, and tailpipe CO₂ in collection decisions and evaluation. The corrected normal-demand result used more fuel than fixed service, so the climate-aligned next step is a field-calibrated hybrid policy—not a claim that the present smart policy already cuts emissions.

These mappings describe intended engineering contribution and evaluation criteria. Field kilometres, litres, emissions, overflow, and service outcomes are required before claiming real SDG impact.

## 15. Implementation map

| File | Responsibility |
| --- | --- |
| `config.json` | All pilot, sensor, operations, fuel, traffic, map, and stress assumptions |
| `binsight/observations.py` | Hidden-to-observed sensor model and leakage guard |
| `binsight/forecast.py` | Observed-feature 48-hour forecaster |
| `binsight/dispatch.py` | External snapshot validation, three-state decision, audit, mock dispatch |
| `binsight/network.py` | OSRM service/duration matrices and geometry cache |
| `binsight/routing.py` | Preselection, OR-Tools, exact fallback, route proxy |
| `binsight/simulation.py` | Minute-level policy and trip execution |
| `binsight/fuel.py` | Traffic, payload, driving, and idle fuel components |
| `binsight/maps.py` | Consolidated markers, routes, bounds, and tracking HTML |
| `binsight/tracking.py` | Timeline manifest and truck interpolation |
| `app.py` | Operator portal |
| `firmware/esp32_binsight/` | Three-bin controller firmware and payload harness |
| `artifacts/` | Locked forecasts, metrics, events, routes, seeds, and provenance |

## 16. Sources and assumption boundary

- MBSJ Voluntary Local Review 2021: https://www.mbsj.gov.my/sites/default/files/Subang%20Jaya%20Voluntary%20Local%20Review%202021.pdf
- DOSM MyCensus 2020 administrative-district findings: https://www.dosm.gov.my/uploads/publications/20221018120328.pdf
- VDL UGC underground system: https://www.vdltranslift.nl/en/products/crane-collection-vehicles/underground-bin-system-ugc
- VDL Maxxum: https://www.vdltranslift.nl/en/products/sideloader-collection-vehicles/sideloader-maxxum
- OSRM HTTP API: https://project-osrm.org/docs/v26.4.0/api/
- OpenStreetMap tile policy: https://operations.osmfoundation.org/policies/tiles/
- US EPA diesel CO₂ reference: https://www.epa.gov/energy/greenhouse-gas-equivalencies-calculator-calculations-and-references

Waste density, commercial generation, truck payload, base fuel rate, traffic multipliers, payload penalty, idle rate, service time, compaction, and preliminary coordinates remain prototype assumptions until measured locally.
