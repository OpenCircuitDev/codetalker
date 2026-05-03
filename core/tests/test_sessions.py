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
