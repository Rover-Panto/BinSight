# AAR: BinSight routing and demand-model revision

**Type:** Project closeout / model review  
**Date of event:** 27–28 August 2026  
**AAR date:** 28 August 2026  
**Scope:** PR #1 routing policy, demand simulation, telemetry boundary and validation evidence  
**Facilitator:** BinSight routing maintainer  
**Inputs:** PR history/comments, owner hardware handoff, source/tests, v1 artifacts and matched v2 simulation artifacts

## Summary

BinSight set out to prevent overflow while avoiding wasteful departures and reducing route distance. The corrected v1 comparison showed that its threshold-first policy did not consistently meet that objective: an earlier apparent 5.08% saving came from an unfair day-zero fixed sweep, and the corrected normal-demand result used more trips, distance and fuel than fixed service. The demand process was also too short and weakly patterned to test whether predictive service adapts to weekly, seasonal, event and persistent demand changes.

The root cause was systemic rather than an individual mistake: the policy optimized local thresholds and proximity instead of explicit trip value; model labels crossed an evaluation split; demand shocks were mostly independent and short-lived; simulation/operator paths and physical identity assumptions could diverge; and completed service was not durable evidence against delayed pre-service readings. The revision replaces that design with paired patterned demand, multi-horizon/calibrated synthetic forecasts, prize-collecting trip value, stream-safe routes, a durable plan/service lifecycle and one validation/planning path.

The revised system remains decision support. Its costs and probabilities are synthetic engineering evidence, the road solution is heuristic over a cached network, and the bounded scenario suite cannot prove a fixed or dynamic route is perfect for every future event. Live/autonomous dispatch remains disabled pending field calibration and PR #2 producer validation.

## Impact and goals versus outcomes

| Goal | Outcome | Evidence |
| --- | --- | --- |
| Avoid wasteful trips | Not met under normal demand: 21.73 fixed versus 32.97 dynamic; met in event-heavy demand: 34.93 versus 24.83 | paired 30-replication effects and low-fill pickup audit |
| Decrease distance travelled | Not met: dynamic used more distance in every definitive scenario; normal was 718.89 km versus 505.27 km | common OSRM matrix, paired effects and strong re-routed fixed comparator |
| Avoid overflow | Met in normal/stress operation, but not under sensor failure | normal incidents 3.97→0.90; combined-stress spill −89.14%; sensor-failure incidents 3.57→9.20 |
| Make the route dynamic | Met for observations, age, service, capacity, traffic and active-route suffix changes | shared planner, immutable lifecycle and service-memory tests |
| Fairly test realistic demand | Met in software | 730-day pre-period, 30-day excluded evaluation, 11 scenarios, common arrivals/events/noise |
| Prove universal route optimality | Not achievable from this prototype | solver/scenario/network limitations are explicit in `fixed_baseline_route_audit.json` |

No municipal users or live trucks were affected; all impact figures are simulation evidence.

## Timeline

| Date / phase | Event | Consequence |
| --- | --- | --- |
| Before 27 Aug | v1 threshold routing and five-scenario demand study were implemented | useful prototype, but local heuristics and limited demand variation |
| 27 Aug | Startup/baseline audit found the fixed day-zero empty sweep | 5.08% saving claim withdrawn; fixed timing and equal warm-up corrected |
| 27 Aug | Corrected v1 matched run showed normal-demand distance/fuel regression | prompted explicit trip-value objective and wait alternative |
| 27 Aug | PR comments/handoff supplied C01–C30 and R1–R10 gates | identity, freshness, replay, lifecycle and live-integration boundaries made testable |
| 28 Aug | Latest owner handoff clarified three fill channels: one general, two recycling-return | telemetry 2.1 preserves type/stream; recognition/session events stay separate |
| 28 Aug | Demand-model review required persistent regimes, cyclic seasonality, events, trends and long history | demand equation, 730-day history, 11 scenarios and multi-horizon evaluation added |
| 28 Aug | Acceptance tests and final matched evaluation run | definitive artifacts isolated under `artifacts/dynamic_v2/` |

## Root cause analysis

**Causal chain:**

