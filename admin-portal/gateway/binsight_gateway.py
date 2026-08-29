from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from binsight.sensors import SensorStore, load_calibrations, reading_to_dict


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="BinSight Raspberry Pi sensor gateway")
    parser.add_argument("--calibration", type=Path, required=True)
    parser.add_argument("--database", type=Path, default=Path("data/sensor_readings.sqlite3"))
    parser.add_argument("--input-json", type=Path, help="Ingest one saved ESP32 payload and exit")
    parser.add_argument("--export-csv", type=Path, help="Export model-ready readings after ingest")
    parser.add_argument("--mqtt", action="store_true", help="Subscribe to the configured MQTT broker")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    store = SensorStore(args.database, load_calibrations(args.calibration))
    try:
        if args.input_json:
            payload = json.loads(args.input_json.read_text(encoding="utf-8"))
            print(json.dumps([reading_to_dict(item) for item in store.ingest(payload)], indent=2))
        elif args.mqtt:
            run_mqtt(store)
        else:
            raise SystemExit("Choose --input-json or --mqtt")
        if args.export_csv:
            store.export_model_csv(args.export_csv)
    finally:
        store.close()


def run_mqtt(store: SensorStore) -> None:
    import paho.mqtt.client as mqtt

    host = os.environ.get("BINSIGHT_MQTT_HOST", "127.0.0.1")
    port = int(os.environ.get("BINSIGHT_MQTT_PORT", "1883"))
    topic = os.environ.get("BINSIGHT_MQTT_TOPIC", "binsight/v1/telemetry/+")
    client = mqtt.Client(
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        client_id="binsight-rpi-gateway",
        protocol=mqtt.MQTTv311,
    )
    username = os.environ.get("BINSIGHT_MQTT_USERNAME")
    password = os.environ.get("BINSIGHT_MQTT_PASSWORD")
    if username:
        client.username_pw_set(username, password)
    if os.environ.get("BINSIGHT_MQTT_TLS") == "1":
        client.tls_set()

    def on_connect(client, userdata, flags, reason_code, properties):
        if reason_code != 0:
            raise RuntimeError(f"MQTT connection failed: {reason_code}")
        client.subscribe(topic, qos=1)

    def on_message(client, userdata, message):
        try:
            payload = json.loads(message.payload.decode("utf-8"))
            readings = store.ingest(payload)
            print(json.dumps([reading_to_dict(item) for item in readings]))
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
            print(json.dumps({"status": "rejected", "reason": str(error)}))

    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(host, port, keepalive=60)
    client.loop_forever()


if __name__ == "__main__":
    main()
