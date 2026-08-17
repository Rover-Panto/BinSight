# SEA Engineering Design Competition 2026 - Research Brief and Proposal Outline

## Competition Constraints

- Theme: Sustainability and AI for real-world urban waste/recycling management.
- Preferred focus: A - Smart Bin Monitoring and C - Predictive Collection Optimisation.
- Optional extension: B - AI Waste Classification, only if time and hardware budget allow.
- Prototype: 1:20 street-block model with at least 3 instrumented bins.
- AI component: team-trained or fine-tuned model required; pre-trained APIs cannot replace the team's own model.
- Simulation: 500 households and 20 commercial units over 30 days.
- KPIs: at least two, comparing baseline no-AI vs AI-enabled system.
- Hardware budget: USD 150 / SGD 200.
- Power: target under 10 W continuous, max 12 V DC supply.
- Proposal requirement conflict: table says 2 pages; note says 200 words by 4 Sep 2026, 5:00pm GMT+8.

## Research Takeaways

- The World Bank's latest What a Waste 3.0 page reports that municipal solid waste reached 2.56 billion tonnes in 2022 and could reach 3.86 billion tonnes by 2050 under business-as-usual. This is even stronger than the older 2.01/3.4 billion figures in the competition brief.
- Smart waste collection is a good fit for low-cost IoT because bins only need to send small, infrequent packets: bin ID, fill percentage, battery level, and alert state.
- LoRaWAN is relevant for a city-scale concept because it is designed for low-power wide-area IoT, with long-range and battery-life advantages.
- Route optimization is a mature, defensible AI/OR problem. Google OR-Tools supports Vehicle Routing Problems, including capacity constraints, time windows, and penalties for skipped visits.
- The winning angle should be municipal practicality: fewer overflows, fewer unnecessary truck trips, measurable CO2 reduction, and hardware cheap enough for phased deployment.

## Best Project Direction

### Recommended Concept: GreenRoute AI

GreenRoute AI is a low-cost smart-bin and route-optimization system for urban districts. Each bin reports fill level using ultrasonic sensors and weight sensors. A lightweight time-series ML model predicts which bins will overflow within the next collection window. A risk-weighted route optimizer then selects the high-priority bins and generates a shorter collection route for the truck, subject to truck capacity, road availability, time of day, and event-related waste surges.

### Locked Implementation Scope

Core features to implement:

- Ultrasonic fill-level sensing mounted at the top of each bin.
- Event surge mode for locations such as night markets, schools, festivals, and weekend commercial areas.
- Road closure rerouting inspired by navigation apps such as Waze.
- Multimodal priority score that ranks bins by predicted overflow risk, not only current fill percentage, using fill level, weight, event surge, road access, time since last collection, citizen reports, and truck distance.
- Three-stream recycling return station for glass bottles, PET bottles, and aluminium cans, using a simulated RM0.10 / 10 sen refundable deposit.
- Citizen authorization and feedback through QR login or app account simulation, including optional QR reports for overflow, smell, contamination, or blocked access.
- Bottle/can classification model for the return bin.
- Digital refund flow through simulated e-wallet, QR payment, or bank transfer instead of physical coin payout, with immediate payout when the user completes a return session.
- Anti-fraud checks for rejected items, wrong chute use, duplicate scans, and low-confidence computer vision results.
- Maintenance alerts for sensor faults, abnormal readings, or low battery.
- Municipal dashboard showing live bin status, predicted overflow, recycling returns, alerts, and route recommendation.

Features to keep as future work:

- Advanced 3D reconstruction for volume estimation.
- Full physical reverse vending machine with real coin payout.
- Full general-purpose computer vision waste classification.
- True city-wide deployment with live road traffic API integration.

This strongly covers:

- Focus A: smart bin monitoring, fill prediction, overflow alerting.
- Focus C: predictive route optimization, trip reduction, fuel reduction, CO2 savings.
- Focus B: return-bin classification for PET bottles, glass bottles, and cans.
- Focus D: QR authorization, RM0.10 deposit refunds, e-wallet/bank credit, user recycling history, efficiency scoring, and six-month bonus rewards.

