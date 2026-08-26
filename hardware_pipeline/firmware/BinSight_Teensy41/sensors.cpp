#include "sensors.h"
#include "config.h"
#include <Bounce2.h>   // Arduino Library Manager: "Bounce2" by Thomas O Fredericks

namespace Sensors {

static Bounce btnHeavyWet;
static Bounce btnDryRecyclable;
static Bounce btnCalibrate;

static WasteTypeHint activeHint = WASTE_UNCLASSIFIED;
static uint32_t hintExpiresAtMs = 0;

static uint32_t calibrateHeldSinceMs = 0;
static const uint32_t LONG_PRESS_MS = 2000;

void begin() {
  pinMode(US1_TRIG_PIN, OUTPUT);
  pinMode(US1_ECHO_PIN, INPUT);
  pinMode(US2_TRIG_PIN, OUTPUT);
  pinMode(US2_ECHO_PIN, INPUT);
  digitalWrite(US1_TRIG_PIN, LOW);
  digitalWrite(US2_TRIG_PIN, LOW);

  pinMode(STATUS_LED_PIN, OUTPUT);

  btnHeavyWet.attach(BTN_HEAVY_WET_PIN, INPUT_PULLUP);
  btnHeavyWet.interval(15);
  btnDryRecyclable.attach(BTN_DRY_RECYCLABLE_PIN, INPUT_PULLUP);
  btnDryRecyclable.interval(15);
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

WasteTypeHint pollWasteClassification() {
  btnHeavyWet.update();
  btnDryRecyclable.update();

  uint32_t now = millis();

  if (btnHeavyWet.fell()) {
    activeHint = WASTE_HEAVY_WET;
    hintExpiresAtMs = now + DENSITY_CLASSIFICATION_HOLD_MS;
  } else if (btnDryRecyclable.fell()) {
    activeHint = WASTE_DRY_RECYCLABLE;
    hintExpiresAtMs = now + DENSITY_CLASSIFICATION_HOLD_MS;
  }

  if (activeHint != WASTE_UNCLASSIFIED && now > hintExpiresAtMs) {
    activeHint = WASTE_UNCLASSIFIED;  // classification window expired
  }

  return activeHint;
}

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

float distanceToFillPct(float distanceCm) {
  if (distanceCm < 0) return -1.0f;  // propagate "invalid" to caller

  float pct = (BIN_EMPTY_DISTANCE_CM - distanceCm) /
              (BIN_EMPTY_DISTANCE_CM - BIN_FULL_DISTANCE_CM) * 100.0f;
  if (pct < 0.0f) pct = 0.0f;
  if (pct > 100.0f) pct = 100.0f;
  return pct;
}

float estimateDensity(float fillRateDeltaPctPerSec, WasteTypeHint hint) {
  float baseline;
  switch (hint) {
    case WASTE_HEAVY_WET:      baseline = DENSITY_BASELINE_HEAVY_WET;      break;
    case WASTE_DRY_RECYCLABLE: baseline = DENSITY_BASELINE_DRY_RECYCLABLE; break;
    default:                   baseline = DENSITY_BASELINE_UNCLASSIFIED;   break;
  }

  // A fast positive fill-rate delta (waste arriving quickly) nudges the
  // estimate upward, modeling compaction/settling behavior. This is an
  // engineering proxy, not a calibrated physical measurement — documented
  // as such in the payload/dashboard.
  float adjustment = DENSITY_FILL_RATE_GAIN * fmaxf(fillRateDeltaPctPerSec, 0.0f);
  float estimate = baseline + adjustment;

  return estimate < 0.0f ? 0.0f : estimate;
}

uint8_t computeConfidenceFlag(float us1Cm, float us2Cm) {
  // Either sensor timed out / out of range -> not trustworthy.
  if (us1Cm < 0 || us2Cm < 0) return 0;

  // Sensors disagree beyond tolerance -> likely blockage or angled echo.
  if (fabsf(us1Cm - us2Cm) > US_SENSOR_DISAGREEMENT_CM) return 0;

  return 1;
}

}  // namespace Sensors
