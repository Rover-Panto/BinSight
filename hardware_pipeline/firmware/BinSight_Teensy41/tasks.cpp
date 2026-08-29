#include "tasks.h"
#include "config.h"
#include "sensors.h"
#include "filters.h"
#include "network.h"
#include "esp_link.h"   // [Added 2026-08-28] optional ESP32 Wi-Fi gateway path, see esp_link.h

#include <ArduinoJson.h>   // Arduino Library Manager: "ArduinoJson" by Benoit Blanchon
#include <TimeLib.h>       // Arduino Library Manager: "Time" — wall-clock timestamps

QueueHandle_t g_rawDataQueue = nullptr;
QueueHandle_t g_packetQueue = nullptr;
SemaphoreHandle_t g_serialMutex = nullptr;

void Tasks_InitIPC() {
  g_rawDataQueue = xQueueCreate(RAW_QUEUE_LENGTH, sizeof(RawReading));
  g_packetQueue  = xQueueCreate(PACKET_QUEUE_LENGTH, sizeof(PackagedReading));
  g_serialMutex  = xSemaphoreCreateMutex();

  configASSERT(g_rawDataQueue != nullptr);
  configASSERT(g_packetQueue != nullptr);
  configASSERT(g_serialMutex != nullptr);
}

static void debugPrint(const char *msg) {
  if (xSemaphoreTake(g_serialMutex, pdMS_TO_TICKS(50)) == pdTRUE) {
    Serial.println(msg);
    xSemaphoreGive(g_serialMutex);
  }
}

// =====================================================================
// TASK 1 — Local Sensing & Acquisition (HIGH PRIORITY)
// =====================================================================
// Runs every TASK_SENSE_PERIOD_MS on a fixed schedule (vTaskDelayUntil,
// not vTaskDelay, so drift doesn't accumulate). This task must be short
// and deterministic: no network I/O, no dynamic allocation, no long
// blocking calls beyond the bounded pulseIn() timeout inside the
// ultrasonic read. Being the highest priority, it preempts Task 2/3
// immediately when it becomes ready, guaranteeing acquisition timing
// integrity even while a transmission is in flight.
void Task1_Sensing(void *pvParameters) {
  (void)pvParameters;
  TickType_t lastWake = xTaskGetTickCount();

  // [Removed 2026-08-28] lastFillPct / lastSampleMs — these only existed
  // to compute a fill-rate delta for estimateDensity(), which is gone
  // (see config.h's PSEUDO-DENSITY MODEL removal note). Nothing else in
  // Task 1 needs them.

  for (;;) {
    // [Changed 2026-08-28] Single ultrasonic sensor per bin now — the
    // second read (US2_TRIG_PIN/US2_ECHO_PIN) and the two-sensor
    // confidence cross-check are gone. computeConfidenceFlag() now takes
    // just the one reading; see sensors.h/sensors.cpp for what that
    // trades away (no more detecting a plausible-but-wrong single-sensor
    // reading, only outright timeout/out-of-range).
    float us1 = Sensors::readUltrasonicCm(US1_TRIG_PIN, US1_ECHO_PIN);

    uint8_t confidence = Sensors::computeConfidenceFlag(us1);
    float fillPct = Sensors::distanceToFillPct(us1);
    uint32_t now = millis();

    // [Removed 2026-08-28] WasteTypeHint hint = Sensors::pollWasteClassification()
    // and float density = Sensors::estimateDensity(...) — this bin no
    // longer estimates a density (or weight) proxy at all. See config.h's
    // PSEUDO-DENSITY MODEL removal note.

#if DEBUG_SERIAL_PRINTS
    // Verbose per-sample bring-up/testing output. Written through the
    // shared serial mutex so it never interleaves with Task 3's framed
    // BINSIGHT: lines. Safe to leave on for the demo (set to 0 in
    // config.h to silence it once wiring is validated).
    // [Removed 2026-08-28] "density=" and "hint=" fields — both gone,
    // see above.
    if (xSemaphoreTake(g_serialMutex, 0) == pdTRUE) {
      Serial.print("[Task1] US1=");  Serial.print(us1, 1);
      Serial.print("cm fill=");        Serial.print(fillPct, 1);
      Serial.print("% conf=");           Serial.println(confidence);
      xSemaphoreGive(g_serialMutex);
    }
#endif

    if (Sensors::pollCalibrationRequest()) {
      // Operator requested re-baseline: treat current (assumed-empty) bin
      // reading as the new "empty" distance. Kept local to Task 1 since it
      // only mutates a runtime-tunable value used by distanceToFillPct().
      debugPrint("[Task1] Calibration requested — re-zeroing empty baseline");
    }

    RawReading reading{};
    reading.millis_timestamp  = now;
    reading.us1_distance_cm   = us1;
    // [Removed 2026-08-28] reading.us2_distance_cm — field no longer
    // exists on RawReading (types.h), single-sensor now.
    reading.fill_pct_raw      = fillPct;
    reading.confidence_flag   = confidence;
    // [Removed 2026-08-28] reading.waste_hint and reading.estimated_density
    // — neither field exists on RawReading (types.h) any more.

    // Non-blocking send: if Task 2 has fallen behind and the queue is
    // full, drop the oldest raw sample rather than ever blocking Task 1.
    if (xQueueSend(g_rawDataQueue, &reading, 0) != pdTRUE) {
      RawReading discard;
      xQueueReceive(g_rawDataQueue, &discard, 0);
      xQueueSend(g_rawDataQueue, &reading, 0);
    }

    digitalWrite(STATUS_LED_PIN, confidence ? arduino::HIGH : arduino::LOW);

    vTaskDelayUntil(&lastWake, pdMS_TO_TICKS(TASK_SENSE_PERIOD_MS));
  }
}

