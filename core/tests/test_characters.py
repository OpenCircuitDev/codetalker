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


def test_character_store_save_creates_file_at_expected_path(tmp_path):
    store = CharacterStore(characters_dir=tmp_path / "chars")
    c = Character(id="alice", display_name="Alice", voice_ref="v")
    p = store.save(c)
    assert p.exists()
    assert p.name == "alice.yaml"


def test_character_store_save_sets_created_and_updated_at(tmp_path):
    store = CharacterStore(characters_dir=tmp_path / "chars")
    c = Character(id="alice", display_name="Alice", voice_ref="v")
    store.save(c)
    loaded = store.get("alice")
    assert loaded.created_at > 0
    assert loaded.updated_at > 0


def test_character_store_save_preserves_created_at_updates_updated_at(tmp_path):
    store = CharacterStore(characters_dir=tmp_path / "chars")
    c = Character(id="alice", display_name="Alice", voice_ref="v")
    store.save(c)
    first_created = store.get("alice").created_at
    time.sleep(0.01)
    c2 = store.get("alice")
    c2.display_name = "Alice II"
    store.save(c2)
    final = store.get("alice")
    assert final.created_at == first_created
    assert final.updated_at > first_created
    assert final.display_name == "Alice II"


def test_character_store_get_returns_none_for_missing(tmp_path):
    store = CharacterStore(characters_dir=tmp_path / "chars")
    assert store.get("nope") is None


def test_character_store_get_returns_none_for_invalid_id(tmp_path):
    store = CharacterStore(characters_dir=tmp_path / "chars")
    assert store.get("../etc/passwd") is None
    assert store.get("UPPER") is None
    assert store.get("") is None


def test_character_store_list_sorted_by_display_name_case_insensitive(tmp_path):
    store = CharacterStore(characters_dir=tmp_path / "chars")
    store.save(Character(id="b", display_name="zebra", voice_ref="v"))
    store.save(Character(id="a", display_name="apple", voice_ref="v"))
    store.save(Character(id="c", display_name="Banana", voice_ref="v"))
    names = [c.display_name for c in store.list()]
    assert names == ["apple", "Banana", "zebra"]


def test_character_store_list_empty_when_dir_missing(tmp_path):
    store = CharacterStore(characters_dir=tmp_path / "nonexistent")
    assert store.list() == []


def test_character_store_list_skips_malformed_yaml(tmp_path):
    d = tmp_path / "chars"
    d.mkdir()
    (d / "good.yaml").write_text("id: good\ndisplay_name: G\nvoice_ref: v\n", encoding="utf-8")
    (d / "broken.yaml").write_text("not: valid: yaml: here", encoding="utf-8")
    store = CharacterStore(characters_dir=d)
    chars = store.list()
    assert [c.id for c in chars] == ["good"]


def test_character_store_delete_returns_true_when_existed(tmp_path):
    store = CharacterStore(characters_dir=tmp_path / "chars")
    store.save(Character(id="alice", display_name="Alice", voice_ref="v"))
    assert store.delete("alice") is True
    assert store.get("alice") is None


def test_character_store_delete_returns_false_when_missing(tmp_path):
    store = CharacterStore(characters_dir=tmp_path / "chars")
    assert store.delete("nope") is False


def test_character_store_delete_rejects_invalid_id(tmp_path):
    store = CharacterStore(characters_dir=tmp_path / "chars")
    assert store.delete("../etc/passwd") is False


def test_character_store_save_calls_validate(tmp_path):
    store = CharacterStore(characters_dir=tmp_path / "chars")
    c = Character(id="BAD-ID", display_name="X", voice_ref="v")
    with pytest.raises(CharacterValidationError):
        store.save(c)
