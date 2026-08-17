import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HARNESS_PATH = ROOT / "firmware" / "esp32_binsight" / "tools" / "mqtt_payload_harness.py"


def _load_harness():
    spec = importlib.util.spec_from_file_location("mqtt_payload_harness", HARNESS_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_largest_three_bin_payload_fits_and_is_not_truncated():
    harness = _load_harness()
    result = harness.run_harness()
    assert result["payload_bytes"] >= 422
    assert result["mqtt_packet_bytes"] <= 1024
    assert result["published"] is True
    assert result["not_truncated"] is True


def test_firmware_configures_buffer_checks_publish_and_retains_failures():
    source = (ROOT / "firmware" / "esp32_binsight" / "src" / "main.cpp").read_text(
        encoding="utf-8"
    )
    assert "mqttClient.setBufferSize(kMqttBufferSize)" in source
    assert "measureJson(document)" in source
    assert "const bool published = mqttClient.publish" in source
    assert "kPublishRetries" in source
    assert "MQTT_READING_RETAINED" in source
    assert "qos=0" in source
