"""Tests for SessionRegistry and SessionState."""
import time
from claude_code_talker.sessions import SessionRegistry, SessionState


def test_session_state_default_fields():
    s = SessionState(session_id="abc")
    assert s.session_id == "abc"
    assert s.cwd == ""
    assert s.transcript_path == ""
    assert s.live_overlay == {}
    assert s.attached_profile is None
    assert s.last_hook_at == 0.0


def test_registry_starts_empty():
    r = SessionRegistry()
    assert r.list_active() == []


def test_registry_get_missing_returns_none():
    r = SessionRegistry()
    assert r.get("nope") is None


def test_touch_creates_session():
    r = SessionRegistry()
    r.touch("abc", cwd="/proj/a", transcript_path="/t/abc.jsonl")
    s = r.get("abc")
    assert s is not None
    assert s.cwd == "/proj/a"
    assert s.transcript_path == "/t/abc.jsonl"
    assert s.last_hook_at > 0


def test_touch_updates_last_hook_at():
    r = SessionRegistry()
    r.touch("abc")
    first = r.get("abc").last_hook_at
    time.sleep(0.01)
    r.touch("abc")
    second = r.get("abc").last_hook_at
    assert second > first


def test_touch_preserves_overlay_and_profile():
    r = SessionRegistry()
    r.touch("abc", cwd="/p")
    s = r.get("abc")
    s.live_overlay = {"voice": {"model": "marvin"}}
    s.attached_profile = "verbose-marvin"
    r.touch("abc", cwd="/p")  # second touch — must NOT reset overlay/profile
    s2 = r.get("abc")
    assert s2.live_overlay == {"voice": {"model": "marvin"}}
    assert s2.attached_profile == "verbose-marvin"


def test_expire_idle_drops_old_sessions():
    r = SessionRegistry()
    r.touch("old")
    r.get("old").last_hook_at = time.time() - 10_000  # very old
    r.touch("fresh")
    r.expire_idle(max_idle_seconds=60)
    assert r.get("old") is None
    assert r.get("fresh") is not None


def test_eviction_caps_at_max_active():
    r = SessionRegistry(max_active=3)
    for i, sid in enumerate(["a", "b", "c", "d"]):
        r.touch(sid)
        time.sleep(0.005)  # ensure ordering by last_hook_at
    # "a" is oldest; should be evicted on insert of "d"
    assert r.get("a") is None
    assert r.get("b") is not None
    assert r.get("c") is not None
    assert r.get("d") is not None


def test_update_overlay_deep_merges():
    r = SessionRegistry()
    r.touch("abc")
    r.update_overlay("abc", {"voice": {"model": "marvin"}})
    r.update_overlay("abc", {"voice": {"rate": 1.2}, "active_mode": "live"})
    assert r.get("abc").live_overlay == {
        "voice": {"model": "marvin", "rate": 1.2},
        "active_mode": "live",
    }


def test_update_overlay_invalidates_cache():
    r = SessionRegistry()
    r.touch("abc")
    r.get("abc").cached_cfg = {"some": "cache"}
    r.update_overlay("abc", {"voice": {"model": "marvin"}})
    assert r.get("abc").cached_cfg is None


def test_attach_profile_sets_name_and_invalidates():
    r = SessionRegistry()
    r.touch("abc")
    r.get("abc").cached_cfg = {"x": 1}
    r.attach_profile("abc", "verbose-marvin")
    assert r.get("abc").attached_profile == "verbose-marvin"
    assert r.get("abc").cached_cfg is None


def test_detach_profile_clears_and_invalidates():
    r = SessionRegistry()
    r.touch("abc")
    r.attach_profile("abc", "verbose-marvin")
    r.get("abc").cached_cfg = {"x": 1}
    r.detach_profile("abc")
    assert r.get("abc").attached_profile is None
    assert r.get("abc").cached_cfg is None


def test_invalidate_drops_cache_only():
    r = SessionRegistry()
    r.touch("abc")
    s = r.get("abc")
    s.live_overlay = {"a": 1}
    s.attached_profile = "x"
    s.cached_cfg = {"y": 2}
    r.invalidate("abc")
    s2 = r.get("abc")
    assert s2.cached_cfg is None
    assert s2.live_overlay == {"a": 1}
    assert s2.attached_profile == "x"


def test_update_overlay_on_missing_session_raises():
    import pytest
    r = SessionRegistry()
    with pytest.raises(KeyError):
        r.update_overlay("nope", {"x": 1})


def test_remove_overlay_keypath():
    r = SessionRegistry()
    r.touch("abc")
    r.update_overlay("abc", {"voice": {"model": "marvin", "rate": 1.2}, "active_mode": "live"})
    r.remove_overlay_keypath("abc", "voice.model")
    assert r.get("abc").live_overlay == {"voice": {"rate": 1.2}, "active_mode": "live"}


def test_sweeper_starts_and_stops_cleanly():
    r = SessionRegistry()
    r.start_sweeper(interval_seconds=0.05, max_idle_seconds=0.1)
    assert r._sweeper_thread is not None
    assert r._sweeper_thread.is_alive()
    r.stop_sweeper()
    time.sleep(0.1)
    assert not r._sweeper_thread.is_alive()


def test_sweeper_expires_idle_sessions():
    r = SessionRegistry()
    r.touch("ephemeral")
    r.start_sweeper(interval_seconds=0.05, max_idle_seconds=0.1)
    time.sleep(0.3)  # well past max_idle
    r.stop_sweeper()
    assert r.get("ephemeral") is None
