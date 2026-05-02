"""Hybrid: significant events fire immediately, routine events batch periodically."""
from __future__ import annotations

import time

from claude_code_talker.cadence.base import CadenceStrategy, Decision
from claude_code_talker.event_buffer import Event


class HybridCadence(CadenceStrategy):
    name = "hybrid"

    def __init__(self, threshold: float = 0.5, period_seconds: float = 15.0):
        self.threshold = threshold
        self.period_seconds = period_seconds
        self._routine: list[Event] = []
        self._last_fire: float = time.time()

    def on_event(self, event: Event) -> Decision:
        if event.significance >= self.threshold:
            return Decision(fire_immediately=True, events=[event])
        self._routine.append(event)
        return Decision()

    def tick(self) -> Decision:
        if not self._routine:
            return Decision()
        if time.time() - self._last_fire < self.period_seconds:
            return Decision()
        events = list(self._routine)
        self._routine.clear()
        self._last_fire = time.time()
        return Decision(fire_periodic=True, events=events)
