#include "sensors.h"
#include "config.h"
#include <Bounce2.h>   // Arduino Library Manager: "Bounce2" by Thomas O Fredericks

namespace Sensors {

static Bounce btnCalibrate;

// [Removed 2026-08-28] btnHeavyWet / btnDryRecyclable and the
// activeHint/hintExpiresAtMs state that tracked their classification —
// see config.h's PSEUDO-DENSITY MODEL section.

static uint32_t calibrateHeldSinceMs = 0;
static const uint32_t LONG_PRESS_MS = 2000;

void begin() {
  // [Changed 2026-08-28] US2_TRIG_PIN/US2_ECHO_PIN init removed — single
  // ultrasonic sensor per bin now, see config.h's PIN MAP comment.
  pinMode(US1_TRIG_PIN, OUTPUT);
  pinMode(US1_ECHO_PIN, INPUT);
  digitalWrite(US1_TRIG_PIN, LOW);

  pinMode(STATUS_LED_PIN, OUTPUT);

  // [Removed 2026-08-28] btnHeavyWet/btnDryRecyclable attach calls — see
  // config.h's PIN MAP comment.
  btnCalibrate.attach(BTN_CALIBRATE_RESET_PIN, INPUT_PULLUP);
  btnCalibrate.interval(15);
}

float readUltrasonicCm(uint8_t trigPin, uint8_t echoPin) {
  // Standard HC-SR04 pulse sequence.
  digitalWrite(trigPin, LOW);
  delayMicroseconds(2);
  digitalWrite(trigPin, HIGH);
  delayMicroseconds(10);
  digitalWrite(trigPin, LOW);

  // 25 ms timeout ~= 4.3 m round trip, comfortably above the 400 cm datasheet max.
  uint32_t durationUs = pulseIn(echoPin, HIGH, 25000UL);
  if (durationUs == 0) {
    return -1.0f;  // timeout: no echo, no obstacle detected in range
  }

  float distanceCm = (durationUs * 0.0343f) / 2.0f;  // speed of sound ~343 m/s
  if (distanceCm < US_VALID_MIN_CM || distanceCm > US_VALID_MAX_CM) {
    return -1.0f;
  }
  return distanceCm;
}

// [Removed 2026-08-28] pollWasteClassification() — polled the two
// heavy-wet/dry-recyclable buttons and tracked how long their
// classification stayed active. See config.h's PSEUDO-DENSITY MODEL
// section and estimateDensity() below for the single-baseline model that
// replaced it.

bool pollCalibrationRequest() {
  btnCalibrate.update();
  uint32_t now = millis();

  if (btnCalibrate.fell()) {
    calibrateHeldSinceMs = now;
  }
  if (btnCalibrate.read() == LOW && calibrateHeldSinceMs != 0 &&
      (now - calibrateHeldSinceMs) >= LONG_PRESS_MS) {
    calibrateHeldSinceMs = 0;  // consume the event, avoid re-triggering
    return true;
  }
  if (btnCalibrate.rose()) {
    calibrateHeldSinceMs = 0;
  }
  return false;
}

// [Verified 2026-08-28, unchanged through two bin-geometry revisions
// this same day] This mapping is a generic linear interpolation between
// BIN_EMPTY_DISTANCE_CM and BIN_FULL_DISTANCE_CM (config.h) — it has no
// bin-size-specific logic of its own, so re-tuning for a different bin
// (or a different sensor mounting height) is always just a two-constant
// change in config.h, never an edit here.
float distanceToFillPct(float distanceCm) {
  if (distanceCm < 0) return -1.0f;  // propagate "invalid" to caller

  float pct = (BIN_EMPTY_DISTANCE_CM - distanceCm) /
              (BIN_EMPTY_DISTANCE_CM - BIN_FULL_DISTANCE_CM) * 100.0f;
  if (pct < 0.0f) pct = 0.0f;
  if (pct > 100.0f) pct = 100.0f;
  return pct;
}

// [Changed 2026-08-28] No longer takes a WasteTypeHint / switches on a
// button-selected baseline — always starts from the single
// DENSITY_BASELINE (config.h). See that file's PSEUDO-DENSITY MODEL
// section for why the two-button classification was removed and where a
// future real signal (e.g. a vision-model wet/dry classification) would
// plug back in here.
float estimateDensity(float fillRateDeltaPctPerSec) {
  // A fast positive fill-rate delta (waste arriving quickly) nudges the
  // estimate upward, modeling compaction/settling behavior. This is an
  // engineering proxy, not a calibrated physical measurement — documented
  // as such in the payload/dashboard.
  float adjustment = DENSITY_FILL_RATE_GAIN * fmaxf(fillRateDeltaPctPerSec, 0.0f);
  float estimate = DENSITY_BASELINE + adjustment;

  return estimate < 0.0f ? 0.0f : estimate;
}

// [Added 2026-08-28] weight = density x volume, volume = cross-section
// area x fill height.
//
// ⚠️ THIS IS NOT A CALIBRATED PHYSICAL WEIGHT. densityProxy is an
// arbitrary relative unit, not kg/L (see config.h's PSEUDO-DENSITY MODEL
// section) — there's no load cell on this hardware. Multiplying an
// arbitrary-unit density by a real volume (cm^3) produces a number with
// no meaningful physical unit either. Treat this strictly as a
// relative/comparative signal — "this bin's estimated mass is trending
// up," or "bin A > bin B right now" — never report it to a user as an
// absolute kg figure. Named estimated_weight_proxy everywhere downstream
// (JSON payload, cloud schema, dashboard) specifically to avoid implying
// a real unit.
float estimateWeightProxy(float fillPct, float densityProxy) {
  if (fillPct < 0.0f) return -1.0f;  // propagate "invalid" upstream, same convention as distanceToFillPct()

  // Fill height uses the SAME calibrated span fill_pct itself is derived
  // from (BIN_EMPTY_DISTANCE_CM - BIN_FULL_DISTANCE_CM), not the bin's
  // raw physical height (config.h) — keeps "100% full" meaning the same
  // usable volume here as it already does for fill_pct.
  float fillHeightCm = (fillPct / 100.0f) * (BIN_EMPTY_DISTANCE_CM - BIN_FULL_DISTANCE_CM);

  // Assumes a round bin. For a rectangular bin, replace this with
  // BIN_WIDTH_CM * BIN_DEPTH_CM instead (see config.h's comment on
  // BIN_DIAMETER_CM).
  float radiusCm = BIN_DIAMETER_CM / 2.0f;
  float crossSectionAreaCm2 = PI * radiusCm * radiusCm;

  float volumeCm3 = crossSectionAreaCm2 * fillHeightCm;
  return densityProxy * volumeCm3;
}

// [Changed 2026-08-28] Single-sensor version — see the header comment on
// this function's declaration in sensors.h for what's lost by no longer
// having a second sensor to cross-check against.
uint8_t computeConfidenceFlag(float us1Cm) {
  // Timed out / out of range -> not trustworthy. This is really just
  // re-checking what readUltrasonicCm() already decided (it returns
  // -1.0f for the same reason), kept as its own function/field so the
  // rest of the pipeline (packaging, cloud schema, dashboard) doesn't
  // need to change now or if a smarter confidence heuristic replaces
  // this later.
  if (us1Cm < 0) return 0;
  return 1;
}

}  // namespace Sensors
