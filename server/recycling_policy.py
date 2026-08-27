"""Decide recycling returns from Grove metadata on the central server.

The caller owns authentication, session binding, event persistence and payout
accounting. This module does not receive images or run a model.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Literal


ACCEPTED_MATERIALS = frozenset({"plastic", "metal", "glass"})
Outcome = Literal["waiting", "accepted", "rejected"]


@dataclass(frozen=True)
class PolicyConfig:
    min_confidence: float = 0.70
    required_consecutive_results: int = 3
    timeout_ms: int = 5000

    def __post_init__(self) -> None:
        if (
            isinstance(self.min_confidence, bool)
            or not isinstance(self.min_confidence, (int, float))
            or not isfinite(self.min_confidence)
            or not 0 <= self.min_confidence <= 1
        ):
            raise ValueError("min_confidence must be finite and between 0 and 1")
        if type(self.required_consecutive_results) is not int or self.required_consecutive_results < 1:
            raise ValueError("required_consecutive_results must be a positive integer")
        if type(self.timeout_ms) is not int or self.timeout_ms < 1:
            raise ValueError("timeout_ms must be a positive integer")


@dataclass(frozen=True)
class InferenceSample:
    sequence: int
    material: str | None
    confidence: float | None
    object_count: int = 1


@dataclass(frozen=True)
class Decision:
    outcome: Outcome
    reason: str
    material: str | None = None
    confidence: float | None = None
    stable_results: int = 0
    value_cents: int = 0


class RecyclingInspection:
    """One server-owned inspection, with one terminal decision.

    Pass elapsed time from the server's monotonic clock, not the device clock.
    The backend must bind samples to this inspection before calling observe().
    """

    def __init__(self, config: PolicyConfig | None = None) -> None:
        self.config = config or PolicyConfig()
        self._last_sequence: int | None = None
        self._last_elapsed_ms = 0
        self._candidate: str | None = None
        self._consecutive = 0
        self._minimum_confidence: float | None = None
        self._decision = Decision("waiting", "awaiting_item")

    @property
    def decision(self) -> Decision:
        return self._decision

    def _reset_candidate(self) -> None:
        self._candidate = None
        self._consecutive = 0
        self._minimum_confidence = None

    def _reject(self, reason: str, material: str | None = None) -> Decision:
        self._decision = Decision("rejected", reason, material=material)
        return self._decision

    def poll(self, elapsed_ms: int) -> Decision:
        if self._decision.outcome != "waiting":
            return self._decision
        if type(elapsed_ms) is not int or elapsed_ms < self._last_elapsed_ms:
            return self._reject("invalid_server_time")
        self._last_elapsed_ms = elapsed_ms
        if elapsed_ms >= self.config.timeout_ms:
            return self._reject("inspection_timeout")
        return self._decision

    def observe(self, sample: InferenceSample, elapsed_ms: int) -> Decision:
        if self.poll(elapsed_ms).outcome != "waiting":
            return self._decision

        if type(sample.sequence) is not int or sample.sequence < 0:
            return self._reject("invalid_inference")
        if self._last_sequence is not None and sample.sequence <= self._last_sequence:
            return self._decision
        if type(sample.object_count) is not int or sample.object_count < 0:
            return self._reject("invalid_inference")

        sequence_gap = self._last_sequence is not None and sample.sequence != self._last_sequence + 1
        self._last_sequence = sample.sequence
        if sequence_gap:
            self._reset_candidate()

        if sample.object_count > 1:
            return self._reject("multiple_items")
        if sample.object_count == 0:
            self._reset_candidate()
            self._decision = Decision("waiting", "no_detection")
            return self._decision

        if not isinstance(sample.material, str):
            return self._reject("invalid_inference")
        material = sample.material.strip().lower()
        confidence = sample.confidence
        if (
            isinstance(confidence, bool)
            or not isinstance(confidence, (int, float))
            or not isfinite(confidence)
            or not 0 <= confidence <= 1
        ):
            return self._reject("invalid_inference", material)

        # The owner's material decision tree is evaluated on the server.
        if material not in ACCEPTED_MATERIALS:
            return self._reject("unsupported_material", material)
        if confidence < self.config.min_confidence:
            self._reset_candidate()
            self._decision = Decision("waiting", "low_confidence", material, confidence)
            return self._decision

        if material == self._candidate:
            self._consecutive += 1
            self._minimum_confidence = min(
                self._minimum_confidence if self._minimum_confidence is not None else confidence,
                confidence,
            )
        else:
            self._candidate = material
            self._consecutive = 1
            self._minimum_confidence = confidence

        if self._consecutive >= self.config.required_consecutive_results:
            self._decision = Decision(
                "accepted",
                "eligible_high_confidence",
                material,
                self._minimum_confidence,
                self._consecutive,
                20,
            )
        else:
            self._decision = Decision(
                "waiting", "confirming_item", material, self._minimum_confidence, self._consecutive
            )
        return self._decision
