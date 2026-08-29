// esp_link.cpp — [Added 2026-08-28] see esp_link.h for the full design note.
#include "esp_link.h"
#include "config.h"
#include <string.h>

namespace EspLink {

// Same framing prefix as network.cpp/serial_bridge.py — the ESP32 gateway
// sketch expects this exact prefix on the UART link too.
static const char *FRAME_PREFIX = "BINSIGHT:";

// millis() of the last reply we got from the ESP32 (0 = none yet).
static uint32_t s_lastReplyMillis = 0;

bool begin() {
  ESP_LINK_SERIAL.begin(ESP_LINK_BAUD);
  return true;
}

bool isConnected() {
  if (s_lastReplyMillis == 0) return true;  // no data yet — give it the benefit of the doubt at boot
  return (millis() - s_lastReplyMillis) < ESP_LINK_ACK_TIMEOUT_MS;
}

// Reads one '\n'-terminated line from ESP_LINK_SERIAL, waiting up to
// timeoutMs total. Returns true and null-terminates buf if a full line
// arrived in time; false (with whatever partial bytes arrived so far,
// still null-terminated) on timeout.
static bool readReplyLine(char *buf, size_t bufLen, uint32_t timeoutMs) {
  uint32_t start = millis();
  size_t len = 0;
  while (millis() - start < timeoutMs) {
    while (ESP_LINK_SERIAL.available()) {
      char c = (char)ESP_LINK_SERIAL.read();
      if (c == '\n') {
        buf[len] = '\0';
        return len > 0;
      }
      if (len < bufLen - 1) buf[len++] = c;
    }
  }
  buf[len] = '\0';
  return false;
}

TxResult sendPacket(const PackagedReading &packet) {
  ESP_LINK_SERIAL.print(FRAME_PREFIX);
  ESP_LINK_SERIAL.write((const uint8_t *)packet.json, packet.length);
  ESP_LINK_SERIAL.println();

  char reply[32];
  if (!readReplyLine(reply, sizeof(reply), ESP_LINK_ACK_WAIT_MS)) {
    // No reply at all -- ESP32 not wired up, not flashed with the gateway
    // sketch yet, or busy long enough to miss the window. Distinct from
    // "ESP32 replied DOWN" (below) because we don't even know it's there.
    return TxResult::TX_TIMEOUT;
  }
  s_lastReplyMillis = millis();

  if (strncmp(reply, "ACK:", 4) == 0) {
    return TxResult::TX_OK;
  }
  if (strncmp(reply, "NACK:", 5) == 0) {
    // ESP32 reached the cloud backend, but the backend rejected the
    // payload (bad API key, schema validation, etc.) -- retrying the
    // exact same bytes would just fail the same way again.
    return TxResult::TX_SERVER_REJECTED;
  }
  if (strncmp(reply, "DOWN:", 5) == 0) {
    // ESP32 is alive and talking over UART, but it couldn't reach the
    // cloud backend at all (Wi-Fi down, DNS failure, connection timeout).
    return TxResult::TX_NETWORK_DOWN;
  }
  // Got a reply but not one of the three known prefixes -- treat
  // conservatively as "down" rather than silently assuming success.
  return TxResult::TX_NETWORK_DOWN;
}

}  // namespace EspLink
