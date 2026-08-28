# Focus Area C research brief — Subang Jaya

## Recommended position

BinSight should be presented as a **forecast-then-optimize decision-support prototype**, not an autonomous municipal system:

1. one Teensy 4.1 samples three fill/health channels—one general-waste and two recycling-return—and the PR #2 ESP32-C3 relays them;
2. the producer API validates, stores, acknowledges and replays stable, boot-scoped three-bin events;
3. locally trained tree models estimate 6/24/48/168-hour growth and calibrated synthetic overflow probabilities from observable data;
4. a safe three-state decision separates collection from inspection and no-action;
5. OR-Tools builds capacity-feasible trips from OSM/OSRM road costs; and
6. a paired SimPy experiment reports the safety/cost trade-off against a corrected fixed baseline.

The strongest competition evidence is the transparent end-to-end Focus Area C implementation. The result should not be forced into a fuel-saving success story if the locked data shows otherwise.

## Local waste basis

MBSJ's 2021 Voluntary Local Review reports 249,668.08 tonnes of solid waste in 2019 and a **1.90 kg/capita/day** indicator for Subang Jaya: [MBSJ Voluntary Local Review 2021](https://www.mbsj.gov.my/sites/default/files/Subang%20Jaya%20Voluntary%20Local%20Review%202021.pdf).

DOSM's MyCensus 2020 administrative-district publication gives an average household size of **3.7 people** for Subang Jaya: [DOSM MyCensus 2020](https://www.dosm.gov.my/uploads/publications/20221018120328.pdf).

