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
// pin 6, dry/recyclable on pin 7) are gone. [Also removed 2026-08-28,
// same day] the density/weight-proxy estimate they used to bias is gone
// entirely too, not just their button input — see the PSEUDO-DENSITY
// MODEL section below. Pins 6 and 7 are now free for other use (e.g. a
// future vision-model wet/dry signal, if that's how that gets wired in).
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
//
// [Recalibrated 2026-08-29] The 30.0f empty-distance figure above was an
// estimate; the real demo bin (26cm tall, sensor flush-mounted 1cm below
// the inner lid surface) actually reads 25.7cm with no trash present.
// With the stale 30.0f baseline, an empty bin was computing to a false
// (30.0 - 25.7) / (30.0 - 4.0) * 100 ~= 16.4% instead of 0%. Updated to
// the measured value so an empty bin now reports 0% as expected.
#define BIN_EMPTY_DISTANCE_CM     25.7f   // ultrasonic distance reading when bin is empty (measured, 2026-08-29)
#define BIN_FULL_DISTANCE_CM      4.0f    // ultrasonic distance reading when bin is full to the brim
#define US_VALID_MIN_CM           2.0f    // HC-SR04 datasheet minimum
#define US_VALID_MAX_CM           400.0f  // HC-SR04 datasheet maximum

// [Removed 2026-08-28] BIN_DIAMETER_CM — existed only to convert fill
// height into a volume for estimateWeightProxy(). Removed along with the
// entire PSEUDO-DENSITY MODEL section below; see the README's "Known
// changes" entry for 2026-08-28 (density + weight-proxy removal).

// ============================================================
// [Removed 2026-08-28] PSEUDO-DENSITY MODEL
// ============================================================
// This entire section (DENSITY_BASELINE, DENSITY_FILL_RATE_GAIN) is gone —
// estimated_density and the estimated_weight_proxy computed from it have
// been removed from the firmware, cloud schema/model, and dashboard. The
// bin now reports fill_pct and confidence_flag only. See README.md's
// "Known changes" section for the full removal (and sensors.h/.cpp,
// tasks.cpp, and cloud_backend/app/{schemas,models,crud,config}.py for
// where the code used to live) if this needs to be reintroduced later —
// e.g. once a real signal (load cell, vision-model classification) exists
// to back it, rather than an unbacked engineering proxy.

// ============================================================
// RTOS TASK PRIORITIES  (higher number == higher priority)
// ============================================================
#define TASK_SENSE_PRIORITY      3   // Task 1 — High:   local sensing & acquisition
#define TASK_FILTER_PRIORITY     2   // Task 2 — Medium: filtering & packaging
#define TASK_COMM_PRIORITY       1   // Task 3 — Low:    secure transmission

// Stack sizes (words, not bytes, per FreeRTOS convention)
#define TASK_SENSE_STACK_WORDS   256
// [Fixed 2026-08-28] Bumped from 384 -> 512. The Filter task was hitting a
// genuine stack overflow on real hardware (Serial Monitor: "stack
// overflow: Filter"), most likely from ArduinoJson's StaticJsonDocument
// plus the full 256-byte PackagedReading::json buffer plus several
// Arduino String temporaries all live on this task's stack at once — a
// margin that got tighter each time a field was added to the payload
// (most recently estimated_weight_proxy). Since estimated_density and
// estimated_weight_proxy are removed as of this same change (see the
// PSEUDO-DENSITY MODEL removal above), the payload is smaller again and
// the String temporaries in Task2 have been replaced with fixed char
// buffers + snprintf (see tasks.cpp) — 512 is deliberately generous
// headroom on top of that, not a minimum. Teensy 4.1 has 1MB of RAM, so
// this costs nothing meaningful.
#define TASK_FILTER_STACK_WORDS  512
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
// [Changed 2026-08-28] "and density" removed from this comment — the
// density filter/field is gone, see the PSEUDO-DENSITY MODEL removal note
// above. MOVING_AVERAGE_WINDOW now applies to fill_pct only.
#define MOVING_AVERAGE_WINDOW      5    // samples, applied to fill_pct
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
