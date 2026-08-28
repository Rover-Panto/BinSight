# Central Server Recycling Policy

`recycling_policy.py` implements the owner's material decision tree on the central server:

```text
plastic -> accept after the confidence/stability gate
metal   -> accept after the confidence/stability gate
glass   -> accept after the confidence/stability gate
anything else -> reject
```

The default gate requires three consecutive matching results at confidence 0.70 or above. A result at exactly 0.70 qualifies. Low-confidence eligible results wait for more evidence; the server rejects an unfinished inspection after five seconds. Multiple items and malformed results reject. Validate this threshold against held-out prototype data before presenting accuracy claims.

Grove Vision AI V2 runs the model. The demonstrator's shared ESP32-C3 relays class, confidence, sequence and object count to the backend while independently forwarding Teensy fill telemetry. The central server calls this policy, stores its terminal decision, and sends the outcome to the station and citizen website. The ESP32-C3 controls the chute only after receiving the matching server decision. Neither the server nor the website needs an image stream.

Both recycling bins also have independent fill sensors. The Teensy sends those readings through the same C3 but a separate routing queue; they never enter `RecyclingInspection`. Software faults must be contained between tasks, although a shared ESP power loss or reset interrupts both streams.

## Integration Boundary

`main` currently has no backend application. This package is the start of the main-owned recycling server. The main server must expose the inference and QR-session endpoints, using one `RecyclingInspection` per server-created inspection ID. PR #1 and PR #2 do not own or host this policy.

The API layer must authenticate the station, bind it to the active return session, validate event identity and freshness, persist samples/decisions, and make event processing idempotent. Supply elapsed milliseconds from a server monotonic clock. Do not trust a device-provided stable-result count. The policy computes that count itself.

`Decision.value_cents` is the proposed simulated credit, not proof of payment. Persist one terminal decision per inspection before updating the session total. A repeated poll or replay returns the same decision and must not add another RM0.20. A server restart must restore the active inspection or mark it interrupted; it must not replay old samples into a new inspection.

No dataset or trained model is present in PR #3 at `ed6f8a8`. Its current class names match this policy, but its broad material labels do not prove that the object is a beverage container. The model contributor must narrow the dataset semantics or provide a separate container-eligibility signal before claiming bottle/can validation.

See [the PR #3 review](../docs/PR3_RECYCLING_VISION_REVIEW.md) for transport, frontend and merge requirements.

## Tests

Run from the repository root:

```powershell
python -m unittest discover -s server/tests -v
```
