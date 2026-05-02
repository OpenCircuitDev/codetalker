"""Tests for the MCP server skeleton."""
import pytest
from claude_code_talker.server import build_server_state


def test_build_server_state_loads_engines_providers_modes():
    state = build_server_state()
    assert "piper" in state.engines
    assert "ollama" in state.providers
    assert "direct" in state.modes
    assert "brief" in state.modes


def test_build_server_state_has_default_active_mode():
    state = build_server_state()
    assert state.active_mode in ("direct", "brief")


def test_build_server_state_loads_config():
    state = build_server_state()
    assert isinstance(state.cfg, dict)
    assert state.cfg.get("enabled", True) in (True, False)


from claude_code_talker.server import build_mcp_server


def test_mcp_server_registers_tools():
    state = build_server_state()
    server = build_mcp_server(state)
    tool_names = {t.name for t in server.list_tools()}
    expected = {"tts_speak", "tts_set_mode", "tts_status", "tts_mute", "tts_unmute", "tts_list_voices"}
    assert expected.issubset(tool_names)


@pytest.mark.asyncio
async def test_tts_set_mode_changes_state():
    state = build_server_state()
    server = build_mcp_server(state)

    result = await server.call_tool("tts_set_mode", {"mode": "brief"})
    assert state.active_mode == "brief"
    assert "brief" in result.lower()


@pytest.mark.asyncio
async def test_tts_set_mode_rejects_unknown():
    state = build_server_state()
    server = build_mcp_server(state)

    with pytest.raises((ValueError, RuntimeError)):
        await server.call_tool("tts_set_mode", {"mode": "nonsense"})


@pytest.mark.asyncio
async def test_tts_status_reports_state():
    state = build_server_state()
    state.active_mode = "direct"
    server = build_mcp_server(state)

    result = await server.call_tool("tts_status", {})
    assert "direct" in result.lower()
    assert "enabled" in result.lower() or "muted" in result.lower()


@pytest.mark.asyncio
async def test_tts_mute_unmute_toggles_enabled():
    state = build_server_state()
    state.cfg["enabled"] = True
    server = build_mcp_server(state)

    await server.call_tool("tts_mute", {})
    assert state.cfg["enabled"] is False

    await server.call_tool("tts_unmute", {})
    assert state.cfg["enabled"] is True


from claude_code_talker.audio import AudioQueue


def test_server_state_has_audio_queue():
    state = build_server_state()
    assert isinstance(state.audio_queue, AudioQueue)


def test_server_state_audio_queue_started():
    state = build_server_state()
    # The queue's worker thread should be running after build_server_state.
    assert state.audio_queue._worker.is_alive()
    state.audio_queue.shutdown(drain_timeout=2.0)


@pytest.mark.asyncio
async def test_tts_shutdown_signals_state():
    state = build_server_state()
    server = build_mcp_server(state)

    # Track shutdown via a flag on the state.
    result = await server.call_tool("tts_shutdown", {})

    assert "shutting down" in result.lower()
    assert state.shutting_down is True
