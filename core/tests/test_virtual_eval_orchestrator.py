"""Integration tests for virtual_eval.run_eval orchestrator."""
import json
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from claude_code_talker.narration_log import NarrationLog, NarrationEntry
from claude_code_talker.virtual_eval import run_eval
from claude_code_talker.virtual_eval.history import TuningHistory


@pytest.fixture
def fixtures(tmp_path):
    log = NarrationLog(log_path=tmp_path / "narration.jsonl")
    for i in range(3):
        log.append(NarrationEntry(
            timestamp=2000.0 + i, session_id="s",
            text=f"narration {i}", voice="v", engine="e", mode="live",
        ))
    history = TuningHistory(log_path=tmp_path / "tuning.jsonl")
    overlay_path = tmp_path / "cfg-overlay.yaml"
    return log, history, overlay_path


@pytest.mark.asyncio
async def test_run_eval_full_pipeline(fixtures):
    log, history, overlay_path = fixtures
    provider = MagicMock()
    # Stage 1 (personas): return 5
    personas_response = '[' + ','.join([
        f'{{"name":"P{i}","role":"r","primary_lens":"l","comfort_with_jargon":3,"what_they_care_about":"w"}}'
        for i in range(5)
    ]) + ']'
    # Stage 2 (scoring): return a neutral score for every (persona,narration)
    score_response = '{"clarity":4,"helpfulness":4,"jargon_load":2,"confusing_terms":[],"missing_context":""}'
    # Stage 3 (tuning proposal): suggest one field
    tuning_response = '{"fields_to_set":{"glossary":true},"reasoning":"r"}'

    call_count = [0]
    async def fake_complete(prompt, max_tokens=200):
        call_count[0] += 1
        if "Generate exactly 5 diverse" in prompt:
            return personas_response
        if "tuning a developer-tool" in prompt:
            return tuning_response
        return score_response

    provider.complete = fake_complete

    report = await run_eval(
        narration_log=log, history=history, current_cfg={"glossary": False},
        provider=provider, overlay_path=overlay_path, deployed_at=0.0, max_narrations=10,
    )
    assert report["personas_count"] == 5
    assert report["narrations_evaluated"] == 3
    assert report["aggregate"]["total_evals"] == 15  # 5 × 3
    assert report["proposal"]["fields_to_set"] == {"glossary": True}
    # Auto-applied (1 field, under gate)
    assert report["proposal"]["pending_approval"] is False
    assert report["applied"] is True
    # History has one entry
    assert len(history.list_all()) == 1
    # Overlay file written
    assert overlay_path.exists()
    import yaml
    written = yaml.safe_load(overlay_path.read_text(encoding="utf-8"))
    assert written["teacher_mode"]["glossary"] is True


@pytest.mark.asyncio
async def test_run_eval_returns_empty_when_no_narrations(tmp_path):
    log = NarrationLog(log_path=tmp_path / "empty.jsonl")
    history = TuningHistory(log_path=tmp_path / "h.jsonl")
    provider = MagicMock()
    provider.complete = AsyncMock(return_value='[]')
    report = await run_eval(
        narration_log=log, history=history, current_cfg={},
        provider=provider, overlay_path=tmp_path / "ov.yaml",
        deployed_at=0.0,
    )
    assert report["narrations_evaluated"] == 0
    assert report["proposal"]["fields_to_set"] == {}
    assert report["applied"] is False


@pytest.mark.asyncio
async def test_run_eval_pending_approval_does_not_apply(fixtures):
    log, history, overlay_path = fixtures
    provider = MagicMock()
    personas_response = '[' + ','.join([
        f'{{"name":"P{i}","role":"r","primary_lens":"l","comfort_with_jargon":3,"what_they_care_about":"w"}}'
        for i in range(5)
    ]) + ']'
    score_response = '{"clarity":3,"helpfulness":3,"jargon_load":4,"confusing_terms":[],"missing_context":""}'
    # Propose 4 fields — over the gate
    tuning_response = '{"fields_to_set":{"depth_level":4,"verbosity":"expanded","glossary":true,"reframe":true},"reasoning":"big change"}'
    async def fake_complete(prompt, max_tokens=200):
        if "Generate exactly 5" in prompt: return personas_response
        if "tuning a developer-tool" in prompt: return tuning_response
        return score_response
    provider.complete = fake_complete
    report = await run_eval(
        narration_log=log, history=history, current_cfg={},
        provider=provider, overlay_path=overlay_path, deployed_at=0.0,
    )
    assert report["proposal"]["pending_approval"] is True
    assert report["applied"] is False  # NOT applied
    # History has the entry but marked applied=False
    entries = history.list_all()
    assert len(entries) == 1
    assert entries[0].applied is False
    # Overlay NOT written
    assert not overlay_path.exists()
