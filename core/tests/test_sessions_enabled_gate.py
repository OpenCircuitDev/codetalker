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


@pytest.mark.asyncio
async def test_handle_notification_skipped_when_session_disabled():
    state = build_server_state()
    server = build_mcp_server(state)
    state.sessions.touch("disabled-sid")
    state.sessions.get("disabled-sid").enabled = False
    captured = []
    state.audio_queue.submit = lambda job: captured.append(job)

    result = await server.call_tool("tts_handle_notification", {
        "session_id": "disabled-sid",
        "message": "hello",
    })
    assert "skipped: per-session disabled" in result
    assert len(captured) == 0


@pytest.mark.asyncio
async def test_handle_pretool_skipped_and_no_event_buffer_push_when_disabled():
    state = build_server_state()
    server = build_mcp_server(state)
    state.sessions.touch("disabled-sid", cwd="/proj/c")
    state.sessions.get("disabled-sid").enabled = False
    initial_buffer_size = len(state.event_buffer.recent(1000))

    result = await server.call_tool("tts_handle_pretool", {
        "session_id": "disabled-sid",
        "tool_name": "Edit",
        "tool_input": {"file_path": "x.py"},
        "cwd": "/proj/c",
    })
    assert "skipped: per-session disabled" in result
    assert len(state.event_buffer.recent(1000)) == initial_buffer_size


@pytest.mark.asyncio
async def test_handle_posttool_skipped_and_no_event_buffer_push_when_disabled():
    state = build_server_state()
    server = build_mcp_server(state)
    state.sessions.touch("disabled-sid", cwd="/proj/d")
    state.sessions.get("disabled-sid").enabled = False
    initial_buffer_size = len(state.event_buffer.recent(1000))

    result = await server.call_tool("tts_handle_posttool", {
        "session_id": "disabled-sid",
        "tool_name": "Edit",
        "tool_input": {},
        "tool_response": {"success": True},
        "cwd": "/proj/d",
    })
    assert "skipped: per-session disabled" in result
    assert len(state.event_buffer.recent(1000)) == initial_buffer_size
