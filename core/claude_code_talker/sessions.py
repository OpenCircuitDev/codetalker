"""SessionRegistry: thread-safe map of session_id → SessionState.

Sessions are in-memory only. Daemon restart drops them; they reappear on
next hook event. Reattach-on-restart is handled by ProfileStore.last_profile_for_cwd.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Callable, TYPE_CHECKING

if TYPE_CHECKING:
    from claude_code_talker.profiles import ProfileStore
    from claude_code_talker.persistent_sessions import PersistentSessionStore


@dataclass
class SessionState:
    session_id: str
    cwd: str = ""
    transcript_path: str = ""
    last_hook_at: float = 0.0
    live_overlay: dict = field(default_factory=dict)
    attached_profile: str | None = None
    attached_character: str | None = None
    cached_cfg: dict | None = None
    enabled: bool = True


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

    def __init__(
        self,
        max_active: int = 50,
        *,
        profile_store: "ProfileStore | None" = None,
        persistent_session_store: "PersistentSessionStore | None" = None,
        base_cfg_provider: "Callable[[], dict] | None" = None,
        character_store=None,
    ):
        self._sessions: dict[str, SessionState] = {}
        self._lock = threading.RLock()
        self._max_active = max_active
        self._sweeper_thread: threading.Thread | None = None
        self._sweeper_stop = threading.Event()
        self._profile_store = profile_store
        self._persistent_session_store = persistent_session_store
        self._base_cfg_provider = base_cfg_provider
        self._character_store = character_store

    def get(self, session_id: str) -> SessionState | None:
        with self._lock:
            return self._sessions.get(session_id)

    def list_active(self) -> list[SessionState]:
        with self._lock:
            return list(self._sessions.values())

    def touch(self, session_id: str, *, cwd: str = "", transcript_path: str = "") -> SessionState:
        """Create-or-update a session. On first creation, load persistent settings if any,
        else fall back to cwd-based last_profile binding."""
        import time
        with self._lock:
            s = self._sessions.get(session_id)
            is_new = s is None
            if is_new:
                self._evict_oldest_if_full_locked()
                s = SessionState(session_id=session_id)
                self._sessions[session_id] = s
            if cwd:
                s.cwd = cwd
            if transcript_path:
                s.transcript_path = transcript_path
            s.last_hook_at = time.time()

            if is_new:
                # Phase 8: persistent session store WINS over cwd-binding.
                loaded_persistent = False
                if self._persistent_session_store is not None:
                    from claude_code_talker.persistent_sessions import SessionIdError
                    try:
                        payload = self._persistent_session_store.get(session_id)
                    except SessionIdError:
                        # cwd-fallback session_ids (e.g. Windows paths) can't be
                        # persisted; treat as "no payload for this session".
                        payload = None
                    if payload is not None:
                        s.live_overlay = dict(payload.get("live_overlay") or {})
                        s.attached_profile = payload.get("attached_profile")
                        s.attached_character = payload.get("attached_character")
                        s.enabled = bool(payload.get("enabled", True))
                        s.cached_cfg = None
                        loaded_persistent = True
                # Phase 7 cwd-binding: only fall back if no persistent settings loaded.
                if not loaded_persistent and cwd and self._profile_store is not None and s.attached_profile is None:
                    last = self._profile_store.last_profile_for_cwd(cwd)
                    if last is not None and self._profile_store.exists(last):
                        s.attached_profile = last
                        s.cached_cfg = None
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

    def config_for(self, session_id: str) -> dict:
        """Return the resolved cfg for a session. Falls back to base_cfg if session unknown."""
        from claude_code_talker.config import resolve_for_session
        if self._base_cfg_provider is None:
            raise RuntimeError("SessionRegistry constructed without base_cfg_provider")
        base = self._base_cfg_provider()
        with self._lock:
            s = self._sessions.get(session_id)
        if s is None:
            return base
        if self._profile_store is None:
            raise RuntimeError("SessionRegistry constructed without profile_store")
        return resolve_for_session(base, s, self._profile_store, self._character_store)

    def start_sweeper(self, *, interval_seconds: float = 60.0, max_idle_seconds: float = 1800.0) -> None:
        """Start a background thread that calls expire_idle on a timer."""
        if self._sweeper_thread is not None and self._sweeper_thread.is_alive():
            return
        self._sweeper_stop.clear()

        def _run():
            while not self._sweeper_stop.wait(interval_seconds):
                try:
                    self.expire_idle(max_idle_seconds=max_idle_seconds)
                except Exception:
                    import logging
                    logging.warning("session sweeper iteration failed", exc_info=True)

        self._sweeper_thread = threading.Thread(
            target=_run, daemon=True, name="codetalker-session-sweeper"
        )
        self._sweeper_thread.start()

    def stop_sweeper(self) -> None:
        self._sweeper_stop.set()
        t = self._sweeper_thread
        if t is not None:
            t.join(timeout=2.0)

    def _evict_oldest_if_full_locked(self) -> None:
        """Caller holds self._lock. Drops the oldest-idle session if at capacity."""
        if len(self._sessions) < self._max_active:
            return
        oldest_sid = min(self._sessions.items(), key=lambda kv: kv[1].last_hook_at)[0]
        del self._sessions[oldest_sid]


# Phase 25a — backwards-compat alias for tests that reference the older name
LiveSession = SessionState
