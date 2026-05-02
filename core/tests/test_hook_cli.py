"""Tests for hook CLI — now an MCP client posting to the daemon."""
import asyncio
import json
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from claude_code_talker.hook_cli import dispatch_hook


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
