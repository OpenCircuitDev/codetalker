"""Rolling event buffer for Mode C live narration."""
from __future__ import annotations

import threading
from collections import deque
from dataclasses import dataclass, field
from typing import Callable


@dataclass
class Event:
    timestamp: float
    type: str  # USER_PROMPT | PRE_TOOL | POST_TOOL | PROSE | NOTIFICATION
    metadata: dict
    significance: float = 0.2
    session_id: str = ""  # set by push site from the hook payload's session_id


class EventBuffer:
    """Thread-safe rolling buffer with subscriber notification."""

    def __init__(self, max_size: int = 60):
        self._events: deque[Event] = deque(maxlen=max_size)
        self._lock = threading.RLock()
        self._subscribers: list[Callable[[Event], None]] = []

    def push(self, event: Event) -> None:
        """Append an event and notify all subscribers. Subscriber failures are logged and swallowed."""
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
        """Return the *n* most recently pushed events (newest last)."""
        with self._lock:
            return list(self._events)[-n:]

    def since(self, timestamp: float) -> list[Event]:
        """Return all buffered events with `timestamp > timestamp` (in push order)."""
        with self._lock:
            return [e for e in self._events if e.timestamp > timestamp]

    def recent_for_session(self, n: int, session_id: str) -> list[Event]:
        """Return the *n* most recent events that belong to *session_id*."""
        with self._lock:
            matching = [e for e in self._events if e.session_id == session_id]
            return matching[-n:]

    def active_session_ids(self) -> list[str]:
        """Return deduplicated session_ids present in the buffer (insertion order)."""
        with self._lock:
            seen: dict[str, None] = {}
            for e in self._events:
                if e.session_id:
                    seen[e.session_id] = None
            return list(seen)

    def subscribe(self, callback: Callable[[Event], None]) -> None:
        """Register a callback invoked synchronously after every `push`."""
        with self._lock:
            self._subscribers.append(callback)

    def clear(self) -> None:
        """Drop every buffered event. Subscribers are kept."""
        with self._lock:
            self._events.clear()


def score_significance(event: Event, keywords: list[str]) -> float:
    """Deterministic significance scoring 0.0–1.0.

    Notifications max out (user needs to hear). Errors and findings score high.
    Edits/Writes score moderate. Reads/Greps score low.
    """
    if event.type == "NOTIFICATION":
        return 1.0

    if event.type == "POST_TOOL":
        if not event.metadata.get("success", True):
            return 0.9
        tool = event.metadata.get("tool_name", "")
        if tool in ("Edit", "Write"):
            return 0.6
        if tool == "Bash":
            cmd = event.metadata.get("input", "") or ""
            if any(s in cmd.lower() for s in ("rm ", "kill", "drop ", "delete ")):
                return 0.7
            return 0.3
        return 0.2

    if event.type == "PRE_TOOL":
        tool = event.metadata.get("tool_name", "")
        if tool == "Bash":
            cmd = event.metadata.get("input", "") or ""
            if any(s in cmd.lower() for s in ("rm ", "kill", "drop ", "delete ")):
                return 0.7
        return 0.2

    if event.type == "PROSE":
        text = (event.metadata.get("text", "") or "").lower()
        for kw in keywords:
            if kw.lower() in text:
                return 0.8
        return 0.2

    return 0.2
