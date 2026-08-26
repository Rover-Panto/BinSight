#pragma once
/*
 * filters.h — local sanity/moving-average filtering used by Task 2.
 *
 * Two independent filter stages, applied to fill_pct and estimated_density
 * separately:
 *   1. Sanity clamp — rejects a single-sample jump bigger than physically
 *      plausible (e.g. an ultrasonic multi-path glitch), substituting the
 *      previous accepted value instead of forwarding a spike.
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
    hasLast_ = false;
  }

  // Applies the sanity clamp, then folds the (possibly clamped) sample
  // into the moving average and returns the smoothed value.
  float process(float sample, float maxJumpAllowed) {
    float accepted = sample;
    if (hasLast_ && fabsf(sample - lastAccepted_) > maxJumpAllowed) {
      // Implausible jump: hold at the last accepted value rather than
      // propagating a spike downstream.
      accepted = lastAccepted_;
    }
    lastAccepted_ = accepted;
    hasLast_ = true;

    buffer_[index_] = accepted;
    index_ = (index_ + 1) % MOVING_AVERAGE_WINDOW;
    if (count_ < MOVING_AVERAGE_WINDOW) count_++;

    float sum = 0.0f;
    for (uint8_t i = 0; i < count_; i++) sum += buffer_[i];
    return sum / (float)count_;
  }

 private:
  float   buffer_[MOVING_AVERAGE_WINDOW];
  uint8_t count_;
  uint8_t index_;
  float   lastAccepted_;
  bool    hasLast_;
};
