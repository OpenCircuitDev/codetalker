"""CCT-31 — BuddyClaude session tests."""
from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from claude_code_talker.companion.buddy import (
    BuddyClaude,
    BuddyEvent,
    read_recent_transcript,
)


def test_read_recent_transcript_returns_last_n_messages(tmp_path):
    p = tmp_path / "session.jsonl"
    lines = [
        '{"role":"user","content":"q1"}',
        '{"role":"assistant","content":"a1"}',
        '{"role":"user","content":"q2"}',
        '{"role":"assistant","content":"a2"}',
    ]
    p.write_text("\n".join(lines), encoding="utf-8")
    out = read_recent_transcript(p, max_messages=3)
    assert len(out) == 3
    assert out[-1]["content"] == "a2"


def test_read_recent_transcript_handles_missing_file(tmp_path):
    out = read_recent_transcript(tmp_path / "missing.jsonl", max_messages=5)
    assert out == []


def test_buddy_construct_requires_api_key(tmp_path):
    with pytest.raises(ValueError, match="api_key"):
        BuddyClaude(user_session_id="x", transcript_path=tmp_path / "s.jsonl", anthropic_api_key="")


def test_buddy_construct_validates_transcript_path_exists_or_creates(tmp_path):
    p = tmp_path / "s.jsonl"
    BuddyClaude(user_session_id="x", transcript_path=p, anthropic_api_key="sk-test")
    # OK to point at a non-existent transcript; reads return [] silently.


@pytest.mark.asyncio
async def test_buddy_inject_appends_to_history():
    with patch("claude_code_talker.companion.buddy.anthropic") as mock_anth:
        stream_ctx = AsyncMock()
        stream_ctx.__aenter__.return_value.__aiter__ = lambda s: iter([])
        mock_anth.AsyncAnthropic.return_value.messages.stream.return_value = stream_ctx
        b = BuddyClaude(user_session_id="x", transcript_path=Path("/nope.jsonl"), anthropic_api_key="sk")
        events = []
        async for ev in b.inject("hello"):
            events.append(ev)
        assert b.history[-1]["role"] == "user"
        assert b.history[-1]["content"] == "hello"


@pytest.mark.asyncio
async def test_buddy_inject_emits_partial_then_final():
    fake_events = [
        MagicMock(type="content_block_delta", delta=MagicMock(text="hel")),
        MagicMock(type="content_block_delta", delta=MagicMock(text="lo")),
        MagicMock(type="message_stop"),
    ]
    with patch("claude_code_talker.companion.buddy.anthropic") as mock_anth:
        stream = MagicMock()
        stream.__aiter__ = lambda s: iter(fake_events)
        ctx = AsyncMock()
        ctx.__aenter__.return_value = stream
        mock_anth.AsyncAnthropic.return_value.messages.stream.return_value = ctx
        b = BuddyClaude(user_session_id="x", transcript_path=Path("/nope.jsonl"), anthropic_api_key="sk")
        events = [ev async for ev in b.inject("hi")]
        kinds = [e.kind for e in events]
        assert "partial_text" in kinds
        assert "final_text" in kinds or "done" in kinds


def test_buddy_event_partial_text_constructor():
    e = BuddyEvent(kind="partial_text", text="he")
    assert e.kind == "partial_text"
    assert e.text == "he"


def test_buddy_includes_transcript_context_in_system(tmp_path):
    p = tmp_path / "s.jsonl"
    p.write_text('{"role":"user","content":"earlier"}\n', encoding="utf-8")
    b = BuddyClaude(user_session_id="x", transcript_path=p, anthropic_api_key="sk")
    sys_prompt = b._build_system_prompt()
    assert "AR voice companion" in sys_prompt
    assert str(p) in sys_prompt or "transcript" in sys_prompt


def test_buddy_manager_creates_one_buddy_per_session(tmp_path):
    from claude_code_talker.companion.buddy import BuddyManager
    mgr = BuddyManager(api_key="sk", transcript_dir=tmp_path)
    b1 = mgr.start("sid-1")
    b2 = mgr.start("sid-1")
    assert b1 is b2  # same session reuses


def test_buddy_manager_independent_per_session(tmp_path):
    from claude_code_talker.companion.buddy import BuddyManager
    mgr = BuddyManager(api_key="sk", transcript_dir=tmp_path)
    b1 = mgr.start("sid-1")
    b2 = mgr.start("sid-2")
    assert b1 is not b2


def test_buddy_manager_stop_removes_buddy(tmp_path):
    from claude_code_talker.companion.buddy import BuddyManager
    mgr = BuddyManager(api_key="sk", transcript_dir=tmp_path)
    mgr.start("sid-1")
    mgr.stop("sid-1")
    assert "sid-1" not in mgr._buddies