// =====================================================================
// TASK 2 — Data Filtering & Packaging (MEDIUM PRIORITY)
// =====================================================================
// Drains g_rawDataQueue, applies moving-average + sanity filtering, and
// packages the smoothed result into the standardized JSON schema with a
// precise timestamp and bin_id. Runs at medium priority: it preempts
// Task 3 (so packaging never starves behind a slow network call) but
// yields to Task 1 (so acquisition timing is never disturbed).
void Task2_FilterAndPackage(void *pvParameters) {
  (void)pvParameters;
  TickType_t lastWake = xTaskGetTickCount();

  MovingAverageFilter fillFilter;
  // [Removed 2026-08-28] MovingAverageFilter densityFilter — no more
  // estimated_density to filter. See config.h's PSEUDO-DENSITY MODEL
  // removal note.
  uint32_t sequenceId = 0;

  for (;;) {
    RawReading raw;
    // Drain everything currently queued this cycle (bounded by queue length).
    while (xQueueReceive(g_rawDataQueue, &raw, 0) == pdTRUE) {
      // [Fixed 2026-08-28] The invalid-reading branch used to call
      // fillFilter.process(0.0f, ...) — despite the old comment claiming
      // to "hold last good value", that actually fed a fabricated 0.0f
      // sample into the filter's internal state (lastAccepted_, and the
      // circular buffer), which could corrupt the running average and,
      // combined with the freeze bug in filters.h, permanently lock the
      // filter at zero after a run of invalid readings. lastOutput() below
      // returns the previous smoothed value without touching filter state
      // at all, so an invalid reading now has no side effect on the filter.
      float smoothedFill = (raw.fill_pct_raw >= 0.0f)
          ? fillFilter.process(raw.fill_pct_raw, MAX_FILL_PCT_JUMP_PER_SAMPLE)
          : fillFilter.lastOutput();  // hold last good value (no fabricated sample)
      // [Removed 2026-08-28] smoothedDensity / weightProxy — estimated_density
      // and estimated_weight_proxy are both gone. See config.h's
      // PSEUDO-DENSITY MODEL removal note for the full picture.

      // Wall-clock timestamp: TimeLib's now() must be synced at boot
      // (e.g. via NTP once the network is up, or a battery-backed RTC —
      // see setup() in the .ino). Formatted as ISO-8601 UTC to match the
      // cloud ingestion schema exactly.
      char timestampBuf[25];
      snprintf(timestampBuf, sizeof(timestampBuf), "%04d-%02d-%02dT%02d:%02d:%02dZ",
               year(), month(), day(), hour(), minute(), second());

      // [Removed 2026-08-28] estimated_density / estimated_weight_proxy
      // fields — both gone from the payload. See config.h's
      // PSEUDO-DENSITY MODEL removal note.
      //
      // [Fixed 2026-08-28] fill_pct now goes through a fixed char buffer +
      // snprintf instead of Arduino's String class. This was one of the
      // contributors to Task 2 ("Filter") overflowing its stack on real
      // hardware — each String(...) temporary pulls in String's
      // heap-allocating float-formatting path, which is both slower and
      // less deterministic than a fixed buffer inside an RTOS task, and
      // adds meaningfully to peak stack usage when several are live at
      // once (this payload used to build three of them). snprintf's
      // "%.1f" output is byte-identical to String(float, 1), so this is a
      // behavior-preserving swap. See config.h's TASK_FILTER_STACK_WORDS
      // comment for the rest of the stack-overflow fix.
      char fillPctBuf[12];
      snprintf(fillPctBuf, sizeof(fillPctBuf), "%.1f", smoothedFill);

      StaticJsonDocument<256> doc;
      doc["timestamp"]        = timestampBuf;
      doc["bin_id"]            = BIN_ID;
      doc["fill_pct"]          = serialized(fillPctBuf);
      doc["confidence_flag"]   = raw.confidence_flag;

      PackagedReading packet{};
      packet.length = serializeJson(doc, packet.json, sizeof(packet.json));
      packet.sequence_id = sequenceId++;

      if (xQueueSend(g_packetQueue, &packet, 0) != pdTRUE) {
        // Comms is falling behind the filter stage — drop the oldest
        // packet. Losing one historical sample is preferable to Task 2
        // ever blocking (which would back-pressure into Task 1's queue).
        PackagedReading discard;
        xQueueReceive(g_packetQueue, &discard, 0);
        xQueueSend(g_packetQueue, &packet, 0);
      }
    }

    vTaskDelayUntil(&lastWake, pdMS_TO_TICKS(TASK_FILTER_PERIOD_MS));
  }
}

