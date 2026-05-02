"""Tests for OpenRouter provider."""
import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from claude_code_talker.providers.base import LLMProvider


def test_openrouter_inherits_base():
    from claude_code_talker.providers.openrouter import OpenRouterProvider
    p = OpenRouterProvider(api_key="sk-fake")
    assert isinstance(p, LLMProvider)
    assert p.name == "openrouter"


@pytest.mark.asyncio
async def test_openrouter_complete_posts_chat_completions():
    from claude_code_talker.providers.openrouter import OpenRouterProvider

    captured = {}

    class FakeResponse:
        def raise_for_status(self): pass
        def json(self):
            return {"choices": [{"message": {"content": "response text"}}]}

    class FakeClient:
        def __init__(self, **kw): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): pass
        async def post(self, url, headers, json):
            captured["url"] = url
            captured["headers"] = headers
            captured["json"] = json
            return FakeResponse()

    with patch("claude_code_talker.providers.openrouter.httpx.AsyncClient", return_value=FakeClient()):
        p = OpenRouterProvider(api_key="sk-test", model="anthropic/claude-haiku-4-5")
        result = await p.complete("hi", max_tokens=42)

    assert result == "response text"
    assert "openrouter.ai" in captured["url"]
    assert captured["headers"]["Authorization"] == "Bearer sk-test"
    assert captured["json"]["model"] == "anthropic/claude-haiku-4-5"
    assert captured["json"]["max_tokens"] == 42


@pytest.mark.asyncio
async def test_openrouter_wraps_http_errors():
    from claude_code_talker.providers.openrouter import OpenRouterProvider
    import httpx

    class ErrClient:
        def __init__(self, **kw): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): pass
        async def post(self, *a, **kw):
            raise httpx.HTTPError("boom")

    with patch("claude_code_talker.providers.openrouter.httpx.AsyncClient", return_value=ErrClient()):
        p = OpenRouterProvider(api_key="sk-test")
        with pytest.raises(RuntimeError, match="openrouter"):
            await p.complete("hi", max_tokens=10)


@pytest.mark.skipif(not os.environ.get("OPENROUTER_API_KEY"), reason="no API key")
@pytest.mark.asyncio
async def test_openrouter_real_smoke():
    from claude_code_talker.providers.openrouter import OpenRouterProvider
    p = OpenRouterProvider(api_key=os.environ["OPENROUTER_API_KEY"])
    result = await p.complete("Reply with exactly: OK", max_tokens=10)
    assert "ok" in result.lower()
