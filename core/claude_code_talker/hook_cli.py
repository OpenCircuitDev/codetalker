"""CLI entry point invoked by Claude Code hooks.

Reads JSON from stdin, posts it to the daemon's REST hook dispatch
endpoint. If the daemon isn't running, spawns it detached and exits
silently. The next hook will succeed.

v1.0 (2026-05-11): switched from MCP SSE client to plain HTTP POST.
The MCP path's SSE handshake was costing 10-22 seconds per hook from
the Windows .exe wrapper, causing every Stop/PreToolUse/PostToolUse
to silently time out before the tool dispatch ran. Net result: hooks
fired client-side but never reached the daemon, so no narration was
generated. REST POST completes in <100ms.
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from claude_code_talker.daemon import (
    DAEMON_PIDFILE, daemon_url, is_process_alive, read_pidfile, spawn_detached,
)


# 5s ceiling on the hook POST. Claude Code hooks are configured with
# async: true so the user's chat never blocks on us, but we still want
# to bail fast if the daemon is wedged — better to ensure_daemon and
# let the next hook deliver cleanly than to hang for 30+ seconds.
_HOOK_POST_TIMEOUT_SEC = 5.0

# 2026-05-11 — spawn circuit breaker. Without rate-limiting, every Claude
# Code hook event (Stop, PreToolUse, PostToolUse, Notification,
# UserPromptSubmit) that finds the daemon dead immediately spawns a new
# one. If the daemon crashes during startup OR is in a port-bound-but-
# unresponsive state, this produces an infinite spawn loop that can leak
# memory, lock the pidfile, and starve the system. The breaker enforces:
#   (a) at most one spawn attempt per ``_SPAWN_LOCKOUT_SEC`` (cooldown), and
#   (b) at most ``_SPAWN_RATE_LIMIT_COUNT`` spawns within
#       ``_SPAWN_RATE_LIMIT_WINDOW_SEC`` (sustained rate cap).
# Beyond the cap, the hook is a no-op — the user gets no narration but the
# system stays sane until a human intervenes.
_SPAWN_LOCKOUT_SEC = 30.0
_SPAWN_RATE_LIMIT_WINDOW_SEC = 600.0  # 10 minutes
_SPAWN_RATE_LIMIT_COUNT = 12  # at most 1.2 spawns/min sustained
_SPAWN_LOG = Path.home() / ".claude" / "scripts" / "codetalker_spawn_attempts.log"


def _daemon_base_url() -> str:
    """Derive the daemon's REST base from the same URL daemon.py uses
    for its MCP SSE endpoint. ``daemon_url()`` returns the SSE path
    (``http://127.0.0.1:17832/sse``); strip the suffix to get base."""
    url = daemon_url().rstrip("/")
    if url.endswith("/sse"):
        url = url[: -len("/sse")]
    return url


def _post_hook(payload: dict) -> None:
    """POST the hook payload to the daemon's REST dispatch endpoint.
    Raises on connection / HTTP error so the caller can ensure_daemon
    on next invocation."""
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        _daemon_base_url() + "/api/hooks/dispatch",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=_HOOK_POST_TIMEOUT_SEC) as resp:
        # Drain the response so the connection closes cleanly. The
        # response body has the daemon's handler result (e.g.
        # ``{"event": "Stop", "result": "queued: 751 chars"}``) but
        # hook_cli is fire-and-forget so we don't use it.
        resp.read()


def _read_spawn_attempts() -> list[float]:
    """Load timestamps of recent spawn attempts. Returns [] on missing/parse error."""
    if not _SPAWN_LOG.exists():
        return []
    try:
        lines = _SPAWN_LOG.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    out: list[float] = []
    for ln in lines:
        parts = ln.strip().split()
        if not parts:
            continue
        try:
            out.append(float(parts[0]))
        except ValueError:
            continue
    return out


