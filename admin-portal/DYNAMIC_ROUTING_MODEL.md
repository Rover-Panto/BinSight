# Dynamic routing model v2

Policy version: `dynamic-trip-value-v2`

## Objective contract

BinSight treats overflow prevention as a service constraint and then minimizes avoidable dispatch, distance and operating effort. It compares dispatching now with waiting for the next planning opportunity instead of making every threshold crossing a mandatory stop.

For bin \(i\), conservative fill is:

\[
U_i=\operatorname{clip}\left(\max(F_i,100W_i/C_i)+m_i,0,150\right)
\]

The margin is 3.29 percentage points for fresh agreeing fill and weight, 7.5 points for one available channel, and 15 points for low-confidence/conflicting evidence. Retained last-good fill ages by 0.75 percentage points per hour and preserves its original event time.

The upper forecast is the calibrated 90th percentile of 48-hour growth. Time to overflow is:

\[
T_i=(100-U_i)/(\widehat G_i^{0.90}/48)
\]

The model also produces calibrated synthetic classifiers for overflow within 6 and 48 hours. The fresh/confident 6-hour probability is the planner's primary next-opportunity probability. When the classifier or forecast is unavailable/cold-start, the named fallback uses current conservative fill and the documented 0.75 percentage-point/hour conservative growth assumption. It never manufactures a low-risk forecast.

## Overflow service constraint

A stop is mandatory when any of these apply:

- upstream risk is critical;
- fresh/confident current conservative fill is at least 90%;
- fresh/confident calibrated overflow probability before the next opportunity is at least \(1-\epsilon\), where \(\epsilon=0.10\); or
- the calibrated probability is unavailable and fresh/confident q90 time-to-overflow is at most six hours.

Low-confidence/stale evidence is retained for inspection and capacity conservatism but cannot by itself convert a model forecast into an automatic trip. Independent upstream `critical` evidence remains service-relevant. Lower 65–85% uncertainty boundaries proved too aggressive because a one-sided margin or isolated outlier could turn ordinary mid-fill readings into mandatory departures.

Mandatory stops can still require operator inspection. If mass, volume or route-time constraints cannot serve them, dispatch is blocked and the bins are recorded as unserved required stops.

## Trip-value objective

For optional bin \(i\), the skip penalty is its prototype avoided-loss value:

\[
B_i=180000p_i+90000\max(0,p_i-0.10)
\]

where \(p_i\) is the greater of the calibrated synthetic 6-hour probability and the 48-hour probability amortized over its eight six-hour opportunities, when fresh/confident model output is available. The 48-hour term is only for consolidating an already eligible stop into a justified route; it cannot create a mandatory stop. Units are **metre-equivalent decision units**, not measured Malaysian Ringgit or real municipal loss.

Optional eligibility normally requires a fresh central fill estimate of at least 45%. A lower-fill bin can qualify at the scheduled batch only when its observable time-to-overflow is within the next 72-hour batch interval. Fresh uncertain evidence cannot start an optional route; a high-conservative-fill uncertain bin may only join a site that already has at least two confident eligible bins or mandatory work.

When the classifier is unavailable, `p_i` falls back to a transparent planning-risk proxy. Let `H=6` hours and let `T_i` be the q90 upper-growth time to overflow. Its time component is:

\[
p_T=\begin{cases}
1,&T_i\le0\\
0.10+0.90(1-T_i/H),&0<T_i\le H\\
0.10(H/T_i)^2,&T_i>H
\end{cases}
\]

The maximum of that component, small upstream risk priors (`0`, `0.001`, `0.005`, `0.02`, `0.25` for unknown through critical), and documented projected-fill floors is used only for the fallback. This matters: an upper q90 path that reaches overflow in 69 hours is not assigned a flat 5% chance of overflow in the next six hours. That earlier mapping aggregated many low-fill bins into false positive-value trips and was rejected during development. The trained classifier is calibrated only against synthetic history; field data must replace or recalibrate it before live decisions.

The route solver minimizes:

\[
\sum d_{ij}x_{ijk}
+120\sum \tau_{ij}^{minutes}x_{ijk}
+15000\sum z_k
+120\sum 8y_i
+100\sum(50-E_i)^+y_i
+\sum B_i(1-y_i)
\]

subject to route flow, a 9,000 kg mass limit, 22 m³ compacted-body limit, two daily trips, 480-minute route limit, mandatory-stop service and stable tie-breaking. OR-Tools disjunctions implement optional skip penalties.

