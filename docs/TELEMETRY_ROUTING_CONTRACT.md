# Telemetry-to-routing contract

Contract version: **2.1**  
Registry schema: **1.0**  
Routing plan schema: **2.0**  
Status: fixture/replay and PR #2 history-adapter integration ready; physical producer acceptance pending

## Ownership and live gate

The telemetry producer owns acquisition, buffering, authentication, acknowledgement and the ingestion database. The routing service is a read-only consumer. It must never write the producer database or use receipt time as a replacement for acquisition time.

Live route controls remain disabled until the repaired producer passes the shared fixtures, stable event-identity, UTC, replay, outage and acknowledgement tests. A successful HTTP connection is not evidence of sensor accuracy or reliable delivery.

BinSight has two bin types and two independent event domains. The shared Teensy/PR #2 relay sends `fill_observation` events for one general-waste and two recycling bins; all three are routing inputs. OV5647/Grove Vision AI V2 and the separate PR #3 relay send recognition/session events, which routing rejects by event kind. General waste has no camera, and fill never determines recycling acceptance.

The canonical files are:

- `admin-portal/hardware/telemetry-routing-v2.schema.json`: decision-envelope schema.
- `admin-portal/config/bin_registry.json`: hardware/canonical mapping and operating profiles.
- `admin-portal/tests/fixtures/telemetry_v2_valid.json`: consumer acceptance fixture.
- `admin-portal/binsight/telemetry_adapter.py`: normalization and replay-order rules.
- `admin-portal/binsight/telemetry_client.py`: read-only API boundary.
- `admin-portal/binsight/pr2_forecasting.py`: PR #2 history cleaning, adaptive forecast, complete snapshot alignment and evaluation.
- `admin-portal/config/pr2_forecasting.json`: explicit PR #2 ID maps and forecast policy.

## Three representations

1. **Producer event:** immutable evidence received from a device or producer replay.
2. **Normalized routing observation:** canonical bin mapping, per-channel values, age and quality.
3. **Decision snapshot:** an immutable cutoff of source event IDs plus decision/config/network/model assumptions used for one plan.

No representation may silently gain evidence that was absent upstream. Estimated weight, retained values and forecast output remain distinguishable from measurements.

## Envelope

Every version-2 envelope contains:

| Field | Meaning |
| --- | --- |
| `schema_version` | `2.1`; unknown future versions are rejected. Legacy `2.0` is accepted only with its general-waste-fill meaning. |
| `snapshot_id` | Producer snapshot identity when supplied. Routing creates a new decision-snapshot ID for every evaluation cutoff. |
| `decision_at` | UTC routing cutoff, separate from acquisition and receipt. |
| `source_mode` | `hardware`, `replay`, `synthetic`, or `legacy`. |
| `partial` | True when the producer could not provide complete coverage. |
| `next_cursor` | Optional opaque producer cursor. |
| `events` | Immutable producer events. |

Every 2.1 routing event declares `event_kind: fill_observation` and a registry-matching `bin_type` of `general_waste` or `recycling_return`. Recognition, classification and return-session event kinds are rejected even when they reference a recycling bin. `waste_stream` is taken from the registry, not trusted from the device, and incompatible streams are assigned to separate route trips.

## Event identity and time

An event carries `event_id` and the independently auditable tuple `device_id`, `boot_id`, `sequence`, and `hardware_bin_id`. The tuple prevents sequence resets after a reboot from colliding with earlier observations. Retries preserve the same identity.

`observed_at` is the acquisition time. `received_at` is server receipt. Both are normalized to UTC. Equivalent offsets therefore compare as the same instant. A synchronized event requires `observed_at`. An unsynchronized or ambiguous clock uses a null acquisition time and is routed to inspection; BinSight does not guess an offset or substitute `received_at`.

An old replay cannot replace a newer accepted observation. Same-second events remain distinct through event identity. A decision records every selected source event ID.

Live cadence defaults are provisional:

- stale after 15 minutes;
- offline after 60 minutes;
- re-evaluate every 15 minutes or on a material event.

