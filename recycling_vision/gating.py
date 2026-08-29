"""Local visual confirmation gate for the development webcam overlay.

This module does not make a station decision or create a credit. The main
server remains responsible for the production inspection state machine.
"""

from __future__ import annotations

from dataclasses import dataclass

ACCEPTED_CLASSES = frozenset({"plastic", "metal", "glass"})


@dataclass(frozen=True)
class GateResult:
    status: str
    label: str | None
    consecutive: int
    emitted_acceptance: bool = False


class ConsecutiveDetectionGate:
    """Require matching accepted labels before showing a local acceptance cue."""

    def __init__(self, required_consecutive: int = 3) -> None:
        if type(required_consecutive) is not int or required_consecutive < 1:
            raise ValueError("required_consecutive must be a positive integer")
        self.required_consecutive = required_consecutive
        self._label: str | None = None
        self._consecutive = 0
        self._accepted = False

    def observe(self, label: str | None) -> GateResult:
        """Record one single-object observation; ``None`` re-arms the gate."""
        if label is None:
            self._label = None
            self._consecutive = 0
            self._accepted = False
            return GateResult("idle", None, 0)

        if label not in ACCEPTED_CLASSES:
            self._label = None
            self._consecutive = 0
            return GateResult("rejected", label, 0)

        if self._accepted:
            return GateResult("accepted", self._label, self._consecutive)

        if label == self._label:
            self._consecutive += 1
        else:
            self._label = label
            self._consecutive = 1

        if self._consecutive >= self.required_consecutive:
            self._accepted = True
            return GateResult("accepted", label, self._consecutive, emitted_acceptance=True)
        return GateResult("confirming", label, self._consecutive)
