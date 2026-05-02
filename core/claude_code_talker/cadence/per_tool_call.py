"""Narrates every event immediately. Chattiest mode."""
from __future__ import annotations

from claude_code_talker.cadence.base import CadenceStrategy, Decision
from claude_code_talker.event_buffer import Event


class PerToolCallCadence(CadenceStrategy):
    name = "per_tool_call"

    def on_event(self, event: Event) -> Decision:
        return Decision(fire_immediately=True, events=[event])

    def tick(self) -> Decision:
        return Decision()
