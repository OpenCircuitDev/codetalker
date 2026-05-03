"""Tests for auto-reattach of last_profile_for_cwd on session touch."""
import pytest
from pathlib import Path
from claude_code_talker.sessions import SessionRegistry
from claude_code_talker.profiles import ProfileStore


@pytest.fixture
def profiles_with_marvin(tmp_path):
    p = ProfileStore(profiles_dir=tmp_path)
    p.save("marvin", {"voice": {"model": "marvin"}})
    return p


def test_first_touch_for_cwd_with_last_profile_auto_attaches(profiles_with_marvin):
    profiles_with_marvin.set_last_profile_for_cwd("/proj/a", "marvin")
    r = SessionRegistry(profile_store=profiles_with_marvin)
    s = r.touch("new-session", cwd="/proj/a")
    assert s.attached_profile == "marvin"


def test_subsequent_touch_does_not_reset_attached_profile(profiles_with_marvin):
    profiles_with_marvin.set_last_profile_for_cwd("/proj/a", "marvin")
    r = SessionRegistry(profile_store=profiles_with_marvin)
    r.touch("s1", cwd="/proj/a")
    # User detaches manually
    r.detach_profile("s1")
    # Next hook for the same session must NOT re-attach
    r.touch("s1", cwd="/proj/a")
    assert r.get("s1").attached_profile is None


def test_touch_without_cwd_does_not_reattach(profiles_with_marvin):
    profiles_with_marvin.set_last_profile_for_cwd("/proj/a", "marvin")
    r = SessionRegistry(profile_store=profiles_with_marvin)
    s = r.touch("s1")  # no cwd
    assert s.attached_profile is None


def test_touch_with_unknown_cwd_does_not_attach(profiles_with_marvin):
    r = SessionRegistry(profile_store=profiles_with_marvin)
    s = r.touch("s1", cwd="/proj/never-seen")
    assert s.attached_profile is None
