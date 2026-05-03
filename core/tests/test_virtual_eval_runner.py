"""Tests for virtual_eval.runner sample selection."""
import json
import pytest
import time
from pathlib import Path

from claude_code_talker.narration_log import NarrationLog, NarrationEntry
from claude_code_talker.virtual_eval.runner import (
    EvalRequest, select_narration_sample,
)


@pytest.fixture
def populated_log(tmp_path):
    log = NarrationLog(log_path=tmp_path / "narration.jsonl",
                       max_bytes=10 * 1024 * 1024)
    base_ts = 1000.0
    # 10 entries per mode across the 5 in-scope modes
    for mode in ("live", "live-stream", "brief", "prompt-brief", "chat"):
        for i in range(10):
            log.append(NarrationEntry(
                timestamp=base_ts + i, session_id=f"sid-{mode}",
                text=f"narration {mode} {i}", voice="v", engine="e", mode=mode,
            ))
    # Plus 5 entries with an out-of-scope mode (should be filtered out)
    for i in range(5):
        log.append(NarrationEntry(
            timestamp=base_ts + i, session_id="x", text="excluded",
            voice="v", engine="e", mode="some-other-mode",
        ))
    return log


def test_eval_request_defaults():
    req = EvalRequest()
    assert req.max_narrations == 50
    assert req.deployed_at == 0.0
    assert "live" in req.included_modes


def test_select_returns_all_when_under_cap(populated_log):
    req = EvalRequest(max_narrations=200, deployed_at=0.0)
    sample = select_narration_sample(populated_log, req)
    # 50 in-scope entries (10 per mode × 5 modes); 5 excluded
    assert len(sample) == 50
    assert all(s["mode"] != "some-other-mode" for s in sample)


def test_select_filters_by_deployed_at(populated_log):
    # Only entries with timestamp >= 1005 should survive
    req = EvalRequest(max_narrations=200, deployed_at=1005.0)
    sample = select_narration_sample(populated_log, req)
    assert len(sample) == 25  # 5 modes × 5 surviving entries each (i=5..9)
    assert all(s["timestamp"] >= 1005.0 for s in sample)


def test_select_stratified_when_over_cap(populated_log):
    # Cap = 10 → 2 per mode (10 / 5 modes)
    req = EvalRequest(max_narrations=10, deployed_at=0.0)
    sample = select_narration_sample(populated_log, req)
    assert len(sample) == 10
    by_mode: dict[str, int] = {}
    for s in sample:
        by_mode[s["mode"]] = by_mode.get(s["mode"], 0) + 1
    # All 5 modes represented
    assert len(by_mode) == 5
    # ~2 per mode
    for count in by_mode.values():
        assert 1 <= count <= 3


def test_select_returns_empty_when_log_empty(tmp_path):
    log = NarrationLog(log_path=tmp_path / "narration.jsonl")
    req = EvalRequest()
    assert select_narration_sample(log, req) == []


def test_select_cap_zero_returns_empty(populated_log):
    """max_narrations=0 yields an empty sample (defensive boundary)."""
    req = EvalRequest(max_narrations=0, deployed_at=0.0)
    sample = select_narration_sample(populated_log, req)
    assert sample == []


# ---------------------------------------------------------------------------
# Task 3: PersonaScore, build_score_prompt, parse_score_response, run_eval_batch
# ---------------------------------------------------------------------------
import asyncio
from unittest.mock import AsyncMock, MagicMock
from claude_code_talker.virtual_eval.personas import Persona
from claude_code_talker.virtual_eval.runner import (
    PersonaScore, build_score_prompt, parse_score_response, run_eval_batch,
)


def test_persona_score_dataclass_fields():
    s = PersonaScore(persona_name="Riley", narration_text="x",
                     clarity=4, helpfulness=3, jargon_load=5,
                     confusing_terms=["CTE"], missing_context="why does this matter?")
    assert s.persona_name == "Riley"
    assert s.clarity == 4


