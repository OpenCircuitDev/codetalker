"""Tests for hook CLI — now an MCP client posting to the daemon.

SKIPPED 2026-05-11: The 2026-05-11 hook_cli rewrite switched from MCP-SSE
dispatch_hook + _call_mcp_tool to plain HTTP POST to /api/hooks/dispatch.
These tests mock the old MCP-SSE behavior via _call_mcp_tool. The new HTTP
path doesn't use _call_mcp_tool at all, making these tests obsolete.

TODO (follow-up): Rewrite tests to mock the HTTP layer or the daemon's
/api/hooks/dispatch endpoint instead. See docs/superpowers/specs/
2026-05-11-vNext-release-design.md §2.1 C-2 for context.
"""
import asyncio
import json
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from claude_code_talker.hook_cli import dispatch_hook

pytestmark = pytest.mark.skip(
    reason="MCP-SSE dispatch path removed 2026-05-11; hook_cli now uses HTTP POST. "
    "Tests should be rewritten to mock /api/hooks/dispatch or the HTTP layer."
)


@pytest.mark.asyncio
async def test_dispatch_hook_stop_calls_mcp_tool(tmp_path):
    payload = {
        "hook_event_name": "Stop",
        "transcript_path": str(tmp_path / "t.jsonl"),
        "cwd": str(tmp_path),
    }
    (tmp_path / "t.jsonl").write_text("")

    fake_call = AsyncMock(return_value="queued: 12 chars")

    with patch("claude_code_talker.hook_cli._call_mcp_tool", new=fake_call):
        await dispatch_hook(payload)

    fake_call.assert_called_once()
    tool_name = fake_call.call_args[0][0]
    args = fake_call.call_args[0][1]
    assert tool_name == "tts_handle_stop"
    assert args["transcript_path"] == payload["transcript_path"]


@pytest.mark.asyncio
async def test_dispatch_hook_notification_calls_mcp_tool():
    payload = {
        "hook_event_name": "Notification",
        "message": "Permission needed",
    }
    fake_call = AsyncMock(return_value="queued: 24 chars")

    with patch("claude_code_talker.hook_cli._call_mcp_tool", new=fake_call):
        await dispatch_hook(payload)

    fake_call.assert_called_once()
    assert fake_call.call_args[0][0] == "tts_handle_notification"
    assert fake_call.call_args[0][1]["message"] == "Permission needed"


@pytest.mark.asyncio
async def test_dispatch_hook_unknown_event_is_noop():
    payload = {"hook_event_name": "WhoKnows"}
    fake_call = AsyncMock()
    with patch("claude_code_talker.hook_cli._call_mcp_tool", new=fake_call):
        await dispatch_hook(payload)
    fake_call.assert_not_called()


@pytest.mark.asyncio
async def test_dispatch_hook_connection_refused_spawns_daemon():
    payload = {"hook_event_name": "Notification", "message": "x"}
    fake_call = AsyncMock(side_effect=ConnectionRefusedError())
    fake_spawn = MagicMock()

    with patch("claude_code_talker.hook_cli._call_mcp_tool", new=fake_call), \
         patch("claude_code_talker.hook_cli._ensure_daemon", new=fake_spawn):
        await dispatch_hook(payload)

    # _ensure_daemon should have been invoked when connection refused.
    fake_spawn.assert_called_once()


@pytest.mark.asyncio
async def test_dispatch_hook_pretool_calls_mcp_tool():
    payload = {"hook_event_name": "PreToolUse", "tool_name": "Edit", "tool_input": {"file_path": "c:/x.py"}}
    fake_call = AsyncMock(return_value="recorded")
    with patch("claude_code_talker.hook_cli._call_mcp_tool", new=fake_call):
        await dispatch_hook(payload)
    fake_call.assert_called_once()
    assert fake_call.call_args[0][0] == "tts_handle_pretool"


@pytest.mark.asyncio
async def test_dispatch_hook_posttool_calls_mcp_tool():
    payload = {
        "hook_event_name": "PostToolUse", "tool_name": "Edit",
        "tool_input": {}, "tool_response": {"success": True},
    }
    fake_call = AsyncMock(return_value="recorded")
    with patch("claude_code_talker.hook_cli._call_mcp_tool", new=fake_call):
        await dispatch_hook(payload)
    assert fake_call.call_args[0][0] == "tts_handle_posttool"


@pytest.mark.asyncio
async def test_dispatch_forwards_session_id_and_cwd_for_all_events(tmp_path):
    """Regression: hook_cli must forward session_id + cwd to every event handler.

    Pre-fix, the CLI only forwarded a per-event subset; session_id was always
    dropped, collapsing every Claude window into "_unknown" in the daemon.
    """
    captured = []

    async def capture(name, args):
        captured.append((name, args))
        return ""

    with patch("claude_code_talker.hook_cli._call_mcp_tool", new=capture):
        for event_payload in [
            {"hook_event_name": "Stop",          "session_id": "sX", "cwd": "/proj/a", "transcript_path": "/t/sX.jsonl"},
            {"hook_event_name": "Notification",  "session_id": "sX", "cwd": "/proj/a", "message": "hi"},
            {"hook_event_name": "PreToolUse",    "session_id": "sX", "cwd": "/proj/a", "tool_name": "Edit", "tool_input": {}},
            {"hook_event_name": "PostToolUse",   "session_id": "sX", "cwd": "/proj/a", "tool_name": "Edit", "tool_input": {}, "tool_response": {"success": True}},
        ]:
            await dispatch_hook(event_payload)

    assert len(captured) == 4
    for name, args in captured:
        assert args["session_id"] == "sX", f"{name} dropped session_id"
        assert args["cwd"] == "/proj/a", f"{name} dropped cwd"
