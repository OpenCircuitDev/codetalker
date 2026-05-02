"""Tests for Edge TTS engine adapter."""
import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from claude_code_talker.engines.base import TTSEngine


def test_edge_engine_inherits_base():
    pytest.importorskip("edge_tts")
    from claude_code_talker.engines.edge import EdgeEngine
    e = EdgeEngine()
    assert isinstance(e, TTSEngine)
    assert e.name == "edge"


def test_edge_synthesize_returns_mp3():
    pytest.importorskip("edge_tts")
    from claude_code_talker.engines.edge import EdgeEngine
    e = EdgeEngine()

    fake_communicate = MagicMock()

    async def fake_stream():
        yield {"type": "audio", "data": b"MP3_CHUNK_1"}
        yield {"type": "audio", "data": b"MP3_CHUNK_2"}

    fake_communicate.stream = fake_stream

    with patch("claude_code_talker.engines.edge.edge_tts.Communicate", return_value=fake_communicate):
        audio = e.synthesize("hello", "en-US-AriaNeural", rate=1.0)

    assert audio == b"MP3_CHUNK_1MP3_CHUNK_2"


def test_edge_audio_format_is_mp3():
    pytest.importorskip("edge_tts")
    from claude_code_talker.engines.edge import EdgeEngine
    assert EdgeEngine.audio_format == "mp3"


@pytest.mark.skipif(os.environ.get("CCT_SKIP_REAL_API", "1") == "1", reason="real API skip (set CCT_SKIP_REAL_API=0 to run)")
def test_edge_real_synthesize_smoke():
    pytest.importorskip("edge_tts")
    from claude_code_talker.engines.edge import EdgeEngine
    e = EdgeEngine()
    audio = e.synthesize("hello world", "en-US-AriaNeural", rate=1.0)
    assert len(audio) > 1000  # MP3 of "hello world" is > 1KB
