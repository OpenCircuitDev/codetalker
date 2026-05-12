"""CCT-31 + CCT-32 v0.1.0 polish — BuddyClaude session tests.

The buddy now uses OpenRouter's OpenAI-compatible /chat/completions endpoint
via httpx instead of the Anthropic SDK. Tests mock httpx.AsyncClient.stream
to yield SSE-formatted lines like `data: {...}` and verify the buddy parses
them into BuddyEvents.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from claude_code_talker.companion.buddy import (
    BuddyClaude,
    BuddyEvent,
    BuddyManager,
    read_recent_transcript,
)


# ---------- transcript helpers ----------

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


# ---------- construction ----------

def test_buddy_construct_requires_api_key(tmp_path):
    with pytest.raises(ValueError, match="api_key"):
        BuddyClaude(
            user_session_id="x",
            transcript_path=tmp_path / "s.jsonl",
            anthropic_api_key="",
        )


def test_buddy_construct_validates_transcript_path_exists_or_creates(tmp_path):
    p = tmp_path / "s.jsonl"
    BuddyClaude(
        user_session_id="x",
        transcript_path=p,
        anthropic_api_key="sk-test",
    )


def test_buddy_default_routes_through_openrouter(tmp_path):
    b = BuddyClaude(
        user_session_id="x",
        transcript_path=tmp_path / "s.jsonl",
        anthropic_api_key="sk-test",
    )
    assert b.base_url == "https://openrouter.ai/api/v1"
    assert b.model.startswith("anthropic/")  # default Claude via OpenRouter


def test_buddy_event_partial_text_constructor():
    e = BuddyEvent(kind="partial_text", text="he")
    assert e.kind == "partial_text"
    assert e.text == "he"


def test_buddy_includes_transcript_context_in_system(tmp_path):
    p = tmp_path / "s.jsonl"
    p.write_text('{"role":"user","content":"earlier"}\n', encoding="utf-8")
    b = BuddyClaude(
        user_session_id="x",
        transcript_path=p,
        anthropic_api_key="sk",
    )
    sys_prompt = b._build_system_prompt()
    assert "AR voice companion" in sys_prompt
    assert str(p) in sys_prompt or "transcript" in sys_prompt


# ---------- inject() — SSE-driven streaming ----------

def _sse_event(delta: str) -> str:
    return "data: " + json.dumps({"choices": [{"delta": {"content": delta}}]})


def _mock_stream_response(sse_lines: list[str]):
    """Build a mock that the buddy's `async with client.stream(...)` can use.

    The context manager protocol returns a response object with an async
    iterator over lines.
    """
    resp = MagicMock()
    resp.raise_for_status = MagicMock(return_value=None)

    async def aiter_lines():
        for line in sse_lines:
            yield line

    resp.aiter_lines = aiter_lines

    stream_cm = MagicMock()
    stream_cm.__aenter__ = AsyncMock(return_value=resp)
    stream_cm.__aexit__ = AsyncMock(return_value=None)
    return stream_cm


@pytest.mark.asyncio
async def test_buddy_inject_appends_to_history():
    b = BuddyClaude(
        user_session_id="x",
        transcript_path=Path("/nope.jsonl"),
        anthropic_api_key="sk",
    )
    fake_client = MagicMock()
    fake_client.stream = MagicMock(return_value=_mock_stream_response(["data: [DONE]"]))
    b._client = fake_client
    events = [ev async for ev in b.inject("hello")]
    assert b.history[-1]["role"] == "user" or b.history[-1]["role"] == "assistant"
    # Always at least the user turn must land — even if the stream produced no text.
    assert any(m.get("role") == "user" and m.get("content") == "hello" for m in b.history)
    assert any(e.kind == "done" for e in events)


@pytest.mark.asyncio
async def test_buddy_inject_emits_partial_then_final():
    sse = [
        _sse_event("hel"),
        _sse_event("lo"),
        "data: [DONE]",
    ]
    b = BuddyClaude(
        user_session_id="x",
        transcript_path=Path("/nope.jsonl"),
        anthropic_api_key="sk",
    )
    fake_client = MagicMock()
    fake_client.stream = MagicMock(return_value=_mock_stream_response(sse))
    b._client = fake_client
    events = [ev async for ev in b.inject("hi")]
    kinds = [e.kind for e in events]
    assert "partial_text" in kinds
    assert "final_text" in kinds
    assert "done" in kinds
    final = next(e for e in events if e.kind == "final_text")
    assert final.text == "hello"


@pytest.mark.asyncio
async def test_buddy_inject_ignores_malformed_sse_lines():
    sse = [
        "",
        "comment line",
        "data: not-json",
        _sse_event("ok"),
        "data: [DONE]",
    ]
    b = BuddyClaude(
        user_session_id="x",
        transcript_path=Path("/nope.jsonl"),
        anthropic_api_key="sk",
    )
    fake_client = MagicMock()
    fake_client.stream = MagicMock(return_value=_mock_stream_response(sse))
    b._client = fake_client
    events = [ev async for ev in b.inject("hi")]
    partial = [e for e in events if e.kind == "partial_text"]
    assert len(partial) == 1
    assert partial[0].text == "ok"


# ---------- BuddyManager ----------

def test_buddy_manager_creates_one_buddy_per_session(tmp_path):
    mgr = BuddyManager(api_key="sk", transcript_dir=tmp_path)
    b1 = mgr.start("sid-1")
    b2 = mgr.start("sid-1")
    assert b1 is b2  # same session reuses


def test_buddy_manager_independent_per_session(tmp_path):
    mgr = BuddyManager(api_key="sk", transcript_dir=tmp_path)
    b1 = mgr.start("sid-1")
    b2 = mgr.start("sid-2")
    assert b1 is not b2


def test_buddy_manager_stop_removes_buddy(tmp_path):
    mgr = BuddyManager(api_key="sk", transcript_dir=tmp_path)
    mgr.start("sid-1")
    mgr.stop("sid-1")
    assert "sid-1" not in mgr._buddies


def test_buddy_manager_propagates_model_and_base_url(tmp_path):
    mgr = BuddyManager(
        api_key="sk",
        transcript_dir=tmp_path,
        model="google/gemini-2.0-flash-001",
        base_url="https://example.invalid/v1",
    )
    b = mgr.start("sid-1")
    assert b.model == "google/gemini-2.0-flash-001"
    assert b.base_url == "https://example.invalid/v1"
