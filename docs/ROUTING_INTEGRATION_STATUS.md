# Routing integration acceptance status

Reviewed: 28 August 2026  
Routing branch: `feature/admin-operations-portal` / PR #1  
Starting routing commit: `2e9f84ba2c2b13f93910728cdddda1589eb015ad`  
Merged documentation baseline: `9fca9d47afb805f40034da970bb47d791ba8f0b4`  
Contract: telemetry-routing 2.1, registry 1.0, route-plan 2.0

This file tracks the GitHub routing handoff and owner clarification. “Software complete” means deterministic local tests/replay passed; it does not mean that physical sensors, Wi-Fi, the ingestion producer or a truck were verified.

## C01–C36 acceptance matrix

| ID | Status | Evidence or remaining gate |
| --- | --- | --- |
| C01 | Complete | Current Python suite: 97 passed. Existing stale/missing/critical/capacity/chronology cases plus PR #2 forecast, demand, pairing, stream and lifecycle regressions are retained. |
| C02 | Complete | Legacy input and schema 2.0/2.1 normalize; unknown versions, malformed/non-finite values, non-fill events and unknown history schemas fail without reset. |
| C03 | Complete | `BinRegistry` checks explicit IDs, duplicates/conflicts, coordinates, order and matrix dimensions. |
| C04 | Complete | Separate `physical-pilot` three-bin (one general, two recycling-return fill channels) and `competition-simulation` 33-bin profiles; simulation sizing remains strict. |
| C05 | Complete | UTC normalization and different per-bin ages are covered; decision/receipt time cannot refresh acquisition time. |
| C06 | Complete | Future, ambiguous and unsynchronized acquisition states reject or remain explicit unknown/inspection. |
| C07 | Complete | Fill-only last-good history keeps original event/time/calibration provenance while weight remains absent. |
| C08 | Complete | Missing weight remains null; single-channel uncertainty and conservative capacity load remain labelled. |
| C09 | Complete | `unavailable`, `cold_start`, `model_error` and `stable_no_overflow` forecasts use null, never wire sentinels. |
| C10 | Complete | Named fill-threshold fallback can require fresh high-fill collection; stale/missing data cannot prove low risk. |
| C11 | Complete | Critical low-confidence evidence remains collection-relevant with inspection warnings; optional service uses quality-aware value. |
| C12 | Partial | Consumer preserves invalid/missing/filter-recovery states and simulation covers failure/emptying. Producer startup/blockage/large-deposit replay evidence remains PR #2 work. |
| C13 | Complete | Forecast features are timestamp-windowed and include gaps, resets and cold-start/missing policy. |
| C14 | Complete | Train/calibration/holdout purge the complete 168-hour maximum target; latent/future values stay outside decision features. |
| C15 | Complete | Event/boot/sequence identity, same-second distinction, reboot migration and late-replay rejection are tested. |
| C16 | Partial | Read-only client surfaces authentication and 503/network failures and adapter preserves partial coverage. Producer/API timeout and partial-fetch handshake remain pending. |
| C17 | Complete | Captured source IDs plus registry/config/network/model/policy versions produce an immutable, deterministic plan audit. |
| C18 | Complete | Browser-independent `plan-once`/runner and single-worker lock have tests and explicit start/stop/status controls. |
| C19 | Complete | Idempotency is bounded by a planning-time bucket; elapsed time creates a new evaluation even without new events. |
| C20 | Complete | Immutable lifecycle and one transactional mock dispatch per accepted plan are tested. |
| C21 | Complete | Mandatory-service failures block dispatch; collection and inspection are independent and auditable. |
| C22 | Complete | Focused SQLite store uses WAL/transactions/schema checks; legacy sensor migration and corrupt/unknown history preservation are tested. |
| C23 | Complete | Legacy/demo and route/map/tracking paths retain explicit provenance; browser QA exercised input, decision, approval, mock dispatch and audit log. |
| C24 | Complete | Definitive dynamic-v2 artifacts contain 660 complete policy runs, 330 seed pairs, 11 scenarios, 30 replications, units, chronology, completeness and provenance. |
| C25 | Complete | Contamination/energy remain unavailable without evidence; fuel/CO2 and all simulation values stay labelled modelled/synthetic. |
| C26 | Producer blocked | Shared lost-acknowledgement, replay and UTC round-trip handshake requires repaired PR #2 ingestion. |
| C27 | Producer blocked | Fixture/replay reaches route preview/audit, but saved physical producer events have not completed the full ingestion path. |
| C28 | Complete | No citizen code or storage key changed; citizen lint, 7 unit tests, production build and responsive E2E (7 passed, 1 intentional visual skip) passed. |
| C29 | Complete | Streamlit desktop/tablet/mobile browser QA passed with no console/page errors or horizontal overflow; approval-before-dispatch and audit-log paths passed. |
| C30 | Physical blocked | No physical Wi-Fi/end-to-end validation is claimed. Outage recovery and module details require hardware evidence. |
| C31 | Complete | PR #2 history is cleaned without future leakage: impossible values and contradictory duplicates are excluded, resets split growth segments, gaps remain explicit, and isolated ultrasonic jumps cannot create critical alerts. |
| C32 | Complete | Every configured bin receives one shared-cutoff record with explicit PR #2-to-PR #1 ID mapping, actual observation age, null missing evidence, model version/cutoff, and validator-compatible risk/confidence. |
| C33 | Complete | Adaptive 6/24/48/168-hour distribution forecasts combine recent rates, gated calendar/event patterns, site/area fallbacks, online residual updates, scheduled/drift retraining and interpolated conservative threshold crossing. |
| C34 | Complete | `estimated_density` remains labelled context, is excluded from the model, and never becomes measured `weight_kg`; absent calibration emits null. |
| C35 | Complete | Chronological rolling-origin evaluation compares current fill, last rate, prior week and seasonal-average baselines; it reports MAE, TTO error, precision/recall, Brier/calibration, interval coverage, false triggers and missed overflows by all five requested regimes. |
| C36 | Producer blocked | The read-only client and append-only consumer cache work with PR #2's current 2,000-row endpoint, but the current one-bin/two-second branch cannot itself supply the owner-specified three-channel long history needed for field seasonal validation. |

