/*
 * BinSight_ESP32_Gateway.ino — [Added 2026-08-28]
 * =========================================================================
 * Wi-Fi/HTTP gateway for BinSight. Runs on a separate ESP32 dev board
 * wired to the Teensy 4.1 over UART — see esp_link.h/esp_link.cpp on the
 * Teensy side, and SETUP_AND_WIRING_GUIDE.md Part D for wiring.
 *
 * ROLE: this board owns ALL Wi-Fi/HTTP communication with the cloud
 * backend, per the "ESP module handles all Wi-Fi communications" design.
 * The Teensy never touches Wi-Fi credentials or the network stack at
 * all — it just writes the same BINSIGHT:<json> framed lines to this
 * board over UART that it already writes to USB for
 * tools/serial_bridge.py, and this board takes it from there.
 *
 * ADDITIVE, NOT A REPLACEMENT: the existing USB-serial + laptop bridge
 * (tools/serial_bridge.py) keeps working exactly as before, whether or
 * not this board is present. Same schema, same cloud endpoint, same
 * API key — this is just a second way for a reading to reach the
 * backend, useful once the demo is off a tethered laptop.
 *
 * DATA FLOW TO Kai's ROUTING SYSTEM: this sketch does not talk to the
 * routing system directly. It POSTs to the same
 * cloud_backend /api/v1/telemetry endpoint tools/serial_bridge.py already
 * uses; per docs/PROJECT_STATE.md / PR_REVIEW_2026-08-28.md, the routing
 * work reads bin state back out via the backend's existing GET endpoints
 * (/api/v1/bins/summary, /api/v1/telemetry/{bin_id}/history). If Kai's
 * routing system actually needs a different delivery mechanism (a direct
 * push, a different schema, a separate endpoint), that's a decision to
 * confirm with them before wiring this sketch to anything else -- ask
 * before assuming.
 *
 * PROTOCOL back to the Teensy (one line per received frame):
 *   ACK:<http-status>\n   -- cloud backend accepted the reading (2xx)
 *   NACK:<http-status>\n  -- cloud backend reachable but rejected it
 *                             (e.g. bad API key, schema validation)
 *   DOWN:<error-code>\n   -- couldn't reach the backend at all
 *                             (Wi-Fi down, DNS failure, timeout)
 *
 * REQUIRED LIBRARIES: WiFi and HTTPClient, both bundled with the ESP32
 * board package (Arduino IDE: Boards Manager -> "esp32" by Espressif
 * Systems -- install that first if the ESP32 board type isn't available
 * under Tools -> Board).
 *
 * SETUP:
 *   1. Copy esp_config.example.h -> esp_config.h in this same folder and
 *      fill in your Wi-Fi SSID/password, BINSIGHT_API_KEY (must match
 *      cloud_backend/.env exactly), and CLOUD_BACKEND_URL (your laptop's
 *      LAN IP, NOT localhost -- see esp_config.example.h for why).
 *   2. Wire the ESP32 to the Teensy 4.1 per SETUP_AND_WIRING_GUIDE.md
 *      Part D (Teensy Serial3 <-> ESP32 Serial2, shared ground, ESP32
 *      powered from its own USB cable, NOT from the Teensy).
 *   3. Tools -> Board -> select your ESP32 dev board (e.g. "ESP32 Dev
 *      Module"). Flash this sketch.
 *   4. Open the Serial Monitor at 115200 baud to watch Wi-Fi connect and
 *      each reading's ACK/NACK/DOWN status.
 * =========================================================================
 */

#include <WiFi.h>
#include <HTTPClient.h>
#include "esp_config.h"

// ---------------------------------------------------------------------
// UART link to the Teensy. Must match ESP_LINK_SERIAL/ESP_LINK_BAUD in
// the Teensy's config.h (default: Serial3, 115200). Default pins for
// ESP32's hardware Serial2 are GPIO16 (RX) / GPIO17 (TX) on most dev
// boards -- change below (and in SETUP_AND_WIRING_GUIDE.md Part D) if
// your board's Serial2 pins differ or are already in use.
// ---------------------------------------------------------------------
#define TEENSY_LINK_SERIAL   Serial2
#define TEENSY_LINK_BAUD     115200
#define TEENSY_LINK_RX_PIN   16
#define TEENSY_LINK_TX_PIN   17

static const char *FRAME_PREFIX = "BINSIGHT:";  // must match network.cpp/esp_link.cpp on the Teensy

// ---------------------------------------------------------------------
// Small in-RAM retry queue for readings that failed to send while Wi-Fi
// or the backend was down. Mirrors the on-disk queue added to
// tools/serial_bridge.py in the same review pass -- same idea (don't
// silently drop a reading just because the network hiccuped), sized to
// fit comfortably in the ESP32's RAM.
//
// NOTE: unlike the laptop bridge's on-disk queue, this one is NOT
// persisted across a reboot/power cycle -- a queued reading is lost if
// the ESP32 itself resets while it's still pending. Flagging this as a
// known tradeoff rather than fixing it silently: a LittleFS-backed
// version would survive a reset, at the cost of flash wear and more
// code. Worth adding if a reset-while-queued scenario turns out to
// matter for the demo -- ask before assuming which way to go here.
// ---------------------------------------------------------------------
#define PENDING_QUEUE_CAPACITY   20
static String s_pendingQueue[PENDING_QUEUE_CAPACITY];
static uint8_t s_pendingCount = 0;

