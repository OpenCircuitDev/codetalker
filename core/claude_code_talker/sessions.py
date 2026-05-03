"""SessionRegistry: thread-safe map of session_id → SessionState.

Sessions are in-memory only. Daemon restart drops them; they reappear on
next hook event. Reattach-on-restart is handled by ProfileStore.last_profile_for_cwd.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass, field


@dataclass
class SessionState:
    session_id: str
    cwd: str = ""
    transcript_path: str = ""
    last_hook_at: float = 0.0
    live_overlay: dict = field(default_factory=dict)
    attached_profile: str | None = None
    cached_cfg: dict | None = None


class SessionRegistry:
    """Thread-safe registry of active sessions."""

    def __init__(self, max_active: int = 50):
        self._sessions: dict[str, SessionState] = {}
        self._lock = threading.RLock()
        self._max_active = max_active

    def get(self, session_id: str) -> SessionState | None:
        with self._lock:
            return self._sessions.get(session_id)

    def list_active(self) -> list[SessionState]:
        with self._lock:
            return list(self._sessions.values())
