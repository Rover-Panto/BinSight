#pragma once
/*
 * esp_link.h — [Added 2026-08-28] Teensy <-> ESP32 gateway transport.
 *
 * Used by Task 3 ALONGSIDE (not instead of) the existing USB-serial path
 * in network.h/network.cpp. That original path — Task 3 writes framed
 * JSON to USB, tools/serial_bridge.py on a laptop forwards it to the
 * cloud backend — is completely untouched by this file and keeps working
 * exactly as before, with or without an ESP32 wired up.
 *
 * TRANSPORT: hardware UART (ESP_LINK_SERIAL / config.h, default Serial3 —
 * RX3 = pin 15, TX3 = pin 14) to a separate ESP32 dev board. That board
 * runs its own sketch (firmware/BinSight_ESP32_Gateway/) which joins
 * Wi-Fi and POSTs each reading to the SAME cloud endpoint
 * tools/serial_bridge.py already uses — the ESP32 is a second, on-device
 * path to the same backend, not a new destination or a new schema.
 *
 * Why a separate file instead of extending network.h: network.h's own
 * header comment describes it as "the transport used exclusively by
 * Task 3" for the USB-serial bridge specifically, and callers elsewhere
 * (or future contributors) may reasonably assume Network::* only ever
 * means "the laptop bridge." Keeping this as its own namespace/module
 * means the two transports can never accidentally share state, and
 * either one can be deleted/disabled independently without touching the
 * other.
 *
 * Kept as an independent, best-effort path: if no ESP32 is wired up (or
 * it's wired up but not yet flashed with the gateway sketch), sendPacket()
 * simply times out waiting for a reply and reports TX_TIMEOUT — Task 3's
 * USB-serial path is entirely unaffected.
 *
 * Protocol (one line back from the ESP32 per packet sent to it — see
 * BinSight_ESP32_Gateway.ino for the sending side):
 *   "ACK:<http-status>\n"   -> cloud backend accepted it (2xx)      -> TX_OK
 *   "NACK:<http-status>\n"  -> cloud backend reachable but rejected -> TX_SERVER_REJECTED
 *   "DOWN:<reason>\n"       -> ESP32 couldn't reach the backend     -> TX_NETWORK_DOWN
 *   (nothing within ESP_LINK_ACK_WAIT_MS)                           -> TX_TIMEOUT
 */

#include <Arduino.h>
#include "types.h"

namespace EspLink {

// Starts the UART used to talk to the ESP32. Safe to call even if no
// ESP32 is physically connected yet — sendPacket() will just always
// time out until one is wired up and flashed.
bool begin();

// True if the ESP32 has replied (ACK, NACK, or DOWN — any of the three
// counts, since all of them mean the board itself is alive and talking)
// within the last ESP_LINK_ACK_TIMEOUT_MS. This says nothing about
// whether the ESP32 currently has Wi-Fi — only that the UART link to it
// is alive. Before the first reply ever arrives (e.g. right after boot)
// this optimistically returns true, matching Network::isConnected()'s
// "assume present until proven otherwise" behavior on the USB side.
bool isConnected();

// Writes one packaged reading to the ESP32 over UART, framed identically
// to the USB path (BINSIGHT:<json>), and blocks up to ESP_LINK_ACK_WAIT_MS
// waiting for the ESP32's ACK/NACK/DOWN reply. See the protocol note above.
TxResult sendPacket(const PackagedReading &packet);

}  // namespace EspLink
