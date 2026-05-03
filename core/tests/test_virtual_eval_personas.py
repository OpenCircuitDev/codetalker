"""Tests for virtual_eval.personas."""
import pytest
from claude_code_talker.virtual_eval.personas import (
    Persona, validate_personas, build_generation_prompt, parse_personas_response,
)


def test_persona_dataclass_fields():
    p = Persona(name="Riley", role="Junior dev",
                primary_lens="audio listener", comfort_with_jargon=2,
                what_they_care_about="why over what")
    assert p.name == "Riley"
    assert p.comfort_with_jargon == 2


def test_validate_personas_accepts_5_valid():
    raw = [
        {"name": "Riley", "role": "Junior backend dev (8mo)",
         "primary_lens": "audio listener while pair-programming",
         "comfort_with_jargon": 2,
         "what_they_care_about": "why a change is happening"},
    ] * 5
    out = validate_personas(raw)
    assert len(out) == 5
    assert all(isinstance(p, Persona) for p in out)


def test_validate_personas_rejects_wrong_count():
    with pytest.raises(ValueError, match="exactly 5"):
        validate_personas([{"name": "x"}] * 3)


def test_validate_personas_rejects_missing_field():
    raw = [{"name": "x", "role": "y"}] * 5  # missing other required fields
    with pytest.raises(ValueError, match="missing"):
        validate_personas(raw)


def test_validate_personas_clamps_jargon_comfort():
    raw = [
        {"name": f"P{i}", "role": "r", "primary_lens": "l",
         "comfort_with_jargon": 99, "what_they_care_about": "x"}
        for i in range(5)
    ]
    out = validate_personas(raw)
    # Should clamp 99 → 5 (max valid)
    for p in out:
        assert 1 <= p.comfort_with_jargon <= 5


def test_build_generation_prompt_includes_diversity_dimensions():
    prompt = build_generation_prompt()
    assert "5" in prompt
    assert "English-native" in prompt or "English" in prompt
    assert "JSON" in prompt


def test_build_generation_prompt_targets_vibe_developers():
    """Personas must specifically be vibe coders/devs — codetalker's actual users."""
    prompt = build_generation_prompt()
    assert "vibe" in prompt.lower()
    assert "claude code" in prompt.lower() or "AI assistant" in prompt or "AI" in prompt


def test_build_generation_prompt_requires_2d_spectrum():
    """Personas must span both axes: vibe-coding experience × domain expertise."""
    prompt = build_generation_prompt()
    text = prompt.lower()
    # AXIS A: vibe-coding experience
    assert "fresh-to-ai" in text or "first week" in text or "new vibe" in text
    assert "power user" in text or "veteran vibe" in text or "power vibe" in text
    # AXIS B: domain expertise
    assert "novice" in text
    assert "expert" in text or "staff" in text or "principal" in text
    # The 2x2 corners (and middle) must be named
    assert "new vibe" in text and "new domain" in text
    assert "veteran" in text or "power" in text
    assert "mid" in text


def test_parse_personas_response_handles_clean_json():
    raw_response = '''[
        {"name": "A", "role": "r1", "primary_lens": "l1", "comfort_with_jargon": 3, "what_they_care_about": "w1"},
        {"name": "B", "role": "r2", "primary_lens": "l2", "comfort_with_jargon": 4, "what_they_care_about": "w2"},
        {"name": "C", "role": "r3", "primary_lens": "l3", "comfort_with_jargon": 1, "what_they_care_about": "w3"},
        {"name": "D", "role": "r4", "primary_lens": "l4", "comfort_with_jargon": 2, "what_they_care_about": "w4"},
        {"name": "E", "role": "r5", "primary_lens": "l5", "comfort_with_jargon": 5, "what_they_care_about": "w5"}
    ]'''
    personas = parse_personas_response(raw_response)
    assert len(personas) == 5


def test_parse_personas_response_strips_markdown_fence():
    raw = '```json\n[' + ','.join(
        ['{"name":"P","role":"r","primary_lens":"l","comfort_with_jargon":3,"what_they_care_about":"w"}'] * 5
    ) + ']\n```'
    personas = parse_personas_response(raw)
    assert len(personas) == 5


def test_parse_personas_response_raises_on_garbage():
    with pytest.raises(ValueError):
        parse_personas_response("not json at all")


def test_validate_personas_non_int_jargon_falls_back_to_3():
    """When comfort_with_jargon isn't coercible to int, fall back to 3 (neutral)."""
    raw = [
        {"name": f"P{i}", "role": "r", "primary_lens": "l",
         "comfort_with_jargon": "not-an-int", "what_they_care_about": "x"}
        for i in range(5)
    ]
    out = validate_personas(raw)
    for p in out:
        assert p.comfort_with_jargon == 3
