"""Tests for triggers.tags — Tag dataclass + TagLibrary CRUD."""
import pytest
from dataclasses import asdict
from claude_code_talker.triggers.tags import (
    Tag, TagLibrary, STARTER_TAGS, compose_skill_content, compose_skill_body,
)


def test_tag_dataclass_defaults():
    t = Tag(id="audible_summary", display_name="Audible Summary")
    assert t.enabled is False
    assert t.editor_mode == "structured"
    assert t.when_to_trigger == ""
    assert t.format_template == ""
    assert t.example == ""
    assert t.freeform_text == ""


def test_starter_tags_includes_ten_audible():
    """Phase 21: starter set is 5 generic + 5 Claude-Code-tuned = 10 total."""
    ids = {t.id for t in STARTER_TAGS}
    assert "audible_summary" in ids
    assert "audible_synopsis" in ids
    assert "audible_briefs" in ids
    assert "audible_listings" in ids
    assert "audible_details" in ids
    assert len(STARTER_TAGS) == 10


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
    assert len(lib.list()) == 10


def test_library_bootstrap_idempotent():
    lib = TagLibrary()
    lib.bootstrap_starters()
    lib.bootstrap_starters()
    assert len(lib.list()) == 10


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


def test_starter_tags_includes_claude_code_tuned_starters():
    """Phase 21: 5 new starters tuned to Claude Code's response shapes, all disabled-by-default."""
    cc_starter_ids = {
        "audible_plan_entry",
        "audible_subagent_done",
        "audible_todo_advance",
        "audible_skill_invoked",
        "audible_permission_request",
    }
    starter_ids = {t.id for t in STARTER_TAGS}
    assert cc_starter_ids.issubset(starter_ids), (
        f"missing CC-tuned starters: {cc_starter_ids - starter_ids}"
    )
    cc_starters = [t for t in STARTER_TAGS if t.id in cc_starter_ids]
    for tag in cc_starters:
        assert tag.enabled is False, f"{tag.id} must ship disabled-by-default"
        assert tag.editor_mode == "structured"
        assert tag.when_to_trigger, f"{tag.id} missing when_to_trigger"
        assert tag.format_template, f"{tag.id} missing format_template"
        assert tag.example, f"{tag.id} missing example"


@pytest.mark.parametrize("tag_id,expected_display", [
    ("audible_plan_entry", "Audible Plan Entry"),
    ("audible_subagent_done", "Audible Subagent Result"),
    ("audible_todo_advance", "Audible Todos Update"),
    ("audible_skill_invoked", "Audible Skill Invoked"),
    ("audible_permission_request", "Audible Permission Request"),
])
def test_compose_skill_body_includes_cc_tuned_tag_when_enabled(tag_id, expected_display):
    """Phase 21: each CC-tuned starter, when enabled, appears in the composed skill body."""
    lib = TagLibrary()
    for t in STARTER_TAGS:
        copy = Tag(**asdict(t))
        if copy.id == tag_id:
            copy.enabled = True
        lib.add(copy)
    body = compose_skill_body(lib)
    assert f"## {expected_display}" in body
    assert "## Trigger blocks" in body
    assert "## Style guidance" in body