## Producer blockers R1–R10

These remain owned by the hardware/API contributor; consumer defenses do not prove a producer repair.

| ID | Producer blocker | Routing-side preparation |
| --- | --- | --- |
| R1 | Incorrect ECHO wiring diagram | Physical acceptance stays gated. |
| R2 | Teensy FreeRTOS build mismatch | Fixture/replay development is separate from a verified producer build. |
| R3 | Filter freezes after large fill changes | Quality flags, resets and failure traces remain visible. |
| R4 | Invalid readings become zero | Missing/invalid stays unknown; confident zero is not manufactured. |
| R5 | File API key ignored | Client surfaces authentication failure and does not bypass it. |
| R6 | Serial diagnostics corrupt frames | Malformed/partial data cannot become a healthy complete snapshot. |
| R7 | Temporary upload failure loses events | Stable source IDs, replay ordering and outage visibility are supported; durable producer replay remains pending. |
| R8 | Timestamp offsets disappear/collide | UTC/offset parsing and ambiguous clock states are enforced without guessing. |
| R9 | Calibration button does not change baseline | Calibration version is retained in observations/history/audit. |
| R10 | Stale/unreliable bins look healthy | Age, availability and quality drive operator state and route eligibility. |

## Owner architecture clarification

The shared Teensy/PR #2 ESP32-C3 relay produces `fill_observation` events for exactly three physical bins: one `general_waste` channel and two `recycling_return` channels. All three fill channels may enter overflow prediction and routing while preserving their bin type and waste stream. The separate OV5647/Grove Vision AI V2/PR #3 path produces recognition and return-session events; schema 2.1 rejects those event kinds. General waste has no vision model, fill never decides item acceptance, and the route solver never mixes incompatible general/recycling streams in one trip.

## Live-integration decision

`live_integration_enabled` remains `false`. Fixture/replay integration is ready for review, but C26, C27 and C30 plus the R1–R10 producer gates prevent any claim of physical integration, sensor accuracy, Wi-Fi reliability, real dispatch or municipal savings.

## PR #2 forecast acceptance evidence

The committed deterministic 33-bin fixture uses four chronological rolling origins and includes normal, event, sparse-history, sensor-failure and distribution-drift slices. It is acceptance evidence, not field performance. Overall fill MAE is 0.935, 1.352, 2.140 and 3.509 percentage points at 6, 24, 48 and 168 hours respectively, versus 1.521, 4.946, 9.500 and 26.174 for current-fill-only. At 48 hours, precision is 0.933, recall is 0.737, Brier score is 0.0308, false-trigger rate is 6.7%, missed-overflow rate is 26.3%, and central-band coverage is 81.4%. Seven-day coverage falls to 66.3%, and the small drift slice is materially worse; both are explicit follow-up items. Full numbers and calibration bins are in `admin-portal/artifacts/pr2_forecast_adapter_evaluation.json`.
