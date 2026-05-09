"""Phase 18.4 — assert the static-shell + body split is round-trip equivalent."""
import pytest

from claude_code_talker.triggers.tags import (
    STARTER_TAGS,
    Tag,
    TagLibrary,
    compose_skill_body,
    compose_skill_content,
    compose_skill_static_shell,
)


def _seed_lib(enabled_ids: set[str]) -> TagLibrary:
    lib = TagLibrary()
    for t in STARTER_TAGS:
        copy = Tag(
            id=t.id,
            display_name=t.display_name,
            enabled=(t.id in enabled_ids),
            editor_mode=t.editor_mode,
            when_to_trigger=t.when_to_trigger,
            format_template=t.format_template,
            example=t.example,
            freeform_text=t.freeform_text,
        )
        lib.add(copy)
    return lib


@pytest.mark.parametrize(
    "enabled,teacher,persona",
    [
        ({"audible_summary"}, "standard", "methodical"),
        ({"audible_summary", "audible_briefs"}, "plain", "methodical"),
        ({"audible_summary", "audible_details"}, "technical", "warm"),
        (set(), "standard", "methodical"),  # no enabled tags
    ],
)
def test_split_round_trips(enabled, teacher, persona):
    lib = _seed_lib(enabled)
    full = compose_skill_content(lib, teacher_level=teacher, persona=persona)
    rebuilt = compose_skill_static_shell() + "\n" + compose_skill_body(
        lib, teacher_level=teacher, persona=persona,
    )
    assert full == rebuilt


def test_static_shell_contains_frontmatter_and_intro():
    shell = compose_skill_static_shell()
    assert shell.startswith("---\n")
    assert "name: codetalker-narration" in shell
    assert "# Codetalker Narration" in shell
    # Style guidance and trigger blocks belong to the body, not the shell.
    assert "## Trigger blocks" not in shell
    assert "## Style guidance" not in shell


def test_body_contains_style_guidance_when_tags_enabled():
    lib = _seed_lib({"audible_summary"})
    body = compose_skill_body(lib)
    assert "## Trigger blocks" in body
    assert "## Style guidance" in body
    assert "Audible Summary" in body
    # Frontmatter and the welcome paragraph should NOT be in the body.
    assert body.count("---") == 0
    assert "# Codetalker Narration" not in body


def test_body_empty_state_when_no_tags_enabled():
    lib = _seed_lib(set())
    body = compose_skill_body(lib)
    assert "No tags enabled" in body
    assert "## Trigger blocks" not in body
