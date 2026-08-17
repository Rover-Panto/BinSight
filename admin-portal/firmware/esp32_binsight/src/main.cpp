#include <Arduino.h>
#include <ArduinoJson.h>
#include <PubSubClient.h>
#include <WiFi.h>
#include <time.h>

#include "secrets.h"

namespace {
constexpr char kControllerId[] = "ESP32-001";
constexpr char kFirmwareVersion[] = "0.1.0";
constexpr char kTopic[] = "binsight/v1/telemetry/ESP32-001";
constexpr uint32_t kPublishIntervalMs = 15UL * 60UL * 1000UL;
constexpr uint8_t kBinCount = 3;
constexpr uint8_t kUltrasonicSamples = 5;
constexpr size_t kMqttBufferSize = 1024;
constexpr size_t kPayloadCapacity = 896;
constexpr uint8_t kPendingQueueDepth = 4;
constexpr uint8_t kPublishRetries = 3;
constexpr uint32_t kPublishBackoffMs = 250;

// Echo lines from 5 V ultrasonic modules require a divider/level shifter to 3.3 V.
constexpr uint8_t kTrigPins[kBinCount] = {16, 18, 25};
constexpr uint8_t kEchoPins[kBinCount] = {17, 19, 26};
constexpr uint8_t kPressurePins[kBinCount] = {32, 33, 34};
constexpr char const *kBinIds[kBinCount] = {"UGB-001", "UGB-002", "UGB-003"};

WiFiClient wifiClient;
PubSubClient mqttClient(wifiClient);
uint32_t sequenceNumber = 0;
uint32_t lastPublishMs = 0;

struct PendingReading {
  char payload[kPayloadCapacity];
  size_t length;
  uint32_t sequence;
};

PendingReading pendingReadings[kPendingQueueDepth];
uint8_t pendingHead = 0;
uint8_t pendingCount = 0;

template <typename T, size_t N>
void sortSmall(T (&values)[N], uint8_t used) {
  for (uint8_t i = 1; i < used; ++i) {
    T value = values[i];
    int8_t j = static_cast<int8_t>(i) - 1;
    while (j >= 0 && values[j] > value) {
      values[j + 1] = values[j];
      --j;
    }
    values[j + 1] = value;
  }
}

float readUltrasonicMedianMm(uint8_t channel) {
  float samples[kUltrasonicSamples];
  uint8_t valid = 0;
  for (uint8_t sample = 0; sample < kUltrasonicSamples; ++sample) {
    digitalWrite(kTrigPins[channel], LOW);
    delayMicroseconds(3);
    digitalWrite(kTrigPins[channel], HIGH);
    delayMicroseconds(10);
    digitalWrite(kTrigPins[channel], LOW);
    const unsigned long durationUs = pulseIn(kEchoPins[channel], HIGH, 30000UL);
    if (durationUs > 0) {
      const float distanceMm = durationUs * 0.343f / 2.0f;
      if (distanceMm >= 20.0f && distanceMm <= 10000.0f) {
        samples[valid++] = distanceMm;
      }
    }
    delay(65);  // Sequential firing prevents cross-talk between the three sensors.
  }
  if (valid < 3) {
    return NAN;
  }
  sortSmall(samples, valid);
  return samples[valid / 2];
}

uint16_t readPressureMedianAdc(uint8_t channel) {
  uint16_t samples[9];
  for (uint8_t i = 0; i < 9; ++i) {
    samples[i] = analogRead(kPressurePins[channel]);
    delay(5);
  }
  sortSmall(samples, 9);
  return samples[4];
}

void connectWifi() {
  WiFi.mode(WIFI_STA);
  WiFi.begin(BINSIGHT_WIFI_SSID, BINSIGHT_WIFI_PASSWORD);
  const uint32_t started = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - started < 20000UL) {
    delay(250);
  }
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("WIFI_CONNECTION_FAILED timeout_ms=20000");
  }
}

bool connectMqtt() {
  if (mqttClient.connected()) {
    return true;
  }
  bool connected = false;
  if (BINSIGHT_MQTT_USERNAME[0] != '\0') {
    connected = mqttClient.connect(
        kControllerId, BINSIGHT_MQTT_USERNAME, BINSIGHT_MQTT_PASSWORD);
  } else {
    connected = mqttClient.connect(kControllerId);
  }
  if (!connected) {
    Serial.printf("MQTT_CONNECTION_FAILED state=%d\n", mqttClient.state());
  }
  return connected;
}

String utcTimestamp() {
  struct tm timeInfo;
  if (!getLocalTime(&timeInfo, 2000)) {
    return "1970-01-01T00:00:00Z";
  }
  char timestamp[25];
  strftime(timestamp, sizeof(timestamp), "%Y-%m-%dT%H:%M:%SZ", &timeInfo);
  return String(timestamp);
}

bool enqueueReading(const char *payload, size_t length, uint32_t sequence) {
  if (length == 0 || length >= kPayloadCapacity) {
    Serial.printf("MQTT_QUEUE_REJECTED sequence=%lu length=%u capacity=%u\n",
                  static_cast<unsigned long>(sequence),
                  static_cast<unsigned int>(length),
                  static_cast<unsigned int>(kPayloadCapacity));
    return false;
  }
  if (pendingCount >= kPendingQueueDepth) {
    Serial.printf("MQTT_QUEUE_FULL sequence=%lu depth=%u reading_preserved=false\n",
                  static_cast<unsigned long>(sequence), pendingCount);
    return false;
  }
  const uint8_t tail = (pendingHead + pendingCount) % kPendingQueueDepth;
  memcpy(pendingReadings[tail].payload, payload, length);
  pendingReadings[tail].payload[length] = '\0';
  pendingReadings[tail].length = length;
  pendingReadings[tail].sequence = sequence;
  ++pendingCount;
  return true;
}