These imply `1.90 × 3.7 = 7.03 kg/household/day`, or 3,515 kg/day for 500 households. The additional **4.43 kg/commercial unit/day** is retained as a configurable planning value from an older Malaysian waste-minimization supporting report: [JPSPN/KPKT supporting report](https://jpspn.kpkt.gov.my/jpspn/resources/Images%20JPSPN/Sumber%20Rujukan/Kajian/Kajian%20Mengenai%20Pengurangan%20Sisa%20di%20Malaysia/SupportingReport1_V2.pdf). It contributes 88.6 kg/day, giving 3,603.6 kg/day total. Replace the commercial value with an MBSJ/operator audit before field claims.

## Bin and vehicle archetype

VDL lists underground UGC containers in 3 m³ and 4.5 m³ variants; BinSight uses 4.5 m³: [VDL UGC](https://www.vdltranslift.nl/en/products/crane-collection-vehicles/underground-bin-system-ugc).

VDL describes the Maxxum for 4.5 m³ underground containers and lists a 1,500 kg maximum lift: [VDL Maxxum](https://www.vdltranslift.nl/en/products/sideloader-collection-vehicles/sideloader-maxxum). Its IES family includes a 22 m³ body: [VDL IES](https://www.vdltranslift.nl/en/products/body-types/ies).

BinSight's 120 kg/m³ loose mixed-waste density, 3.5 compaction ratio, 9,000 kg route payload, and fuel parameters are prototype assumptions. The resulting nominal 540 kg per bin is below the 1,500 kg lift reference but is not a manufacturer-approved wet gross mass. Malaysian chassis, axle, crane, water-ingress, and homologation limits require verification.

## Why 44 bins

For three days and a 25% reserve, the district design load is:

`3,603.6 × 3 × 1.25 = 13,513.5 kg`

The four configurable material allocations require 11 general, 11 plastic, 6 metal, and 8 glass bins by district capacity. The demonstration deliberately puts one of every material at each of 11 sites, giving **44 bins and 11 service sites** with consistent source separation. `SITING_PLAN.md` shows the calculation. This is a routing/capacity model, not 11 deployed controllers. The physical profile is one Teensy 4.1/C3 relay with only three registered fill channels and is therefore explicitly incomplete for this four-bin target.

## OpenStreetMap and OSRM

OSRM's Table service computes durations—and optionally distances—between all ordered pairs of supplied coordinates. Distances are along the fastest routes, in metres: [OSRM Table service](https://project-osrm.org/docs/v26.4.0/api/#table-service).

BinSight caches the depot/recycling-facility/site matrix, its expansion to an origin plus 44 bins, requested/snapped coordinates, durations, distances, and display geometry. Four bins at one site repeat the same site costs because they are physically co-located. Separate return matrices charge dry-recycling routes for unloading at the recycling facility and returning to the depot. The UI uses one site marker rather than misleading visual offsets.

Normal human map viewing must preserve visible attribution and comply with the OpenStreetMap Foundation's tile rules. The public tile service is best-effort, requires correct URL/attribution, and prohibits bulk prefetch: [OSMF Tile Usage Policy](https://operations.osmfoundation.org/policies/tiles/). Deployment should use a suitable hosted provider or self-hosted Malaysian OSM stack.

The depot at **3.06192, 101.55272** and MBSJ USJ 9 Recycling Centre at **3.04547, 101.58697** are provisional routing anchors, not operator authorization. Vehicle acceptance, material handling, access, and hours remain field gates.

## Legacy electronics/MQTT reference and current target

The retained ESP32/gateway implementation is a legacy executable reference, not the approved physical producer. The current fill target keeps all three fill channels on Teensy 4.1 and uses the PR #2 ESP32-C3 only as the relay. A separate PR #3 ESP32-C3 relays Grove Vision AI V2 recognition/session results for recycling returns; those events never feed fill routing. Every real pressure/load channel needs rated structural hardware, overload protection and conditioning. A hobby FSR is not a safe full-container weighing solution.

The legacy controller publishes a three-bin JSON message. Its maximum harness case fits the configured 1,024-byte MQTT buffer. PubSubClient QoS 0, retries and a RAM queue do not provide acknowledged durable delivery. The current producer must instead satisfy telemetry-routing 2.1 event identity/type, acknowledgement/replay, UTC and quality gates before live integration is enabled.

## Observation and decision safety

The simulator separates hidden physical mass from noisy sensor observations. Random noise, bias, drift, outliers, missing data, disagreement, confidence, and uncertainty use saved seeds. The forecast/dispatcher never receives hidden truth.

A single available sensor receives a 7.5-point margin. General low-confidence/aged evidence receives 15 points. Both sensors missing with no valid history produces inspection, not a fabricated safe zero or full load. A predictive-AI critical/high record remains collection-relevant, with conservative capacity reserved and an operator warning.

This policy is intentionally asymmetric: uncertainty is never silently safe, but uncertain optional pickups are not added merely to make a route look efficient.

## Fuel and carbon assumptions

Fuel includes base driving, time-band traffic, payload penalty, collection idle, and depot idle. Only the carbon conversion is externally anchored: the US EPA uses **10,180 g CO₂ per US gallon of diesel**, about 2.69 kg/L: [US EPA calculations](https://www.epa.gov/energy/greenhouse-gas-equivalencies-calculator-calculations-and-references). BinSight uses 2.68 kg/L as a close approximation.

The 0.45 L/km base rate, 3.0 L/hour idle rate, 15% full-payload penalty, and traffic multipliers are assumptions. A real truck logger/fuel audit is required before economic or climate claims.

## Forecast and experiment design

The v2 forecaster is trained on a separate 730-day patterned synthetic pre-period. Train, calibration and untouched holdout timestamps are separated by the complete 168-hour maximum target horizon; calibration fits the 48-hour q90 adjustment, while holdout reports 6/24/48/168-hour errors, time-to-overflow error, alert quality, interval coverage and probability calibration. The 30-day operational window is excluded. The confirmatory policy design uses 30 paired replications per scenario, with fixed and dynamic policies sharing arrivals, events and observation noise within each pair. The current four-bin artifact is only a two-pair normal-scenario smoke run; the older 30-pair studies have a different configuration hash and are retained as historical evidence.

Eleven separate scenarios cover normal patterned demand, a high-demand season, event-heavy demand, persistent and localized surges, gradual trend, abrupt change, traffic disruption, sensor failure, reduced capacity and combined demand/operational stress. The demand equation combines normalized hourly/day/week/month/year factors, targeted event shapes, bounded trends, district/local AR(1) regimes and non-negative Gamma arrivals. Confidence intervals represent Monte Carlo variation under assumptions, not field causality.

<!-- LOCKED_RESEARCH_RESULTS_START -->

The following numbers are the retained **historical v1** result. They do not describe the changed dynamic-v2 demand or routing model; current v2 evidence is regenerated separately in `artifacts/dynamic_v2/` and `DYNAMIC_V2_RESULTS.md`.

The final forecaster achieved **2.484 percentage-point MAE** on the synthetic chronological 48-hour holdout, versus **7.646** for the naive benchmark (67.52% improvement).

In the primary equal three-day post-warm-up base comparison, fixed service averaged 511.730 km and 413.323 L; smart averaged 633.448 km and 491.458 L. The smart policy was therefore **23.79% worse for distance** and **18.90% worse for fuel/CO₂**, with intervals wholly favoring fixed. Fixed averaged zero overflow; smart averaged 0.067 incidents, with the paired overflow interval crossing zero.

The safety value appears under stress. At 1.45× demand, smart reduced overflow incidents from 62.667 to 2.733 (95.64%) and spill from 3,006.703 to 58.828 kg (98.04%), but used 59.09% more fuel. At 0.65× truck capacity it reduced incidents from 7.133 to 0.100 and unserved required bins from 9.900 to 0.633, but used 25.62% more fuel. Under sensor failure, fixed remained at zero overflow while smart averaged 0.167 and more than doubled fuel.

The v1 result does **not** support routine fuel-saving deployment. It motivated the v2 trip-value and demand-model revision. Earlier claims of 5.08% lower distance/fuel remain withdrawn.

<!-- LOCKED_RESEARCH_RESULTS_END -->

## Competition interpretation

The digital Focus Area C requirements are substantially covered: 500 households, 20 commercial units, 30 days, multiple KPIs, fixed-versus-AI comparison, statistical analysis, source, seeds, and a live simulation portal.

Full competition compliance is not complete. The physical 1:20 build/photos, measured <10 W power evidence, sustainability materials statement, BOM/receipts, cost-benefit, scaling budget, SDG mapping, final deck/video, and proposal consistency remain open. The proposal also promises a Teensy/FreeRTOS sensing platform, camera classifier, and physical ESP32 QR return station that this repository does not currently demonstrate. See `../docs/COMPETITION_COMPLIANCE_AUDIT.md`.

## Operational recommendation

Keep fixed three-day service as the field safeguard. Use BinSight first in shadow mode: ingest calibrated real readings, issue inspection/route recommendations without controlling trucks, compare recommendations with operator decisions, and prospectively measure overflow, kilometres, litres, service time, data outages, and false alerts. Only then tune/authorize a deployment policy.
