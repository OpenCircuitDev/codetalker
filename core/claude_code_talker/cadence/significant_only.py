"""Narrates only events with significance >= threshold."""
from __future__ import annotations

from claude_code_talker.cadence.base import CadenceStrategy, Decision
from claude_code_talker.event_buffer import Event


class SignificantOnlyCadence(CadenceStrategy):
    name = "significant_only"

    def __init__(self, threshold: float = 0.5):
        self.threshold = threshold

    def on_event(self, event: Event) -> Decision:
        if event.significance >= self.threshold:
            return Decision(fire_immediately=True, events=[event])
        return Decision()

    def tick(self) -> Decision:
        return Decision()
