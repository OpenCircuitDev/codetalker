"""Fires narration every period_seconds if buffer has events since last fire."""
from __future__ import annotations

import time

from claude_code_talker.cadence.base import CadenceStrategy, Decision
from claude_code_talker.event_buffer import Event


class PeriodicCadence(CadenceStrategy):
    name = "periodic"

    def __init__(self, period_seconds: float = 12.0):
        self.period_seconds = period_seconds
        self._buffer: list[Event] = []
        self._last_fire: float = time.time()

    def on_event(self, event: Event) -> Decision:
        self._buffer.append(event)
        return Decision()  # never fires immediately

    def tick(self) -> Decision:
        if not self._buffer:
            return Decision()
        if time.time() - self._last_fire < self.period_seconds:
            return Decision()
        events = list(self._buffer)
        self._buffer.clear()
        self._last_fire = time.time()
        return Decision(fire_periodic=True, events=events)
