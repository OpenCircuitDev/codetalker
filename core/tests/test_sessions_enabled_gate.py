"""Tests for hook handlers respecting SessionState.enabled gate."""
import pytest
from claude_code_talker.server import build_server_state, build_mcp_server


@pytest.mark.asyncio
async def test_handle_stop_skipped_when_session_disabled():
    state = build_server_state()
    server = build_mcp_server(state)
    state.sessions.touch("disabled-sid", cwd="/proj/a")
    state.sessions.get("disabled-sid").enabled = False
    captured = []
    state.audio_queue.submit = lambda job: captured.append(job)

    result = await server.call_tool("tts_handle_stop", {
        "session_id": "disabled-sid",
        "transcript_path": "/t/disabled-sid.jsonl",
        "cwd": "/proj/a",
    })
    assert "skipped: per-session disabled" in result
    assert len(captured) == 0


@pytest.mark.asyncio
async def test_handle_stop_proceeds_when_session_enabled():
    state = build_server_state()
    server = build_mcp_server(state)
    state.sessions.touch("enabled-sid", cwd="/proj/b")
    captured = []
    state.audio_queue.submit = lambda job: captured.append(job)
    state.sessions.update_overlay("enabled-sid", {"enabled": True})
    result = await server.call_tool("tts_handle_stop", {
        "session_id": "enabled-sid",
        "transcript_path": "/t/nonexistent.jsonl",
        "cwd": "/proj/b",
    })
    assert "per-session disabled" not in result
