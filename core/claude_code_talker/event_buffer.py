"""Rolling event buffer for Mode C live narration."""
from __future__ import annotations

import threading
from collections import deque
from dataclasses import dataclass, field
from typing import Callable


@dataclass
class Event:
    timestamp: float
    type: str  # PRE_TOOL | POST_TOOL | PROSE | NOTIFICATION
    metadata: dict
    significance: float = 0.2


class EventBuffer:
    """Thread-safe rolling buffer with subscriber notification."""

    def __init__(self, max_size: int = 30):
        self._events: deque[Event] = deque(maxlen=max_size)
        self._lock = threading.RLock()
        self._subscribers: list[Callable[[Event], None]] = []

    def push(self, event: Event) -> None:
        with self._lock:
            self._events.append(event)
            subs = list(self._subscribers)
        for sub in subs:
            try:
                sub(event)
            except Exception:
                import logging
                logging.warning("event subscriber failed", exc_info=True)

    def recent(self, n: int = 10) -> list[Event]:
        with self._lock:
            return list(self._events)[-n:]

    def since(self, timestamp: float) -> list[Event]:
        with self._lock:
            return [e for e in self._events if e.timestamp > timestamp]

    def subscribe(self, callback: Callable[[Event], None]) -> None:
        with self._lock:
            self._subscribers.append(callback)

    def clear(self) -> None:
        with self._lock:
            self._events.clear()
