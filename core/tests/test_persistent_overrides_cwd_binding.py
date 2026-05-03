"""Regression: persistent settings WIN over cwd-binding when both apply."""
import pytest
from pathlib import Path
from claude_code_talker.sessions import SessionRegistry
from claude_code_talker.profiles import ProfileStore
from claude_code_talker.persistent_sessions import PersistentSessionStore


@pytest.fixture
def stores(tmp_path):
    profiles = ProfileStore(profiles_dir=tmp_path / "profiles")
    persistent = PersistentSessionStore(sessions_dir=tmp_path / "persistent")
    profiles.save("from-binding", {"voice": {"model": "jenny"}})
    profiles.save("from-persistent", {"voice": {"model": "marvin"}})
    return profiles, persistent


def test_persistent_wins_over_cwd_binding(stores):
    profiles, persistent = stores
    profiles.set_last_profile_for_cwd("/proj/a", "from-binding")
    persistent.save("sid-1", {
        "live_overlay": {}, "attached_profile": "from-persistent",
        "enabled": True, "display_name": None, "last_modified": 1.0,
    })
    r = SessionRegistry(profile_store=profiles, persistent_session_store=persistent)
    s = r.touch("sid-1", cwd="/proj/a")
    assert s.attached_profile == "from-persistent"


def test_cwd_binding_used_when_no_persistent(stores):
    profiles, persistent = stores
    profiles.set_last_profile_for_cwd("/proj/b", "from-binding")
    r = SessionRegistry(profile_store=profiles, persistent_session_store=persistent)
    s = r.touch("sid-2", cwd="/proj/b")
    assert s.attached_profile == "from-binding"


def test_neither_present_means_no_attached_profile(stores):
    profiles, persistent = stores
    r = SessionRegistry(profile_store=profiles, persistent_session_store=persistent)
    s = r.touch("sid-3", cwd="/proj/never-seen")
    assert s.attached_profile is None
