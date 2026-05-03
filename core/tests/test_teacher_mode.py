"""Tests for teacher mode prompt directives."""
import pytest
from claude_code_talker.teacher_mode import (
    teacher_directives,
    merge_teacher_into_prompt,
    DEFAULT_TEACHER_CONFIG,
)


def test_disabled_returns_empty():
    assert teacher_directives({"enabled": False}) == ""
    assert teacher_directives(None) == ""
    assert teacher_directives({}) == ""


def test_enabled_returns_directive_block():
    block = teacher_directives({"enabled": True, "depth_level": 3})
    assert "TEACHER MODE" in block
    assert "Audience" in block


def test_depth_levels_have_distinct_audience_labels():
    blocks = [
        teacher_directives({"enabled": True, "depth_level": d})
        for d in range(1, 6)
    ]
    # Each depth should produce a different audience line
    audience_lines = []
    for b in blocks:
        for ln in b.splitlines():
            if "Audience" in ln:
                audience_lines.append(ln)
                break
    assert len(set(audience_lines)) == 5  # all distinct


def test_depth_clamped_to_valid_range():
    # depth 99 should be treated as 5 (max)
    high = teacher_directives({"enabled": True, "depth_level": 99})
    expected = teacher_directives({"enabled": True, "depth_level": 5})
    assert high == expected
    # depth 0 should be treated as 1 (min)
    low = teacher_directives({"enabled": True, "depth_level": 0})
    expected_low = teacher_directives({"enabled": True, "depth_level": 1})
    assert low == expected_low


def test_depth_invalid_falls_back_to_3():
    block = teacher_directives({"enabled": True, "depth_level": "not-a-number"})
    expected = teacher_directives({"enabled": True, "depth_level": 3})
    assert block == expected


def test_substitution_directive_only_when_enabled():
    on = teacher_directives({"enabled": True, "substitution": True})
    off = teacher_directives({"enabled": True, "substitution": False})
    assert "Substitute jargon" in on
    assert "Substitute jargon" not in off


def test_glossary_directive_only_when_enabled():
    on = teacher_directives({"enabled": True, "glossary": True})
    off = teacher_directives({"enabled": True, "glossary": False})
    assert "define it inline" in on
    assert "define it inline" not in off


def test_reframe_directive_only_when_enabled():
    on = teacher_directives({"enabled": True, "reframe": True})
    off = teacher_directives({"enabled": True, "reframe": False})
    assert "teaching moment" in on
    assert "teaching moment" not in off


def test_all_three_toggles_independent():
    block = teacher_directives({
        "enabled": True,
        "depth_level": 4,
        "substitution": True,
        "glossary": True,
        "reframe": True,
    })
    assert "Substitute jargon" in block
    assert "define it inline" in block
    assert "teaching moment" in block


def test_merge_appends_when_enabled():
    out = merge_teacher_into_prompt("BASE PROMPT", {"enabled": True})
    assert out.startswith("BASE PROMPT")
    assert "TEACHER MODE" in out


def test_merge_noop_when_disabled():
    out = merge_teacher_into_prompt("BASE PROMPT", {"enabled": False})
    assert out == "BASE PROMPT"
    out2 = merge_teacher_into_prompt("BASE PROMPT", None)
    assert out2 == "BASE PROMPT"


def test_default_config_is_disabled():
    assert DEFAULT_TEACHER_CONFIG["enabled"] is False
    assert DEFAULT_TEACHER_CONFIG["depth_level"] == 3
    assert DEFAULT_TEACHER_CONFIG["substitution"] is False
    assert DEFAULT_TEACHER_CONFIG["glossary"] is False
    assert DEFAULT_TEACHER_CONFIG["reframe"] is False
