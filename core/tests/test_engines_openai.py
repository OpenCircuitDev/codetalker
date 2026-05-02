"""Tests for OpenAI TTS engine adapter."""
import os
import pytest
from unittest.mock import patch, MagicMock
from claude_code_talker.engines.base import TTSEngine


def test_openai_inherits_base():
    from claude_code_talker.engines.openai import OpenAIEngine
    e = OpenAIEngine(api_key="sk-fake")
    assert isinstance(e, TTSEngine)
    assert e.name == "openai"
    assert e.audio_format == "wav"


def test_openai_synthesize_calls_api():
    from claude_code_talker.engines.openai import OpenAIEngine
    e = OpenAIEngine(api_key="sk-test")

    fake_response = MagicMock()
    fake_response.content = b"WAV_BYTES"
    fake_response.raise_for_status = MagicMock()

    fake_client = MagicMock()
    fake_client.__enter__ = MagicMock(return_value=fake_client)
    fake_client.__exit__ = MagicMock(return_value=None)
    fake_client.post = MagicMock(return_value=fake_response)

    with patch("claude_code_talker.engines.openai.httpx.Client", return_value=fake_client):
        audio = e.synthesize("hello", "nova", rate=1.0)

    assert audio == b"WAV_BYTES"
    args, kwargs = fake_client.post.call_args
    url = args[0]
    assert "audio/speech" in url
    assert kwargs["headers"]["Authorization"] == "Bearer sk-test"
    assert kwargs["json"]["voice"] == "nova"


def test_openai_synthesize_unknown_voice_raises():
    from claude_code_talker.engines.openai import OpenAIEngine
    e = OpenAIEngine(api_key="sk-test")
    with pytest.raises(ValueError, match="unknown voice"):
        e.synthesize("hi", "not-a-voice", rate=1.0)


def test_openai_list_voices_returns_canonical_set():
    from claude_code_talker.engines.openai import OpenAIEngine
    e = OpenAIEngine(api_key="sk-test")
    voices = e.list_voices()
    assert "nova" in voices
    assert "alloy" in voices


@pytest.mark.skipif(not os.environ.get("OPENAI_API_KEY"), reason="no API key")
def test_openai_real_synthesize_smoke():
    from claude_code_talker.engines.openai import OpenAIEngine
    e = OpenAIEngine(api_key=os.environ["OPENAI_API_KEY"])
    audio = e.synthesize("hello", "nova", rate=1.0)
    assert len(audio) > 1000
