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

// Echo lines from 5 V ultrasonic modules require a divider/level shifter to 3.3 V.
constexpr uint8_t kTrigPins[kBinCount] = {16, 18, 25};
constexpr uint8_t kEchoPins[kBinCount] = {17, 19, 26};
constexpr uint8_t kPressurePins[kBinCount] = {32, 33, 34};
constexpr char const *kBinIds[kBinCount] = {"UGB-001", "UGB-002", "UGB-003"};

WiFiClient wifiClient;
PubSubClient mqttClient(wifiClient);
uint32_t sequenceNumber = 0;
uint32_t lastPublishMs = 0;

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
}

bool connectMqtt() {
  if (mqttClient.connected()) {
    return true;
  }
  if (BINSIGHT_MQTT_USERNAME[0] != '\0') {
    return mqttClient.connect(
        kControllerId, BINSIGHT_MQTT_USERNAME, BINSIGHT_MQTT_PASSWORD);
  }
  return mqttClient.connect(kControllerId);
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

void sampleAndPublish() {
  JsonDocument document;
  document["schema_version"] = "1.0";
  document["controller_id"] = kControllerId;
  document["sequence"] = sequenceNumber++;
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
  char payload[1536];
  const size_t length = serializeJson(document, payload, sizeof(payload));
  if (length == 0 || length >= sizeof(payload)) {
    Serial.println("Telemetry serialization failed");
    return;
  }
  if (!mqttClient.publish(kTopic, payload, false)) {
    Serial.println("MQTT publish failed");
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
  }
  if (millis() - lastPublishMs >= kPublishIntervalMs) {
    sampleAndPublish();
    lastPublishMs = millis();
  }
  delay(10);
}
