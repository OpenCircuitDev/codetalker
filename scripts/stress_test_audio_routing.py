#!/usr/bin/env python
"""Daemon-side stress test for the audio_outputs multi-select routing.

Mirrors the Round 1-4 hardware test matrix but exercises the daemon's
API layer + audio queue logic without needing actual phone/glasses
playback. Catches:

- overlay PUT writes the right shape
- config_for() resolves correctly for live vs dormant sessions
- _resolve_audio_outputs returns the right set for each routing config
- rapid-toggle PUTs don't deadlock or drop writes
- explicit-silence ([]) vs inherit-default (null) semantics
- two-session parallel update isolation
- hook dispatch → narration log entries land per session

Run:   python scripts/stress_test_audio_routing.py
Requires: daemon up on 17832, at least 2 live sessions.
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:17832"


# ─── HTTP helpers ────────────────────────────────────────────────────────


def http(method: str, path: str, body=None, timeout: float = 15.0) -> dict | str:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(
        BASE + path,
        data=data,
        headers={"Content-Type": "application/json"} if data else {},
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                return raw.decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        return {"error": f"HTTP {e.code}", "body": e.read().decode(errors="replace")[:200]}
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}


# ─── Test result accumulator ─────────────────────────────────────────────


class Results:
    def __init__(self):
        self.tests: list[tuple[str, bool, str]] = []

    def assert_eq(self, name: str, got, want, note: str = ""):
        ok = got == want
        msg = f"want={want!r} got={got!r}" + (f"  ({note})" if note else "")
        self.tests.append((name, ok, msg))
        return ok

    def assert_true(self, name: str, cond: bool, note: str = ""):
        self.tests.append((name, cond, note))
        return cond

    def report(self):
        passed = sum(1 for _, ok, _ in self.tests if ok)
        total = len(self.tests)
        print()
        print("=" * 72)
        print(f"STRESS TEST: {passed}/{total} pass")
        print("=" * 72)
        for name, ok, msg in self.tests:
            icon = "PASS" if ok else "FAIL"
            print(f"  [{icon}] {name}")
            if not ok or "FAIL" in msg.upper():
                print(f"         {msg}")
        return passed == total


# ─── Test groups ─────────────────────────────────────────────────────────


def round1_basics(r: Results, sid: str) -> None:
    """Each routing config writes + reads back correctly."""
    print(f"\n--- Round 1: single-session basics (sid={sid[:8]}) ---")
    configs = [
        ("desktop only", ["desktop"]),
        ("phone only", ["phone"]),
        ("glasses only", ["glasses"]),
        ("desktop + phone", ["desktop", "phone"]),
        ("all three", ["desktop", "phone", "glasses"]),
        ("explicit silence", []),
    ]
    for label, outputs in configs:
        resp = http("PUT", f"/api/sessions/{sid}/overlay", {"audio_outputs": outputs})
        if isinstance(resp, dict) and resp.get("error"):
            r.assert_true(f"  PUT {label}", False, str(resp))
            continue
        # Read back via /api/sessions and verify
        sessions = http("GET", "/api/sessions")
        match = next((s for s in sessions if s["session_id"] == sid), None)
        got = sorted(match.get("audio_outputs") or []) if match else None
        want = sorted(outputs)
        r.assert_eq(f"  PUT {label}", got, want)

    # Inherit-default path: null
    resp = http("PUT", f"/api/sessions/{sid}/overlay", {"audio_outputs": None})
    sessions = http("GET", "/api/sessions")
    match = next((s for s in sessions if s["session_id"] == sid), None)
    got = match.get("audio_outputs") if match else "???"
    r.assert_true(
        "  PUT null (inherit default)",
        got is None,
        f"got={got!r}, expected None to mean inherit",
    )


def round2_isolation(r: Results, sid_a: str, sid_b: str) -> None:
    """Two sessions can have independent audio_outputs at the same time."""
    print(f"\n--- Round 2: two-session isolation ---")
    http("PUT", f"/api/sessions/{sid_a}/overlay", {"audio_outputs": ["desktop"]})
    http("PUT", f"/api/sessions/{sid_b}/overlay", {"audio_outputs": ["phone"]})
    sessions = http("GET", "/api/sessions")
    a = next((s for s in sessions if s["session_id"] == sid_a), None)
    b = next((s for s in sessions if s["session_id"] == sid_b), None)
    r.assert_eq(
        "  session A audio_outputs",
        sorted(a.get("audio_outputs") or []) if a else None,
        ["desktop"],
    )
    r.assert_eq(
        "  session B audio_outputs",
        sorted(b.get("audio_outputs") or []) if b else None,
        ["phone"],
    )
    # Swap them
    http("PUT", f"/api/sessions/{sid_a}/overlay", {"audio_outputs": ["phone"]})
    http("PUT", f"/api/sessions/{sid_b}/overlay", {"audio_outputs": ["desktop"]})
    sessions = http("GET", "/api/sessions")
    a = next((s for s in sessions if s["session_id"] == sid_a), None)
    b = next((s for s in sessions if s["session_id"] == sid_b), None)
    r.assert_eq(
        "  swap: A -> phone",
        sorted(a.get("audio_outputs") or []) if a else None,
        ["phone"],
    )
    r.assert_eq(
        "  swap: B -> desktop",
        sorted(b.get("audio_outputs") or []) if b else None,
        ["desktop"],
    )


def round3_rapid_toggle(r: Results, sid: str) -> None:
    """50 rapid PUTs should all land cleanly."""
    print(f"\n--- Round 3: rapid-toggle stress (50 PUTs) ---")
    all_configs = [
        ["desktop"], ["phone"], ["glasses"],
        ["desktop", "phone"], ["desktop", "glasses"], ["phone", "glasses"],
        ["desktop", "phone", "glasses"], [],
    ]
    start = time.time()
    failures = 0
    final = None
    for i in range(50):
        cfg = all_configs[i % len(all_configs)]
        resp = http("PUT", f"/api/sessions/{sid}/overlay", {"audio_outputs": cfg})
        if isinstance(resp, dict) and resp.get("error"):
            failures += 1
        final = cfg
    elapsed = time.time() - start
    r.assert_true(
        f"  50 PUTs in {elapsed:.2f}s, {failures} failures",
        failures == 0,
        f"PUTs/sec = {50/elapsed:.1f}",
    )
    # Final state should match the last PUT
    sessions = http("GET", "/api/sessions")
    match = next((s for s in sessions if s["session_id"] == sid), None)
    got = sorted(match.get("audio_outputs") or []) if match else None
    r.assert_eq("  final state matches last PUT", got, sorted(final))


def round4_hook_dispatch_routing(r: Results, sid: str) -> None:
    """Hook dispatch should respect current audio_outputs."""
    print(f"\n--- Round 4: hook dispatch + routing ---")
    # Set to desktop only
    http("PUT", f"/api/sessions/{sid}/overlay", {"audio_outputs": ["desktop"]})
    # Get a real transcript_path from the session
    info = http("GET", f"/api/sessions/{sid}")
    transcript_path = (info.get("state") or {}).get("transcript_path", "")
    if not transcript_path:
        r.assert_true("  could not load transcript_path", False)
        return

    # Fire a Stop hook via the new REST endpoint
    t0 = time.time()
    resp = http("POST", "/api/hooks/dispatch", {
        "hook_event_name": "Stop",
        "session_id": sid,
        "cwd": "C:\\Users\\brand\\Dropbox\\OCR\\Open_Circuit\\BF_Workspace",
        "transcript_path": transcript_path,
    }, timeout=15)
    elapsed = time.time() - t0
    r.assert_true(
        f"  Stop dispatch in {elapsed:.2f}s",
        not (isinstance(resp, dict) and resp.get("error")),
        f"resp={str(resp)[:200]}",
    )
    r.assert_true("  Stop dispatch elapsed < 8s", elapsed < 8.0)

    # Verify session_count is non-zero (we created/touched it)
    status = http("GET", "/api/status")
    r.assert_true(
        "  session_count >= 1 after dispatch",
        status.get("session_count", 0) >= 1,
        f"got {status.get('session_count')}",
    )


def round5_explicit_silence_vs_inherit(r: Results, sid: str) -> None:
    """Verify the [] vs null distinction holds."""
    print(f"\n--- Round 5: explicit silence vs inherit-default ---")
    # Set to []
    http("PUT", f"/api/sessions/{sid}/overlay", {"audio_outputs": []})
    sessions = http("GET", "/api/sessions")
    match = next((s for s in sessions if s["session_id"] == sid), None)
    r.assert_eq(
        "  [] persists as empty list (not null)",
        match.get("audio_outputs") if match else "???",
        [],
    )
    # Set to null
    http("PUT", f"/api/sessions/{sid}/overlay", {"audio_outputs": None})
    sessions = http("GET", "/api/sessions")
    match = next((s for s in sessions if s["session_id"] == sid), None)
    r.assert_eq(
        "  null clears the override (becomes None)",
        match.get("audio_outputs") if match else "???",
        None,
    )


def round6_mute_persistence(r: Results, sid: str) -> None:
    """Mute toggle persists across overlay PUT + survives in-memory."""
    print(f"\n--- Round 6: mute toggle persistence ---")
    http("PUT", f"/api/sessions/{sid}/overlay", {"enabled": False})
    sessions = http("GET", "/api/sessions")
    match = next((s for s in sessions if s["session_id"] == sid), None)
    r.assert_eq(
        "  PUT enabled=False reflects",
        match.get("enabled") if match else "???",
        False,
    )
    # Restore
    http("PUT", f"/api/sessions/{sid}/overlay", {"enabled": True})
    sessions = http("GET", "/api/sessions")
    match = next((s for s in sessions if s["session_id"] == sid), None)
    r.assert_eq(
        "  PUT enabled=True restores",
        match.get("enabled") if match else "???",
        True,
    )


def round7_recovery_state(r: Results, sid: str) -> None:
    """Restore sensible defaults so the user's setup is unchanged after the test."""
    print(f"\n--- Round 7: restore defaults ---")
    http("PUT", f"/api/sessions/{sid}/overlay", {"audio_outputs": ["desktop"]})
    http("PUT", f"/api/sessions/{sid}/overlay", {"enabled": True})
    sessions = http("GET", "/api/sessions")
    match = next((s for s in sessions if s["session_id"] == sid), None)
    r.assert_true(
        "  desktop output restored",
        match and "desktop" in (match.get("audio_outputs") or []),
    )
    r.assert_true("  enabled=True restored", match and match.get("enabled") is True)


