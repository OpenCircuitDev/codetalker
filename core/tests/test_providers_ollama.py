"""Tests for Ollama LLM provider."""
import pytest
from unittest.mock import patch, MagicMock
from codetalker.providers.base import LLMProvider
from codetalker.providers.ollama import OllamaProvider


@pytest.mark.asyncio
async def test_ollama_inherits_base():
    p = OllamaProvider(endpoint="http://localhost:11434", model="llama3.2:1b")
    assert isinstance(p, LLMProvider)
    assert p.name == "ollama"


@pytest.mark.asyncio
async def test_ollama_complete_posts_to_endpoint():
    p = OllamaProvider(endpoint="http://localhost:11434", model="llama3.2:1b")

    with patch("codetalker.providers.ollama.httpx.AsyncClient") as mock_client_cls:
        mock_client = MagicMock()
        mock_client_cls.return_value.__aenter__.return_value = mock_client
        mock_response = MagicMock()
        mock_response.json.return_value = {"response": "hello world"}
        mock_response.raise_for_status = MagicMock()

        async def post(*args, **kwargs):
            return mock_response
        mock_client.post = post

        result = await p.complete("test prompt", max_tokens=100)
        assert result == "hello world"


@pytest.mark.asyncio
async def test_ollama_complete_passes_max_tokens():
    p = OllamaProvider(endpoint="http://localhost:11434", model="llama3.2:1b")

    captured_payload = {}

    class FakeResponse:
        def raise_for_status(self):
            pass
        def json(self):
            return {"response": "ok"}

    class FakeClient:
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            pass
        async def post(self, url, json):
            captured_payload.update(json)
            return FakeResponse()

    with patch("codetalker.providers.ollama.httpx.AsyncClient", return_value=FakeClient()):
        await p.complete("hi", max_tokens=42)

    assert captured_payload["model"] == "llama3.2:1b"
    assert captured_payload["prompt"] == "hi"
    assert captured_payload["options"]["num_predict"] == 42
    assert captured_payload["stream"] is False