def test_build_score_prompt_includes_persona_context():
    p = Persona(name="Sam", role="PM", primary_lens="audio",
                comfort_with_jargon=1, what_they_care_about="why")
    prompt = build_score_prompt(p, "Editing api.py to add the per-mode dropdown.")
    assert "Sam" in prompt
    assert "PM" in prompt
    assert "Editing api.py" in prompt
    assert "JSON" in prompt


def test_parse_score_response_handles_clean_json():
    raw = '{"clarity": 4, "helpfulness": 5, "jargon_load": 3, "confusing_terms": ["CTE"], "missing_context": "why"}'
    s = parse_score_response("Riley", "narration text", raw)
    assert s.persona_name == "Riley"
    assert s.clarity == 4
    assert s.confusing_terms == ["CTE"]


def test_parse_score_response_clamps_out_of_range():
    raw = '{"clarity": 10, "helpfulness": -1, "jargon_load": 99, "confusing_terms": [], "missing_context": ""}'
    s = parse_score_response("X", "n", raw)
    assert 1 <= s.clarity <= 5
    assert 1 <= s.helpfulness <= 5
    assert 1 <= s.jargon_load <= 5


def test_parse_score_response_falls_back_on_garbage():
    s = parse_score_response("X", "n", "not json")
    # Should produce a placeholder score with neutral 3s rather than raise
    assert s.clarity == 3
    assert s.helpfulness == 3
    assert s.confusing_terms == []


def test_parse_score_response_extracts_expected_received():
    raw = '{"clarity":4,"helpfulness":4,"jargon_load":2,"expectation_match":3,"expected":"a brief WHY","received":"a list of files","confusing_terms":[],"missing_context":""}'
    s = parse_score_response("X", "n", raw)
    assert s.expected == "a brief WHY"
    assert s.received == "a list of files"
    assert s.expectation_match == 3


def test_build_score_prompt_with_narration_with_context_includes_session_state():
    from claude_code_talker.virtual_eval.context import NarrationWithContext
    p = Persona(name="X", role="r", primary_lens="l", comfort_with_jargon=3, what_they_care_about="w")
    nwc = NarrationWithContext(
        text="latest narration", session_id="sid", timestamp=1.0,
        prior_narrations=["[live] earlier-A", "[live] earlier-B"],
        last_user_prompt="please add the feature",
        recent_transcript_lines=["USER: please add the feature", "ASSISTANT: working on it"],
    )
    prompt = build_score_prompt(p, nwc)
    assert "please add the feature" in prompt
    assert "earlier-A" in prompt
    assert "USER: please add the feature" in prompt
    assert "latest narration" in prompt
    # The two-step exercise prompt must mention "expected"/"step 1" and "received"/"step 2"
    assert "expected" in prompt.lower()
    assert "received" in prompt.lower()


@pytest.mark.asyncio
async def test_run_eval_batch_calls_provider_per_pair():
    p1 = Persona(name="A", role="r", primary_lens="l", comfort_with_jargon=3, what_they_care_about="w")
    p2 = Persona(name="B", role="r", primary_lens="l", comfort_with_jargon=3, what_they_care_about="w")
    sample = [{"text": "n1", "session_id": "s1"}, {"text": "n2", "session_id": "s2"}]
    provider = MagicMock()
    provider.complete = AsyncMock(
        return_value='{"clarity":4,"helpfulness":4,"jargon_load":2,"expectation_match":4,"expected":"x","received":"y","confusing_terms":[],"missing_context":""}'
    )
    scores = await run_eval_batch([p1, p2], sample, provider, batch_size=2)
    # 2 personas × 2 narrations = 4 calls
    assert provider.complete.await_count == 4
    assert len(scores) == 4


@pytest.mark.asyncio
async def test_run_eval_batch_handles_provider_failure_gracefully():
    p = Persona(name="A", role="r", primary_lens="l", comfort_with_jargon=3, what_they_care_about="w")
    sample = [{"text": "n", "session_id": "s"}]
    provider = MagicMock()
    provider.complete = AsyncMock(side_effect=RuntimeError("provider down"))
    scores = await run_eval_batch([p], sample, provider, batch_size=1)
    assert len(scores) == 1
    # Failed call → neutral fallback score
    assert scores[0].clarity == 3
