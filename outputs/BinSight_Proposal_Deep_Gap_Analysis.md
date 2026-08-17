# BinSight proposal: deep gap analysis

**Team:** MON BLUE  
**Audit date:** 17 August 2026  
**Compared documents:** current `BinSight_Final_Proposal.pdf` and `Degree level question paper-SEAR 1.pdf`  
**Excluded:** GreenRoute material, by instruction  
**Research mode:** requirements audit, five specialist lenses, technical source check, after-action review and adversarial judge review

## Executive verdict

BinSight has a coherent problem, a plausible prototype and a useful fixed-route comparison. The proposal is concise, readable and within the 200-word body limit. It is not yet a secure engineering submission under the degree-level brief.

The weakness is evidence, not concept. The proposal names hardware, FreeRTOS, a tree model, a classifier and a simulation, but it omits several items that the brief explicitly asks judges to assess: the 1:20 scale, the 500-household/20-commercial-unit district, quantifiable KPIs, statistical analysis, reproducible seeds, measured power, material sustainability, team training/fine-tuning, safety voltage and explicit SDG alignment. These are high-confidence gaps because they are direct differences between the governing brief and visible proposal text.

The strongest repair is to make **reliability-aware collection** the technical centre of BinSight: calibrated sensor readings receive confidence and freshness flags; the prediction and routing stages consume those flags; low-confidence data trigger resampling or a safe fixed-schedule fallback. That is more defensible than presenting four loosely connected focus areas.

## What already works

- The problem statement identifies a real operational conflict: fixed schedules can collect underfilled bins while other sites overflow.
- The physical concept includes the required minimum of three instrumented bins and at least one physical AI element.
- The use of Teensy 4.1 for bins, ESP32 for the return station and a local hub respects the intended edge-computing direction.
- FreeRTOS tasks, confidence flags and watchdog recovery give the proposal a credible reliability thread.
- The simulation already proposes a 30-day comparison between fixed collection and priority collection.
- The language treats the work as a prototype and simulation, not a deployed or proven system.
- The current body is 195 words under the established counting method, leaving only five words of margin.

## Requirements traceability

| Brief requirement or scoring signal | Visible in current proposal | Status | Required repair |
|---|---|---|---|
| PDF proposal, 200 words | 195-word body | Meets | Keep a small counting margin in the final revision |
| Project Proposal, 2 pages | Two-page PDF: cover plus one content page | Ambiguous | Confirm whether the cover counts; the brief does not resolve this |
| Physical prototype at minimum 1:20 scale | Street-block prototype, no scale | Missing | State `1:20` |
| At least three instrumented bins | Three smart bins | Meets | Keep |
| At least one physical AI component | Camera classifier and actuator flow proposed | Partial | State what runs live and what output the judges will see |
| Real-time output | LED states and dashboard logging implied | Partial | State live fill/confidence/accept-reject output |
| Materials documented with sustainability statement | Not stated | Missing | Add material documentation; prepare a mass/reuse/end-of-life table |
| Measured continuous power, target below 10 W | Lower sensing energy is mentioned, no measurement | Missing | Measure total DC-input average and peak power against 10 W |
| Maximum 12 V DC and no mains exposure | Not stated | Missing | State prototype operates below 12 V DC |
| 500 households and 20 commercial units | Only "district model" | Missing | State the full simulation population |
| 30-day simulation | Stated | Meets | Keep |
| At least two quantifiable KPIs | "Fewer" and "lower" without units or reported measures | Missing | Name metrics and units; do not need to promise unsupported percentage gains |
| No-AI baseline versus AI-enabled case | Fixed versus priority routes | Partial | Label these explicitly as baseline and AI cases |
| Statistical analysis | Not stated | Missing | Use paired seeds and report mean differences with confidence intervals |
| Reproducible source and seed values | Not stated | Missing | Commit to versioned code, configuration and seed list |
| Team-trained or fine-tuned AI | "Tree-based model" and "camera classifier" only | Missing | State `team-trained` and `team-fine-tuned` |
| Hardware budget, receipts, realistic feasibility | Budget ceiling named, no bill of materials | Partial | Prepare an itemised BOM, contingency and borrowed-equipment note |
| At least two SDGs | Not stated | Missing | Map metrics to SDG 11.6 and 12.5; treat SDG 13 as secondary |
| Cost-benefit and city-scale feasibility | Not stated | Missing from proposal; required later | Prepare cost per bin/site, annual truck-km sensitivity and scaling architecture |
| Focus D citizen engagement | QR session and simulated refund | Partial mismatch | Add a defined reward/history interaction or stop labelling it Focus D |

