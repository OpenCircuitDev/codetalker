"""Integration tests for virtual_eval.run_eval orchestrator."""
import json
import pytest
import yaml as _yaml
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from claude_code_talker.narration_log import NarrationLog, NarrationEntry
from claude_code_talker.virtual_eval import run_eval, apply_tuning, revert_tuning
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


# ---------------------------------------------------------------------------
# Direct tests for apply_tuning / revert_tuning
# ---------------------------------------------------------------------------

def test_apply_tuning_pending_writes_overlay_and_records_applied(tmp_path):
    history = TuningHistory(log_path=tmp_path / "tuning.jsonl")
    overlay = tmp_path / "ov.yaml"
    pending = history.append(
        before={"glossary": False}, after={"glossary": True},
        reasoning="proposed", applied=False,
    )
    ok = apply_tuning(history=history, entry_id=pending.id, overlay_path=overlay)
    assert ok is True
    # Overlay reflects the approved change
    written = _yaml.safe_load(overlay.read_text(encoding="utf-8"))
    assert written["teacher_mode"]["glossary"] is True
    # Two entries now: original (still applied=False) + new applied=True
    entries = history.list_all()
    assert len(entries) == 2
    assert entries[0].id == pending.id and entries[0].applied is False
    assert entries[1].applied is True


def test_apply_tuning_unknown_id_returns_false(tmp_path):
    history = TuningHistory(log_path=tmp_path / "tuning.jsonl")
    ok = apply_tuning(history=history, entry_id="nope", overlay_path=tmp_path / "ov.yaml")
    assert ok is False


def test_apply_tuning_already_applied_returns_false(tmp_path):
    history = TuningHistory(log_path=tmp_path / "tuning.jsonl")
    e = history.append(before={"a": 1}, after={"a": 2}, reasoning="r", applied=True)
    ok = apply_tuning(history=history, entry_id=e.id, overlay_path=tmp_path / "ov.yaml")
    assert ok is False


def test_revert_tuning_writes_before_to_overlay(tmp_path):
    history = TuningHistory(log_path=tmp_path / "tuning.jsonl")
    overlay = tmp_path / "ov.yaml"
    e = history.append(
        before={"depth_level": 3}, after={"depth_level": 4},
        reasoning="apply", applied=True,
    )
    ok = revert_tuning(history=history, entry_id=e.id, overlay_path=overlay)
    assert ok is True
    written = _yaml.safe_load(overlay.read_text(encoding="utf-8"))
    assert written["teacher_mode"]["depth_level"] == 3
    # New history entry recorded the revert with swapped before/after
    entries = history.list_all()
    assert len(entries) == 2
    assert entries[1].before == {"depth_level": 4}
    assert entries[1].after == {"depth_level": 3}
    assert "revert" in entries[1].reasoning


def test_revert_tuning_pending_entry_returns_false(tmp_path):
    history = TuningHistory(log_path=tmp_path / "tuning.jsonl")
    e = history.append(before={"a": 1}, after={"a": 2}, reasoning="r", applied=False)
    ok = revert_tuning(history=history, entry_id=e.id, overlay_path=tmp_path / "ov.yaml")
    assert ok is False


def test_overlay_write_preserves_other_top_level_keys(tmp_path):
    overlay = tmp_path / "ov.yaml"
    # Pre-existing overlay has unrelated keys
    overlay.write_text(_yaml.safe_dump({
        "ui_layout": {"left_width": 180},
        "teacher_mode": {"depth_level": 2},
    }), encoding="utf-8")
    history = TuningHistory(log_path=tmp_path / "tuning.jsonl")
    e = history.append(before={"depth_level": 2}, after={"depth_level": 4},
                       reasoning="r", applied=False)
    ok = apply_tuning(history=history, entry_id=e.id, overlay_path=overlay)
    assert ok is True
    written = _yaml.safe_load(overlay.read_text(encoding="utf-8"))
    assert written["ui_layout"] == {"left_width": 180}  # untouched
    assert written["teacher_mode"]["depth_level"] == 4  # updated


def test_overlay_unparseable_refuses_write(tmp_path, caplog):
    overlay = tmp_path / "ov.yaml"
    overlay.write_text("::: not valid yaml :::\n  nested ::\n", encoding="utf-8")
    original_text = overlay.read_text(encoding="utf-8")
    history = TuningHistory(log_path=tmp_path / "tuning.jsonl")
    e = history.append(before={"a": 1}, after={"a": 2}, reasoning="r", applied=False)
    # apply_tuning should log + refuse without touching the bad file
    ok = apply_tuning(history=history, entry_id=e.id, overlay_path=overlay)
    # Returns True (history was updated) but overlay was NOT touched
    # NOTE: behavior depends on whether _write_overlay returning early leaves apply_tuning
    # success. Per spec it does — history entry was appended either way.
    assert overlay.read_text(encoding="utf-8") == original_text