Refreshing the page or repeating a replay never refreshes acquisition time.

## Values, availability and quality

`fill_pct` and `weight_kg` are independently nullable. Fill confidence does not certify weight. A valid fill with null weight updates fill-only last-good history; weight remains null and routing labels its conservative load as estimated.

`quality_flags` may include filter recovery, missing channel, clock, calibration, event-gap or producer-health evidence. Routing carries those flags into eligibility, inspection, maps and plan audit.

`forecast_status` is one of:

- `available`: finite `time_to_overflow_hours` is required;
- `stable_no_overflow`: model ran but predicts no positive growth, so time-to-overflow is null;
- `unavailable`: no forecast exists;
- `cold_start`: insufficient history;
- `model_error`: forecasting failed.

Null is the only unavailable representation. Infinity, NaN and large wire sentinels are rejected.

## Registry and profiles

Hardware IDs are mapped explicitly to canonical `UGB-###` IDs. Unknown, duplicate or conflicting mappings fail. Coordinates, bin order and matrix dimensions are validated together.

The physical registry identifies channel 1 as general waste and channels 2–3 as recycling return, with independent waste streams and calibration state. It separates:

- `physical-pilot`: three Teensy channels delivered through the planned ESP32-C3 communications module; and
- `competition-simulation`: 33 synthetic bins at 11 service sites.

Physical controller topology is not inferred from simulated co-location. The simulation's three-bin service grouping does not claim 11 deployed controllers.

## Legacy adapter

Existing seven-column CSV/JSON remains supported as `legacy` input. Its shared timestamp remains the observation time of every row. Legacy input does not gain producer event identities, clock-health evidence, calibration provenance or per-bin timestamps.

The legacy ESP32/MQTT demonstration payload is now schema 1.1 and adds `boot_id`. Schema 1.0 is accepted as `LEGACY-UNSCOPED` only for migration; it cannot prove reboot-safe identity.

## Current PR #2 history bridge

PR #2's current API is not a telemetry-routing 2.1 producer. Its history response contains `timestamp`, `bin_id`, `fill_pct`, `estimated_density`, `confidence_flag`, and `ingested_at`. The routing-owned forecasting adapter reads that response without mutating the producer, preserves acquisition and ingestion time separately, requires both to be at or before the decision cutoff, explicitly maps `bin_XX` to `UGB-###`, and creates a complete PR #1 snapshot at one decision cutoff.

The bridge treats PR #2's dashboard overflow badge only as a current-fill threshold; it does not consume it as a forecast. It retains pseudo-density as context, sets `estimated_density_used=false`, and emits null `weight_kg` because no calibrated mass conversion exists.

Because the PR #2 history endpoint caps each bin at 2,000 readings, API mode uses an append-only routing-owned SQLite cache. Exact retries are idempotent; contradictory same-bin/same-time readings are refused and never overwrite prior evidence. This cache is a consumer accommodation, not proof of durable producer replay or a replacement for PR #2's unresolved event-identity requirements.

Forecast output includes expected/lower/upper fill and overflow probability at 6, 24, 48, and 168 hours, interpolated conservative time to overflow, risk/confidence, observation age, quality flags, model version, and model/data cutoffs. Missing bins remain explicit unavailable records. The output is passed through the existing PR #1 validator before routing. Mathematical details and synthetic rolling-origin acceptance evidence are in `admin-portal/PR2_FORECASTING_ADAPTER.md`.

## Producer requirements still pending

The hardware/API contributor must provide a repaired endpoint and confirm:

- persistent device/boot/event identity and stored/duplicate acknowledgements;
- durable bounded replay after lost acknowledgement or temporary failure;
- UTC normalization without rewriting ambiguous legacy timestamps;
- null/unknown readings instead of fabricated zero;
- calibration version and filter-recovery quality;
- authentication loaded from the documented configuration;
- partial-coverage, queue age, drop count and producer-health signals.

Until those checks pass, fixture and recorded replay are the only enabled integration modes.