## Highest-priority gaps

### 1. The proposed KPIs are not quantifiable

"Fewer overflows," "shorter route distance" and "lower fuel and CO2" identify directions, not test variables. A judge cannot tell what will be counted, in what units, or how uncertainty will be handled. This directly weakens the system-efficiency and sustainability criterion.

**Repair:** predeclare at least four outputs: overflow incidents per 30 days, collection trips, route distance in kilometres and estimated collection CO2 in kilograms. Run the baseline and AI case on the same demand seeds. Report the paired mean difference and a 95% confidence interval. SciPy supports paired bootstrap resampling, while the simulation itself is a natural fit for process-based discrete-event modelling in [SimPy](https://simpy.readthedocs.io/en/stable/index.html) and uncertainty reporting with [SciPy bootstrap](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.bootstrap.html).

This avoids unsupported percentage promises while still satisfying the requirement for measurable KPIs.

### 2. The required district scale and reproducibility are absent

The brief specifies 500 households, 20 commercial units and 30 days. The proposal states only a 30-day district model. It also omits source code and seed values.

**Repair:** state the population explicitly. Use prototype logs to calibrate sensor noise and fill observations, not as the sole basis for 520 units. Generate separate household and commercial waste-arrival processes, save every input parameter, and run both strategies on identical seed sets. Submit the code, configuration, dependency list and seeds.

### 3. Reliability is named but not testable

FreeRTOS and a watchdog do not by themselves establish determinism or reliability. FreeRTOS uses fixed-priority pre-emptive scheduling by default, and a continuously ready high-priority task can starve lower-priority work. Timing therefore depends on task design, priorities and blocking behaviour, not on the RTOS name alone. See the official [FreeRTOS scheduling description](https://key.freertos.org/Documentation/02-Kernel/02-Kernel-features/01-Tasks-and-co-routines/04-Task-scheduling).

**Repair:** replace "deterministic polling" with "periodic polling with measured deadlines" or "bounded polling jitter." Record:

- sampling deadline-miss rate;
- polling jitter;
- stale-reading detection time;
- watchdog recovery time;
- packet-loss or hub-disconnection behaviour.

Inject four faults during the demonstration: blocked ultrasonic path, load-cell offset, stalled sensor task and lost hub link. Show that confidence falls, stale data are not used as normal measurements, and collection falls back safely.

### 4. The architecture omits the bin-to-hub interface

The proposal says the hub logs bin data but never states how data arrive. Teensy 4.1 supports USB serial and wired Ethernet, but Ethernet needs a separate connector; its serial ports can also connect to a wireless module. These are materially different cost, power and integration choices in the [PJRC specification](https://www.pjrc.com/store/teensy41.html).

**Repair:** use wired USB serial for the 1:20 prototype and state it. This is simple, visible and avoids unsupported wireless claims. Measure the complete system at the shared DC input, including the hub and all USB-powered boards.

### 5. The BCRS claim is technically inaccurate

The current classifier accepts plastic, metal and glass while the text says the station follows Singapore's Beverage Container Return Scheme. NEA states that the scheme covers deposit-mark plastic and metal beverage containers from 150 mL to 3 L; glass is excluded. The official refund methods are also not described as the proposal's QR session. See the [NEA scheme page](https://www.nea.gov.sg/our-services/waste-management/beverage-container-return-scheme) and [NEA producer Q&A](https://www.nea.gov.sg/docs/default-source/default-document-library/bcrs-qna-for-19-and-26-feb-2025-producers-briefing_final.pdf).

**Repair:** accept deposit-mark plastic bottles and metal cans only. Describe the prototype as **inspired by BCRS eligibility rules**, not as reproducing the official RVM protocol. Let the camera classify the container and a mock printed code validate deposit eligibility; acceptance requires both. Treat the QR session as a simulated user reward mechanism.

### 6. AI depth is asserted, not specified

The tree model has no features, training source, validation split or error metric. The camera has no class definitions, dataset, held-out test or failure threshold. The brief specifically limits pre-trained APIs to supplemental use.

**Repair for fill prediction:** use features such as recent fill level, fill-rate slope, weight, bin/site identity and time-of-day. Use a chronological split so future observations do not leak into training; [TimeSeriesSplit](https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html) exists for this reason. Report time-to-overflow MAE in hours and overflow-event recall.

**Repair for classification:** define `eligible plastic bottle`, `eligible metal can` and `reject`. Fine-tune a lightweight model on team-labelled images, separate physical container instances across train/validation/test sets, and report per-class precision, recall and a confusion matrix. The [Ultralytics custom-data workflow](https://docs.ultralytics.com/yolov5/tutorials/train-custom-data) and [scikit-learn evaluation guidance](https://scikit-learn.org/stable/modules/model_evaluation.html) support this structure.

### 7. "Rank pickups" is not route optimisation

Ranking identifies which bins deserve service; it does not determine a feasible vehicle route. The route method needs locations, a distance matrix, capacity, service rules and an objective.

**Repair:** use the prediction to select or penalise visits, then solve a capacity-constrained vehicle-routing problem. Compare this with a fixed schedule under the same simulated demand. [OR-Tools](https://developers.google.com/optimization/routing) supports capacitated and time-constrained routing, but its documentation warns that larger problems may yield good rather than proven-optimal solutions. Call the result `priority route` or `solver route`, not `optimal route`, unless optimality is established.

### 8. Budget feasibility is narrow and unproven

As of this audit, SparkFun lists a Teensy 4.1 at USD31.50. Three boards therefore total USD94.50 before sensors, ESP32, servo, camera, wiring, power equipment and structural materials. See [SparkFun's current product listing](https://www.sparkfun.com/teensy-4-1.html). The USD150/SGD200 ceiling may still be achievable, but the proposal provides no evidence.

**Repair:** choose one hub. A Raspberry Pi is more compatible with the power target than treating an unspecified laptop as part of the continuous prototype. List purchased and borrowed items separately, include shipping only if the rules require it, retain receipts and reserve contingency. Do not write `Raspberry Pi/laptop`; it reads as an unresolved architecture decision.

### 9. Power feasibility must be measured, not inferred

The Raspberry Pi documentation lists a Pi 4 bare-board active current around 600 mA and a camera requirement around 250 mA, while noting that peripherals alter demand. This makes sub-10 W operation plausible for a carefully selected hub, not proven. See [Raspberry Pi power requirements](https://www.raspberrypi.com/documentation/computers/raspberry-pi.html#typical-power-requirements).

**Repair:** measure voltage and current at the common DC input during idle, normal sensing, camera inference and servo actuation. Report continuous average, maximum observed power and test duration. Keep all exposed prototype supplies below 12 V DC. If a laptop is used only to present the dashboard, label it external presentation equipment and confirm with organisers whether its power is outside the prototype limit.

### 10. Sustainability alignment is currently declarative rather than traceable

The proposal mentions lower fuel, CO2 and contamination but does not name an SDG or explain the relationship.

**Repair:** use two primary mappings:

- **SDG 11.6:** overflow incidents and controlled municipal collection, directly aligned with urban waste management in [UN Goal 11](https://sdgs.un.org/goals/goal11).
- **SDG 12.5:** accepted recyclable containers, rejection error and contamination, aligned with waste reduction and recycling in [UN Goal 12](https://sdgs.un.org/goals/goal12).

Use Goal 13 only as a secondary connection through estimated collection emissions. Do not imply that a prototype directly achieves a national climate target. Estimate CO2 from route distance or fuel use with one documented vehicle/fuel factor and label the result as estimated. The [US EPA](https://www.epa.gov/moves/moves-best-tool-my-work) notes that simple per-mile or per-fuel rates can suit non-regulatory estimates when a full transport model is unnecessary; select a factor appropriate to the simulated vehicle and disclose its limits.

## Engineering design remedies

### Physical sensing and data quality

1. Calibrate each ultrasonic sensor at empty and full reference positions.
2. Calibrate each load cell with known masses and record zero drift.
3. Filter ultrasonic spikes and store both raw and filtered values.
4. Define confidence rules, for example out-of-range distance, flat-lined sensor, disagreement between distance and weight, or stale timestamp.
5. Send `bin_id`, timestamp, fill estimate, weight, confidence, fault code and power state to the hub.
6. Never allow a low-confidence reading to silently enter model training as ground truth.

### Reliability-aware decision chain

The distinctive engineering contribution should be the propagation of measurement quality through the whole system:

`sensor reading -> calibration/filter -> confidence and freshness -> fill prediction -> pickup eligibility -> route -> fallback`

When confidence is low, the hub should resample, use a conservative rule or retain the fixed schedule. This makes the watchdog and confidence flags operationally relevant instead of decorative.

NASA's systems-engineering guidance recommends requirements flow-down, defined verification methods, acceptance tests and a requirement verification matrix. A one-page internal matrix is sufficient for this prototype: requirement, method, test input, acceptance threshold, result and evidence file. See the [NASA V&V appendix](https://www.nasa.gov/reference/system-engineering-handbook-appendix/).

### Model and simulation separation

Keep four datasets distinct:

- sensor calibration data;
- fill-model training/validation data;
- camera train/validation/test images;
- district simulation inputs and outputs.

Prototype readings can calibrate measurement noise and fill dynamics, but three bins cannot by themselves represent 520 premises. Define household and commercial generation distributions separately, test low/normal/high demand, and run baseline and AI policies on paired seeds. Record assumptions in a configuration file. NIST's AI RMF calls for documented test sets, benchmarks, uncertainty, repeatable evaluation and performance under conditions similar to use; it also recommends safe failure behaviour and documented limits. See the [NIST AI RMF Core](https://airc.nist.gov/airmf-resources/airmf/5-sec-core/).

### KPI definition

| Layer | Metric | Unit | Comparison |
|---|---|---|---|
| Sensor | Fill error | percentage points or centimetres | Reference fill levels |
| RTOS | Deadline misses and polling jitter | count; milliseconds | Normal and fault-injected runs |
| Reliability | Fault detection and recovery time | seconds | Four defined injected faults |
| Prediction | Time-to-overflow MAE; overflow recall | hours; proportion | Chronological held-out period |
| Classifier | Per-class precision/recall; false accept rate | proportion | Held-out container instances |
| Collection | Overflow incidents; trips; distance | count; count; kilometres | Paired fixed versus priority runs |
| Environment | Estimated fuel and CO2 | litres; kg CO2 | Same route seeds and vehicle factor |
| Power | Average and peak system power | watts | Idle, sensing, inference, actuation |
| Cost | Prototype cost | USD or SGD | Itemised BOM versus cap |

No improvement percentage must be promised before testing. The engineering requirement is to define how results will be measured and compared.

## Five-expert review

### Requirements assessor

The proposal's largest risk is omission of explicit brief language. A strict marker cannot assume that "district" means 500 households and 20 commercial units, or that "lower energy" means measured operation below 10 W. This reviewer would spend scarce words on scale, measurement, seeds, voltage and SDGs.

### Embedded-systems and reliability engineer

The hardware concept is plausible, but `Raspberry Pi/laptop` and the missing interface show that the architecture is not frozen. This reviewer would choose Raspberry Pi plus wired USB serial, define tasks and deadlines, and prove the watchdog and fault flags with injected failures. They disagree with the requirements assessor on breadth: adding more checklist phrases is less valuable than one verified end-to-end path.

### AI and simulation reviewer

The simulation lacks a data-generating model, a validation split and uncertainty. Three prototype bins cannot supply representative district data without explicit assumptions. This reviewer would prioritise paired seeded runs, chronological model evaluation and held-out classifier testing over adding another AI feature. They also reject the loose use of "route optimisation" for pickup ranking.

### Sustainability and policy reviewer

The current BCRS wording is the clearest factual defect: glass is outside the official scheme, and the QR interaction should not be presented as the official refund protocol. This reviewer would map each sustainability claim to a measured variable and use SDGs 11.6 and 12.5 as primary alignments. They disagree with the AI reviewer that route metrics alone are sufficient; materials, power and end-of-life evidence also affect sustainability marks.

### Skeptical competition judge

Smart bins, classifiers and routing are familiar ideas. The proposal becomes memorable only if it states the integration problem it solves. The strongest answer is: **BinSight prevents noisy or stale sensor data from causing bad collection decisions.** The judge would reward a smaller system that demonstrates this chain reliably over four focus areas that are only partially implemented.

### Council synthesis

The central tension is breadth versus proof. Keep all four focus-area references only if the build is scoped as:

- **Core:** Focus A sensing/reliability plus Focus C prediction/routing.
- **Bounded extension:** Focus B eligibility classification plus a small Focus D QR-linked reward record.

Do not add an NLP chatbot unless it can be tested without weakening the core. If Focus D must match the paper literally, either implement a minimal intent-based help interface and reward history or stop claiming full Focus D coverage.

## After-action review of the current proposal

### Intended result

A polished, low-buzzword, one-page engineering brief with a separate cover, all focus areas represented and a body below 200 words.

### Actual result

The document achieved the word limit, visual clarity and concise hardware flow. It lost requirement traceability. Removing numeric targets avoided unsupported claims, but replacing them with directional words also removed measurable KPI definitions. Merging focus-area material saved space but compressed architecture, test method and acceptance evidence into a component list.

### Root-cause chain

1. The redesign optimised for clean appearance and a strict word limit.
2. Detailed sections and target ranges were removed to reduce density and risk.
3. Hardware and model names became substitutes for methods and tests.
4. The final body described what is included, but not how success or failure will be determined.
5. Several exact constraints remained only in the question paper, invisible to a judge reading the proposal.

### Corrective actions

| Priority | Action | Suggested owner | Due |
|---|---|---|---|
| P0 | Freeze Raspberry Pi hub and wired USB serial interface | System lead | Before proposal freeze |
| P0 | Correct BCRS scope: plastic and metal only; simulated QR reward | Return-station lead | Before proposal freeze |
| P0 | Add 1:20, 500+20, seeded baseline/AI runs, confidence intervals, 12 V, 10 W, BOM and SDGs to body | Proposal owner | Before submission |
| P0 | Replace qualitative KPIs with named metrics and units | Simulation lead | Before submission |
| P1 | Define sensor calibration, confidence rules and fault-injection tests | Embedded lead | Before integrated test |
| P1 | Define model features, chronological split, held-out camera test and metrics | AI lead | Before model training |
| P1 | Implement capacity-constrained routing and paired-seed experiment | Simulation lead | Before results freeze |
| P1 | Build requirements-verification matrix and evidence folder | Test lead | Before final presentation |
| P2 | Add cost-benefit, material lifecycle and city-scale assumptions | Sustainability lead | Before final presentation |

## Recommended 200-word replacement body

The following is exactly 200 words under a conservative token count that counts separated numeric elements individually. Headings are excluded. It corrects the most important compliance gaps without presenting untested benefits as results.

### Problem Statement

Fixed schedules empty underfilled bins while sites overflow, wasting fuel and denying operators evidence for service decisions.

### Proposed Solution

BinSight will build a 1:20 block with three Teensy 4.1 bins, an ESP32 return station and Raspberry Pi hub. Focus A uses FreeRTOS to schedule ultrasonic and load-cell sampling; calibrated filters, confidence flags and watchdog recovery isolate blocked, noisy or stale readings. Focus C applies a team-trained tree model to estimate time-to-overflow and a capacity-constrained solver to compare priority collection with fixed schedules. Focus B uses a team-fine-tuned camera to accept deposit-mark plastic bottles and metal cans and reject other items. Focus D logs QR returns and simulated refunds. The prototype shows live states, documents material choices, operates below 12 V DC and measures continuous power against the 10 W target.

### Simulation / Proposed Measures

A seeded 30-day SimPy model of 500 households and 20 commercial units will report overflows, trips, route distance and estimated CO2 for paired baseline and AI runs, with confidence intervals. Model error, per-class precision/recall, fault recovery, power and an itemised USD150/SGD200 bill of materials will be reported. The design supports SDG 11.6, SDG 12.5 and SDG 13 through improved waste collection, recycling and lower collection emissions.

## Final recommendation

Do not broaden BinSight. Make the current concept auditable. Freeze the interface and hub, correct the BCRS scope, state the exact prototype and simulation scales, name measurable outputs, and show how sensor uncertainty changes routing decisions. With those changes, the proposal reads as an engineering plan rather than a catalogue of technologies.

The cover-plus-content interpretation of "2 pages" remains the only unresolved submission-format risk. Seek written confirmation from the organiser before adding or removing a page.

## Research record

The full claim-to-source registry is stored in `work/research-notes/binsight_gap_analysis/evidence_registry.md`. GreenRoute sources were not consulted or used. Core external sources were official government, manufacturer, intergovernmental or project documentation; inaccessible academic pages and secondary mirrors were excluded from decisive claims.
