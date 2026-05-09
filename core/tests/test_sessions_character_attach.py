"""Phase 25a — session attach lifecycle + cfg merge precedence tests."""
from __future__ import annotations

from pathlib import Path

import pytest

from claude_code_talker.characters import Character, CharacterStore
from claude_code_talker.sessions import LiveSession


def test_live_session_has_attached_character_field():
    s = LiveSession(session_id="abc", cwd="/tmp", last_hook_at=0.0)
    assert hasattr(s, "attached_character")
    assert s.attached_character is None


def test_live_session_attached_character_setter():
    s = LiveSession(session_id="abc", cwd="/tmp", last_hook_at=0.0)
    s.attached_character = "alice"
    assert s.attached_character == "alice"


def test_resolve_for_session_with_character_overrides_voice_and_persona(tmp_path):
    from claude_code_talker.config import resolve_for_session
    from claude_code_talker.profiles import ProfileStore

    base = {"voice": {"engine": "piper", "model": "default-voice", "rate": 1.0}, "triggers": {"persona": "warm"}}
    profile_store = ProfileStore(profiles_dir=tmp_path / "profiles")
    char_store = CharacterStore(characters_dir=tmp_path / "chars")
    char_store.save(Character(id="alice", display_name="Alice", voice_ref="alice-voice", persona="methodical"))

    s = LiveSession(session_id="abc", cwd="/tmp", last_hook_at=0.0)
    s.attached_character = "alice"

    resolved = resolve_for_session(base, s, profile_store, char_store)
    assert resolved["voice"]["model"] == "alice-voice"
    assert resolved["triggers"]["persona"] == "methodical"
    assert resolved["voice"]["engine"] == "piper"  # base preserved
    assert resolved["voice"]["rate"] == 1.0


def test_resolve_for_session_overlay_beats_character(tmp_path):
    from claude_code_talker.config import resolve_for_session
    from claude_code_talker.profiles import ProfileStore

    base = {"voice": {"model": "default"}, "triggers": {"persona": "warm"}}
    profile_store = ProfileStore(profiles_dir=tmp_path / "profiles")
    char_store = CharacterStore(characters_dir=tmp_path / "chars")
    char_store.save(Character(id="alice", display_name="Alice", voice_ref="alice-voice", persona="methodical"))

    s = LiveSession(session_id="abc", cwd="/tmp", last_hook_at=0.0)
    s.attached_character = "alice"
    s.live_overlay = {"voice": {"model": "override-voice"}}

    resolved = resolve_for_session(base, s, profile_store, char_store)
    assert resolved["voice"]["model"] == "override-voice"  # overlay wins
    assert resolved["triggers"]["persona"] == "methodical"  # character still wins for persona


def test_resolve_for_session_dangling_character_falls_back(tmp_path):
    from claude_code_talker.config import resolve_for_session
    from claude_code_talker.profiles import ProfileStore

    base = {"voice": {"model": "default"}, "triggers": {"persona": "warm"}}
    profile_store = ProfileStore(profiles_dir=tmp_path / "profiles")
    char_store = CharacterStore(characters_dir=tmp_path / "chars")  # empty

    s = LiveSession(session_id="abc", cwd="/tmp", last_hook_at=0.0)
    s.attached_character = "missing-char"

    # Should not raise; character missing → fall back to base
    resolved = resolve_for_session(base, s, profile_store, char_store)
    assert resolved["voice"]["model"] == "default"
    assert resolved["triggers"]["persona"] == "warm"


def test_resolve_for_session_character_store_none_is_safe(tmp_path):
    from claude_code_talker.config import resolve_for_session
    from claude_code_talker.profiles import ProfileStore

    base = {"voice": {"model": "default"}}
    profile_store = ProfileStore(profiles_dir=tmp_path / "profiles")

    s = LiveSession(session_id="abc", cwd="/tmp", last_hook_at=0.0)
    s.attached_character = "alice"  # set but no store

    resolved = resolve_for_session(base, s, profile_store, None)
    assert resolved["voice"]["model"] == "default"  # graceful fallback