bool publishQueuedReading(const PendingReading &reading) {
  if (!mqttClient.connected()) {
    Serial.printf("MQTT_PUBLISH_DEFERRED sequence=%lu reason=not_connected\n",
                  static_cast<unsigned long>(reading.sequence));
    return false;
  }
  for (uint8_t attempt = 1; attempt <= kPublishRetries; ++attempt) {
    // PubSubClient's publish API sends at QoS 0. The Boolean result confirms
    // only that the packet was accepted for transmission by this client.
    const bool published = mqttClient.publish(
        kTopic,
        reinterpret_cast<const uint8_t *>(reading.payload),
        static_cast<unsigned int>(reading.length),
        false);
    if (published) {
      Serial.printf("MQTT_PUBLISH_OK sequence=%lu length=%u attempt=%u qos=0\n",
                    static_cast<unsigned long>(reading.sequence),
                    static_cast<unsigned int>(reading.length), attempt);
      return true;
    }
    Serial.printf("MQTT_PUBLISH_FAILED sequence=%lu attempt=%u state=%d\n",
                  static_cast<unsigned long>(reading.sequence), attempt,
                  mqttClient.state());
    if (attempt < kPublishRetries) {
      delay(kPublishBackoffMs * attempt);
      if (!mqttClient.connected()) {
        connectMqtt();
      }
    }
  }
  return false;
}

void flushPendingReadings() {
  while (pendingCount > 0) {
    PendingReading &reading = pendingReadings[pendingHead];
    if (!publishQueuedReading(reading)) {
      Serial.printf("MQTT_READING_RETAINED sequence=%lu queue_depth=%u\n",
                    static_cast<unsigned long>(reading.sequence), pendingCount);
      return;
    }
    pendingHead = (pendingHead + 1) % kPendingQueueDepth;
    --pendingCount;
  }
}

void sampleAndPublish() {
  JsonDocument document;
  document["schema_version"] = "1.0";
  document["controller_id"] = kControllerId;
  const uint32_t readingSequence = sequenceNumber++;
  document["sequence"] = readingSequence;
  document["captured_at_utc"] = utcTimestamp();
  document["firmware_version"] = kFirmwareVersion;
  document["wifi_rssi_dbm"] = WiFi.RSSI();
  JsonArray bins = document["bins"].to<JsonArray>();
  for (uint8_t channel = 0; channel < kBinCount; ++channel) {
    const float distanceMm = readUltrasonicMedianMm(channel);
    const uint16_t pressureAdc = readPressureMedianAdc(channel);
    JsonObject row = bins.add<JsonObject>();
    row["channel"] = channel + 1;
    row["bin_id"] = kBinIds[channel];
    if (isnan(distanceMm)) {
      row["ultrasonic_distance_mm"] = nullptr;
    } else {
      row["ultrasonic_distance_mm"] = distanceMm;
    }
    row["pressure_adc"] = pressureAdc;
  }
  const size_t measuredLength = measureJson(document);
  if (measuredLength == 0 || measuredLength >= kPayloadCapacity) {
    Serial.printf("TELEMETRY_BUFFER_FAILED sequence=%lu measured=%u capacity=%u\n",
                  static_cast<unsigned long>(readingSequence),
                  static_cast<unsigned int>(measuredLength),
                  static_cast<unsigned int>(kPayloadCapacity));
    return;
  }
  char payload[kPayloadCapacity];
  const size_t serializedLength = serializeJson(document, payload, sizeof(payload));
  if (serializedLength != measuredLength || serializedLength >= sizeof(payload)) {
    Serial.printf("TELEMETRY_SERIALIZATION_FAILED sequence=%lu measured=%u serialized=%u\n",
                  static_cast<unsigned long>(readingSequence),
                  static_cast<unsigned int>(measuredLength),
                  static_cast<unsigned int>(serializedLength));
    return;
  }
  if (enqueueReading(payload, serializedLength, readingSequence)) {
    flushPendingReadings();
  }
}
}  // namespace

void setup() {
  Serial.begin(115200);
  analogReadResolution(12);
  for (uint8_t channel = 0; channel < kBinCount; ++channel) {
    pinMode(kTrigPins[channel], OUTPUT);
    pinMode(kEchoPins[channel], INPUT);
    pinMode(kPressurePins[channel], INPUT);
  }
  connectWifi();
  configTime(0, 0, "pool.ntp.org", "time.google.com");
  mqttClient.setServer(BINSIGHT_MQTT_HOST, BINSIGHT_MQTT_PORT);
  if (!mqttClient.setBufferSize(kMqttBufferSize)) {
    Serial.printf("MQTT_BUFFER_CONFIGURATION_FAILED requested=%u\n",
                  static_cast<unsigned int>(kMqttBufferSize));
  } else {
    Serial.printf("MQTT_BUFFER_READY bytes=%u\n",
                  static_cast<unsigned int>(kMqttBufferSize));
  }
  connectMqtt();
  sampleAndPublish();
  lastPublishMs = millis();
}

void loop() {
  if (WiFi.status() != WL_CONNECTED) {
    connectWifi();
  }
  if (WiFi.status() == WL_CONNECTED && connectMqtt()) {
    mqttClient.loop();
    flushPendingReadings();
  }
  if (millis() - lastPublishMs >= kPublishIntervalMs) {
    sampleAndPublish();
    lastPublishMs = millis();
  }
  delay(10);
}