### Core System Flow

Smart Bin -> ESP32/Arduino -> Raspberry Pi, Laptop, or Cloud Platform -> Prediction AI -> Priority Scoring -> Route Optimizer -> Municipal Dashboard

The key idea is to move from reactive collection to predictive collection. Instead of collecting only after a bin is already full, the system forecasts which bins will become urgent based on fill trend, location, day of week, time range, nearby events, and historical usage patterns.

## Prototype Plan

- Build a 1:20 street block with 3 bins and one model collection truck.
- Mount one ultrasonic sensor at the top of each bin to measure empty space from lid to waste surface.
- Add a load cell/weight sensor to each smart bin if budget allows; otherwise use at least one enhanced bin with weight sensing.
- Fuse ultrasonic height and weight readings to estimate fill level more reliably than either sensor alone.
- Use ESP32 or Arduino for sensor collection.
- Use Raspberry Pi or laptop edge dashboard for prediction and route calculation.
- Show live bin states using LEDs: green under 60%, amber 60-85%, red above 85% or predicted overflow.
- Dashboard displays current fill, predicted overflow risk, recommended pickup order, trips saved, and estimated CO2 saved.

Possible low-cost hardware:

- ESP32 or Arduino-compatible microcontroller.
- 3 ultrasonic sensors such as HC-SR04.
- 1-3 load-cell modules with HX711 amplifier boards.
- Camera module or laptop webcam for return-bin item classification.
- LEDs or small OLED/LCD screen.
- Recycled cardboard/acrylic for street and bin model.
- USB power meter for reporting prototype power draw.

Prototype measurements to report:

- Overflow incidents.
- Collection trips.
- Average fill level at pickup.
- Route distance.
- Estimated fuel consumption.
- Estimated CO2 emissions.
- Prototype power consumption.
- Maintenance alerts triggered.
- Recycling containers returned and deposit value refunded.
- Return-bin classification accuracy.
- Authorized vs rejected return attempts.

## AI and Simulation Plan

### Fill-Level Prediction

Train a simple model on generated and prototype-collected time-series data. This is the main AI component for Focus A: instead of reacting to a full bin, the model forecasts fill level and overflow risk.

- Inputs: current fill level, fill-rate trend, bin type, hour, day of week, household/commercial zone, nearby event or night-market flag, school-day/weekend flag, road closure status, maintenance status, and recent collection history.
- Models to compare: linear regression baseline, Random Forest Regressor, XGBoost or gradient boosting, and optionally a small neural network.
- Output: predicted fill percentage 6-24 hours ahead and overflow probability.

Example priority logic:

- Bin A and Bin B are both 75% full.
- Bin A is near a night market at dinner time, so its predicted fill rate is high and it may overflow soon.
- Bin B is in a quiet residential area at midnight, so its predicted fill rate is low.
- The system prioritizes Bin A even though the current fill levels are the same.

### Route Optimization

Use the predicted bins needing service as route candidates. The routing part should be described as AI-assisted optimization: the ML model predicts demand, then the route algorithm uses those predictions to build the collection route.

- Baseline: fixed daily route visiting all bins.
- AI route: visit only bins above threshold or likely to overflow soon.
- Solver options: OR-Tools VRP/CVRP, Dijkstra or A* for shortest path between locations, and a priority-based route planner for choosing collection order.
- Constraints: truck capacity, depot start/end, bin demand, road closures, maximum route distance/time, and collection time windows.
- Dynamic inputs: road closure flag, event location, weekday/weekend pattern, school-day effect, night-market/dinner surge, maintenance alerts, and historical fill patterns.

For the prototype, a simplified map can be represented as nodes and roads. If a road is "closed," the algorithm recalculates a different path. This is visually strong for judging because the dashboard can show routes changing in real time.

Waze-style framing:

- The prototype will not integrate with Waze directly unless an approved public API is available.
- Instead, the dashboard will simulate navigation-app style road intelligence using manual road-closure toggles.
- In future deployment, this could connect to municipal traffic feeds, planned roadwork databases, or navigation data providers.

### Priority Score

Suggested explainable score:

Priority Score = current fill level + weight trend + predicted fill increase + event surge factor + citizen report urgency + truck distance + time since last collection + location importance - maintenance penalty

Example inputs:

- Fill level: 75%.
- Weight trend: rising quickly.
- Predicted 6-hour fill increase: high.
- Location: night market.
- Time: dinner period.
- Citizen report: QR complaint for smell or overflow risk.
- Truck distance: nearby truck can collect with a small detour.
- Road access: one nearby road closed.
- Maintenance status: healthy sensor.

This bin should be prioritized over another 75% full bin in a quiet residential area because its overflow risk is higher.

### Maintenance Alerts

Maintenance alerts make the system more realistic and reliable. Trigger alerts when:

- Ultrasonic readings do not change for a long period.
- Sensor value jumps unrealistically.
- Fill level reads above 100% or below 0%.
- Battery or supply voltage is low.
- Bin is physically full but not collected after a defined time.

The dashboard should mark these bins separately so the route optimizer does not blindly trust faulty data.

### 30-Day Simulation

Model:

- 500 households and 20 commercial units.
- At least 20-40 virtual bins in the district, scaled from the prototype.
- Random daily waste generation with higher commercial, weekend, school-day, night-market, and event/festival surges.
- Baseline schedule vs AI predictive collection.
- Different fill patterns by time range and day of week.
- Optional road-closure scenarios that force route recalculation.
- Maintenance fault scenarios that test whether the dashboard can detect unreliable sensors.
- Recycling return scenarios that increase fill level in the recycling bin and trigger pickup priority.
- Reproducible random seeds for fair baseline-vs-AI comparison.
- Confidence intervals across repeated simulation runs, so the team can report whether improvements are consistent rather than lucky.

KPIs:

- Target at least 40% fewer overflow incidents.
- Target at least 25% fewer collection trips.
- Route distance or fuel reduction.
- Target at least 20% estimated CO2 reduction.
- Target at least 15% cleaner recyclables through accepted-item classification and rejected-item alerts.
- Average bin fullness at pickup.
- Optional recycling contamination rate if B is added.

## Optional Focus B and D Add-On

Add only if the core A+C system is stable. Instead of classifying every type of waste, use classification only for the return bin. This is more realistic because the accepted categories are limited and controlled. The team will train or fine-tune its own model using images of sample PET bottles, glass bottles, aluminium cans, and rejected items under the same lighting used in the prototype.

Focus B classification classes:

- PET plastic bottle.
- Glass bottle.
- Aluminium can.
- Rejected or unknown item.

Implementation options:

- Primary option: use a small camera or laptop webcam to classify PET bottles, glass bottles, and cans under controlled lighting.
- Supporting sensors: use weight, IR break-beam, or guide-slot size to improve confidence and detect inserted items.
- Backup demo option: use QR/barcode tags on sample containers if camera accuracy is unstable during judging.

Focus D citizen engagement features:

- Shops sell eligible glass bottles, PET bottles, and aluminium cans with a RM0.10 / 10 sen refundable deposit added to the price.
- Citizen authorizes before inserting items using QR login, app account, RFID card, or simulated user ID linked to an e-wallet or bank account.
- Return station has three dedicated chutes: glass bottles, PET bottles, and aluminium cans.
- Camera model checks whether the inserted item is valid, recyclable, and in the correct chute.
- Verification runs locally on the prototype edge device, with server fallback if local processing fails or confidence is low.
- Accepted items add RM0.10 to the user's pending refund total; rejected items trigger an invalid-item or wrong-chute alert.
- Digital payout is completed through simulated e-wallet credit, QR payment, or direct bank transfer when the user ends the session.
- Dashboard/app view shows containers returned, refund value earned, rejected items, recycling history, and environmental impact.
- Backend calculates user recycling efficiency based on return frequency, correct sorting, accepted/rejected ratio, and contamination rate.
- Six-month bonus programme rewards high-performing recyclers.

Why this works: the return bin lets the project touch B and D without turning the whole waste system into a computer vision project. The A+C system still remains the main technical core, while the return-bin model provides a focused and demonstrable AI classification module.