- **Objective gap:** threshold crossings and a 5 km sibling rule did not price a trip's fixed, distance, time, service or low-fill cost, so repeated small benefits could justify poor departures.
- **Comparator gap:** the original fixed implementation serviced empty bins at day zero, making the first comparison structurally unfair.
- **Demand gap:** independent Gamma noise over 30 days could not represent persistent district/local regimes or validate annual features.
- **Forecast gap:** the original chronological split did not purge the complete future target window, allowing labels to cross boundaries.
- **State gap:** UI/session state and delayed observations could outlive a collection and select an already emptied bin.
- **Integration gap:** simulation service groups were conflated with physical topology, and event identity/freshness/type were not sufficient for replay-safe routing.
- **Evidence gap:** a small stress set could reveal some failures but could not test events, localized changes, trends or combined operational stress.

## Contributing factors

- Prototype cost weights were available but not expressed in one auditable objective.
- The old fixed path was visually “fixed” but its timing, stop intent and route-order adaptation were not separately documented.
- Model evaluation emphasized one 48-hour point metric rather than multiple operational horizons and probability reliability.
- Recognition and fill events shared product language, making their technical boundary easy to misunderstand.
- Browser-local state was convenient during prototyping but was not a worker/operator source of truth.

## What went well

- Common random numbers, retained artifacts and chronology tests made the false saving claim discoverable.
- Hidden simulator mass was already separated from observations, allowing the leakage boundary to be strengthened rather than rebuilt.
- Cached OSRM matrices and OR-Tools supported a stronger fixed comparator and dynamic route engine on the same roads.
- GitHub handoff checks converted ambiguous integration concerns into concrete acceptance and producer gates.
- The latest owner clarification was incorporated without discarding the valid three-channel fill architecture.
- New deterministic tests cover cyclic factors, persistent regimes, event knowledge time, pairing, resets, streams, lifecycle and forecast exclusion.

## Actions

| Action | Owner | Due | Type | Status / definition of done |
| --- | --- | --- | --- | --- |
| Replace local threshold/proximity routing with auditable trip value and wait/merge | Routing maintainer | 2026-08-28 | Code | Complete when simulation, CLI, runner and portal call the shared planner |
| Add patterned/persistent demand and 730-day pre-period with excluded 30-day evaluation | Routing maintainer | 2026-08-28 | Model | Complete when deterministic pattern/leakage/pairing tests pass |
| Preserve one-general/two-recycling fill types and separate incompatible trips | Routing maintainer | 2026-08-28 | Integration | Complete when 2.1 fixtures and stream-route tests pass |
| Publish matched v2 scenario/regime/driver artifacts and fixed-baseline audit | Routing maintainer | 2026-08-28 | Evidence | Complete: untouched 660-run set and artifact integrity checks passed |
| Repair and validate producer R1–R10, including acknowledgement/replay/UTC outage handshake | PR #2 hardware/API owner | 2026-09-11 | Hardware/API | Open; required before live integration can be enabled |
| Collect field fill, service, overflow, route, fuel and operator-decision data; recalibrate probabilities/costs | Pilot operations owner | 2026-09-25 | Field validation | Open; required before performance or autonomous-dispatch claims |
| Re-run a prospective untouched field/shadow holdout and approve/retune fixed safeguard | Routing + operations owners | 2026-10-09 | Governance | Open; approval criteria must be agreed before viewing outcomes |

The external owner/dates above are proposed tracking dates and require owner confirmation; that assignment was not present in the available PR material.

## Lessons and decision

A “fixed route” is not one thing: collection timing and all-bin intent can remain fixed while the road order is re-optimized. That creates a strong operational comparator, but neither a heuristic solver nor eleven scenarios can certify perfection under every possible road closure, sensor failure or demand shock.

The right decision is conditional. Preserve fixed three-day service as the field safeguard and run dynamic v2 in fixture/replay and shadow mode. The current positive trip-value rule still over-dispatches under normal demand and becomes unsafe under sensor failure, so live activation additionally requires a telemetry-health gate and prospectively calibrated cost/safety acceptance thresholds. Do not claim measured savings, universal robustness or autonomous readiness until the producer and prospective field gates close.