Registered `waste_stream` values are also hard constraints. General waste and dry recycling are solved separately under the same daily trip limit. Plastic, metal and glass remain separate monitored bins but share the configured dry-recycling truck stream. General routes start and end at the waste depot. Recycling routes are costed and displayed as `depot -> selected recycling bins -> USJ 9 recycling facility -> depot`; their bin-to-end arc includes both facility unloading access and the return to the depot. No generated trip mixes general waste with recycling.

Here `E_i` is the central fused fill estimate before the one-sided safety margin. Safety selection and capacity use conservative `U_i`; low-fill economics use `E_i` so an uncertainty margin does not erase the cost of an expected low-fill pickup.

The reported trip value is:

\[
V(R,t)=\sum_{i\in R}B_i-C_{trip}-C_{distance}-C_{time}-C_{service}-C_{low-fill}
\]

A non-emergency route is dispatched only when \(V(R,t)>0\). Otherwise its candidates are labelled `Defer – wait or merge`. Emergency/service-constraint routes remain mandatory even if their monetary proxy is negative.

The values above are transparent pilot defaults. Operations must replace them with measured fixed-trip, per-kilometre, driver-time, service-time, overflow, emergency and route-failure costs before field use.

## Dynamic operation

The simulation evaluates at every six-hour sensor observation. Non-mandatory positive-value departures are consolidated behind a 72-hour minimum gap; from the shared empty start, the first optional trip also waits 72 hours. Emergency/service constraints override it. The local server runner defaults to a 15-minute evaluation interval, where reevaluation updates evidence but does not itself authorize an optional departure inside the gap. Additional evaluation should be triggered by:

- a new or corrected source event;
- a stale/offline or forecast-risk transition;
- actual collected mass differing from the estimate;
- traffic, blockage or vehicle-capacity change; or
- completion of a collection leg.

Repeated inputs are idempotent within the interval, but elapsed time creates a new decision snapshot because observation age changes. Draft proposals never overwrite an accepted route.

A completed service is a durable planning event. For six hours it supersedes delayed pre-service readings with a confirmed-empty state, preventing immediate duplicate collection. That override then expires: without a genuinely newer post-service acquisition, fill and weight become unknown, the forecast becomes unavailable, and the bin is sent to inspection. The service plan ID and service timestamp remain separate durable facts, so the system neither forgets the collection nor claims the bin stays empty forever.

## Current four-bin smoke evidence

The bounded `four-bin-smoke` run contains two paired normal-scenario replications. It verified end-to-end execution with no routing fallbacks or unfinished trips. Mean wasted pickups fell from 197.5 to 39.5 and mean overflow incidents fell from 6 to 4, while mean distance increased from 766.0 km to 1,273.6 km and trips increased from 18 to 36. Two replications are not inferential evidence. The result shows that the current safety settings do not yet satisfy the distance objective, so dynamic routing remains demonstration/shadow-mode logic rather than a proven replacement for the fixed schedule.

For an active route, the current leg is frozen. `PlanningService.replan_remaining_after_event()` uses the frozen destination as the start of a new suffix, excludes completed/current-service bins, applies residual mass and volume, and writes a separate draft referencing the active accepted plan. Operator acceptance remains required.

## Forecast validation

Two years of synthetic pre-period history are separate from the 30-day operational evaluation. Training, calibration and final chronological holdout windows are separated by the complete 168-hour maximum target horizon. The calibration interval adjusts the upper quantile; the untouched holdout reports:

- 6/24/48/168-hour mean-growth MAE and naïve MAE;
- time-to-overflow MAE and 6/48-hour overflow Brier scores;
- alert precision/recall and probability calibration bins;
- empirical upper-quantile coverage and coverage error;
- 0.90 pinball loss; and
- mean upper-versus-mean forecast width.

Features use acquisition-time windows, gaps and collection resets. Rapid two-second events are not interpreted as six-hour intervals. Synthetic validation does not establish accuracy for physical ultrasonic volume readings; hardware validation remains pending.

## Decision evidence

Every durable plan includes source event IDs, snapshot and decision time, selected/deferred/unserved bins, reasons, conservative mass/volume, solver status, source mode, registry/config/network/model assumptions and lifecycle state. States are `DRAFT`, `ACCEPTED`, `COMPLETED` and `CANCELLED`. One accepted plan can create at most one idempotent mock dispatch.