Suggested return-bin flow:

1. Citizen scans QR code and selects an e-wallet or bank account for payout.
2. Return station activates the glass, PET, and can chutes.
3. Citizen places the item into the matching chute.
4. Lid closes and a camera model classifies the item locally, with server fallback for low-confidence cases.
5. Accepted item drops into the correct recycling bin and adds RM0.10 to the pending refund total.
6. Rejected item triggers an invalid-item, wrong-chute, duplicate-scan, or low-confidence alert.
7. Citizen repeats the process until finished.
8. Citizen ends the session and the total refund is immediately deposited to the selected account.
9. Recycling app updates user history, funds earned, recycling efficiency score, and environmental impact.
10. Municipal dashboard receives return volume, fill level, contamination, and user engagement data.

## Proposal Structure

### Title

GreenRoute AI: Low-Cost Smart Bins and Predictive Collection for Sustainable Urban Waste Management

### Problem

Urban waste collection is often fixed-schedule and reactive. Trucks visit bins that may not be full, while fast-filling bins overflow before the next round. This wastes fuel, increases emissions, raises operating cost, and reduces public cleanliness.

Stronger technical version:

Urban waste management in Southeast Asia is predominantly reactive and schedule-driven, leading to severe inefficiencies. Fixed collection cycles fail to account for stochastic, high-variance waste generation caused by local events, festivals, schools, night markets, and changing pedestrian density. As a result, fast-filling bins overflow while trucks still spend fuel and labour servicing underfilled bins. Centralized cloud-only IoT systems may also face latency and connectivity issues in dense urban areas, making local edge processing valuable for resilience.

### Proposed Solution

GreenRoute AI combines smart bin sensing, fill-level prediction, citizen feedback, and route optimization. Instrumented bins send fill-level and weight data to an edge dashboard, while QR feedback lets residents report overflow, odour, contamination, or blocked access. A team-trained ML model predicts near-future overflow risk, then a multimodal priority score ranks bins using fill level, weight, predicted fill rate, location, event surge, road access, time since last collection, citizen reports, and truck distance. An optimization engine generates efficient truck routes that prioritize urgent bins and skip low-need stops.

Stronger technical version:

GreenRoute AI introduces a decentralized, edge-assisted smart-bin ecosystem. ESP32-equipped bins measure fill level using ultrasonic sensors and weight sensors. Data is sent to a Raspberry Pi or central dashboard, where a lightweight machine-learning model forecasts fill-level trends and overflow risk. The system assigns each bin a multimodal priority score based on predicted fill level, weight trend, location, time of day, day of week, nearby events, road availability, truck distance, and QR citizen reports. A route optimizer then creates an adaptive collection route, reducing unnecessary trips, preventing overflow incidents, lowering fuel use and CO2 emissions, and giving municipal operators a real-time dashboard for data-driven decisions. A return-bin module adds citizen engagement by authorizing users, classifying bottles/cans, issuing simulated digital refunds, and collecting QR feedback.

Use "swarm" carefully:

- Good phrase: "edge-assisted smart-bin ecosystem with distributed priority scoring."
- Risky phrase: "fully autonomous swarm negotiation between bins."
- Best compromise: "swarm-inspired priority coordination," if the team wants the futuristic angle.

### Prototype

The physical prototype will be a 1:20 street block with at least 3 smart bins. Each bin will contain a fill-level sensor, weight sensor where budget allows, QR feedback label, and status indicator. The edge dashboard will show real-time bin fill, predicted overflow, citizen alerts, multimodal priority score, and recommended collection route. Prototype power will be measured and kept below 10 W continuous using duty-cycled sensing.

### Simulation

The simulation will model 500 households and 20 commercial units for 30 days. It will compare fixed-schedule collection against GreenRoute AI using reproducible random seeds and confidence intervals. Measurable KPIs will include at least 40% fewer overflow incidents, 25% fewer collection trips, 20% lower estimated CO2 emissions, 15% cleaner recyclables through the return-bin module, route distance reduction, and average bin fullness at pickup.

### Sustainability and SDGs

