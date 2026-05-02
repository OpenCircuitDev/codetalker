"""Tests for ElevenLabs engine adapter."""
import os
import pytest
from unittest.mock import patch, MagicMock
from claude_code_talker.engines.base import TTSEngine


def test_elevenlabs_inherits_base():
    from claude_code_talker.engines.elevenlabs import ElevenLabsEngine
    e = ElevenLabsEngine(api_key="sk-fake")
    assert isinstance(e, TTSEngine)
    assert e.name == "elevenlabs"
    assert e.audio_format == "mp3"


def test_elevenlabs_synthesize_calls_api():
    from claude_code_talker.engines.elevenlabs import ElevenLabsEngine
    e = ElevenLabsEngine(api_key="sk-test")

    fake_response = MagicMock()
    fake_response.content = b"MP3_BYTES"
    fake_response.raise_for_status = MagicMock()

    fake_client = MagicMock()
    fake_client.__enter__ = MagicMock(return_value=fake_client)
    fake_client.__exit__ = MagicMock(return_value=None)
    fake_client.post = MagicMock(return_value=fake_response)

    with patch("claude_code_talker.engines.elevenlabs.httpx.Client", return_value=fake_client):
        audio = e.synthesize("hello", "voice_xyz", rate=1.0)

    assert audio == b"MP3_BYTES"
    args, kwargs = fake_client.post.call_args
    url = args[0]
    assert "voice_xyz" in url
    assert kwargs["headers"]["xi-api-key"] == "sk-test"


def test_elevenlabs_synthesize_rate_limited():
    from claude_code_talker.engines.elevenlabs import ElevenLabsEngine
    import httpx
    e = ElevenLabsEngine(api_key="sk-test")

    fake_response = MagicMock()
    fake_response.raise_for_status = MagicMock(
        side_effect=httpx.HTTPStatusError(
            "rate limited", request=MagicMock(), response=MagicMock(status_code=429)
        )
    )
    fake_client = MagicMock()
    fake_client.__enter__ = MagicMock(return_value=fake_client)
    fake_client.__exit__ = MagicMock(return_value=None)
    fake_client.post = MagicMock(return_value=fake_response)

    with patch("claude_code_talker.engines.elevenlabs.httpx.Client", return_value=fake_client):
        with pytest.raises(RuntimeError, match="elevenlabs"):
            e.synthesize("hi", "v", rate=1.0)


@pytest.mark.skipif(not os.environ.get("ELEVENLABS_API_KEY"), reason="no API key")
def test_elevenlabs_real_synthesize_smoke():
    from claude_code_talker.engines.elevenlabs import ElevenLabsEngine
    e = ElevenLabsEngine(api_key=os.environ["ELEVENLABS_API_KEY"])
    audio = e.synthesize("hello", "pNInz6obpgDQGcFmaJgB", rate=1.0)
    assert len(audio) > 1000
