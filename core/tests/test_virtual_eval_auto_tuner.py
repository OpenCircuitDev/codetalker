"""Tests for virtual_eval.auto_tuner."""
import pytest
from unittest.mock import AsyncMock, MagicMock

from claude_code_talker.virtual_eval.aggregator import AggregateReport
from claude_code_talker.virtual_eval.auto_tuner import (
    propose_tuning, TUNABLE_FIELDS, MAX_FIELDS_PER_PASS, parse_tuning_response,
    TUNING_PROMPT_TEMPLATE,
)


def test_tuning_prompt_template_includes_signal_to_knob_rubric():
    # The template should explicitly help the LLM map signal types to knobs
    assert "Signal" in TUNING_PROMPT_TEMPLATE or "rubric" in TUNING_PROMPT_TEMPLATE.lower()
    # Specifically: the missing-context-about-filenames signal should NOT default
    # to verbosity. Make sure the rubric calls this out.
    assert "prompt_directive_extras" in TUNING_PROMPT_TEMPLATE
    assert "verbosity" in TUNING_PROMPT_TEMPLATE


def test_tuning_prompt_template_warns_against_verbosity_for_content_gaps():
    """The template must explicitly tell the LLM not to pick verbosity when
    the signal is missing-content (filenames, commands, outcomes)."""
    template = TUNING_PROMPT_TEMPLATE.lower()
    # Some phrasing along the lines of: missing concrete details → directive
    assert ("missing context" in template or "missing-context" in template)
    # And explicitly: don't pick verbosity for content gaps
    assert "content" in template or "concrete" in template


def test_tuning_prompt_template_maps_jargon_to_glossary_or_extras():
    """Personas flagging specific terms → glossary OR prompt_directive_extras
    (definition snippet), not verbosity/depth."""
    template = TUNING_PROMPT_TEMPLATE.lower()
    # Should mention glossary / substitution / definition for jargon
    assert ("glossary" in template and ("jargon" in template or "term" in template))


def test_tunable_fields_locked():
    # The user-locked tunable fields per spec
    assert "depth_level" in TUNABLE_FIELDS
    assert "verbosity" in TUNABLE_FIELDS
    assert "granularity" in TUNABLE_FIELDS
    assert "substitution" in TUNABLE_FIELDS
    assert "glossary" in TUNABLE_FIELDS
    assert "reframe" in TUNABLE_FIELDS
    assert "prompt_directive_extras" in TUNABLE_FIELDS


def test_max_fields_per_pass_default():
    assert MAX_FIELDS_PER_PASS == 3


def test_parse_tuning_response_clean_json():
    raw = '{"fields_to_set": {"depth_level": 4, "glossary": true}, "reasoning": "personas asked"}'
    result = parse_tuning_response(raw)
    assert result["fields_to_set"] == {"depth_level": 4, "glossary": True}
    assert "personas" in result["reasoning"]


def test_parse_tuning_response_strips_unknown_fields():
    raw = '{"fields_to_set": {"depth_level": 4, "wat": "x"}, "reasoning": "r"}'
    result = parse_tuning_response(raw)
    assert "depth_level" in result["fields_to_set"]
    assert "wat" not in result["fields_to_set"]


def test_parse_tuning_response_validates_bounds():
    raw = '{"fields_to_set": {"depth_level": 99, "verbosity": "wat"}, "reasoning": "r"}'
    result = parse_tuning_response(raw)
    # depth_level clamped, verbosity rejected (not a valid value)
    assert result["fields_to_set"]["depth_level"] == 5
    assert "verbosity" not in result["fields_to_set"]


def test_parse_tuning_response_caps_extras_length():
    huge = "x" * 1000
    raw = '{"fields_to_set": {"prompt_directive_extras": "' + huge + '"}, "reasoning": "r"}'
    result = parse_tuning_response(raw)
    assert len(result["fields_to_set"]["prompt_directive_extras"]) <= 500


def test_parse_tuning_response_rejects_shell_chars_in_extras():
    raw = '{"fields_to_set": {"prompt_directive_extras": "ok\\u0000nul"}, "reasoning": "r"}'
    result = parse_tuning_response(raw)
    # null bytes stripped
    assert "\x00" not in result["fields_to_set"].get("prompt_directive_extras", "")


def test_parse_tuning_response_returns_empty_on_garbage():
    result = parse_tuning_response("not json")
    assert result["fields_to_set"] == {}


@pytest.mark.asyncio
async def test_propose_tuning_calls_provider_with_report():
    rep = AggregateReport(
        total_evals=10,
        per_persona={"A": {"clarity_avg": 3.0, "helpfulness_avg": 3.0, "jargon_load_avg": 4.0, "n": 5}},
        systemic_jargon={"cte": 3},
        missing_context_samples=["why does this matter"],
        overall={"clarity_avg": 3.0, "helpfulness_avg": 3.0, "jargon_load_avg": 4.0},
    )
    provider = MagicMock()
    provider.complete = AsyncMock(
        return_value='{"fields_to_set": {"glossary": true}, "reasoning": "cte unclear"}'
    )
    out = await propose_tuning(rep, current_cfg={"glossary": False}, provider=provider)
    assert out["fields_to_set"] == {"glossary": True}
    assert "cte" in out["reasoning"].lower()
    # Verify the prompt mentioned the systemic jargon
    sent_prompt = provider.complete.call_args[0][0]
    assert "cte" in sent_prompt.lower()


@pytest.mark.asyncio
async def test_propose_tuning_max_divergence_gate_marks_pending(monkeypatch):
    rep = AggregateReport(total_evals=1, overall={"clarity_avg": 2.0})
    provider = MagicMock()
    # Propose 5 changes — exceeds MAX_FIELDS_PER_PASS
    provider.complete = AsyncMock(return_value='''{
        "fields_to_set": {"depth_level": 4, "verbosity": "expanded", "glossary": true,
                          "substitution": true, "reframe": true},
        "reasoning": "everything"
    }''')
    out = await propose_tuning(rep, current_cfg={}, provider=provider)
    assert out["pending_approval"] is True
    assert len(out["fields_to_set"]) == 5  # all proposals preserved


@pytest.mark.asyncio
async def test_propose_tuning_below_gate_marks_applied():
    rep = AggregateReport(total_evals=1, overall={"clarity_avg": 4.0})
    provider = MagicMock()
    provider.complete = AsyncMock(return_value='{"fields_to_set": {"glossary": true}, "reasoning": "ok"}')
    out = await propose_tuning(rep, current_cfg={"glossary": False}, provider=provider)
    assert out["pending_approval"] is False


@pytest.mark.asyncio
async def test_propose_tuning_handles_provider_failure():
    rep = AggregateReport(total_evals=1)
    provider = MagicMock()
    provider.complete = AsyncMock(side_effect=RuntimeError("down"))
    out = await propose_tuning(rep, current_cfg={}, provider=provider)
    # Failed call → empty diff (no tuning), not raise
    assert out["fields_to_set"] == {}
    assert out["pending_approval"] is False
