"""Tests that hook handlers touch sessions and use per-session config."""
import pytest
from claude_code_talker.server import build_server_state, build_mcp_server


@pytest.mark.asyncio
async def test_handle_pretool_touches_session():
    state = build_server_state()
    server = build_mcp_server(state)
    await server.call_tool("tts_handle_pretool", {
        "session_id": "sess-1",
        "tool_name": "Edit",
        "tool_input": {"file_path": "x.py"},
        "cwd": "/proj/a",
    })
    s = state.sessions.get("sess-1")
    assert s is not None
    assert s.cwd == "/proj/a"


@pytest.mark.asyncio
async def test_handle_posttool_touches_session():
    state = build_server_state()
    server = build_mcp_server(state)
    await server.call_tool("tts_handle_posttool", {
        "session_id": "sess-2",
        "tool_name": "Edit",
        "tool_input": {},
        "tool_response": {"success": True},
        "cwd": "/proj/b",
    })
    s = state.sessions.get("sess-2")
    assert s is not None
    assert s.cwd == "/proj/b"


@pytest.mark.asyncio
async def test_handle_stop_touches_session_with_transcript():
    state = build_server_state()
    server = build_mcp_server(state)
    await server.call_tool("tts_handle_stop", {
        "session_id": "sess-3",
        "transcript_path": "/t/sess-3.jsonl",
        "cwd": "/proj/c",
    })
    s = state.sessions.get("sess-3")
    assert s is not None
    assert s.transcript_path == "/t/sess-3.jsonl"


@pytest.mark.asyncio
async def test_handler_uses_per_session_overlay_voice():
    """When a session has overlay voice=marvin, the AudioJob must carry voice=marvin."""
    state = build_server_state()
    server = build_mcp_server(state)
    # Pre-create the session and overlay
    state.sessions.touch("sess-4", cwd="/proj/d")
    state.sessions.update_overlay("sess-4", {"voice": {"model": "marvin"}, "enabled": True})

    captured = []
    state.audio_queue.submit = lambda job: captured.append(job)

    await server.call_tool("tts_handle_notification", {
        "session_id": "sess-4",
        "message": "Permission required.",
    })
    assert len(captured) == 1
    assert captured[0].voice == "marvin"