The system supports SDG 11 by reducing urban overflow and improving public health, SDG 12 by improving waste management efficiency, and SDG 13 by lowering collection-related emissions. It is designed for municipal adoption through low-cost sensors, edge processing, and scalable low-power communication.

### Feasibility

The project fits the USD 150 / SGD 200 prototype budget using common sensors, microcontrollers, recycled materials, and open-source software. The A+C scope is technically strong while keeping Focus B and D as controlled extensions through the recycling return bin.

### Why It Can Win

GreenRoute AI is stronger than a simple fill-level bin because it combines visible hardware, team-trained prediction AI, multimodal priority scoring, citizen QR feedback, a baseline-controlled simulation, and a realistic municipal adoption story. It gives judges a working prototype they can understand quickly, plus quantitative proof that predictive collection can reduce overflow, truck trips, emissions, and recycling contamination.

## Recycling Incentive Extension

This is a strong policy and sustainability extension, but it should be presented as an add-on to the A+C system rather than the main prototype scope.

### Concept: Smart Deposit-Return Incentive

The project can include a deposit-return recycling model inspired by European and Singaporean bottle/can return schemes, including the three-stream reverse-vending style seen in the Netherlands. Shops sell eligible glass bottles, PET bottles, and aluminium drink cans with a RM0.10 / 10 sen refundable deposit added to the price. When customers return the empty container to an approved smart recycling return station, they receive the deposit back through e-wallet credit, QR payment transfer, bank transfer, public transport credit, or municipal reward points.

This is better than calling it an additional sales tax. A sales tax sounds like a permanent charge, while a deposit-return system is refundable. Citizens who recycle get their money back; citizens who do not return containers help fund collection, recycling operations, and machine maintenance through unclaimed deposits.

The return station has three dedicated chutes: one for glass bottles, one for PET bottles, and one for aluminium cans. Before returning items, the citizen scans a QR code that links the session to their e-wallet or bank account. The user places an item into the correct chute, the lid closes, and a camera-based computer vision model checks whether the item is valid, recyclable, and placed in the correct stream. The model should run locally on the prototype edge device for fast response and resilience, with server fallback when local processing fails or the model confidence is low.

If the item is accepted, it drops into the recycling bin and RM0.10 is added to the pending refund total shown on screen. The citizen can keep adding items in the same session. When the session is completed, the total refund is immediately deposited to the selected account. If the item is rejected, the system flags the reason, such as invalid item, wrong chute, duplicate scan, or low-confidence result.

### How It Fits GreenRoute AI

- Focus A: smart bins can track returned bottles/cans and fill level.
- Focus B: the return bin can classify accepted items such as PET bottles, glass bottles, and aluminium cans.
- Focus C: route optimizer can prioritize recycling bins that are nearly full or located near high-return areas.
- Focus D: citizen app/dashboard can show refund history, funds earned, accepted/rejected items, recycling efficiency, bonus eligibility, and environmental impact.
- Government cost offset: unclaimed deposits, producer contributions, and recovered material value can help fund operations.

### Prototype Version

For the physical prototype, keep it simple:

- Add a labeled three-chute recycling return station: glass bottles, PET bottles, and aluminium cans.
- Citizen authorizes using a QR code, app login, RFID card, or simulated user ID linked to an e-wallet or bank account before inserting items.
- Use a controlled camera model as the main item validation method, supported by weight/IR sensing if available.
- Run validation locally on the laptop/Raspberry Pi, with a server-fallback mode simulated on the dashboard for low-confidence cases.
- Dashboard shows "user ID," "item type," "accepted/rejected status," "containers returned," "deposit value refunded," "digital payout method," "recycling efficiency score," and "recycling bin fill level."
- Route optimizer includes the recycling bin when it becomes high priority.
- Backend stores registered user history, funds earned, environmental impact, accepted/rejected ratio, contamination rate, and six-month bonus eligibility.

Do not build a full physical reverse vending machine unless the team has extra time. A complete machine with real payout hardware and anti-fraud mechanics would add cost and complexity. For this prototype, the refund can be simulated digitally through the dashboard or a simple web/app interface.

### Policy Framing

