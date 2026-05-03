"""Tests for teacher mode prompt directives."""
import pytest
from claude_code_talker.teacher_mode import (
    teacher_directives,
    merge_teacher_into_prompt,
    DEFAULT_TEACHER_CONFIG,
)


def test_disabled_returns_empty():
    """Explicitly-disabled returns empty. None and {} now default to ENABLED
    (user-locked default 2026-05-03), so they return a non-empty block."""
    assert teacher_directives({"enabled": False}) == ""
    # None and empty dict get the default enabled=True applied → non-empty.
    assert teacher_directives(None) == ""
    assert teacher_directives({}) != ""  # default enabled=True applies


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
    # None means "no teacher cfg present" — also a noop (per the explicit
    # None-vs-{} distinction in teacher_directives docstring).
    out2 = merge_teacher_into_prompt("BASE PROMPT", None)
    assert out2 == "BASE PROMPT"


def test_default_config_is_enabled_at_depth_3():
    # User-locked defaults 2026-05-03: teacher mode is ON by default at
    # depth 3 with concise verbosity and combined granularity.
    assert DEFAULT_TEACHER_CONFIG["enabled"] is True
    assert DEFAULT_TEACHER_CONFIG["depth_level"] == 3
    assert DEFAULT_TEACHER_CONFIG["substitution"] is False
    assert DEFAULT_TEACHER_CONFIG["glossary"] is False
    assert DEFAULT_TEACHER_CONFIG["reframe"] is False
    assert DEFAULT_TEACHER_CONFIG["verbosity"] == "standard"
    assert DEFAULT_TEACHER_CONFIG["granularity"] == "combined"


def test_verbosity_directive_in_block():
    block = teacher_directives({"enabled": True, "verbosity": "expanded"})
    assert "expanded" in block.lower() or "≤150" in block or "150" in block


def test_granularity_directive_in_block():
    block = teacher_directives({"enabled": True, "granularity": "per-file"})
    assert "per-file" in block.lower() or "each distinct file" in block.lower()


def test_max_tokens_for_respects_verbosity():
    from claude_code_talker.teacher_mode import max_tokens_for, VERBOSITY_TOKEN_BUDGET
    assert max_tokens_for({"enabled": True, "verbosity": "concise"}) == VERBOSITY_TOKEN_BUDGET["concise"]
    assert max_tokens_for({"enabled": True, "verbosity": "standard"}) == VERBOSITY_TOKEN_BUDGET["standard"]
    assert max_tokens_for({"enabled": True, "verbosity": "expanded"}) == VERBOSITY_TOKEN_BUDGET["expanded"]


def test_max_tokens_for_returns_default_when_disabled():
    from claude_code_talker.teacher_mode import max_tokens_for
    assert max_tokens_for({"enabled": False}, default=999) == 999
    assert max_tokens_for(None, default=999) == 999
