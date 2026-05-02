"""Buffers events until natural break (idle gap or max size)."""
from __future__ import annotations

import time

from claude_code_talker.cadence.base import CadenceStrategy, Decision
from claude_code_talker.event_buffer import Event


class PerClusterCadence(CadenceStrategy):
    name = "per_cluster"

    def __init__(self, cluster_gap_seconds: float = 4.0, max_cluster_size: int = 8):
        self.gap = cluster_gap_seconds
        self.max_size = max_cluster_size
        self._cluster: list[Event] = []
        self._last_event_at: float = 0.0

    def on_event(self, event: Event) -> Decision:
        self._cluster.append(event)
        self._last_event_at = time.time()
        if len(self._cluster) >= self.max_size:
            events = list(self._cluster)
            self._cluster.clear()
            return Decision(fire_immediately=True, events=events)
        return Decision()

    def tick(self) -> Decision:
        if not self._cluster:
            return Decision()
        if time.time() - self._last_event_at < self.gap:
            return Decision()
        events = list(self._cluster)
        self._cluster.clear()
        return Decision(fire_periodic=True, events=events)
