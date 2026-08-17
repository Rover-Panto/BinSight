# ESP32-to-Raspberry Pi sensor contract

## Physical topology

One ESP32 controls exactly three underground bins. Each bin has:

- one downward-facing ultrasonic channel for occupied-volume percentage; and
- one conditioned analogue pressure/force channel for estimated waste mass.

The ESP32 fires ultrasonic sensors sequentially to limit acoustic cross-talk, takes median-filtered readings, and publishes one atomic MQTT message containing all three bins. The Raspberry Pi validates, calibrates, fuses, deduplicates, and stores each channel separately.

## MQTT

- Topic: `binsight/v1/telemetry/<controller_id>`
- Current ESP32 client publish level: QoS 0 (`PubSubClient` publish API)
- Raspberry Pi subscription request: QoS 1 where the broker/client supports it; this cannot upgrade a QoS 0 publication already sent by the ESP32
- Payload: UTF-8 JSON matching `hardware/telemetry.schema.json`
- Default interval: 15 minutes
- Production: use broker authentication and TLS; never place credentials in firmware source control.

The firmware sets a 1,024-byte MQTT buffer. The checked maximum three-bin JSON message is 555 bytes and the complete MQTT packet is 616 bytes, leaving buffer headroom. The controller serializes once, verifies serialization length, attempts each publish up to three times with backoff, and retains up to four unsent messages in a local RAM queue. Serial logs distinguish connection, serialization, publish, retry, queue, and queue-overflow failures.

These measures prevent silent truncation and reduce transient loss, but QoS 0 has no broker acknowledgement and a RAM queue is lost on power failure. A field deployment that requires at-least-once telemetry must migrate to an ESP32 MQTT library with acknowledged QoS 1 publish, add durable local storage where appropriate, and test duplicate handling at the gateway.

The gateway stores both calibrated estimates and flags a difference above 20 percentage points rather than silently averaging it away. The planning simulator and route-input adapter preserve missing/low-confidence states, calculate conservative uncertainty, and may request inspection. In the simulation, one available sensor receives a 7.5-point margin; broader low-confidence or aged evidence receives 15 points. When both sensors are absent, a last-valid value may be aged conservatively; without one, inspection is required and no false collection load is fabricated. Uncertainty must never be converted into a reassuring zero.

The predictive-AI routing snapshot uses:

```text
timestamp,bin_id,fill_pct,weight_kg,time_to_overflow_hours,risk_level,confidence_flag
```

There must be one row for each of the 33 bins with a shared timezone-aware timestamp. Snapshot freshness, future timestamps, duplicate IDs, sensor ranges, missing data, sensor disagreement, and risk/confidence values are validated before routing.

## Calibration gate

The example ADC and distance values are placeholders. For every installed bin:

1. Measure the empty distance at five lid positions and save the median.
2. Establish the operational full distance without placing a person inside the bin.
3. Tare the pressure system with the empty inner container installed.
4. Add traceable known masses across at least five points up to the safe test limit.
5. Fit/check linearity, hysteresis, temperature drift, and repeatability.
6. Verify that a simulated collection reset is detected.

An ordinary force-sensitive resistor under a 4.5 m³ container is not a safe structural weighing solution. Use rated load/pressure hardware, mechanical overload protection, and a conditioned 0–3.3 V output designed by a qualified engineer. The ESP32 input must never exceed 3.3 V.

## Raspberry Pi flow

```text
ESP32 (3 bins) -> MQTT broker -> gateway validation/fusion -> SQLite -> model-ready CSV
```

Run a saved-payload test:

```powershell
python -m gateway.binsight_gateway `
  --calibration hardware/controller_calibration.example.json `
  --database data/sensor_readings.sqlite3 `
  --input-json hardware/example_payload.json `
  --export-csv data/model_sensor_log.csv
```

Run live MQTT ingestion:

```powershell
$env:BINSIGHT_MQTT_HOST = "127.0.0.1"
python -m gateway.binsight_gateway `
  --calibration hardware/controller_calibration.example.json `
  --database data/sensor_readings.sqlite3 `
  --mqtt
```
