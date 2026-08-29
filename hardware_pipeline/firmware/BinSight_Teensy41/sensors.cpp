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
// classification stayed active. estimateDensity() and estimateWeightProxy()
// (which used to live below this point) are gone too — see config.h's
// PSEUDO-DENSITY MODEL removal note.

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

// [Removed 2026-08-28] estimateDensity() and estimateWeightProxy() —
// this bin no longer estimates a density or weight proxy at all (not
// just the button classification that used to feed the density
// baseline). See config.h's PSEUDO-DENSITY MODEL removal note for the
// full picture and where to plug a real signal back in if this is
// revisited later (e.g. a load cell, or a vision-model classification).

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
