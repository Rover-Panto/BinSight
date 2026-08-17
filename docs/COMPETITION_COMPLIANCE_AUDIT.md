# Competition compliance and proposal-gap audit

Last verified: 17 August 2026

## Source documents

This audit compares the repository with:

- `Degree level question paper-SEAR 1.pdf` (5 pages); and
- `BinSight_Final_Proposal.pdf` (2 pages, with one content page).

Document text is treated as requirements/background only. It does not override the user's implementation instructions or prove that a physical component exists.

## Deadline record

The question paper's submission table states:

| Item | Stated deadline |
| --- | --- |
| Project proposal (2-page PDF) | Week 5 |
| Progress report + prototype photos | Week 10 |
| Simulation source code + README | Week 10 |
| Final report (maximum 20 pages) | Week 12 |
| Presentation slides + video | Week 12 |
| Live judging | Week 12 |

Its final notes give two absolute dates: a 200-word proposal by **4 September 2026 at 5:00 pm GMT+8**, and the final online presentation on **5 September 2026**. These absolute dates appear inconsistent with a normal 12-week sequence and should be confirmed with the organizers in writing.

## Deliverable compliance

| Requirement from question paper | Current evidence | Status |
| --- | --- | --- |
| 1:20 street-block physical model with at least 3 instrumented bins | Firmware, wiring, schema, and a one-controller/three-bin design exist; no completed build, scale proof, or photos are committed | Open |
| At least one physical AI component | Sensor-to-forecast software path exists; operation on assembled ESP32/Raspberry Pi hardware is not evidenced | Partial |
| Real-time physical output | Streamlit dashboard works; no photographed LED/screen/actuator output from the physical model | Partial |
| Materials sustainability statement | No material inventory or reuse statement | Open |
| Measured continuous power, target <10 W | No wattmeter method or measurement | Open |
| 500 households + 20 commercial units over 30 days | Configuration, site plan, and simulation enforce these values | Meets |
| At least two quantitative KPIs | Overflow, spill, trips, stops, distance, time, fuel, CO₂, utilization, and data-quality metrics are produced | Meets |
| Baseline versus AI with statistical analysis | Paired fixed/smart replications, common randomness, confidence intervals, and sign-flip tests | Meets |
| Live or recorded simulation demo | Runnable Streamlit portal with route input, operations, and mock tracking | Meets for live demo |
| Reproducible source and seeds | Source, configuration, cached matrices, seed manifest, provenance, and tests | Meets |
| 15-minute presentation + 5-minute Q&A | No final deck/timing script | Open |
| Video demo ≤3 minutes | No final MP4/storyboard | Open |
| Cost-benefit analysis | No sourced BOM, operating cost, payback, or sensitivity table | Open |
| Sustainability impact assessment | Routing emissions are modelled, but hardware/material/energy impacts are incomplete | Partial |
| City-wide scaling within realistic budget | No deployment architecture, communications cost, maintenance staffing, or staged budget | Open |
| Hardware ≤USD150/SGD200 with receipts | No final BOM or receipts | Open |
| Safe ≤12 V DC prototype | Design uses low-voltage electronics, but assembled-system inspection is not evidenced | Partial |
| Team-implemented/trained AI | Histogram gradient boosting is trained locally on synthetic data; real-data training/validation remains open | Partial |
| At least two UN SDGs in final report/deck | The Focus Area C report maps evidence and limitations to SDG 11.6 and SDG 13.2; the final deck must retain the same claim boundary | Meets in report; deck open |

## Proposal-to-implementation contradictions

1. **Controller platform.** The proposal promises Teensy 4.1 with FreeRTOS for the three sensing bins. The implemented and user-approved topology uses one ESP32 for three bins. Update the proposal/final report to the ESP32 design or implement and test the promised Teensy path; do not claim both.

2. **Focus B camera classifier.** The proposal promises a camera that accepts plastic, metal, and glass and rejects non-recyclables. No camera model, dataset, training evaluation, actuator integration, or hardware evidence exists in this repository.

3. **Focus D return station.** The proposal promises an ESP32 QR/chute/servo station aligned with a return-machine flow. The citizen app contains simulated return sessions, but there is no corresponding ESP32 station firmware or physical verification.

4. **Prototype logs.** The proposal says the 30-day simulation uses prototype logs. The current experiment uses locally scaled synthetic arrivals and simulated sensor errors. It can accept a predictive snapshot, but no 30-day physical log has been used. Change the wording to synthetic planning data until real logs are collected.

5. **Outcome direction.** The proposal lists fewer overflows, shorter distance, and lower fuel/CO₂ as targets. Targets must not be reported as achieved. The final report must use the locked experiment results, including any metric where the smart policy is worse.

## Strongest completed area

Focus Area C is the most mature competition component. It has district sizing, Malaysian coordinates, OSM/OSRM matrices, capacity-constrained OR-Tools routing, a safe three-state sensor decision, chronological vehicle execution, paired stress scenarios, a modern operator dashboard, and mock route tracking. It satisfies the core digital-simulation structure but remains synthetic and requires field calibration.

## Priority completion list

1. Freeze the 30-pair base/stress results and use only those values in the report and deck.
2. Assemble and photograph the 1:20 three-bin ESP32 prototype; record repeatable sensor/forecast/dashboard operation.
3. Measure continuous and peak power with a documented instrument and test duration.
4. Create the complete BOM, receipts, total in both USD and SGD, material sustainability statement, and safety checklist.
5. Decide whether Focus B and hardware Focus D remain in scope. Either build/test them or revise the final scope so the proposal gap is explicit.
6. Replace synthetic calibration assumptions with measured empty/full distances, known masses, service time, and at least a short telemetry log.
7. Add cost-benefit, full sustainability evidence, and a city-scale architecture/budget; retain the completed SDG 11.6/13.2 mapping in the final deck.
8. Prepare a timed 15-minute deck, ≤3-minute demo, Q&A evidence sheet, and confirmation that every member presents.
9. Ask the organizers to reconcile the Week 5/10/12 table with the 4–5 September absolute dates.

## Safe competition claim

BinSight currently demonstrates a reproducible **Focus Area C digital prototype** and a hardware-ready three-bin sensing design. It does not yet demonstrate a completed competition physical prototype, measured power/budget compliance, camera classification, or a physical QR return station.
