# Return API v1

Implemented on `codex/integration-test` under `server/`. One station: `RRS-001`. One shared gateway: `shared-gateway-01`. Fictional citizens, simulated credits, no actuator commands. The citizen UI has not switched to this API.

## Access

Send `Authorization: Bearer <token>`. POST bodies must use `Content-Type: application/json`. The local configuration gives each citizen a distinct token and the gateway a separate device token. No device token belongs in React, a QR, logs or Git. A QR will carry only a station ID; the frontend QR/login handoff remains pending.

The launcher binds to loopback only. Mock OTP is not LAN authentication. No CORS allowance, public listener, report API or payment endpoint is enabled.

## Endpoints

| Method and path | Role | Purpose |
| --- | --- | --- |
| `GET /health` | None | Simulation and disabled actuation/payment flags |
| `POST /api/v1/return-sessions` | Citizen | Create a station-bound session |
| `GET /api/v1/return-sessions/{session_id}` | Owning citizen | Read inspections and credit total |
| `POST /api/v1/return-sessions/{session_id}/inspections` | Owning citizen | Begin an inspection |
| `POST /api/v1/return-sessions/{session_id}/finish` | Owning citizen | Finish and interrupt any pending inspection |
| `GET /api/v1/recycling/stations/{station_id}` | Device | Read current session/inspection and readiness |
| `POST /api/v1/recycling/stations/{station_id}/ready` | Device | Acknowledge removal after the latest inspection |
| `POST /api/v1/recycling/inferences` | Device | Submit image-free PR3 metadata |

## Session and Removal Flow

1. Device reads station state. POST `/ready` with `request_id`, `device_id`, `boot_id`, `after_inspection_id`, `empty: true` and `is_simulation: true`. Initially `after_inspection_id` is null; thereafter it must match `last_inspection_id` from the server. Reuse a request ID only to retry the identical acknowledgement.
2. Citizen POSTs a session with `request_id` and `station_id`. Use the returned `session_id`. Another active session at that station receives 409. The default session lifetime is 20 minutes.
3. Citizen POSTs an inspection with `request_id`. Use the returned `inspection_id`. The five-second server window starts here. The device should poll station state promptly, not at a five-second interval.
4. Device relays raw samples using those server-issued IDs. The server computes the consecutive-result gate and stores the result. Citizen polls the session, not the camera.
5. After a terminal result, device confirms that the item has left the inspection area with a fresh `/ready` request. The citizen cannot perform this acknowledgement. Only then can another inspection start.
6. Citizen POSTs `/finish` with `request_id`. The server retains credits and rejects any unfinished inspection. This does not send a payment.

A repeated action request returns its existing session/inspection or acknowledgement. An old removal retry does not set the station ready again; read station state for current readiness. A changed payload under the same request ID receives 409. Restart rejects interrupted inspections and clears readiness, while preserving prior credits. A new device boot interrupts pending inspection state; a retired boot cannot re-arm the station.

## Inference Envelope

The fields match PR3 `InferenceMetadata` at `819ff37b41a78208ba1624ad0060f8bec0358346`:

| Fields | Constraint |
| --- | --- |
| `schema_version` | Integer 1, not a boolean |
| `event_id`, `station_id`, `device_id`, `boot_id` | Nonempty bounded identifiers; stable event ID across retries |
| `sequence` | Nonnegative integer, strictly increasing within the recognition boot namespace |
| `session_id`, `inspection_id` | Server-issued IDs from the current station flow |
| `observed_at` | Timezone-aware timestamp, within the inspection and no more than five seconds old; at most one second ahead |
| `source` | `grove-vision-ai-v2` |
| `model_version` | Nonempty identifier; test harness marks its model as not trained |
| `material` | `plastic`, `metal`, `glass`, `paper` or `other` |
| `confidence` | Finite number from 0 to 1, or null for no detection |
| `object_count`, `inference_ms` | Bounded nonnegative integers |
| `is_simulation` | Must be true in this build; false receives 409 |

No image, base64, video, predicted acceptance, payout amount or stable-result count is accepted. Fill events belong to PR2 and use their own endpoint and sequence namespace.

Three consecutive matching plastic/metal/glass results at confidence >=0.70 within five seconds earn a single simulated 20-sen credit. Paper/other and multiple objects reject. Low confidence or no object resets confirmation and waits until timeout. The server bounds each inspection to 128 stored samples. A sequence gap resets the consecutive run.

Exact event retries return the stored inspection result with `duplicate: true`. Changing an existing event payload or repeating a sequence under another ID receives 409. A new event cannot reopen an accepted inspection. Session reads expose `credit_cents`, `currency: MYR`, `is_simulation`, status and inspections; each inspection has one `decision` containing outcome, reason, material, confidence, stable-results count and value in cents.

## Failures and Limits

401 means missing/wrong-role credentials; 404 hides unknown or another citizen's resources; 409 means conflicting state or identity; 422 means invalid metadata; 415 means a non-JSON POST; 413 means a body over 16 KiB. An API failure must not trigger mock acceptance in the future citizen client.

No response authorizes hardware actuation. Station state reports `actuation_enabled: false`. A future hardware contract still needs expiring command IDs, execution acknowledgement, physical removal evidence and fault tests. Do not treat a stored decision or repeated acknowledgement as a command to open a gate.

## Contributor Check

Run `python -m integration.return_preflight --vision-root PATH_TO_PR3_CHECKOUT` after installing `server/requirements.txt`. This imports PR3's serializer, sends real loopback HTTP requests, accepts metal, rejects paper and verifies one stored 20-sen credit after a retry. It uses temporary credentials/data and stops its server. It does not test a trained model, Grove, ESP wiring, the citizen browser or routing.
