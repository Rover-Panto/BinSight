#pragma once
/*
 * network.h — transmission handler used exclusively by Task 3
 * (low priority). Isolating all transport logic here means Task 1/Task 2
 * never block on I/O — if the transport stalls, only Task 3's queue
 * backs up (bounded by PACKET_QUEUE_LENGTH; oldest packets are dropped
 * once full, so acquisition/filtering are never starved).
 *
 * TRANSPORT: USB-Serial bridge (no Ethernet/WiFi hardware required).
 * The Teensy streams each packaged JSON reading, framed with a fixed
 * prefix, over its USB serial connection. A small Python script on the
 * laptop (tools/serial_bridge.py) reads those framed lines and forwards
 * them to the FastAPI cloud backend over HTTP, attaching the API key
 * there — the MCU itself never needs network credentials.
 *
 * This keeps the hardware exactly to the available parts list (Teensy
 * 4.1, 2x ultrasonic, 3x buttons, breadboard, jumper wires). If a PJRC
 * Ethernet kit or a WiFi module is added later, only this file's
 * implementation changes — Task 3's call site (Network::sendPacket)
 * stays identical, so the rest of the firmware is untouched.
 */

#include <Arduino.h>
#include "types.h"

namespace Network {

// Call once from setup(). Serial.begin() has already run by this point;
// this just confirms the framing/transport is ready.
bool begin();

// True if the USB serial connection is currently open on the host side.
bool isConnected();

// Writes one packaged reading to Serial, framed for tools/serial_bridge.py.
TxResult sendPacket(const PackagedReading &packet);

}  // namespace Network
