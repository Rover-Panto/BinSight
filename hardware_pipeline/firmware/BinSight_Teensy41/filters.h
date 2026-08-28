#pragma once
/*
 * filters.h — local sanity/moving-average filtering used by Task 2.
 *
 * Two independent filter stages, applied to fill_pct and estimated_density
 * separately:
 *   1. Sanity clamp — rejects a single-sample jump bigger than physically
 *      plausible (e.g. an ultrasonic multi-path glitch), substituting the
 *      previous accepted value instead of forwarding a spike. A jump that
 *      keeps recurring for REACQUIRE_AFTER_N_REJECTS consecutive samples is
 *      treated as a real, sustained change (e.g. a large deposit or the bin
 *      being emptied) rather than a glitch, and the filter reacquires on
 *      the new value instead of freezing on the old one indefinitely.
 *      [Fixed 2026-08-28: see process() below — this reacquire step is the
 *      fix for the "fill filter can freeze after a large deposit/collection"
 *      finding.]
 *   2. Moving average — smooths sensor noise over MOVING_AVERAGE_WINDOW
 *      samples using a small fixed-size circular buffer (no heap use,
 *      RTOS-task-safe as long as each task owns its own instance).
 */

#include <Arduino.h>
#include "config.h"

class MovingAverageFilter {
 public:
  MovingAverageFilter() { reset(); }

  void reset() {
    for (uint8_t i = 0; i < MOVING_AVERAGE_WINDOW; i++) buffer_[i] = 0.0f;
    count_ = 0;
    index_ = 0;
    lastAccepted_ = 0.0f;
    lastAverage_ = 0.0f;
    hasLast_ = false;
    rejectStreak_ = 0;
  }

  // Applies the sanity clamp, then folds the (possibly clamped) sample
  // into the moving average and returns the smoothed value.
  //
  // [Fixed 2026-08-28] Previously, once a sample was rejected as an
  // implausible jump, lastAccepted_ never moved again unless a later
  // sample happened to land back within maxJumpAllowed of it — so a
  // real, sustained change (a large deposit landing in one sample, or
  // the bin being emptied) would report the *same* "implausible" delta
  // on every subsequent sample and freeze the filter forever. We now
  // count consecutive rejections and, after REACQUIRE_AFTER_N_REJECTS in
  // a row, trust the sensor again and snap to the new value. A single
  // rejected sample is still treated as a glitch (unchanged behavior);
  // only a *sustained* jump reacquires.
  float process(float sample, float maxJumpAllowed) {
    float accepted = sample;
    if (hasLast_ && fabsf(sample - lastAccepted_) > maxJumpAllowed) {
      rejectStreak_++;
      if (rejectStreak_ >= REACQUIRE_AFTER_N_REJECTS) {
        // Sustained jump across multiple samples — this is real, not a
        // one-off glitch. Reacquire on the new value instead of holding
        // stale data indefinitely.
        accepted = sample;
        rejectStreak_ = 0;
      } else {
        // Implausible jump: hold at the last accepted value rather than
        // propagating a spike downstream.
        accepted = lastAccepted_;
      }
    } else {
      rejectStreak_ = 0;
    }
    lastAccepted_ = accepted;
    hasLast_ = true;

    buffer_[index_] = accepted;
    index_ = (index_ + 1) % MOVING_AVERAGE_WINDOW;
    if (count_ < MOVING_AVERAGE_WINDOW) count_++;

    float sum = 0.0f;
    for (uint8_t i = 0; i < count_; i++) sum += buffer_[i];
    lastAverage_ = sum / (float)count_;
    return lastAverage_;
  }

  // [Added 2026-08-28] Returns the most recently computed smoothed output
  // without consuming a new sample or touching the reject-streak / clamp
  // state. Used by callers (see tasks.cpp) when the current raw reading is
  // known to be invalid, so they can genuinely "hold the last good value"
  // instead of feeding a fabricated placeholder sample into process() —
  // which previously corrupted lastAccepted_ with a fake 0.0f and could
  // combine with the freeze above to lock the filter at zero.
  float lastOutput() const { return hasLast_ ? lastAverage_ : 0.0f; }

 private:
  static const uint8_t REACQUIRE_AFTER_N_REJECTS = 3;

  float   buffer_[MOVING_AVERAGE_WINDOW];
  uint8_t count_;
  uint8_t index_;
  float   lastAccepted_;
  float   lastAverage_;
  bool    hasLast_;
  uint8_t rejectStreak_;
};
