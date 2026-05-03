"""Tests for resolve_for_session 5-layer merge."""
import pytest
from pathlib import Path
from claude_code_talker.config import resolve_for_session
from claude_code_talker.sessions import SessionState
from claude_code_talker.profiles import ProfileStore


@pytest.fixture
def profiles(tmp_path):
    return ProfileStore(profiles_dir=tmp_path)


def test_no_overlay_no_profile_returns_base(profiles):
    base = {"voice": {"model": "jenny"}, "active_mode": "direct"}
    s = SessionState(session_id="abc")
    cfg = resolve_for_session(base, s, profiles)
    assert cfg == base


def test_overlay_overrides_base(profiles):
    base = {"voice": {"model": "jenny", "rate": 1.0}, "active_mode": "direct"}
    s = SessionState(session_id="abc", live_overlay={"voice": {"model": "marvin"}})
    cfg = resolve_for_session(base, s, profiles)
    assert cfg["voice"]["model"] == "marvin"
    assert cfg["voice"]["rate"] == 1.0  # base preserved
    assert cfg["active_mode"] == "direct"


def test_profile_layers_between_base_and_overlay(profiles):
    profiles.save("verbose", {"active_mode": "live", "voice": {"rate": 1.3}})
    base = {"voice": {"model": "jenny", "rate": 1.0}, "active_mode": "direct"}
    s = SessionState(
        session_id="abc",
        attached_profile="verbose",
        live_overlay={"voice": {"model": "marvin"}},
    )
    cfg = resolve_for_session(base, s, profiles)
    assert cfg["active_mode"] == "live"            # from profile
    assert cfg["voice"]["rate"] == 1.3             # from profile
    assert cfg["voice"]["model"] == "marvin"       # from overlay (wins)


def test_attached_profile_missing_falls_through(profiles):
    base = {"voice": {"model": "jenny"}}
    s = SessionState(session_id="abc", attached_profile="does-not-exist")
    cfg = resolve_for_session(base, s, profiles)
    # Missing profile is silently skipped
    assert cfg == base


def test_resolve_caches_on_session(profiles):
    base = {"voice": {"model": "jenny"}}
    s = SessionState(session_id="abc")
    assert s.cached_cfg is None
    cfg1 = resolve_for_session(base, s, profiles)
    assert s.cached_cfg is cfg1
    cfg2 = resolve_for_session(base, s, profiles)
    assert cfg2 is cfg1  # same object — served from cache


def test_resolve_does_not_mutate_base(profiles):
    base = {"voice": {"model": "jenny"}}
    s = SessionState(session_id="abc", live_overlay={"voice": {"model": "marvin"}})
    resolve_for_session(base, s, profiles)
    assert base == {"voice": {"model": "jenny"}}  # untouched
