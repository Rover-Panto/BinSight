"""Deterministic PubSubClient buffer harness for the maximum three-bin payload."""

from __future__ import annotations

import json


MQTT_BUFFER_BYTES = 1024
MQTT_MAX_HEADER_BYTES = 5
TOPIC_PREFIX = "binsight/v1/telemetry/"


def maximum_supported_payload() -> tuple[str, bytes]:
    controller_id = "C" * 32
    topic = TOPIC_PREFIX + controller_id
    payload = {
        "schema_version": "1.0",
        "controller_id": controller_id,
        "sequence": 4_294_967_295,
        "captured_at_utc": "2099-12-31T23:59:59Z",
        "firmware_version": "F" * 32,
        "wifi_rssi_dbm": -130,
        "bins": [
            {
                "channel": channel,
                "bin_id": f"B{channel}" + "X" * 30,
                "ultrasonic_distance_mm": 10000.0,
                "pressure_adc": 4095,
            }
            for channel in (1, 2, 3)
        ],
    }
    encoded = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return topic, encoded


def mqtt_packet_bytes(topic: str, payload: bytes) -> int:
    return MQTT_MAX_HEADER_BYTES + 2 + len(topic.encode("utf-8")) + len(payload)


class FixedBufferPublisher:
    def __init__(self, capacity: int = MQTT_BUFFER_BYTES):
        self.capacity = capacity
        self.last_payload = b""

    def publish(self, topic: str, payload: bytes) -> bool:
        if mqtt_packet_bytes(topic, payload) > self.capacity:
            return False
        self.last_payload = bytes(payload)
        return True


def run_harness() -> dict[str, int | bool]:
    topic, payload = maximum_supported_payload()
    publisher = FixedBufferPublisher()
    published = publisher.publish(topic, payload)
    return {
        "payload_bytes": len(payload),
        "mqtt_packet_bytes": mqtt_packet_bytes(topic, payload),
        "buffer_bytes": publisher.capacity,
        "published": published,
        "not_truncated": publisher.last_payload == payload,
    }


if __name__ == "__main__":
    result = run_harness()
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result["published"] and result["not_truncated"] else 1)
