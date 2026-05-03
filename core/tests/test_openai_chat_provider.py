"""Tests for OpenAIChatProvider."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from claude_code_talker.providers.openai_chat import OpenAIChatProvider


def test_requires_api_key():
    with pytest.raises(ValueError):
        OpenAIChatProvider(api_key="")


def test_supports_streaming_flag():
    p = OpenAIChatProvider(api_key="sk-test")
    assert p.supports_streaming is True


def test_default_model():
    p = OpenAIChatProvider(api_key="sk-test")
    assert p.model == "gpt-4o-mini"


def test_custom_model():
    p = OpenAIChatProvider(api_key="sk-test", model="gpt-5-mini")
    assert p.model == "gpt-5-mini"


@pytest.mark.asyncio
async def test_complete_returns_choice_text(monkeypatch):
    p = OpenAIChatProvider(api_key="sk-test")

    async def fake_post(*args, **kwargs):
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json = MagicMock(return_value={
            "choices": [{"message": {"content": "Hello world"}}]
        })
        return resp

    class _FakeClient:
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return None
        post = fake_post

    monkeypatch.setattr("claude_code_talker.providers.openai_chat.httpx.AsyncClient",
                        lambda *a, **kw: _FakeClient())
    out = await p.complete("hi", max_tokens=50)
    assert out == "Hello world"


@pytest.mark.asyncio
async def test_stream_yields_deltas(monkeypatch):
    p = OpenAIChatProvider(api_key="sk-test")

    sse_lines = [
        'data: {"choices":[{"delta":{"content":"Hello"}}]}',
        'data: {"choices":[{"delta":{"content":" world"}}]}',
        'data: {"choices":[{"delta":{"content":"!"}}]}',
        'data: [DONE]',
    ]

    class _FakeStream:
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return None
        def raise_for_status(self): pass
        async def aiter_lines(self):
            for ln in sse_lines:
                yield ln

    class _FakeClient:
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return None
        def stream(self, *a, **kw):
            return _FakeStream()

    monkeypatch.setattr("claude_code_talker.providers.openai_chat.httpx.AsyncClient",
                        lambda *a, **kw: _FakeClient())

    out = []
    async for chunk in p.stream("hi", max_tokens=50):
        out.append(chunk)
    assert "".join(out) == "Hello world!"


@pytest.mark.asyncio
async def test_stream_skips_malformed_lines(monkeypatch):
    p = OpenAIChatProvider(api_key="sk-test")
    sse_lines = [
        '',  # empty
        'noise',  # no data: prefix
        'data: not-json',  # bad JSON
        'data: {"choices":[]}',  # missing delta
        'data: {"choices":[{"delta":{"content":"good"}}]}',
        'data: [DONE]',
    ]

    class _FakeStream:
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return None
        def raise_for_status(self): pass
        async def aiter_lines(self):
            for ln in sse_lines:
                yield ln

    class _FakeClient:
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return None
        def stream(self, *a, **kw):
            return _FakeStream()

    monkeypatch.setattr("claude_code_talker.providers.openai_chat.httpx.AsyncClient",
                        lambda *a, **kw: _FakeClient())

    out = []
    async for chunk in p.stream("hi", max_tokens=50):
        out.append(chunk)
    assert "".join(out) == "good"


@pytest.mark.asyncio
async def test_default_stream_yields_complete_for_non_streaming_provider():
    """Verify the LLMProvider.stream() default falls back to complete()."""
    from claude_code_talker.providers.base import LLMProvider

    class FakeProvider(LLMProvider):
        name = "fake"
        async def complete(self, prompt: str, max_tokens: int) -> str:
            return "all-at-once"

    p = FakeProvider()
    assert p.supports_streaming is False
    out = []
    async for chunk in p.stream("hi", max_tokens=50):
        out.append(chunk)
    assert out == ["all-at-once"]
