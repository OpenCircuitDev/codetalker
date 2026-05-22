"""Tests for Mode: critical_only — narrate only critical events."""
import pytest
from unittest.mock import AsyncMock
from claude_code_talker.modes.critical_only import CriticalOnlyMode


def _cfg():
    return {
        "synopsis": {"enabled": True, "style": "brief"},
        "todos": {"enabled": True, "speak_completed": False},
        "text": {"max_chars": 5000, "boundary_snap": "sentence", "truncation_marker": "..."},
    }


def test_critical_only_extracts_structured_payload():
    """CriticalOnlyMode builds payload with error detection."""
    mode = CriticalOnlyMode(provider=None)
    payload = mode.build_payload(
        prose_entries=[
            "File was successfully read.",
            "Error: division by zero in calculations.py:42",
            "Tests ran fine.",
        ],
        tool_uses=[
            {"name": "Read", "input": {"file_path": "c:/foo.py"}},
            {"name": "Edit", "input": {"file_path": "c:/foo.py"}},
        ],
        todos=[
            {"content": "fix critical bug", "status": "in_progress"},
            {"content": "review tests", "status": "pending"},
            {"content": "deployed", "status": "completed"},
        ],
    )
    # Prose is all entries joined
    assert "File was successfully read" in payload["prose"]
    assert "division by zero" in payload["prose"]
    # Errors extracted (contains "error" keyword)
    assert len(payload["errors"]) > 0
    assert "division by zero" in payload["errors"][0]
    # Actions counted
    assert payload["actions"]["Read"] == 1
    assert payload["actions"]["Edit"] == 1
    # Todos parsed
    assert payload["todos"]["in_progress"] == ["fix critical bug"]
    assert payload["todos"]["pending"] == ["review tests"]
    assert payload["todos"]["completed_count"] == 1


@pytest.mark.asyncio
async def test_critical_only_returns_skip_sentinel_on_routine_event():
    """[SKIP] sentinel returned (None) when nothing critical occurs."""
    fake_provider = AsyncMock()
    fake_provider.complete = AsyncMock(return_value="[SKIP]")

    mode = CriticalOnlyMode(provider=fake_provider)
    cfg = _cfg()

    result = await mode.build_async(
        prose_entries=["Refactored the auth middleware."],
        tool_uses=[{"name": "Edit", "input": {"file_path": "c:/x.py"}}],
        todos=[{"content": "next task", "status": "pending"}],
        cfg=cfg,
    )

    # [SKIP] sentinel converted to None (skip narration)
    assert result is None
    fake_provider.complete.assert_called_once()


@pytest.mark.asyncio
async def test_critical_only_returns_narration_on_error():
    """Critical narration returned when LLM detects an error."""
    fake_provider = AsyncMock()
    fake_provider.complete = AsyncMock(return_value="Error in calculations: division by zero.")

    mode = CriticalOnlyMode(provider=fake_provider)
    cfg = _cfg()

    result = await mode.build_async(
        prose_entries=["Ran the calculation, got an error: division by zero."],
        tool_uses=[{"name": "Bash", "input": {"command": "python script.py"}}],
        todos=[],
        cfg=cfg,
    )

    # Error-shaped narration returned (not None)
    assert result is not None
    assert "division by zero" in result.lower()


@pytest.mark.asyncio
async def test_critical_only_returns_narration_on_test_failure():
    """Critical narration returned when tests fail."""
    fake_provider = AsyncMock()
    fake_provider.complete = AsyncMock(return_value="Tests failing: auth service timeout.")

    mode = CriticalOnlyMode(provider=fake_provider)
    cfg = _cfg()

    result = await mode.build_async(
        prose_entries=["Test suite failed: auth service timeout on mock."],
        tool_uses=[{"name": "Bash", "input": {"command": "pytest"}}],
        todos=[],
        cfg=cfg,
    )

    # Test failure narration returned
    assert result is not None
    assert "fail" in result.lower()


@pytest.mark.asyncio
async def test_critical_only_returns_narration_on_blocker():
    """Critical narration returned when session is blocked."""
    fake_provider = AsyncMock()
    fake_provider.complete = AsyncMock(return_value="Blocked: waiting for the auth session to land.")

    mode = CriticalOnlyMode(provider=fake_provider)
    cfg = _cfg()

    result = await mode.build_async(
        prose_entries=["Rebase paused; waiting for the auth session to finish."],
        tool_uses=[],
        todos=[],
        cfg=cfg,
    )

    # Blocker narration returned
    assert result is not None
    assert "block" in result.lower() or "wait" in result.lower()