// =====================================================================
// TASK 3 — Secure Communication / Transmission Handler (LOW PRIORITY)
// =====================================================================
// The only task allowed to block on I/O. Runs at the lowest priority so a
// slow/degraded network link never steals CPU time from sensing or
// packaging — it only runs when Task 1 and Task 2 have no work pending.
//
// [Added 2026-08-28] Each packet is now sent down TWO independent,
// best-effort transports: the original USB-serial path (network.h, for
// tools/serial_bridge.py on a laptop) and the new ESP32 Wi-Fi gateway
// path (esp_link.h). They share no state and one failing has no effect
// on the other — if only one of the two is actually present at demo
// time (e.g. ESP32 not wired up yet, or no laptop plugged in), the
// packet still gets through via whichever one is. This is why Task 3 is
// the only task allowed to block: worst case, both transports exhaust
// NETWORK_MAX_RETRIES with full backoff one after another, which can
// take several seconds — acceptable here because it only delays Task 3's
// own queue (bounded, drop-oldest-when-full, per Task 2 above), and can
// never preempt or stall Task 1/Task 2's real-time sensing/filtering.
void Task3_Transmit(void *pvParameters) {
  (void)pvParameters;
  TickType_t lastWake = xTaskGetTickCount();

  uint8_t usbConsecutiveFailures = 0;
  uint8_t espConsecutiveFailures = 0;

  for (;;) {
    PackagedReading packet;
    if (xQueueReceive(g_packetQueue, &packet, pdMS_TO_TICKS(TASK_COMM_PERIOD_MS)) == pdTRUE) {
      // -- Path 1: USB-serial bridge (unchanged from before) --
      TxResult usbResult = TxResult::TX_NETWORK_DOWN;
      for (uint8_t attempt = 0; attempt < NETWORK_MAX_RETRIES; attempt++) {
        usbResult = Network::sendPacket(packet);
        if (usbResult == TxResult::TX_OK) break;
        vTaskDelay(pdMS_TO_TICKS(NETWORK_RETRY_BACKOFF_MS * (attempt + 1)));  // linear backoff
      }
      if (usbResult == TxResult::TX_OK) {
        usbConsecutiveFailures = 0;
      } else {
        usbConsecutiveFailures++;
        debugPrint("[Task3] USB-serial transmission failed after retries");
      }

      // -- Path 2: ESP32 Wi-Fi gateway (new) --
      TxResult espResult = TxResult::TX_NETWORK_DOWN;
      for (uint8_t attempt = 0; attempt < NETWORK_MAX_RETRIES; attempt++) {
        espResult = EspLink::sendPacket(packet);
        if (espResult == TxResult::TX_OK) break;
        vTaskDelay(pdMS_TO_TICKS(NETWORK_RETRY_BACKOFF_MS * (attempt + 1)));
      }
      if (espResult == TxResult::TX_OK) {
        espConsecutiveFailures = 0;
      } else {
        espConsecutiveFailures++;
        // Expected/benign if no ESP32 is wired up yet -- only worth
        // investigating if it persists after the ESP32 is connected and
        // flashed with BinSight_ESP32_Gateway.ino.
        debugPrint("[Task3] ESP32 gateway transmission failed after retries");
      }
    }

    vTaskDelayUntil(&lastWake, pdMS_TO_TICKS(TASK_COMM_PERIOD_MS));
  }
}
