# PR #3 Recycling Vision Review and Main Integration Contract

Reviewed: 27 August 2026

- Pull request: [#3, Feature/recycling yolo detector](https://github.com/Rover-Panto/BinSight/pull/3)
- Reviewed head: `ed6f8a83dca0869fea69eb40685a328133c93794`
- Base `main`: `9fca9d47afb805f40034da970bb47d791ba8f0b4`
- Review decision: **changes required before merge**

## Required Outcome

Only the two recycling bins participate in the computer-vision return flow. Their fill sensors are independent and belong to the shared Teensy/PR #2 telemetry path. The OV5647 camera connects to Grove Vision AI V2, and Grove runs the deployed model locally. The dedicated PR #3 ESP32-C3 relays compact inference results only. The server makes the accept/reject decision and returns it to the C3 for chute feedback and to the website for session updates.

The citizen website must not open, stream or store camera images. During an active return session it waits for one terminal station event, then shows the detected container and whether the station accepted it. The eligible classes are:

- `plastic`
- `metal`
- `glass`

The owner's server-side decision tree accepts those three material labels after the confidence/stability gate and rejects every other label, including `paper` and `other`. Low or missing confidence remains in the inspecting state until the inspection timeout, then produces a rejection. A rejected result must leave the session active so the resident can add another item.

## Does PR #3 Contain the Model?

**No trained model artifact is present.** The branch contains `train_recycling.py`, `webcam_recycling.py`, `recycling_data.yaml`, an unpinned dependency list and two copies of the guide. It contains no `.pt`, `.onnx`, `.tflite`, `.pth`, `.bin` or dataset files. `weights/yolo11n.pt` is a configured base-weight path and `runs/recycling/yolo11n_recycling/weights/best.pt` is the expected training output; neither file is committed. Ask the contributor for the trained artifact, class map, training provenance and held-out metrics before calling it a supplied model.

## Review Findings

### [P1] The current display policy includes paper and broad material objects

Sources: [`recycling_data.yaml:9`](https://github.com/Rover-Panto/BinSight/blob/ed6f8a83dca0869fea69eb40685a328133c93794/recycling_data.yaml#L9), [`webcam_recycling.py:14`](https://github.com/Rover-Panto/BinSight/blob/ed6f8a83dca0869fea69eb40685a328133c93794/webcam_recycling.py#L14).

The configured classes are `plastic`, `metal`, `glass`, `paper` and `other`. `paper` is included in `TARGET_CLASSES`, although the owner's return policy rejects it. The guide also defines the accepted materials as containers and objects, so a plastic object, metal tool or glass object can receive the same class as a deposit container.

Keep the five-class model interface, but the server must accept only `plastic`, `metal` and `glass`. Remove `paper` from the demo's accepted display set. The material decision tree alone does not prove beverage-container eligibility: either restrict the training label meanings to the intended containers or add a separately tested container-eligibility signal. Do not claim can/bottle validation from generic material labels.

### [P1] The pull request does not deploy inference to Grove Vision AI V2

Sources: [`train_recycling.py:16`](https://github.com/Rover-Panto/BinSight/blob/ed6f8a83dca0869fea69eb40685a328133c93794/train_recycling.py#L16), [`RECYCLING_YOLO.md:31`](https://github.com/Rover-Panto/BinSight/blob/ed6f8a83dca0869fea69eb40685a328133c93794/docs/RECYCLING_YOLO.md#L31), [`RECYCLING_YOLO.md:56`](https://github.com/Rover-Panto/BinSight/blob/ed6f8a83dca0869fea69eb40685a328133c93794/docs/RECYCLING_YOLO.md#L56).

The current path trains a PyTorch `.pt` model and runs Python/OpenCV on a laptop webcam. Grove Vision AI V2 is not a DirectShow camera backend for this design. The competition prototype requires the model to execute on Grove and the ESP32-C3 to receive results through SSCMA.

Add a documented export and deployment path that produces a Grove-compatible fully integer Vela-compiled TFLite model, records its checksum and class order, and flashes it to the module. Seeed's deployment guide requires the `*_int8_vela.tflite` artifact for Grove Vision AI V2. Its SSCMA Arduino library supports ESP32-C3 over I2C or hardware UART; select one transport and record the tested pins, baud rate, firmware and library versions.

Official references: [Grove model deployment](https://wiki.seeedstudio.com/grove_vision_ai_v2_sscma/), [SSCMA AT/Arduino interface](https://wiki.seeedstudio.com/grove_vision_ai_v2_at/), [SSCMA-Micro](https://github.com/Seeed-Studio/SSCMA-Micro).

### [P1] No machine-readable decision reaches the return session

Source: [`webcam_recycling.py:71`](https://github.com/Rover-Panto/BinSight/blob/ed6f8a83dca0869fea69eb40685a328133c93794/webcam_recycling.py#L71).

The script draws boxes in a local window. It creates no inference event, session binding, event identity, ESP transport, server request or acknowledgement. `main` still creates a simulated result after an 850 ms browser timer in `web/src/pages/ReturnPages.tsx` and reads the result from demonstration settings in `web/src/store.tsx`.

Do not connect the browser directly to the ESP32-C3. Add a server endpoint for authenticated, idempotent inference samples and call the server policy added in `server/recycling_policy.py`. The website should use a small return-station client that polls or subscribes to the server for the active session. Keep a mock client for local demonstrations and browser tests.

### [P1] Frame-by-frame detections cannot count physical items safely

Sources: [`webcam_recycling.py:66`](https://github.com/Rover-Panto/BinSight/blob/ed6f8a83dca0869fea69eb40685a328133c93794/webcam_recycling.py#L66), [`webcam_recycling.py:72`](https://github.com/Rover-Panto/BinSight/blob/ed6f8a83dca0869fea69eb40685a328133c93794/webcam_recycling.py#L72).

The loop handles every box in every frame. It has no single-item region, stable-result rule, timeout, duplicate suppression or removal/re-arm state. A direct network connection built on this loop could credit the same can many times or accept a one-frame false result.

Implement one server-owned decision state machine:

```text
IDLE -> ARMED -> INSPECTING -> ACCEPTED or REJECTED
     -> WAIT_FOR_REMOVAL -> IDLE
```

Use these prototype defaults as configuration, not measured truth:

- minimum eligible confidence: `0.70` inclusive
- matching results required: `3` consecutive inference results
- inspection timeout: `5000 ms`
- one terminal event per inspection request
- re-arm only after item removal or an explicit new-item command

Set the final confidence threshold from held-out test results. The server counts consecutive results itself; it must not trust a stable-result count supplied by the ESP32-C3. Multiple objects reject, class changes reset the stable run, and low-confidence/no-object inspections reject at timeout. Do not add payout value while the state remains `INSPECTING`.

### [P2] The branch lacks merge and reproducibility controls

Sources: [`requirements.txt`](https://github.com/Rover-Panto/BinSight/blob/ed6f8a83dca0869fea69eb40685a328133c93794/requirements.txt), [`docs/RECYCLING_YOLO.md`](https://github.com/Rover-Panto/BinSight/blob/ed6f8a83dca0869fea69eb40685a328133c93794/docs/RECYCLING_YOLO.md), [`docs/docs/RECYCLING_YOLO.md`](https://github.com/Rover-Panto/BinSight/blob/ed6f8a83dca0869fea69eb40685a328133c93794/docs/docs/RECYCLING_YOLO.md).

The same guide appears under `docs/` and `docs/docs/`. The root dependency file has no version pins and can collide with the main-owned server environment. The repository ignore rules do not exclude datasets, training runs or weights. The branch adds no tests, model card, export record or held-out metrics, and the pull-request description remains the empty template.

Keep one guide at `docs/RECYCLING_VISION.md`. Put training code, pinned dependencies and tests under `recycling_vision/`. Ignore `dataset/`, `runs/`, `weights/`, `.pt`, `.onnx` and generated `.tflite` files unless the team approves a small release artifact with its licence and checksum. Fill in the pull-request description and attach actual command results.

## Required Data Contract

Grove may return boxes and scores to the ESP32-C3 through SSCMA. The ESP32-C3 sends compact inference metadata to the server, which owns the decision. Do not include JPEG, base64 image, video, webcam URL or camera-stream fields.

```json
{
  "schema_version": 1,
  "event_id": "0191f4d8-7b92-7bce-9d2d-0af9157fd381",
  "station_id": "RRS-001",
  "device_id": "recycling-relay-01",
  "boot_id": "boot-8dd78c",
  "sequence": 42,
  "session_id": "BS-1234",
  "inspection_id": "INS-1234-01",
  "observed_at": "2026-08-27T09:30:12.345Z",
  "source": "grove-vision-ai-v2",
  "model_version": "recycling-yolo-1.0.0",
  "material": "plastic",
  "confidence": 0.93,
  "object_count": 1,
  "inference_ms": 84,
  "is_simulation": true
}
```

The model's class map uses `plastic`, `metal`, `glass`, `paper` and `other`; unknown labels fail closed. The server returns `waiting`, `accepted` or `rejected` with a reason such as `eligible_high_confidence`, `unsupported_material`, `low_confidence`, `inspection_timeout`, `multiple_items` or `invalid_inference`.

The backend must enforce:

- one stored record for each `event_id`, including retries;
- monotonic sequence tracking per `device_id` and `boot_id`;
- an active, unexpired `session_id` bound to the same `station_id`;
- `accepted` only for `plastic`, `metal` or `glass` after the server computes the confidence/stability gate;
- `valueCents = 20` only after the decision event has been stored;
- no payout for a duplicate, stale, rejected or unacknowledged event;
- no image payload fields;
- separate storage from general-waste fill telemetry and truck routing.

### Fill-system boundary

PR #3 must not read, relay, validate or store fill levels. The one Teensy and PR #2 ESP32-C3 report all three demo bins, including both recycling bins, through the routing telemetry contract. PR #3 may use a stable recycling `bin_id` only to bind an inference to the correct return location. It must not require a current fill reading before inference, acceptance or payout.

## Implemented Server Decision Policy

`server/recycling_policy.py` now contains the dependency-free policy and `server/tests/test_recycling_policy.py` covers its decision rules. The networking node neither runs the model nor makes the final acceptance decision.

```python
from server.recycling_policy import InferenceSample, RecyclingInspection

inspection = RecyclingInspection()
decision = inspection.observe(
    InferenceSample(sequence=42, material="plastic", confidence=0.93, object_count=1),
    elapsed_ms=300,
)
```

The API layer must persist samples and the terminal decision, authenticate/bind the station and session, validate freshness and restore or interrupt active inspections after a server restart. The policy does not implement those transport or storage responsibilities. It supplies a proposed 20-sen value only for an accepted result; the backend must store the decision before crediting the session.

The ESP32-C3 queues raw inference events through a network outage and acts on the matching server decision after reconnecting. A network timeout cannot become local acceptance. See `server/README.md` for the integration boundary.

## Website Integration Contract

Add a transport boundary rather than camera code to React:

```ts
export type ReturnMaterial = 'plastic' | 'metal' | 'glass'

export interface StationDecision {
  eventId: string
  stationId: string
  sessionId: string
  material: ReturnMaterial | 'paper' | 'other' | 'unknown'
  confidence: number | null
  decision: 'accepted' | 'rejected'
  reason: string
  modelVersion: string | null
  observedAt: string
  source: 'grove-vision-ai-v2' | 'mock'
}

export interface ReturnStationClient {
  beginInspection(sessionId: string, stationId: string): Promise<{ inspectionId: string }>
  waitForDecision(inspectionId: string, signal: AbortSignal): Promise<StationDecision>
}
```

`ReturnSessionPage` should enter `INSPECTING`, call `beginInspection`, wait for a terminal decision and then pass the normalized event to the store. It must abort polling when the page unmounts or the session finishes. Do not call `navigator.mediaDevices`, render `<video>` or accept a user-selected item category.

Retain `MockReturnStationClient` as the default until the local backend and hardware path pass their contract tests. Enable the API client through local configuration. A missing server, timeout or malformed event should show a station-unavailable state and must not create an accepted item.

Updating `ItemEvent` requires a versioned citizen-data migration. Preserve existing version 3 `Can` records. Existing `Bottle` records do not prove glass or plastic, so migrate them to a display-only `legacy_bottle` value rather than inventing a material. Deduplicate new events by `eventId` before adding RM0.20.

## Main Integration Order

1. **Repair PR #3.** Rebase from current `main`; exclude paper from the accepted display policy; document the five-class map and its container-eligibility limits; remove the duplicate guide; isolate and pin dependencies; add ignore rules, model evaluation and the Grove export procedure.
2. **Complete the PR #3 recycling device path.** Supply the Grove-compatible model artifact and the dedicated recycling ESP32-C3 relay. It reads SSCMA class/confidence results and sends the inference contract above. It does not read or relay fill data. PR #3 must not depend on or modify PR #1 or PR #2.
3. **Build the main-owned server endpoint.** Add authenticated `/api/v1/recycling/inferences`, QR-bound return-session endpoints, durable event storage and `server/recycling_policy.py`. Main owns the decision, session credit and citizen-facing result.
4. **Integrate the citizen return flow in main.** Add a QR deep link such as `/return/start?station=RRS-001`, preserve it through login, create a station-bound session, wait for server decisions and keep a mock fallback for tests. Keep camera data out of the browser.
5. **Run one end-to-end pilot.** User opens station QR -> main creates the return session -> Grove result -> PR #3 ESP32-C3 metadata relay -> main server confidence/stability gate -> stored decision -> website accept/reject -> exactly one RM0.20 credit for an accepted item.

PR #1 and PR #2 form the separate three-bin fill/routing track and are not dependencies of recognition. Keep the PR #3 device work and main-owned server/citizen changes in reviewable commits with an explicit API version.

## Acceptance Checks

| ID | Required result |
| --- | --- |
| V01 | Dataset class order is `plastic`, `metal`, `glass`, `paper`, `other` in training, export, Grove metadata and tests. |
| V02 | The server accepts only plastic, metal and glass. Paper, other and unknown labels reject. Any beverage-container eligibility claim has separate dataset/test evidence. |
| V03 | An eligible result below the configured threshold remains `INSPECTING`; it does not add RM0.20. |
| V04 | Three matching eligible results above the threshold produce one accepted event. |
| V05 | Conflicting, multiple, missing and low-confidence results reach a bounded rejection without a payout. |
| V06 | Holding one item in view cannot create a second event until the station re-arms. |
| V07 | The deployed artifact is the recorded Grove-compatible integer Vela TFLite file and the class order matches the firmware. |
| V08 | The ESP32-C3 obtains class, confidence and timing from Grove over the documented SSCMA I2C/UART link and runs no model. |
| V09 | Network loss and lost acknowledgement replay the same event ID; the server stores and credits it once. |
| V10 | The server computes acceptance from raw samples and rejects ineligible classes, malformed data, stale sessions and wrong stations. It does not trust an ESP32-supplied acceptance or stable-result count. |
| V11 | The website receives decision metadata and displays no camera element, image, frame or stream. |
| V12 | A rejected item leaves `Add another item` available. |
| V13 | Version 3 citizen returns and payouts survive the new event migration without relabelling old bottles as glass or plastic. |
| V14 | Existing login, payout, report and attachment browser tests still pass. |
| V15 | Held-out results report per-class precision, recall, confusion matrix, confidence threshold and failure examples under prototype lighting. |
| V16 | PR #2 recycling fill reports continue through a PR #3 vision fault; PR #3 decisions continue through a fill-path fault; fill level never changes item acceptance or payout. |

## Verification Performed During Review

- Inspected all six files in PR #3 at `ed6f8a8`.
- Python syntax compilation passed for `train_recycling.py` and `webcam_recycling.py`.
- The new central-server policy passed all 16 unit tests, including the inclusive 0.70 threshold, stability, timeout, rejection and duplicate-sequence cases.
- The PR has no automated status checks and includes no tests.
- `train_recycling.py --help` could not run in the review environment because `ultralytics` was not installed; dependencies were not installed into the shared workspace for a review-only check.
- No training run, Grove export, physical inference, ESP32-C3 link, server delivery or browser integration was demonstrated by the pull request.
