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
