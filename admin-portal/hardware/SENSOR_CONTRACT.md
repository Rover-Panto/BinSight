# ESP32-to-Raspberry Pi sensor contract

## Physical topology

One ESP32 controls exactly three underground bins. Each bin has:

- one downward-facing ultrasonic channel for occupied-volume percentage; and
- one conditioned analogue pressure/force channel for estimated waste mass.

The ESP32 fires ultrasonic sensors sequentially to limit acoustic cross-talk, takes median-filtered readings, and publishes one atomic MQTT message containing all three bins. The Raspberry Pi validates, calibrates, fuses, deduplicates, and stores each channel separately.

## MQTT

- Topic: `binsight/v1/telemetry/<controller_id>`
- QoS expected by the Raspberry Pi: 1
- Payload: UTF-8 JSON matching `hardware/telemetry.schema.json`
- Default interval: 15 minutes
- Production: use broker authentication and TLS; never place credentials in firmware source control.

The gateway uses the maximum of calibrated ultrasonic fill and pressure-derived mass fill as the conservative routing value. Both estimates remain stored. A difference above 20 percentage points is flagged rather than silently averaged away.

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
