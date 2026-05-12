"""End-to-end integration test for Phase 2A hook-cli MCP client.

SKIPPED 2026-05-11: These tests were written for the MCP-SSE dispatch_hook
that validates Stop/Notification events route through _call_mcp_tool. The
2026-05-11 rewrite switched hook_cli to plain HTTP POST to /api/hooks/dispatch.
The old MCP-SSE path is gone; these tests assert obsolete behavior.

TODO (follow-up): Rewrite to mock the HTTP layer or /api/hooks/dispatch endpoint.
See docs/superpowers/specs/2026-05-11-vNext-release-design.md §2.1 C-2.
"""
import json
import pytest
from pathlib import Path
from unittest.mock import patch, AsyncMock, MagicMock
from claude_code_talker.hook_cli import dispatch_hook

pytestmark = pytest.mark.skip(
    reason="MCP-SSE dispatch path removed 2026-05-11; hook_cli now uses HTTP POST. "
    "Tests should be rewritten to mock /api/hooks/dispatch or the HTTP layer."
)


FIXTURES = Path(__file__).parent / "fixtures"


@pytest.mark.asyncio
async def test_e2e_stop_flow_calls_tts_handle_stop(tmp_path):
    transcript = tmp_path / "t.jsonl"
    transcript.write_text(
        json.dumps({"type": "user", "message": {"content": [{"type": "text", "text": "Investigate."}]}}) + "\n" +
        json.dumps({"type": "assistant", "message": {"content": [{"type": "text", "text": "Smoking gun found. The skeleton ref pose is in meters."}]}}) + "\n"
    )

    payload = {
        "hook_event_name": "Stop",
        "transcript_path": str(transcript),
        "cwd": str(tmp_path),
    }

    fake_call = AsyncMock(return_value="queued: 42 chars")

    with patch("claude_code_talker.hook_cli._call_mcp_tool", new=fake_call):
        await dispatch_hook(payload)

    fake_call.assert_called_once()
    tool_name, args = fake_call.call_args[0]
    assert tool_name == "tts_handle_stop"
    assert args["transcript_path"] == str(transcript)
    assert args["cwd"] == str(tmp_path)


@pytest.mark.asyncio
async def test_e2e_notification_flow(tmp_path):
    payload = {
        "hook_event_name": "Notification",
        "message": "Permission required.",
    }

    fake_call = AsyncMock(return_value="queued: 24 chars")

    with patch("claude_code_talker.hook_cli._call_mcp_tool", new=fake_call):
        await dispatch_hook(payload)

    fake_call.assert_called_once()
    tool_name, args = fake_call.call_args[0]
    assert tool_name == "tts_handle_notification"
    assert args["message"] == "Permission required."


@pytest.mark.asyncio
async def test_e2e_unknown_event_skips_mcp_call(tmp_path):
    payload = {"hook_event_name": "UnknownEvent"}

    fake_call = AsyncMock()

    with patch("claude_code_talker.hook_cli._call_mcp_tool", new=fake_call):
        await dispatch_hook(payload)

    fake_call.assert_not_called()
