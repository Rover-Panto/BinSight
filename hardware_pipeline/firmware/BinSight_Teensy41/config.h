#pragma once
/*
 * config.h — BinSight Teensy 4.1 firmware
 * -----------------------------------------------------------------------
 * Central configuration: pin map, RTOS task priorities/periods, sensor
 * thresholds, and network settings. Keeping these in one file means the
 * competition team can retune the system (different bin geometry, a
 * different Wi-Fi/Ethernet setup, etc.) without touching task logic.
 * -----------------------------------------------------------------------
 */

#include <Arduino.h>

// ============================================================
// IDENTITY
// ============================================================
#define BIN_ID                  "bin_01"     // must match ^bin_[0-9]+$ on the cloud side
#define FIRMWARE_VERSION        "1.0.0"

// ============================================================
// PIN MAP
// ============================================================
// Ultrasonic sensor — fill-level sensor, mounted at the lid, facing
// straight down at the waste surface.
//
// [Changed 2026-08-28] This bin now uses a SINGLE ultrasonic sensor per
// bin (previously two — see "Known changes" in README.md). The former
// US2_TRIG_PIN (4) / US2_ECHO_PIN (5) are no longer defined and are free
// for other use; the cross-sensor disagreement check that used to feed
// confidence_flag is gone too (see sensors.cpp's computeConfidenceFlag).
#define US1_TRIG_PIN             2
#define US1_ECHO_PIN             3

// Push buttons — manual waste-type injection (there is no load cell, so a
// human operator classifies what was just dropped in during testing/demo).
#define BTN_HEAVY_WET_PIN         6   // e.g. food waste, liquids
#define BTN_DRY_RECYCLABLE_PIN    7   // e.g. paper, plastic, cardboard
#define BTN_CALIBRATE_RESET_PIN   8   // long-press: re-zero "empty bin" baseline

// Status LED (onboard or external) — reflects overall system health.
#define STATUS_LED_PIN            13

// ============================================================
// BIN GEOMETRY (for fill_pct calculation)
// ============================================================
#define BIN_EMPTY_DISTANCE_CM     80.0f   // ultrasonic distance reading when bin is empty
#define BIN_FULL_DISTANCE_CM      8.0f    // ultrasonic distance reading when bin is full to the brim
#define US_VALID_MIN_CM           2.0f    // HC-SR04 datasheet minimum
#define US_VALID_MAX_CM           400.0f  // HC-SR04 datasheet maximum
// [Removed 2026-08-28] US_SENSOR_DISAGREEMENT_CM no longer applies —
// there's only one ultrasonic sensor now, so there's nothing to disagree
// with. See computeConfidenceFlag() in sensors.cpp for the new definition.

// ============================================================
// PSEUDO-DENSITY MODEL
// ============================================================
// Baseline "density" units are an arbitrary relative scale (NOT kg/L —
// clearly labeled as an estimate/proxy throughout, since there is no load
// cell). Button presses bias the baseline; fast fill-rate deltas nudge it
// further, simulating compaction / heavy wet waste arriving quickly.
#define DENSITY_BASELINE_UNCLASSIFIED   1.2f
#define DENSITY_BASELINE_HEAVY_WET      3.0f
#define DENSITY_BASELINE_DRY_RECYCLABLE 0.6f
#define DENSITY_FILL_RATE_GAIN          0.08f   // scales %/s fill-rate delta into the estimate
#define DENSITY_CLASSIFICATION_HOLD_MS  8000UL  // how long a button press biases the estimate

// ============================================================
// RTOS TASK PRIORITIES  (higher number == higher priority)
// ============================================================
#define TASK_SENSE_PRIORITY      3   // Task 1 — High:   local sensing & acquisition
#define TASK_FILTER_PRIORITY     2   // Task 2 — Medium: filtering & packaging
#define TASK_COMM_PRIORITY       1   // Task 3 — Low:    secure transmission

// Stack sizes (words, not bytes, per FreeRTOS convention)
#define TASK_SENSE_STACK_WORDS   256
#define TASK_FILTER_STACK_WORDS  384   // ArduinoJson serialization needs headroom
#define TASK_COMM_STACK_WORDS    768   // TLS/HTTP client needs the most headroom

// Task periods
#define TASK_SENSE_PERIOD_MS     200    // 5 Hz acquisition
#define TASK_FILTER_PERIOD_MS    500    // packaging cadence (drains the raw queue)
#define TASK_COMM_PERIOD_MS      2000   // transmission cadence (drains the packet queue)

// Inter-task queues
#define RAW_QUEUE_LENGTH          20    // RawReading items buffered between Task1 -> Task2
#define PACKET_QUEUE_LENGTH       10    // PackagedReading items buffered between Task2 -> Task3

// ============================================================
// FILTERING
// ============================================================
#define MOVING_AVERAGE_WINDOW      5    // samples, applied to fill_pct and density
#define MAX_FILL_PCT_JUMP_PER_SAMPLE 25.0f // sanity clamp: reject implausible single-sample jumps

// ============================================================
// TRANSPORT — USB-Serial bridge (see network.cpp / network.h)
// ============================================================
// No Ethernet or WiFi hardware is assumed (the parts list is Teensy 4.1,
// 2x ultrasonic, 3x buttons, breadboard, jumper wires only). Task 3
// streams each packaged JSON reading over the USB serial connection;
// tools/serial_bridge.py on the laptop reads it and forwards to the
// cloud backend over HTTP. The API key therefore lives in the bridge
// script's config, NOT on the MCU. If an Ethernet/WiFi module is added
// later, only network.h/network.cpp need to change.
#define NETWORK_RETRY_BACKOFF_MS    500
#define NETWORK_MAX_RETRIES         3

// ============================================================
// ESP32 GATEWAY LINK (added 2026-08-28) — optional second transport
// ============================================================
// A separate ESP32 dev board, wired to the Teensy over UART, that owns
// all Wi-Fi/HTTP communication with the cloud backend (see esp_link.h/
// .cpp and firmware/BinSight_ESP32_Gateway/). This is purely ADDITIVE:
// the USB-serial path above (network.h/.cpp, tools/serial_bridge.py)
// is completely unchanged and keeps working with or without the ESP32
// present — Task 3 just tries both transports independently.
//
// Uses Serial3 (RX3 = pin 15, TX3 = pin 14) so it doesn't collide with
// the button pins already on Serial2's pins (7/8, see PIN MAP above).
// See SETUP_AND_WIRING_GUIDE.md Part D for the Teensy<->ESP32 wiring.
#define ESP_LINK_SERIAL           Serial3
#define ESP_LINK_BAUD             115200
#define ESP_LINK_ACK_WAIT_MS      500       // how long to wait for the ESP32's ACK/NACK/DOWN reply per packet
#define ESP_LINK_ACK_TIMEOUT_MS   10000UL   // no reply from the ESP32 for this long -> EspLink::isConnected() reports down

// ============================================================
// DEBUG
// ============================================================
#define DEBUG_SERIAL_PRINTS         1   // 1 = Task 1 prints each sample for bring-up/testing
