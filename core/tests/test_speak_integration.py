"""Tests that tts_speak dispatches to the active engine + audio playback."""
import pytest
from unittest.mock import patch, MagicMock
from claude_code_talker.server import build_server_state, build_mcp_server


@pytest.mark.asyncio
async def test_tts_speak_invokes_engine_and_plays():
    state = build_server_state()

    fake_engine = MagicMock()
    fake_engine.synthesize = MagicMock(return_value=b"FAKE_WAV")
    fake_engine.list_voices = MagicMock(return_value=["en_GB-jenny_dioco-medium"])
    state.engines["piper"] = fake_engine
    state.cfg["enabled"] = True
    state.cfg.setdefault("voice", {})["model"] = "en_GB-jenny_dioco-medium"
    state.cfg.setdefault("voice", {})["rate"] = 1.0

    server = build_mcp_server(state)

    with patch("claude_code_talker.server.play_wav_bytes") as mock_play:
        result = await server.call_tool("tts_speak", {"text": "hello"})
        fake_engine.synthesize.assert_called_once()
        mock_play.assert_called_once_with(b"FAKE_WAV")
        assert "spoke" in result.lower() or "ok" in result.lower()


@pytest.mark.asyncio
async def test_tts_speak_returns_no_op_when_muted():
    state = build_server_state()
    state.cfg["enabled"] = False

    fake_engine = MagicMock()
    state.engines["piper"] = fake_engine

    server = build_mcp_server(state)
    with patch("claude_code_talker.server.play_wav_bytes") as mock_play:
        result = await server.call_tool("tts_speak", {"text": "hello"})
    fake_engine.synthesize.assert_not_called()
    mock_play.assert_not_called()
    assert "mut" in result.lower()
