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


@pytest.mark.asyncio
async def test_brief_strips_checkpoint_prefix_and_prepends_cue():
    """[CHECKPOINT] prefix is stripped and 'Checkpoint. ' is prepended."""
    fake_provider = AsyncMock()
    fake_provider.complete = AsyncMock(return_value="[CHECKPOINT] Chose REST over websocket.")

    mode = BriefMode(provider=fake_provider)
    cfg = _cfg()

    result = await mode.build_async(
        prose_entries=["Deciding on API shape."],
        tool_uses=[],
        todos=[],
        cfg=cfg,
    )

    # Prefix is stripped and "Checkpoint. " cue is prepended
    assert result.startswith("Checkpoint. ")
    assert "[CHECKPOINT]" not in result
    assert "Chose REST over websocket." in result


@pytest.mark.asyncio
async def test_brief_strips_unsure_prefix():
    """[UNSURE] prefix is stripped silently (no audible cue)."""
    fake_provider = AsyncMock()
    fake_provider.complete = AsyncMock(return_value="[UNSURE] Maybe the tests passed?")

    mode = BriefMode(provider=fake_provider)
    cfg = _cfg()

    result = await mode.build_async(
        prose_entries=["Running tests."],
        tool_uses=[],
        todos=[],
        cfg=cfg,
    )

    # Prefix is stripped, no "Checkpoint. " cue (it's not a checkpoint)
    assert "[UNSURE]" not in result
    assert not result.startswith("Checkpoint. ")
    assert "Maybe the tests passed?" in result


@pytest.mark.asyncio
async def test_brief_handles_both_prefixes_together():
    """Both [CHECKPOINT] and [UNSURE] are handled correctly when both present."""
    fake_provider = AsyncMock()
    fake_provider.complete = AsyncMock(
        return_value="[CHECKPOINT] [UNSURE] Might use Postgres for the new table."
    )

    mode = BriefMode(provider=fake_provider)
    cfg = _cfg()

    result = await mode.build_async(
        prose_entries=["Picking database."],
        tool_uses=[],
        todos=[],
        cfg=cfg,
    )

    # Both prefixes stripped, "Checkpoint. " cue prepended (checkpoint wins priority)
    assert "[CHECKPOINT]" not in result
    assert "[UNSURE]" not in result
    assert result.startswith("Checkpoint. ")
    assert "Might use Postgres for the new table." in result


# ---------------------------------------------------------------------------
# [ALERT] prefix — error / blocker / needs-input urgency cue
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_brief_strips_alert_prefix_and_prepends_cue():
    """[ALERT] prefix is stripped and 'Heads up. ' is prepended."""
    fake_provider = AsyncMock()
    fake_provider.complete = AsyncMock(return_value="[ALERT] Build broke on the auth refactor.")

    mode = BriefMode(provider=fake_provider)
    cfg = _cfg()

    result = await mode.build_async(
        prose_entries=["CI run."],
        tool_uses=[],
        todos=[],
        cfg=cfg,
    )

    assert result.startswith("Heads up. ")
    assert "[ALERT]" not in result
    assert "Build broke on the auth refactor." in result


@pytest.mark.asyncio
async def test_brief_alert_and_checkpoint_both_prefix_cues():
    """[ALERT] + [CHECKPOINT] together → both cues, alert first."""
    fake_provider = AsyncMock()
    fake_provider.complete = AsyncMock(
        return_value="[ALERT] [CHECKPOINT] Migration stuck — needs a manual schema decision."
    )

    mode = BriefMode(provider=fake_provider)
    cfg = _cfg()

    result = await mode.build_async(
        prose_entries=["Mid-migration."],
        tool_uses=[],
        todos=[],
        cfg=cfg,
    )

    # Both cues prepended; alert comes first (urgency before architectural marker)
    assert "[ALERT]" not in result
    assert "[CHECKPOINT]" not in result
    assert result.startswith("Heads up. Checkpoint. ")
    assert "Migration stuck — needs a manual schema decision." in result


@pytest.mark.asyncio
async def test_brief_alert_unsure_and_checkpoint_all_three():
    """All three prefixes; [ALERT] + [CHECKPOINT] cues prepended, [UNSURE] silent."""
    fake_provider = AsyncMock()
    fake_provider.complete = AsyncMock(
        return_value="[ALERT] [CHECKPOINT] [UNSURE] Might need to roll back the failing migration."
    )

    mode = BriefMode(provider=fake_provider)
    cfg = _cfg()

    result = await mode.build_async(
        prose_entries=["Considering rollback."],
        tool_uses=[],
        todos=[],
        cfg=cfg,
    )

    for marker in ("[ALERT]", "[CHECKPOINT]", "[UNSURE]"):
        assert marker not in result
    assert result.startswith("Heads up. Checkpoint. ")
    assert "Might need to roll back the failing migration." in result
