"""Tests for session_focus.SessionFocus + SessionFocusRegistry."""
import pytest
from unittest.mock import AsyncMock, MagicMock

from claude_code_talker.session_focus import SessionFocus, SessionFocusRegistry


def test_focus_starts_empty():
    f = SessionFocus()
    assert list(f.recent_user_prompts) == []
    assert f.files_in_play == {}
    assert f.task_header == ""


def test_record_user_prompt_keeps_last_three():
    f = SessionFocus()
    for i in range(5):
        f.record_user_prompt(f"prompt {i}")
    assert list(f.recent_user_prompts) == ["prompt 2", "prompt 3", "prompt 4"]


def test_record_user_prompt_dedups_consecutive():
    f = SessionFocus()
    f.record_user_prompt("hi")
    f.record_user_prompt("hi")
    f.record_user_prompt("there")
    assert list(f.recent_user_prompts) == ["hi", "there"]


def test_record_file_touch_caps_at_eight():
    f = SessionFocus()
    for i in range(12):
        f.record_file_touch(f"file{i}.py", timestamp=float(i))
    # Should keep only the 8 most-recent
    assert len(f.files_in_play) == 8
    # The newest 8 should be present
    for i in range(4, 12):
        assert f"file{i}.py" in f.files_in_play
    # The oldest 4 should be gone
    for i in range(4):
        assert f"file{i}.py" not in f.files_in_play


def test_record_file_touch_updates_existing_timestamp():
    f = SessionFocus()
    f.record_file_touch("a.py", timestamp=1.0)
    f.record_file_touch("a.py", timestamp=5.0)
    assert f.files_in_play["a.py"] == 5.0


def test_should_refresh_header_when_stale_count(monkeypatch):
    f = SessionFocus()
    f.task_header = "old header"
    f.task_header_at = 100.0
    f.narrations_since_refresh = 5
    # Patch time so we're not actually 60s past
    import claude_code_talker.session_focus as sf
    monkeypatch.setattr(sf.time, "time", lambda: 110.0)  # 10s past
    assert f.should_refresh_header() is True


def test_should_refresh_header_when_stale_time(monkeypatch):
    f = SessionFocus()
    f.task_header = "old header"
    f.task_header_at = 100.0
    f.narrations_since_refresh = 1
    import claude_code_talker.session_focus as sf
    monkeypatch.setattr(sf.time, "time", lambda: 200.0)  # 100s past
    assert f.should_refresh_header() is True


def test_should_refresh_header_false_when_fresh(monkeypatch):
    f = SessionFocus()
    f.task_header = "fresh header"
    f.task_header_at = 100.0
    f.narrations_since_refresh = 1
    import claude_code_talker.session_focus as sf
    monkeypatch.setattr(sf.time, "time", lambda: 110.0)  # 10s past
    assert f.should_refresh_header() is False


def test_should_refresh_header_true_if_empty():
    f = SessionFocus()
    assert f.task_header == ""
    assert f.should_refresh_header() is True


@pytest.mark.asyncio
async def test_refresh_header_calls_provider_and_stores(monkeypatch):
    f = SessionFocus()
    f.recent_user_prompts.append("add JWT auth to the server")
    f.files_in_play = {"server.py": 1.0, "auth.py": 2.0}
    provider = MagicMock()
    provider.complete = AsyncMock(return_value="implementing JWT middleware in the auth pipeline")
    import claude_code_talker.session_focus as sf
    monkeypatch.setattr(sf.time, "time", lambda: 500.0)
    await f.refresh_header(provider)
    assert f.task_header == "implementing JWT middleware in the auth pipeline"
    assert f.task_header_at == 500.0
    assert f.narrations_since_refresh == 0
    # Provider was called with both prompt context and file list
    call_arg = provider.complete.call_args[0][0]
    assert "JWT" in call_arg
    assert "auth.py" in call_arg


@pytest.mark.asyncio
async def test_refresh_header_keeps_stale_on_provider_failure():
    f = SessionFocus()
    f.task_header = "stale but real"
    provider = MagicMock()
    provider.complete = AsyncMock(side_effect=RuntimeError("down"))
    await f.refresh_header(provider)
    # Stale header preserved; counter NOT reset (so we'll try again next cycle)
    assert f.task_header == "stale but real"


def test_render_block_compact():
    f = SessionFocus()
    f.recent_user_prompts.append("rewrite the menu system to support multiple choices")
    f.files_in_play = {"menu.tsx": 1.0, "MenuItem.tsx": 2.0}
    f.task_header = "rewriting menu UI for multi-select"
    block = f.render_block()
    assert "SESSION FOCUS" in block
    assert "rewriting menu UI for multi-select" in block
    assert "menu.tsx" in block
    assert "rewrite the menu system" in block


def test_render_block_skips_empty_sections():
    f = SessionFocus()
    block = f.render_block()
    # Empty SessionFocus → empty block (so prompt isn't polluted with placeholders)
    assert block == "" or "SESSION FOCUS" not in block


def test_registry_returns_same_focus_for_same_session():
    reg = SessionFocusRegistry()
    f1 = reg.get_or_create("session-a")
    f2 = reg.get_or_create("session-a")
    assert f1 is f2


def test_registry_separate_focus_per_session():
    reg = SessionFocusRegistry()
    a = reg.get_or_create("session-a")
    b = reg.get_or_create("session-b")
    assert a is not b
    a.record_user_prompt("for A")
    assert "for A" not in list(b.recent_user_prompts)


def test_registry_handles_event_dispatch():
    reg = SessionFocusRegistry()
    # Simulate the dispatch the LiveMode will do
    from collections import namedtuple
    Event = namedtuple("Event", "type metadata timestamp")
    reg.on_event("s1", Event("USER_PROMPT", {"text": "do the thing"}, 1.0))
    reg.on_event("s1", Event("PRE_TOOL", {"tool_name": "Edit", "input": "{'file_path': 'foo.py'}"}, 2.0))
    f = reg.get_or_create("s1")
    assert "do the thing" in list(f.recent_user_prompts)
    assert "foo.py" in f.files_in_play


# ---------------------------------------------------------------------------
# Phase 13.8 R5: dirty flag — record_user_prompt sets dirty
# ---------------------------------------------------------------------------

def test_record_user_prompt_sets_dirty():
    """record_user_prompt should set dirty=True so the focus header refreshes."""
    f = SessionFocus()
    assert f.dirty is False
    f.record_user_prompt("implement the auth pipeline")
    assert f.dirty is True


def test_should_refresh_header_true_when_dirty(monkeypatch):
    """should_refresh_header returns True when dirty=True even if count+time are fine."""
    f = SessionFocus()
    f.task_header = "fresh header"
    f.task_header_at = 100.0
    f.narrations_since_refresh = 0
    import claude_code_talker.session_focus as sf
    monkeypatch.setattr(sf.time, "time", lambda: 110.0)  # 10s past, not stale
    # Without dirty: should be False
    assert f.should_refresh_header() is False
    # Set dirty: should now be True
    f.dirty = True
    assert f.should_refresh_header() is True


@pytest.mark.asyncio
async def test_refresh_header_clears_dirty():
    """refresh_header must clear dirty=True after a successful LLM call."""
    f = SessionFocus()
    f.dirty = True
    f.recent_user_prompts.append("build the widget")
    provider = MagicMock()
    provider.complete = AsyncMock(return_value="building the widget")
    await f.refresh_header(provider)
    assert f.dirty is False
