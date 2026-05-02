"""Tests that tts_speak submits to the audio queue with the right job."""
import pytest
from unittest.mock import MagicMock
from claude_code_talker.audio import AudioJob
from claude_code_talker.server import build_server_state, build_mcp_server


@pytest.mark.asyncio
async def test_tts_speak_enqueues_job():
    state = build_server_state()
    state.cfg["enabled"] = True

    fake_engine = MagicMock()
    fake_engine.synthesize = MagicMock(return_value=b"WAV")
    fake_engine.list_voices = MagicMock(return_value=["jenny"])
    state.engines["piper"] = fake_engine

    state.cfg.setdefault("voice", {})["model"] = "jenny"
    state.cfg.setdefault("voice", {})["rate"] = 1.0

    # Replace the running queue with a mock so we can verify submit() directly.
    submitted: list[AudioJob] = []
    state.audio_queue = MagicMock()
    state.audio_queue.submit = lambda job: submitted.append(job)

    server = build_mcp_server(state)
    result = await server.call_tool("tts_speak", {"text": "hello"})

    assert len(submitted) == 1
    assert submitted[0].text == "hello"
    assert submitted[0].voice == "jenny"
    assert submitted[0].rate == 1.0
    assert "queued" in result.lower()


@pytest.mark.asyncio
async def test_tts_speak_skips_when_muted():
    state = build_server_state()
    state.cfg["enabled"] = False
    submitted: list[AudioJob] = []
    state.audio_queue = MagicMock()
    state.audio_queue.submit = lambda job: submitted.append(job)
    server = build_mcp_server(state)
    result = await server.call_tool("tts_speak", {"text": "hi"})
    assert submitted == []
    assert "mut" in result.lower()


@pytest.mark.asyncio
async def test_tts_speak_skips_when_no_text():
    state = build_server_state()
    state.cfg["enabled"] = True
    submitted: list[AudioJob] = []
    state.audio_queue = MagicMock()
    state.audio_queue.submit = lambda job: submitted.append(job)
    server = build_mcp_server(state)
    result = await server.call_tool("tts_speak", {"text": ""})
    assert submitted == []
    assert "no text" in result.lower() or "skipped" in result.lower()


@pytest.mark.asyncio
async def test_tts_speak_skips_when_no_voices():
    state = build_server_state()
    state.cfg["enabled"] = True
    fake_engine = MagicMock()
    fake_engine.list_voices = MagicMock(return_value=[])
    state.engines["piper"] = fake_engine
    state.cfg["voice"] = {}  # no model, no available voices
    submitted: list[AudioJob] = []
    state.audio_queue = MagicMock()
    state.audio_queue.submit = lambda job: submitted.append(job)
    server = build_mcp_server(state)
    result = await server.call_tool("tts_speak", {"text": "hi"})
    assert submitted == []
    assert "no voices" in result.lower() or "skipped" in result.lower()
