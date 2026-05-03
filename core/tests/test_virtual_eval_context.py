"""Tests for virtual_eval.context — per-narration context gathering."""
import json
import pytest
from pathlib import Path
from unittest.mock import MagicMock

from claude_code_talker.narration_log import NarrationLog, NarrationEntry
from claude_code_talker.virtual_eval.context import (
    NarrationWithContext, gather_context_for_narration,
)


@pytest.fixture
def populated_log(tmp_path):
    log = NarrationLog(log_path=tmp_path / "narration.jsonl")
    # Session A: 5 narrations
    for i in range(5):
        log.append(NarrationEntry(
            timestamp=100.0 + i, session_id="sid-A",
            text=f"narration A-{i}", voice="v", engine="e", mode="live",
        ))
    # Session B: 3 narrations
    for i in range(3):
        log.append(NarrationEntry(
            timestamp=200.0 + i, session_id="sid-B",
            text=f"narration B-{i}", voice="v", engine="e", mode="live",
        ))
    return log


def test_narration_with_context_dataclass_fields():
    nwc = NarrationWithContext(
        text="x", session_id="s", timestamp=1.0,
        prior_narrations=["a", "b"], last_user_prompt="why",
        recent_transcript_lines=["USER: hi", "ASSISTANT: hello"],
    )
    assert nwc.text == "x"
    assert len(nwc.prior_narrations) == 2


def test_gather_pulls_prior_narrations_from_same_session(populated_log):
    target = {"session_id": "sid-A", "text": "narration A-3", "timestamp": 103.0, "mode": "live"}
    nwc = gather_context_for_narration(target, populated_log, catalog=None,
                                        max_prior_narrations=5)
    # Should have A-0, A-1, A-2 as prior (NOT A-3 itself, NOT A-4 which is later)
    assert len(nwc.prior_narrations) == 3
    assert "A-0" in nwc.prior_narrations[0]
    assert "A-3" not in " ".join(nwc.prior_narrations)


def test_gather_excludes_other_sessions(populated_log):
    target = {"session_id": "sid-A", "text": "x", "timestamp": 200.0, "mode": "live"}
    nwc = gather_context_for_narration(target, populated_log, catalog=None,
                                        max_prior_narrations=10)
    # Should pull A's 5 narrations as prior (all are <= timestamp 200)
    # but NOT any B narrations
    for n in nwc.prior_narrations:
        assert "B-" not in n


def test_gather_respects_max_prior_cap(populated_log):
    target = {"session_id": "sid-A", "text": "x", "timestamp": 999.0, "mode": "live"}
    nwc = gather_context_for_narration(target, populated_log, catalog=None,
                                        max_prior_narrations=2)
    assert len(nwc.prior_narrations) == 2
    # The MOST RECENT 2 should be retained
    assert "A-3" in nwc.prior_narrations[-1] or "A-4" in nwc.prior_narrations[-1]


def test_gather_handles_no_catalog(populated_log):
    target = {"session_id": "sid-A", "text": "x", "timestamp": 100.0, "mode": "live"}
    nwc = gather_context_for_narration(target, populated_log, catalog=None)
    # Without a catalog, transcript lines are empty but no crash
    assert nwc.recent_transcript_lines == []
    assert nwc.last_user_prompt == ""


def test_gather_pulls_transcript_when_catalog_has_entry(populated_log, tmp_path):
    # Build a catalog with a fake entry whose transcript_path exists
    transcript = tmp_path / "fake-transcript.jsonl"
    transcript.write_text(
        json.dumps({"type": "user", "message": {"content": "make it work"}}) + "\n" +
        json.dumps({"type": "assistant", "message": {"content": [{"type": "text", "text": "I will."}]}}) + "\n",
        encoding="utf-8",
    )
    from claude_code_talker.catalog import CatalogEntry
    catalog_mock = MagicMock()
    catalog_mock.entry_for.return_value = CatalogEntry(
        session_id="sid-A", project_slug="p", transcript_path=transcript,
        last_modified=1.0, title="t", vscode_label="",
    )
    target = {"session_id": "sid-A", "text": "x", "timestamp": 100.0, "mode": "live"}
    nwc = gather_context_for_narration(target, populated_log, catalog=catalog_mock,
                                        max_transcript_lines=10)
    assert "make it work" in nwc.last_user_prompt
    assert any("USER:" in ln for ln in nwc.recent_transcript_lines)


def test_gather_handles_unknown_catalog_entry(populated_log):
    catalog_mock = MagicMock()
    catalog_mock.entry_for.return_value = None
    target = {"session_id": "unknown-sid", "text": "x", "timestamp": 1.0, "mode": "live"}
    nwc = gather_context_for_narration(target, populated_log, catalog=catalog_mock)
    assert nwc.last_user_prompt == ""
    assert nwc.recent_transcript_lines == []
