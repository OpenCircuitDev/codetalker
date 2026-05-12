"""session_audit.py — identity-printing read/write helper for daemon audits.

M-AUD-4 discipline (2026-05-11): every read or write to /api/sessions/<sid>
prints the session display_name alongside the SID, so an OCRGame-vs-CTDev
mix-up cannot recur (cost ~15 minutes on the audit it triggered).

Usage:
    python scripts/session_audit.py list
    python scripts/session_audit.py get <session-id|display-name>
    python scripts/session_audit.py put <session-id|display-name> <key>=<value> [...]

Examples:
    python scripts/session_audit.py get OCRGame
    python scripts/session_audit.py put OCRGame active_mode=brief
    python scripts/session_audit.py put OCRGame "live.cadence=slow"

Display-name lookup is case-insensitive and matches exactly. Ambiguous names
abort with the full candidate list so the right SID can be picked. Output is
plain-text with a leading `[session=<name> id=<sid>]` prefix on every line that
touches session state.
"""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from typing import Any

# 2026-05-11 — force UTF-8 on stdout so unicode chars (e.g. arrows, em-dashes
# in display_name or audio_outputs labels) render correctly on Windows. The
# default cp1252 codepage replaces them with `?` or `�`, which masked
# the actual content in audit listings.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
except Exception:
    pass

DAEMON_BASE = "http://localhost:17832"


def _fetch_sessions() -> list[dict[str, Any]]:
    with urllib.request.urlopen(f"{DAEMON_BASE}/api/sessions", timeout=5) as resp:
        payload = json.load(resp)
    # The daemon returns a top-level list (the earlier audit's curl showed this).
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict) and isinstance(payload.get("sessions"), list):
        return payload["sessions"]
    raise SystemExit(f"unexpected /api/sessions shape: {type(payload).__name__}")


def _resolve_target(arg: str) -> tuple[str, str]:
    """Return (session_id, display_name). Match SID first, then display_name (case-insensitive)."""
    sessions = _fetch_sessions()
    by_sid = {s.get("session_id"): s for s in sessions if s.get("session_id")}
    if arg in by_sid:
        s = by_sid[arg]
        return arg, s.get("display_name") or s.get("title") or arg
    norm = arg.casefold()
    matches = [s for s in sessions if (s.get("display_name") or "").casefold() == norm]
    if not matches:
        partial = [s for s in sessions if norm in (s.get("display_name") or "").casefold()]
        if len(partial) == 1:
            matches = partial
        elif partial:
            names = ", ".join(sorted((s.get("display_name") or "?") for s in partial))
            raise SystemExit(f"ambiguous display_name '{arg}' — candidates: {names}")
    if not matches:
        raise SystemExit(f"no session matches '{arg}'")
    if len(matches) > 1:
        ids = ", ".join((s.get("display_name") or "?") + "/" + (s.get("session_id") or "?") for s in matches)
        raise SystemExit(f"display_name '{arg}' is not unique — candidates: {ids}")
    s = matches[0]
    return s["session_id"], s.get("display_name") or arg


def _label(sid: str, name: str) -> str:
    return f"[session={name} id={sid}]"


def _parse_kv(arg: str) -> tuple[str, Any]:
    if "=" not in arg:
        raise SystemExit(f"expected key=value, got '{arg}'")
    key, raw = arg.split("=", 1)
    key = key.strip()
    raw = raw.strip()
    # Try JSON first (so true/false/numbers/null and quoted strings work),
    # fall back to raw string.
    try:
        return key, json.loads(raw)
    except Exception:
        return key, raw


def cmd_list() -> int:
    sessions = _fetch_sessions()
    live = [s for s in sessions if s.get("is_live")]
    dormant = [s for s in sessions if not s.get("is_live")]
    print(f"[daemon] active={len(live)} dormant={len(dormant)}")
    for s in live:
        sid = s.get("session_id", "?")
        name = s.get("display_name") or "?"
        mode = s.get("active_mode") or "?"
        cadence = s.get("cadence") or "?"
        audio = ",".join(s.get("audio_outputs") or []) or "—"
        print(f"  {_label(sid, name)} mode={mode} cadence={cadence} audio={audio}")
    return 0


def cmd_get(target: str) -> int:
    sid, name = _resolve_target(target)
    with urllib.request.urlopen(f"{DAEMON_BASE}/api/sessions/{sid}", timeout=5) as resp:
        payload = json.load(resp)
    state = payload.get("state", payload) if isinstance(payload, dict) else {}
    lo = state.get("live_overlay") or {}
    print(f"{_label(sid, name)} active_mode={state.get('active_mode')}")
    print(f"{_label(sid, name)} live_overlay.active_mode={lo.get('active_mode')}")
    print(f"{_label(sid, name)} live_overlay.cadence={lo.get('cadence')}")
    print(f"{_label(sid, name)} live_overlay.auto_mode_enabled={lo.get('auto_mode_enabled')}")
    print(f"{_label(sid, name)} live_overlay.audio_outputs={lo.get('audio_outputs')}")
    if "live" in lo and isinstance(lo["live"], dict):
        print(f"{_label(sid, name)} live_overlay.live.cadence={lo['live'].get('cadence')}")
    return 0


def cmd_put(target: str, kvs: list[str]) -> int:
    sid, name = _resolve_target(target)
    body: dict[str, Any] = {}
    for kv in kvs:
        key, value = _parse_kv(kv)
        # Support dotted paths (e.g. live.cadence=slow) by walking into a
        # nested dict at PUT time, since the daemon's put_overlay does a
        # deep-merge on the top-level keys it recognises.
        if "." in key:
            head, *rest = key.split(".")
            ptr = body.setdefault(head, {})
            for part in rest[:-1]:
                ptr = ptr.setdefault(part, {})
            ptr[rest[-1]] = value
        else:
            body[key] = value
    print(f"{_label(sid, name)} PUT body={json.dumps(body)}")
    req = urllib.request.Request(
        f"{DAEMON_BASE}/api/sessions/{sid}/overlay",
        data=json.dumps(body).encode(),
        method="PUT",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            payload = json.load(resp)
    except urllib.error.HTTPError as e:
        body_text = e.read().decode("utf-8", errors="replace")
        print(f"{_label(sid, name)} HTTP {e.code}: {body_text[:300]}")
        return 1
    state = payload.get("state", {})
    lo = state.get("live_overlay") or {}
    print(f"{_label(sid, name)} POST-PUT live_overlay.active_mode={lo.get('active_mode')}")
    print(f"{_label(sid, name)} POST-PUT live_overlay.cadence={lo.get('cadence')}")
    return 0


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 2
    cmd = argv[1]
    if cmd == "list":
        return cmd_list()
    if cmd == "get" and len(argv) >= 3:
        return cmd_get(argv[2])
    if cmd == "put" and len(argv) >= 4:
        return cmd_put(argv[2], argv[3:])
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