static void enqueuePending(const String &json) {
  if (s_pendingCount >= PENDING_QUEUE_CAPACITY) {
    // Queue full -- drop the OLDEST entry to make room for the newest,
    // same "prefer recent data" tradeoff Task 2 makes on the Teensy side
    // when its own packet queue fills up.
    for (uint8_t i = 1; i < PENDING_QUEUE_CAPACITY; i++) s_pendingQueue[i - 1] = s_pendingQueue[i];
    s_pendingCount--;
  }
  s_pendingQueue[s_pendingCount++] = json;
}

// Attempts one HTTP POST of `json` to the cloud backend.
// Returns the HTTP status code on a real response, or a negative
// HTTPClient error code (see HTTPClient.h's HTTPC_ERROR_* constants) if
// the request never got a response at all (connection refused, DNS
// failure, timeout, etc.) -- or -999 if Wi-Fi itself isn't connected.
static int postReading(const String &json) {
  if (WiFi.status() != WL_CONNECTED) return -999;

  HTTPClient http;
  http.begin(String(CLOUD_BACKEND_URL) + "/api/v1/telemetry");
  http.addHeader("Content-Type", "application/json");
  http.addHeader("X-API-Key", BINSIGHT_API_KEY);
  http.setTimeout(5000);

  int result = http.POST(json);
  http.end();
  return result;
}

// Retries anything queued by an earlier failure, before handling a new
// frame from the Teensy -- same "retry before new work" ordering used in
// tools/serial_bridge.py's flush_pending().
static void flushPending() {
  if (s_pendingCount == 0) return;

  uint8_t stillPending = 0;
  for (uint8_t i = 0; i < s_pendingCount; i++) {
    int status = postReading(s_pendingQueue[i]);
    if (status < 0 || status >= 400) {
      s_pendingQueue[stillPending++] = s_pendingQueue[i];  // keep it, still failing
    }
  }
  if (stillPending < s_pendingCount) {
    Serial.printf("[gateway] flushed %d queued reading(s), %d still pending\n",
                  s_pendingCount - stillPending, stillPending);
  }
  s_pendingCount = stillPending;
}

// Non-blocking-ish reconnect: attempts a (re)connect with a bounded wait,
// then returns control to loop() either way, so this board stays
// responsive to the Teensy even while Wi-Fi is down or reconnecting.
static void ensureWifi() {
  if (WiFi.status() == WL_CONNECTED) return;

  Serial.println("[gateway] Wi-Fi not connected, (re)connecting...");
  WiFi.disconnect();
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  uint32_t start = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - start < 10000) {
    delay(250);
  }

  if (WiFi.status() == WL_CONNECTED) {
    Serial.print("[gateway] Wi-Fi connected, IP: ");
    Serial.println(WiFi.localIP());
  } else {
    Serial.println("[gateway] Wi-Fi connect attempt timed out, will retry next loop.");
  }
}

void setup() {
  Serial.begin(115200);  // USB, local debug logging only -- not the Teensy link
  TEENSY_LINK_SERIAL.begin(TEENSY_LINK_BAUD, SERIAL_8N1, TEENSY_LINK_RX_PIN, TEENSY_LINK_TX_PIN);

  Serial.println("=== BinSight ESP32 Gateway -- booting ===");
  Serial.print("Cloud backend: ");
  Serial.println(CLOUD_BACKEND_URL);

  WiFi.mode(WIFI_STA);
  ensureWifi();
}

void loop() {
  ensureWifi();
  flushPending();

  if (!TEENSY_LINK_SERIAL.available()) {
    return;
  }

  String line = TEENSY_LINK_SERIAL.readStringUntil('\n');
  line.trim();
  if (!line.startsWith(FRAME_PREFIX)) {
    return;  // not a telemetry frame -- shouldn't normally happen on this dedicated link
  }
  String json = line.substring(strlen(FRAME_PREFIX));

  int status = postReading(json);
  if (status >= 200 && status < 300) {
    TEENSY_LINK_SERIAL.print("ACK:");
    TEENSY_LINK_SERIAL.println(status);
  } else if (status >= 400) {
    // Reached the backend, but it rejected the payload. Retrying the
    // exact same bytes would just fail the same way again, so this is
    // reported back but NOT queued -- mirrors serial_bridge.py's
    // post_reading()/flush_pending() split between "network error,
    // retry" and "server said no, don't retry."
    TEENSY_LINK_SERIAL.print("NACK:");
    TEENSY_LINK_SERIAL.println(status);
    Serial.printf("[gateway] backend rejected reading (HTTP %d): %s\n", status, json.c_str());
  } else {
    // Never got a real response at all -- Wi-Fi down, DNS failure,
    // connection timeout, etc. Queue it for a retry on a future loop.
    TEENSY_LINK_SERIAL.print("DOWN:");
    TEENSY_LINK_SERIAL.println(status);
    Serial.printf("[gateway] could not reach backend (error %d), queuing for retry\n", status);
    enqueuePending(json);
  }
}
