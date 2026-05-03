"""Tests for Phase 9 chat_panel."""
import json
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from claude_code_talker.chat_panel import (
    _last_n_transcript_lines,
    _format_events,
    gather_session_context,
    answer_question,
    CHAT_PROMPT_TEMPLATE,
)


def test_transcript_lines_skips_system_tags(tmp_path):
    p = tmp_path / "t.jsonl"
    p.write_text(
        json.dumps({"type": "user", "message": {"content": "<ide_opened_file>noise"}}) + "\n" +
        json.dumps({"type": "user", "message": {"content": "<system-reminder>more noise"}}) + "\n" +
        json.dumps({"type": "user", "message": {"content": "real user message"}}) + "\n",
        encoding="utf-8",
    )
    out = _last_n_transcript_lines(p, n_lines=10)
    assert any("real user message" in ln for ln in out)
    assert not any("<ide_opened_file>" in ln for ln in out)
    assert not any("<system-reminder>" in ln for ln in out)


def test_transcript_lines_extracts_assistant(tmp_path):
    p = tmp_path / "t.jsonl"
    p.write_text(
        json.dumps({"type": "assistant", "message": {"content": [
            {"type": "text", "text": "hello"}, {"type": "tool_use", "input": {}}
        ]}}) + "\n",
        encoding="utf-8",
    )
    out = _last_n_transcript_lines(p, n_lines=10)
    assert any("ASSISTANT: hello" in ln for ln in out)


def test_transcript_lines_includes_ai_title(tmp_path):
    p = tmp_path / "t.jsonl"
    p.write_text(
        json.dumps({"type": "ai-title", "aiTitle": "Refactor cache layer"}) + "\n" +
        json.dumps({"type": "user", "message": {"content": "go"}}) + "\n",
        encoding="utf-8",
    )
    out = _last_n_transcript_lines(p, n_lines=10)
    assert any("[SESSION TITLE: Refactor cache layer]" in ln for ln in out)


def test_transcript_lines_handles_missing_file():
    assert _last_n_transcript_lines(Path("/does/not/exist.jsonl"), n_lines=10) == []


def test_format_events_empty():
    assert _format_events([]) == []


def test_format_events_renders_pre_post_tool():
    Event = type("Event", (), {})
    e1 = Event(); e1.timestamp = 100.0; e1.type = "PRE_TOOL"; e1.metadata = {"tool_name": "Edit"}
    e2 = Event(); e2.timestamp = 100.5; e2.type = "POST_TOOL"; e2.metadata = {"tool_name": "Edit", "success": True}
    out = _format_events([e1, e2])
    assert any("tool→ Edit" in ln for ln in out)
    assert any("tool← Edit ok" in ln for ln in out)


def test_format_events_marks_failures():
    Event = type("Event", (), {})
    e = Event(); e.timestamp = 0.0; e.type = "POST_TOOL"
    e.metadata = {"tool_name": "Bash", "success": False}
    out = _format_events([e])
    assert any("FAILED" in ln for ln in out)


def test_gather_session_context_includes_both_sources(tmp_path):
    p = tmp_path / "t.jsonl"
    p.write_text(
        json.dumps({"type": "user", "message": {"content": "hello session"}}) + "\n",
        encoding="utf-8",
    )
    Event = type("Event", (), {})
    e = Event(); e.timestamp = 0.0; e.type = "PRE_TOOL"; e.metadata = {"tool_name": "Read"}
    out = gather_session_context(transcript_path=p, events=[e])
    assert "--- Recent transcript ---" in out
    assert "--- Recent live events ---" in out
    assert "USER: hello session" in out


def test_gather_session_context_handles_no_inputs():
    out = gather_session_context(transcript_path=None, events=[])
    assert "(no context available)" in out


@pytest.mark.asyncio
async def test_answer_question_calls_provider_and_returns():
    provider = MagicMock()
    provider.complete = AsyncMock(return_value="Here is the answer.")
    out = await answer_question(
        question="what happened?",
        context="some context",
        provider=provider,
        teacher_cfg=None,
    )
    assert out == "Here is the answer."
    provider.complete.assert_awaited_once()
    sent_prompt = provider.complete.call_args[0][0]
    assert "what happened?" in sent_prompt
    assert "some context" in sent_prompt


@pytest.mark.asyncio
async def test_answer_question_injects_teacher_directives():
    provider = MagicMock()
    provider.complete = AsyncMock(return_value="x")
    await answer_question(
        question="q", context="c", provider=provider,
        teacher_cfg={"enabled": True, "depth_level": 5, "glossary": True},
    )
    sent_prompt = provider.complete.call_args[0][0]
    assert "TEACHER MODE" in sent_prompt


@pytest.mark.asyncio
async def test_answer_question_returns_error_on_provider_failure():
    provider = MagicMock()
    provider.complete = AsyncMock(side_effect=RuntimeError("boom"))
    out = await answer_question(
        question="q", context="c", provider=provider, teacher_cfg=None,
    )
    assert "provider error" in out.lower()
    assert "boom" in out
