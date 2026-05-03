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

    def touch(self, session_id: str, *, cwd: str = "", transcript_path: str = "") -> SessionState:
        """Create-or-update a session. Updates last_hook_at; preserves overlay/profile."""
        import time
        with self._lock:
            s = self._sessions.get(session_id)
            if s is None:
                self._evict_oldest_if_full_locked()
                s = SessionState(session_id=session_id)
                self._sessions[session_id] = s
            if cwd:
                s.cwd = cwd
            if transcript_path:
                s.transcript_path = transcript_path
            s.last_hook_at = time.time()
            return s

    def expire_idle(self, max_idle_seconds: float = 1800.0) -> int:
        """Remove sessions idle longer than max_idle_seconds. Returns count removed."""
        import time
        cutoff = time.time() - max_idle_seconds
        with self._lock:
            stale = [sid for sid, s in self._sessions.items() if s.last_hook_at < cutoff]
            for sid in stale:
                del self._sessions[sid]
            return len(stale)

    def _evict_oldest_if_full_locked(self) -> None:
        """Caller holds self._lock. Drops the oldest-idle session if at capacity."""
        if len(self._sessions) < self._max_active:
            return
        oldest_sid = min(self._sessions.items(), key=lambda kv: kv[1].last_hook_at)[0]
        del self._sessions[oldest_sid]
