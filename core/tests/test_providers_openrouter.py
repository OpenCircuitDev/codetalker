"""Tests for OpenRouter provider."""
import os
import pytest
import httpx
from unittest.mock import AsyncMock, MagicMock, patch
from claude_code_talker.providers.base import LLMProvider
import claude_code_talker.providers.openrouter as _or_mod


@pytest.fixture(autouse=True)
def reset_openrouter_singleton():
    """Reset the module-level singleton before each test so patching works cleanly."""
    _or_mod._CLIENT = None
    yield
    _or_mod._CLIENT = None


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


# --- Singleton / connection-pool tests (Phase 13.9b Task 6) ---


def test_get_client_returns_same_singleton():
    """_get_client() must return the same object on repeated calls (no re-creation)."""
    from claude_code_talker.providers.openrouter import _get_client
    a = _get_client()
    b = _get_client()
    assert a is b


def test_get_client_is_async_client():
    """Verify the pool is an httpx.AsyncClient instance."""
    from claude_code_talker.providers.openrouter import _get_client
    c = _get_client()
    assert isinstance(c, httpx.AsyncClient)


def test_get_client_singleton_survives_multiple_provider_instances():
    """Different provider instances share the same underlying client pool."""
    from claude_code_talker.providers.openrouter import OpenRouterProvider, _get_client
    _ = OpenRouterProvider(api_key="sk-a")
    _ = OpenRouterProvider(api_key="sk-b")
    a = _get_client()
    b = _get_client()
    assert a is b


@pytest.mark.skipif(not os.environ.get("OPENROUTER_API_KEY"), reason="no API key")
@pytest.mark.asyncio
async def test_openrouter_real_smoke():
    from claude_code_talker.providers.openrouter import OpenRouterProvider
    p = OpenRouterProvider(api_key=os.environ["OPENROUTER_API_KEY"])
    result = await p.complete("Reply with exactly: OK", max_tokens=10)
    assert "ok" in result.lower()
