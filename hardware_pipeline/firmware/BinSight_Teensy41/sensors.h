#pragma once
/*
 * sensors.h — low-level acquisition for the ultrasonic sensor and 3x
 * push buttons, plus the pseudo-density estimator. Called exclusively
 * from Task 1 (Sensing), which owns this hardware — no other task should
 * touch these pins, so no mutex is needed around the reads themselves.
 *
 * [Changed 2026-08-28] Previously 2x ultrasonic sensors, cross-checked
 * against each other to derive confidence_flag. Now a single sensor per
 * bin — see computeConfidenceFlag() below for how that flag is computed
 * without a second sensor to compare against.
 */

#include <Arduino.h>
#include "types.h"

namespace Sensors {

// Call once from setup(), before the scheduler starts.
void begin();

// Blocking single-shot ultrasonic read (HC-SR04-style trig/echo).
// Returns -1.0f on timeout (out of range / no echo -> treated as noise).
float readUltrasonicCm(uint8_t trigPin, uint8_t echoPin);

// Polls all 3 buttons (debounced) and returns the currently-active
// classification. Buttons are momentary; the classification persists for
// DENSITY_CLASSIFICATION_HOLD_MS after the last press so a single tap
// covers the next few acquisition cycles.
WasteTypeHint pollWasteClassification();

// True on a long-press of the calibrate/reset button; caller should
// re-baseline BIN_EMPTY_DISTANCE_CM against the current empty-bin reading.
bool pollCalibrationRequest();

// Converts a raw distance reading into a fill percentage using the
// configured empty/full calibration distances. Clamped to [0, 100].
float distanceToFillPct(float distanceCm);

// Computes the pseudo-density proxy from the fill-rate delta (%/s) and the
// active button classification. This is the documented workaround for not
// having a physical load cell.
float estimateDensity(float fillRateDeltaPctPerSec, WasteTypeHint hint);

// [Changed 2026-08-28] Was a two-sensor cross-check (computeConfidenceFlag
// (us1, us2)); with a single sensor there's nothing left to cross-check
// against, so this now just validates that the one reading is in range.
// Trade-off worth knowing about: this can no longer catch a single
// sensor giving a plausible-but-wrong reading (e.g. an angled echo off
// waste near the rim) the way disagreement-with-a-second-sensor used to
// — it only catches an outright timeout/out-of-range echo. If that
// distinction matters, consider re-adding some form of cross-check
// (e.g. consistency across consecutive samples) rather than assuming
// this is equivalent to the old behavior.
uint8_t computeConfidenceFlag(float us1Cm);

}  // namespace Sensors
