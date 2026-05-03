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


def _deep_merge(base: dict, overlay: dict) -> dict:
    """Recursively merge overlay into base. Overlay values win. Returns base."""
    for k, v in overlay.items():
        if k in base and isinstance(base[k], dict) and isinstance(v, dict):
            _deep_merge(base[k], v)
        else:
            base[k] = v
    return base


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

    def update_overlay(self, session_id: str, partial: dict) -> SessionState:
        with self._lock:
            s = self._sessions.get(session_id)
            if s is None:
                raise KeyError(f"unknown session: {session_id}")
            _deep_merge(s.live_overlay, partial)
            s.cached_cfg = None
            return s

    def remove_overlay_keypath(self, session_id: str, keypath: str) -> SessionState:
        """Remove a dotted-path key from the overlay. No-op if missing."""
        with self._lock:
            s = self._sessions.get(session_id)
            if s is None:
                raise KeyError(f"unknown session: {session_id}")
            parts = keypath.split(".")
            cur = s.live_overlay
            for part in parts[:-1]:
                if not isinstance(cur, dict) or part not in cur:
                    return s
                cur = cur[part]
            if isinstance(cur, dict) and parts[-1] in cur:
                del cur[parts[-1]]
                s.cached_cfg = None
            return s

    def attach_profile(self, session_id: str, profile_name: str) -> SessionState:
        with self._lock:
            s = self._sessions.get(session_id)
            if s is None:
                raise KeyError(f"unknown session: {session_id}")
            s.attached_profile = profile_name
            s.cached_cfg = None
            return s

    def detach_profile(self, session_id: str) -> SessionState:
        with self._lock:
            s = self._sessions.get(session_id)
            if s is None:
                raise KeyError(f"unknown session: {session_id}")
            s.attached_profile = None
            s.cached_cfg = None
            return s

    def invalidate(self, session_id: str) -> None:
        with self._lock:
            s = self._sessions.get(session_id)
            if s is not None:
                s.cached_cfg = None

    def _evict_oldest_if_full_locked(self) -> None:
        """Caller holds self._lock. Drops the oldest-idle session if at capacity."""
        if len(self._sessions) < self._max_active:
            return
        oldest_sid = min(self._sessions.items(), key=lambda kv: kv[1].last_hook_at)[0]
        del self._sessions[oldest_sid]