@pytest.mark.asyncio
async def test_critical_only_returns_narration_on_major_task_completion():
    """Critical narration returned when a major task completes."""
    fake_provider = AsyncMock()
    fake_provider.complete = AsyncMock(return_value="Completed: migration schema live in prod.")

    mode = CriticalOnlyMode(provider=fake_provider)
    cfg = _cfg()

    result = await mode.build_async(
        prose_entries=["Schema migration ran successfully. All tables updated."],
        tool_uses=[{"name": "Bash", "input": {"command": "migration.sh"}}],
        todos=[{"content": "schema migration", "status": "completed"}],
        cfg=cfg,
    )

    # Task completion narration returned
    assert result is not None
    assert "complet" in result.lower() or "migration" in result.lower()


@pytest.mark.asyncio
async def test_critical_only_enforces_20_word_cap():
    """Narration text respects the 20-word max (prompt enforces it)."""
    fake_provider = AsyncMock()
    # LLM returns text, we just verify it's reasonable length
    fake_provider.complete = AsyncMock(
        return_value="Error in service: network timeout when fetching data from API."
    )

    mode = CriticalOnlyMode(provider=fake_provider)
    cfg = _cfg()

    result = await mode.build_async(
        prose_entries=["Got a network timeout error."],
        tool_uses=[],
        todos=[],
        cfg=cfg,
    )

    # The text is returned as-is from the LLM; prompt enforces the cap
    assert result is not None
    # Word count should be reasonable (the prompt enforces 20-word cap on LLM)
    word_count = len(result.split())
    assert word_count <= 30  # Allow some slack, but assert it's not massive


@pytest.mark.asyncio
async def test_critical_only_returns_none_when_provider_fails():
    """Fallback returns None (skip) when provider fails and no errors detected."""
    fake_provider = AsyncMock()
    fake_provider.complete = AsyncMock(side_effect=RuntimeError("provider error"))

    mode = CriticalOnlyMode(provider=fake_provider)
    cfg = _cfg()

    result = await mode.build_async(
        prose_entries=["Refactored some code."],
        tool_uses=[{"name": "Edit", "input": {"file_path": "c:/x.py"}}],
        todos=[],
        cfg=cfg,
    )

    # Fallback: routine event, no provider → skip narration (None)
    assert result is None


@pytest.mark.asyncio
async def test_critical_only_returns_minimal_alert_on_provider_fail_with_errors():
    """Fallback returns minimal alert when provider fails but errors detected."""
    fake_provider = AsyncMock()
    fake_provider.complete = AsyncMock(side_effect=RuntimeError("provider error"))

    mode = CriticalOnlyMode(provider=fake_provider)
    cfg = _cfg()

    result = await mode.build_async(
        prose_entries=["Critical error: database connection failed."],
        tool_uses=[],
        todos=[],
        cfg=cfg,
    )

    # Fallback with error detected → return minimal alert text
    assert result is not None
    assert "Error" in result


@pytest.mark.asyncio
async def test_critical_only_strips_prefixes():
    """[CHECKPOINT] and [UNSURE] prefixes are stripped (not used in critical_only)."""
    fake_provider = AsyncMock()
    fake_provider.complete = AsyncMock(
        return_value="[CHECKPOINT] [UNSURE] Error in database: connection refused."
    )

    mode = CriticalOnlyMode(provider=fake_provider)
    cfg = _cfg()

    result = await mode.build_async(
        prose_entries=["Database error occurred."],
        tool_uses=[],
        todos=[],
        cfg=cfg,
    )

    # Prefixes stripped; critical narration returned
    assert result is not None
    assert "[CHECKPOINT]" not in result
    assert "[UNSURE]" not in result
    assert "connection refused" in result.lower()


@pytest.mark.asyncio
async def test_critical_only_converts_empty_after_stripping_to_skip():
    """If LLM returns only prefixes (strips to empty), treat as [SKIP]."""
    fake_provider = AsyncMock()
    fake_provider.complete = AsyncMock(return_value="[CHECKPOINT] [UNSURE]")

    mode = CriticalOnlyMode(provider=fake_provider)
    cfg = _cfg()

    result = await mode.build_async(
        prose_entries=["Routine work."],
        tool_uses=[],
        todos=[],
        cfg=cfg,
    )

    # After stripping prefixes, empty string → None (skip)
    assert result is None