def _record_spawn_attempt(reason: str = "respawn") -> None:
    """Append a timestamped spawn-attempt line. Best-effort; never raises.

    Also trims the log to the last 50 entries so it cannot grow unbounded.
    """
    now = time.time()
    try:
        _SPAWN_LOG.parent.mkdir(parents=True, exist_ok=True)
        with _SPAWN_LOG.open("a", encoding="utf-8") as f:
            f.write(f"{now:.3f} {reason}\n")
        try:
            lines = _SPAWN_LOG.read_text(encoding="utf-8").splitlines()
            if len(lines) > 50:
                _SPAWN_LOG.write_text("\n".join(lines[-50:]) + "\n", encoding="utf-8")
        except OSError:
            pass
    except OSError:
        pass


def _spawn_allowed_now() -> bool:
    """Circuit-breaker check: is a respawn permitted right now?

    Returns False when we're inside the lockout window since the last attempt,
    or when the count of recent attempts has exceeded the rate-limit cap.
    """
    attempts = _read_spawn_attempts()
    if not attempts:
        return True
    now = time.time()
    recent = [t for t in attempts if now - t < _SPAWN_RATE_LIMIT_WINDOW_SEC]
    if recent and (now - max(recent) < _SPAWN_LOCKOUT_SEC):
        return False  # too soon since last attempt
    if len(recent) >= _SPAWN_RATE_LIMIT_COUNT:
        return False  # blown the window cap
    return True


def _hydrate_user_env_windows() -> None:
    """2026-05-11 — When Claude Code starts before the user sets a daemon
    env var (e.g. ``CCT_DAEMON_HOST``), the hook's spawn inherits Claude
    Code's frozen env and ignores the user's later choice. On Windows we
    read User-scope env vars from the registry directly so a recently-set
    value still propagates to the spawned daemon without requiring the
    user to restart Claude Code.

    Currently propagates: ``CCT_DAEMON_HOST``. Add more here only when a
    durable user-scope override needs to reach spawned daemons.
    """
    if sys.platform != "win32":
        return
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
            for var in ("CCT_DAEMON_HOST",):
                if os.environ.get(var):
                    continue  # already in env; respect existing value
                try:
                    value, _ = winreg.QueryValueEx(key, var)
                    if value:
                        os.environ[var] = str(value)
                except FileNotFoundError:
                    continue
    except Exception:
        # Best-effort. Never block hook delivery on env hydration.
        pass


def _ensure_daemon() -> None:
    """If the daemon isn't running, spawn it detached. No-op if running.

    Spawn is gated by ``_spawn_allowed_now`` — see the circuit-breaker
    constants at module top. When the breaker trips, the hook becomes a
    silent no-op until the window decays.

    Pulls User-scope env vars (notably ``CCT_DAEMON_HOST``) from the
    Windows registry before spawning so a late-set User-scope value still
    reaches the daemon without needing Claude Code restarted.
    """
    pid = read_pidfile(DAEMON_PIDFILE)
    if pid is not None and is_process_alive(pid):
        return
    if not _spawn_allowed_now():
        return
    _hydrate_user_env_windows()
    spawn_detached([sys.executable, "-m", "claude_code_talker", "serve"])
    _record_spawn_attempt()


def main():
    raw = sys.stdin.read()
    # Debug: every invocation logged for diagnostics.
    try:
        from pathlib import Path
        import time
        log = Path.home() / ".claude" / "scripts" / "codetalker_hook_invocations.log"
        log.parent.mkdir(parents=True, exist_ok=True)
        with log.open("a", encoding="utf-8") as f:
            f.write(f"{time.time():.3f} stdin_bytes={len(raw)} preview={raw[:200]!r}\n")
    except Exception:
        pass
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return
    if not isinstance(payload, dict):
        return
    try:
        _post_hook(payload)
    except (urllib.error.URLError, ConnectionRefusedError, OSError):
        # Daemon not reachable. Spawn it detached and exit silently;
        # next hook will succeed.
        try:
            _ensure_daemon()
        except Exception:
            pass
    except Exception:
        # Any other failure (timeout, HTTP error, bad JSON in response)
        # is silently swallowed — hooks must never break Claude Code.
        pass


if __name__ == "__main__":
    main()