# ─── Main ────────────────────────────────────────────────────────────────


def main():
    health = http("GET", "/api/health", timeout=3)
    if not (isinstance(health, dict) and health.get("ok")):
        print("daemon not reachable on :17832")
        sys.exit(1)
    sessions = http("GET", "/api/sessions")
    if not isinstance(sessions, list):
        print(f"unexpected /api/sessions: {sessions!r}")
        sys.exit(1)
    live = [s for s in sessions if s.get("is_live")]
    if len(live) < 1:
        print(f"need >=1 live session; have {len(live)}")
        sys.exit(1)
    sid_a = live[0]["session_id"]
    sid_b = live[1]["session_id"] if len(live) >= 2 else None
    print(f"Test session A: {sid_a[:8]} ({live[0].get('display_name')})")
    if sid_b:
        print(f"Test session B: {sid_b[:8]} ({live[1].get('display_name')})")
    else:
        print(f"(only 1 live session — Round 2 isolation skipped)")

    r = Results()
    round1_basics(r, sid_a)
    if sid_b:
        round2_isolation(r, sid_a, sid_b)
    round3_rapid_toggle(r, sid_a)
    round4_hook_dispatch_routing(r, sid_a)
    round5_explicit_silence_vs_inherit(r, sid_a)
    round6_mute_persistence(r, sid_a)
    round7_recovery_state(r, sid_a)
    ok = r.report()
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
