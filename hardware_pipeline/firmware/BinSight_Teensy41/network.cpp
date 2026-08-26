#include "network.h"
#include "config.h"

namespace Network {

// Line prefix the host-side bridge script filters on, so debug prints
// (which share the same Serial port) are never mistaken for telemetry.
// Keep this in sync with FRAME_PREFIX in tools/serial_bridge.py.
static const char *FRAME_PREFIX = "BINSIGHT:";

bool begin() {
  return true;  // Serial.begin() already ran in setup(); nothing else to init.
}

bool isConnected() {
  return (bool)Serial;  // true once the host has the USB CDC port open
}

TxResult sendPacket(const PackagedReading &packet) {
  if (!isConnected()) {
    return TxResult::TX_NETWORK_DOWN;
  }

  // Framed as: BINSIGHT:<json>\n
  Serial.print(FRAME_PREFIX);
  Serial.write((const uint8_t *)packet.json, packet.length);
  Serial.println();

  return TxResult::TX_OK;
}

}  // namespace Network
