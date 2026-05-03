"""Tests for SessionRegistry consulting PersistentSessionStore on first touch."""
import pytest
from pathlib import Path
from claude_code_talker.sessions import SessionRegistry, SessionState
from claude_code_talker.persistent_sessions import PersistentSessionStore


@pytest.fixture
def persistent_store_with_payload(tmp_path):
    p = PersistentSessionStore(sessions_dir=tmp_path)
    p.save("known-sid", {
        "live_overlay": {"voice": {"model": "marvin"}, "active_mode": "live"},
        "attached_profile": "verbose",
        "enabled": True,
        "display_name": "MDCycle",
        "last_modified": 1.0,
    })
    return p


def test_session_state_enabled_default_true():
    s = SessionState(session_id="abc")
    assert s.enabled is True


def test_first_touch_loads_persistent_payload(persistent_store_with_payload):
    r = SessionRegistry(persistent_session_store=persistent_store_with_payload)
    s = r.touch("known-sid", cwd="/proj/a")
    assert s.live_overlay == {"voice": {"model": "marvin"}, "active_mode": "live"}
    assert s.attached_profile == "verbose"
    assert s.enabled is True


def test_first_touch_disabled_payload_propagates(tmp_path):
    p = PersistentSessionStore(sessions_dir=tmp_path)
    p.save("muted-sid", {
        "live_overlay": {}, "attached_profile": None, "enabled": False,
        "display_name": None, "last_modified": 1.0,
    })
    r = SessionRegistry(persistent_session_store=p)
    s = r.touch("muted-sid")
    assert s.enabled is False


def test_subsequent_touch_does_not_reload_persistent(persistent_store_with_payload):
    """One-shot load on first creation; subsequent touches preserve runtime mutations."""
    r = SessionRegistry(persistent_session_store=persistent_store_with_payload)
    r.touch("known-sid")
    # User detaches profile at runtime
    r.detach_profile("known-sid")
    # Second touch must NOT reload the saved profile
    r.touch("known-sid")
    assert r.get("known-sid").attached_profile is None


def test_first_touch_unknown_session_uses_defaults(tmp_path):
    p = PersistentSessionStore(sessions_dir=tmp_path)
    r = SessionRegistry(persistent_session_store=p)
    s = r.touch("never-seen", cwd="/proj/a")
    assert s.live_overlay == {}
    assert s.attached_profile is None
    assert s.enabled is True


def test_no_persistent_store_no_load(persistent_store_with_payload):
    """When SessionRegistry has no persistent_session_store, touch behaves as Phase 7."""
    r = SessionRegistry()  # no persistent_session_store
    s = r.touch("known-sid")
    assert s.live_overlay == {}
    assert s.attached_profile is None
    assert s.enabled is True
