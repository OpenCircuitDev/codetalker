"""Tests for Mode B: turn-end brief."""
import pytest
from unittest.mock import AsyncMock
from claude_code_talker.modes.brief import BriefMode


def _cfg():
    return {
        "synopsis": {"enabled": True, "style": "brief"},
        "todos": {"enabled": True, "speak_completed": False},
        "text": {"max_chars": 5000, "boundary_snap": "sentence", "truncation_marker": "..."},
    }


def test_brief_extracts_structured_payload():
    mode = BriefMode(provider=None)
    payload = mode.build_payload(
        prose_entries=["Smoking gun found. Root cause: scale bug."],
        tool_uses=[
            {"name": "Read", "input": {"file_path": "c:/foo.py"}},
            {"name": "Edit", "input": {"file_path": "c:/foo.py"}},
        ],
        todos=[
            {"content": "fix it", "status": "in_progress"},
            {"content": "test it", "status": "pending"},
            {"content": "started", "status": "completed"},
        ],
    )
    assert "Smoking gun" in payload["prose"]
    assert payload["actions"]["Read"] == 1
    assert payload["actions"]["Edit"] == 1
    assert payload["todos"]["in_progress"] == ["fix it"]
    assert payload["todos"]["pending"] == ["test it"]
    assert payload["todos"]["completed_count"] == 1


@pytest.mark.asyncio
async def test_brief_calls_provider_with_template():
    fake_provider = AsyncMock()
    fake_provider.complete = AsyncMock(return_value="Brief response.")

    mode = BriefMode(provider=fake_provider)
    cfg = _cfg()

    result = await mode.build_async(
        prose_entries=["Found the bug."],
        tool_uses=[{"name": "Edit", "input": {"file_path": "c:/x.py"}}],
        todos=[{"content": "next", "status": "pending"}],
        cfg=cfg,
    )

    assert result == "Brief response."
    fake_provider.complete.assert_called_once()
    prompt = fake_provider.complete.call_args[0][0]
    assert "Found the bug" in prompt
    assert "Edit" in prompt
    assert "next" in prompt


@pytest.mark.asyncio
async def test_brief_falls_back_when_provider_fails():
    fake_provider = AsyncMock()
    fake_provider.complete = AsyncMock(side_effect=RuntimeError("boom"))

    mode = BriefMode(provider=fake_provider)
    cfg = _cfg()

    result = await mode.build_async(
        prose_entries=["Found the bug."],
        tool_uses=[{"name": "Edit", "input": {"file_path": "c:/x.py"}}],
        todos=None, cfg=cfg,
    )
    # Fallback: structured text without LLM translation
    assert "Edit" in result or "edited" in result.lower()
    assert "bug" in result.lower()
