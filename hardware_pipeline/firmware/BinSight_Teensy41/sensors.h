#pragma once
/*
 * sensors.h — low-level acquisition for the ultrasonic sensor and the
 * calibration push button, plus the pseudo-density estimator. Called
 * exclusively from Task 1 (Sensing), which owns this hardware — no other
 * task should touch these pins, so no mutex is needed around the reads
 * themselves.
 *
 * [Changed 2026-08-28] Previously 2x ultrasonic sensors, cross-checked
 * against each other to derive confidence_flag. Now a single sensor per
 * bin — see computeConfidenceFlag() below for how that flag is computed
 * without a second sensor to compare against.
 *
 * [Removed 2026-08-28] The 2 manual waste-type classification buttons
 * (heavy/wet, dry/recyclable) and pollWasteClassification() are gone —
 * estimateDensity() below no longer takes a classification hint, only the
 * calibrate/reset button remains.
 */

#include <Arduino.h>
#include "types.h"

namespace Sensors {

// Call once from setup(), before the scheduler starts.
void begin();

// Blocking single-shot ultrasonic read (HC-SR04-style trig/echo).
// Returns -1.0f on timeout (out of range / no echo -> treated as noise).
float readUltrasonicCm(uint8_t trigPin, uint8_t echoPin);

// True on a long-press of the calibrate/reset button; caller should
// re-baseline BIN_EMPTY_DISTANCE_CM against the current empty-bin reading.
bool pollCalibrationRequest();

// Converts a raw distance reading into a fill percentage using the
// configured empty/full calibration distances. Clamped to [0, 100].
float distanceToFillPct(float distanceCm);

// Computes the pseudo-density proxy from the fill-rate delta (%/s), starting
// from a single fixed baseline (config.h's DENSITY_BASELINE). This is the
// documented workaround for not having a physical load cell.
// [Changed 2026-08-28] No longer takes a WasteTypeHint — the manual
// button classification it used to switch on is gone (see config.h's
// PSEUDO-DENSITY MODEL section).
float estimateDensity(float fillRateDeltaPctPerSec);

// [Added 2026-08-28] Estimates a relative WEIGHT PROXY from the current
// fill percentage and the pseudo-density proxy (weight = density x
// volume, volume derived from fill height x bin cross-section). This is
// NOT a calibrated physical weight — see the loud disclaimer on the
// definition in sensors.cpp before using this for anything beyond a
// relative/comparative signal (e.g. "trending up", "bin A > bin B").
// Returns -1.0f if fillPct is itself invalid (propagated from upstream).
float estimateWeightProxy(float fillPct, float densityProxy);

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
