"""Phase 25a — Character dataclass + CharacterStore tests."""
from __future__ import annotations

import time

import pytest

from claude_code_talker.characters import (
    Character,
    CharacterStore,
    CharacterValidationError,
    VALID_PERSONAS,
)


def test_character_validate_accepts_valid_record():
    c = Character(id="my-char", display_name="My Character", voice_ref="en_US-amy-medium", persona="methodical")
    c.validate()  # no raise


def test_character_validate_rejects_uppercase_id():
    c = Character(id="My-Char", display_name="X", voice_ref="v")
    with pytest.raises(CharacterValidationError, match="kebab-case"):
        c.validate()


def test_character_validate_rejects_id_with_spaces():
    c = Character(id="my char", display_name="X", voice_ref="v")
    with pytest.raises(CharacterValidationError):
        c.validate()


def test_character_validate_rejects_id_with_leading_dash():
    c = Character(id="-bad", display_name="X", voice_ref="v")
    with pytest.raises(CharacterValidationError):
        c.validate()


def test_character_validate_rejects_empty_display_name():
    c = Character(id="x", display_name="  ", voice_ref="v")
    with pytest.raises(CharacterValidationError, match="display_name"):
        c.validate()


def test_character_validate_rejects_empty_voice_ref():
    c = Character(id="x", display_name="Name", voice_ref="")
    with pytest.raises(CharacterValidationError, match="voice_ref"):
        c.validate()


def test_character_validate_rejects_unknown_persona():
    c = Character(id="x", display_name="N", voice_ref="v", persona="grumpy")
    with pytest.raises(CharacterValidationError, match="persona"):
        c.validate()


def test_character_validate_accepts_all_known_personas():
    for p in VALID_PERSONAS:
        c = Character(id="x", display_name="N", voice_ref="v", persona=p)
        c.validate()  # no raise


def test_character_from_dict_tolerates_missing_optional_fields():
    c = Character.from_dict({"id": "x", "display_name": "N", "voice_ref": "v"})
    assert c.persona == "methodical"
    assert c.mesh_path is None
    assert c.mesh_provider is None
    assert c.mesh_prompt is None
    assert c.mesh_prompt_history == []
    assert c.created_at == 0.0
    assert c.updated_at == 0.0


def test_character_from_dict_drops_unknown_fields():
    c = Character.from_dict({"id": "x", "display_name": "N", "voice_ref": "v", "color": "red"})
    assert not hasattr(c, "color")
    assert c.id == "x"


def test_character_to_dict_round_trips():
    c = Character(
        id="x", display_name="N", voice_ref="v",
        mesh_prompt_history=["a", "b"], created_at=1000.0, updated_at=2000.0,
    )
    d = c.to_dict()
    c2 = Character.from_dict(d)
    assert c == c2
