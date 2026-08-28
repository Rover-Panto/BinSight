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

// Push button — bin re-calibration only.
// [Removed 2026-08-28] The two manual waste-type buttons (heavy/wet on
// pin 6, dry/recyclable on pin 7) and the density baseline they drove are
// gone — see the PSEUDO-DENSITY MODEL section below for why, and
// sensors.cpp/estimateDensity() for the resulting single-baseline model.
// Pins 6 and 7 are now free for other use (e.g. a future vision-model
// wet/dry signal, if that's how that gets wired in).
#define BTN_CALIBRATE_RESET_PIN   8   // long-press: re-zero "empty bin" baseline

// Status LED (onboard or external) — reflects overall system health.
#define STATUS_LED_PIN            13

// ============================================================
// BIN GEOMETRY (for fill_pct calculation)
// ============================================================
// [Changed 2026-08-28, revised same day] Sensor is mounted ~30cm above
// the empty bin's bottom (raised from the earlier ~8cm/10cm-tall-bin
// setup — see git history / PR comments for that first pass). "Full to
// the brim" is set to 4cm: close enough to register as genuinely full,
// but with a 2cm margin above the HC-SR04's ~2.0cm datasheet minimum
// (US_VALID_MIN_CM below), which avoids the near-field reliability risk
// the previous 2.5cm value had (readings get less stable very close to
// the sensor). distanceToFillPct() in sensors.cpp needs no changes for
// this — it's a generic linear map between these two constants, so
// re-tuning bin geometry is always just a constants change here.
// Re-measure and update both values for any different physical bin;
// don't assume they transfer.
#define BIN_EMPTY_DISTANCE_CM     30.0f   // ultrasonic distance reading when bin is empty
#define BIN_FULL_DISTANCE_CM      4.0f    // ultrasonic distance reading when bin is full to the brim
#define US_VALID_MIN_CM           2.0f    // HC-SR04 datasheet minimum
#define US_VALID_MAX_CM           400.0f  // HC-SR04 datasheet maximum

// [Added 2026-08-28] Bin cross-section, used only by estimateWeightProxy()
// in sensors.cpp to convert the sensed fill height into a volume for the
// weight-proxy estimate. Measured bin: round, 22cm diameter, ~35cm total
// physical height. Assumes a ROUND bin (area = pi * r^2) — if your bin is
// rectangular, change the area formula in estimateWeightProxy() to
// width * depth instead, and swap this for BIN_WIDTH_CM/BIN_DEPTH_CM.
//
// Note the 35cm total physical height is intentionally NOT used for the
// fill-height-to-volume conversion — that reuses BIN_EMPTY_DISTANCE_CM /
// BIN_FULL_DISTANCE_CM above (the sensor's own calibrated span, currently
// 30cm/4cm -> 26cm of usable range) so "100% full" means the same thing
// for the weight estimate as it already does for fill_pct, rather than
// introducing a second height reference that could quietly disagree with
// the first.
#define BIN_DIAMETER_CM           22.0f

// ============================================================
// PSEUDO-DENSITY MODEL
// ============================================================
// Baseline "density" units are an arbitrary relative scale (NOT kg/L —
// clearly labeled as an estimate/proxy throughout, since there is no load
// cell). Fast fill-rate deltas nudge the baseline upward, simulating
// compaction / heavy waste arriving quickly.
//
// [Removed 2026-08-28] The manual heavy-wet / dry-recyclable button
// classification (and its two separate baselines) is gone — estimateDensity()
// now always starts from the single DENSITY_BASELINE below rather than
// picking a baseline by button-injected waste type. If/when a real signal
// (e.g. a vision-model wet/dry classification) replaces this, wire its
// output back into estimateDensity() the same way the button hint used to
// feed it, rather than re-adding buttons.
#define DENSITY_BASELINE                1.2f
#define DENSITY_FILL_RATE_GAIN          0.08f   // scales %/s fill-rate delta into the estimate

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
// No Ethernet or WiFi hardware is required for this path (the parts list
// is Teensy 4.1, 1x ultrasonic sensor, 1x button [changed 2026-08-28 from
// 3x — see PIN MAP above], breadboard, jumper wires; an optional ESP32
// Wi-Fi gateway is available separately, see
// below). Task 3
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
// the calibrate button already on Serial2's pin (8, see PIN MAP above).
// See SETUP_AND_WIRING_GUIDE.md Part D for the Teensy<->ESP32 wiring.
#define ESP_LINK_SERIAL           Serial3
#define ESP_LINK_BAUD             115200
#define ESP_LINK_ACK_WAIT_MS      500       // how long to wait for the ESP32's ACK/NACK/DOWN reply per packet
#define ESP_LINK_ACK_TIMEOUT_MS   10000UL   // no reply from the ESP32 for this long -> EspLink::isConnected() reports down

// ============================================================
// DEBUG
// ============================================================
#define DEBUG_SERIAL_PRINTS         1   // 1 = Task 1 prints each sample for bring-up/testing
