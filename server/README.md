# Central Return Server

Available on `codex/integration-test`, not merged into `main`. This is a **loopback-only, simulation-only integration build** for one recycling station. It does not operate a chute, send money, run a model, receive images or replace the citizen website's current mock flow.

## Run

From the repository root, in a dedicated Python 3.13 environment:

```powershell
python -m pip install -r server/requirements.txt
python -m server --init
python -m server
```

The initializer creates `server/local-config.json` with random, distinct citizen and device credentials. It refuses to overwrite an existing file. Both that file and `server/data/` are ignored by Git. Use fictional account IDs, not NIDs or bank details. Do not commit credentials or paste them into PR comments.

The service listens at `http://127.0.0.1:8010`; `/docs` lists request schemas. Use `--port` to choose another free port. Stop with Ctrl+C. There is no automatic background process, shutdown endpoint, public listener or CORS allowance.

One process owns a database at a time. An OS lock rejects a second instance. Restart retains sessions, decisions, events and credits, rejects interrupted inspections, and requires a fresh station-removal acknowledgement.

## Contract

See [RETURN_API_V1.md](../docs/RETURN_API_V1.md) for the request sequence, authentication and PR3 integration instructions. `POST /api/v1/recycling/inferences` accepts PR3's image-free metadata envelope.

Grove performs recognition. The shared ESP32-C3 relays metadata; the server decides. Three consecutive plastic, metal or glass samples at confidence **>=0.70**, within five seconds measured by the server, earn one simulated 20-sen credit. Other materials or multiple items reject. Missing/low-confidence results wait, then time out. This is material recognition, not proof of beverage-container eligibility or measured model accuracy.

The API stores the terminal decision and credit in the same SQLite transaction. Exact event retries return the existing result; changed event payloads or reused sequence numbers cannot add another credit. Session and inspection creation also support idempotent request IDs.

Only a device-authenticated removal acknowledgement can re-arm the station. The browser does not supply a material, confidence, amount or removal signal. `is_simulation: false` is rejected. No command in this build authorizes actuation.

The recycling demonstrator has an independent fill sensor. Teensy fill readings belong in PR2's telemetry service and reach PR4/PR1 for collection planning. They do not enter this API or influence acceptance. One shared C3 will carry both streams through independent modules.

## Preserve Data

The SQLite store is separate from browser key `binsight-demo-v1`, PR2 telemetry and PR1 planning history. No import or migration from those stores runs. An unknown SQLite schema fails closed instead of recreating tables.

Back up a running or stopped return database with SQLite's backup operation, not a file copy that might omit its WAL:

```powershell
python -m server.backup server/data/returns.sqlite3 server/data/backups/returns-before-change.sqlite3
```

The command verifies the copy and refuses to overwrite a destination. To test a restore, use a separate local configuration pointing to the backup copy and inspect its session totals. Keep the original. Version 1 has no automatic migrations.

## Verify

```powershell
python -m unittest discover -s server/tests -v
python -m integration.return_preflight
python -m integration.return_preflight --vision-root PATH_TO_PR3_CHECKOUT
```

The preflight creates temporary credentials and a temporary database, opens an unused loopback port, sends real HTTP requests, and shuts down its own server. With `--vision-root`, it serializes samples using PR3's actual `InferenceMetadata` class. It does not load weights, run Grove or access a webcam.

Remaining work: citizen QR/login handoff and an explicit mock/API transport, versioned return-history migration, simulated payout integration, shared report API, combined C3 firmware, expiring/deduplicated actuator commands and physical removal evidence. Do not enable LAN or hardware use before those gates pass.
