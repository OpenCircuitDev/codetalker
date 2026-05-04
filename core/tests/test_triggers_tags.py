"""Tests for triggers.tags — Tag dataclass + TagLibrary CRUD."""
import pytest
from claude_code_talker.triggers.tags import (
    Tag, TagLibrary, STARTER_TAGS, compose_skill_content,
)


def test_tag_dataclass_defaults():
    t = Tag(id="audible_summary", display_name="Audible Summary")
    assert t.enabled is False
    assert t.editor_mode == "structured"
    assert t.when_to_trigger == ""
    assert t.format_template == ""
    assert t.example == ""
    assert t.freeform_text == ""


def test_starter_tags_includes_five_audible():
    ids = {t.id for t in STARTER_TAGS}
    assert "audible_summary" in ids
    assert "audible_synopsis" in ids
    assert "audible_briefs" in ids
    assert "audible_listings" in ids
    assert "audible_details" in ids
    assert len(STARTER_TAGS) == 5


def test_starter_only_summary_enabled_by_default():
    enabled = [t for t in STARTER_TAGS if t.enabled]
    assert len(enabled) == 1
    assert enabled[0].id == "audible_summary"


def test_library_add_get_delete():
    lib = TagLibrary()
    t = Tag(id="audible_test", display_name="Audible Test", enabled=True)
    lib.add(t)
    assert lib.get("audible_test") is t
    assert "audible_test" in lib.enabled_ids()
    lib.delete("audible_test")
    assert lib.get("audible_test") is None


def test_library_update_merges_fields():
    lib = TagLibrary()
    lib.add(Tag(id="x", display_name="Audible X", enabled=False))
    lib.update("x", enabled=True, when_to_trigger="when X happens")
    assert lib.get("x").enabled is True
    assert lib.get("x").when_to_trigger == "when X happens"


def test_library_bootstrap_loads_starter_when_missing():
    lib = TagLibrary()
    assert len(lib.list()) == 0
    lib.bootstrap_starters()
    assert len(lib.list()) == 5


def test_library_bootstrap_idempotent():
    lib = TagLibrary()
    lib.bootstrap_starters()
    lib.bootstrap_starters()
    assert len(lib.list()) == 5


def test_compose_skill_includes_enabled_only():
    lib = TagLibrary()
    lib.add(Tag(id="audible_summary", display_name="Audible Summary",
                enabled=True, when_to_trigger="when X",
                format_template="≤60 words", example="example text"))
    lib.add(Tag(id="audible_synopsis", display_name="Audible Synopsis",
                enabled=False, when_to_trigger="when Y"))
    out = compose_skill_content(lib, teacher_level="standard", persona="methodical")
    assert "Audible Summary" in out
    assert "Audible Synopsis" not in out


def test_compose_skill_freeform_uses_freeform_text():
    lib = TagLibrary()
    lib.add(Tag(id="x", display_name="Audible X", enabled=True,
                editor_mode="freeform",
                freeform_text="Use this exact wording every time."))
    out = compose_skill_content(lib, teacher_level="standard", persona="methodical")
    assert "Use this exact wording" in out


def test_compose_skill_structured_uses_fields():
    lib = TagLibrary()
    lib.add(Tag(id="x", display_name="Audible X", enabled=True,
                editor_mode="structured",
                when_to_trigger="when foo", format_template="one paragraph",
                example="Foo example."))
    out = compose_skill_content(lib, teacher_level="plain", persona="energetic")
    assert "when foo" in out
    assert "Foo example" in out
    assert "energetic" in out.lower()
