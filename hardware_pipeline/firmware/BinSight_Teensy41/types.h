#pragma once
/*
 * types.h — shared data structures passed between RTOS tasks via queues.
 *
 * Design note: FreeRTOS queues copy PoD (plain-old-data) structs by value,
 * which is exactly what we want here — Task 1 and Task 2 must never share
 * mutable memory directly (that would need a mutex and reintroduce
 * priority-inversion risk). Keep these structs fixed-size and free of
 * pointers/heap allocation so queue copies stay cheap and deterministic.
 */

#include <Arduino.h>

// Waste-type classification injected by the human operator via push button.
enum WasteTypeHint : uint8_t {
  WASTE_UNCLASSIFIED     = 0,
  WASTE_HEAVY_WET        = 1,
  WASTE_DRY_RECYCLABLE   = 2,
};

// Output of Task 1 (Sensing). One per acquisition cycle.
struct RawReading {
  uint32_t     millis_timestamp;   // millis() at capture, converted to epoch later
  float        us1_distance_cm;    // -1.0f if timed out / invalid
  float        us2_distance_cm;    // -1.0f if timed out / invalid
  float        fill_pct_raw;       // derived from us1 (primary), before filtering
  float        estimated_density;  // pseudo-density proxy, before filtering
  uint8_t      confidence_flag;    // 1 = good reading, 0 = noisy/blocked/disagreement
  WasteTypeHint waste_hint;        // latest active button classification
};

// Output of Task 2 (Filtering & Packaging). Ready-to-transmit payload.
struct PackagedReading {
  char     json[256];   // serialized JSON matching the cloud ingestion schema
  size_t   length;
  uint32_t sequence_id;  // monotonically increasing, used for retry/idempotency
};

// Result of a transmission attempt, used for local diagnostics/status LED.
enum class TxResult : uint8_t {
  TX_OK = 0,
  TX_NETWORK_DOWN,
  TX_TIMEOUT,
  TX_SERVER_REJECTED,
};