Proposed mechanism:

- Add a RM0.10 / 10 sen refundable deposit to eligible glass bottles, PET bottles, and aluminium cans.
- Refund the deposit when the item is returned through an approved bin or reverse-vending point and accepted by the validation system.
- Rate citizen recycling efficiency using return frequency, correct sorting, accepted/rejected ratio, and contamination rate.
- Award six-month bonuses to high-performing recyclers to encourage long-term behaviour change.
- Use unclaimed deposits, producer responsibility fees, and recyclable material sales to offset government collection costs.
- Integrate return-bin data into the same GreenRoute AI dashboard so municipalities can optimize recycling collection.

### Risks To Mention

- Needs retailer/producer participation.
- Requires fraud prevention so non-eligible containers are not refunded.
- Public bins may be disturbed if people search for refundable bottles.
- Needs accessible return points so low-income users are not unfairly burdened.
- Best used as a policy extension, not a mandatory prototype dependency.

## Judge-Friendly Technical Claims

Use these claims confidently:

- "The machine learning model forecasts fill level and overflow risk using time-series and context data."
- "The route optimizer uses predicted risk, not only current fill level."
- "The multimodal priority score combines fill level, weight trend, predicted fill rate, citizen reports, event surge, truck distance, and road access."
- "The dashboard supports municipal decision-making by showing bin status, overflow risk, and recommended routes."
- "QR feedback turns residents into low-cost sensing partners by letting them report overflow, smell, contamination, or blocked bin access."
- "The simulation compares fixed-schedule collection with AI-enabled predictive collection over 30 days using reproducible seeds and confidence intervals."
- "Road closures and event surges can be simulated to show daily route adaptation."
- "A deposit-return incentive can improve recycling participation while reducing net government cost through unclaimed deposits, producer contributions, and recovered material value."

Avoid these unless implemented:

- "The bins negotiate autonomously with each other."
- "The system uses reinforcement learning."
- "The route is fully optimized globally in real time for an entire city."
- "LoRaWAN mesh," because LoRaWAN is usually a star-of-stars network rather than a true mesh network.

## 200-Word Core Proposal Draft

GreenRoute AI is a low-cost smart waste collection system designed to reduce urban bin overflow, unnecessary truck trips, and collection-related carbon emissions. The system combines Focus Area A, Smart Bin Monitoring, with Focus Area C, Predictive Collection Optimisation. In the physical prototype, a 1:20 street block will contain at least three instrumented bins fitted with fill-level sensors, weight sensing where budget allows, QR citizen feedback, and LED status indicators. Sensor and feedback data will be sent to an edge dashboard, where a team-trained machine learning model predicts which bins are likely to overflow before the next collection cycle.

Based on these predictions, a multimodal priority score will combine fill level, weight trend, predicted fill rate, event surge, citizen reports, truck distance, and road access. A route optimisation algorithm will recommend efficient truck routes that prioritise urgent bins and avoid visiting low-fill bins unnecessarily. The digital simulation will scale the concept to a district of 500 households and 20 commercial units over 30 days, comparing a fixed-schedule baseline against the AI-enabled system using reproducible seeds and confidence intervals. Target KPIs are 40% fewer overflows, 25% fewer trips, 20% lower CO2, and 15% cleaner recyclables.

GreenRoute AI supports SDG 11, SDG 12, and SDG 13 by improving urban cleanliness, responsible waste management, and climate impact. The prototype will use low-cost components, recycled materials, and measured power consumption below 10 W.

## Sources

- World Bank, What a Waste 3.0: https://www.worldbank.org/en/publication/what-a-waste
- Google OR-Tools Vehicle Routing documentation: https://developers.google.com/optimization/routing
- Google OR-Tools Capacity Constraints documentation: https://developers.google.com/optimization/routing/cvrp
- LoRa Alliance, About LoRaWAN: https://lora-alliance.org/about-lorawan/
- Singapore Beverage Container Return Scheme overview: https://www.nea.gov.sg/our-services/waste-management/beverage-container-return-scheme
- Ireland Re-turn Deposit Return Scheme: https://re-turn.ie/
