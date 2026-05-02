"""Tests for Anthropic provider adapter."""
import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from claude_code_talker.providers.base import LLMProvider


def test_anthropic_provider_inherits_base():
    pytest.importorskip("anthropic")
    from claude_code_talker.providers.anthropic import AnthropicProvider
    p = AnthropicProvider(api_key="sk-fake")
    assert isinstance(p, LLMProvider)
    assert p.name == "anthropic"


def test_anthropic_requires_api_key():
    pytest.importorskip("anthropic")
    from claude_code_talker.providers.anthropic import AnthropicProvider
    with pytest.raises(ValueError):
        AnthropicProvider(api_key="")


@pytest.mark.asyncio
async def test_anthropic_complete_returns_text():
    pytest.importorskip("anthropic")
    from claude_code_talker.providers.anthropic import AnthropicProvider

    fake_client = MagicMock()
    fake_msg = MagicMock()
    fake_msg.content = [MagicMock(text="hello world")]

    async def messages_create(**kwargs):
        return fake_msg

    fake_client.messages.create = messages_create

    with patch("claude_code_talker.providers.anthropic.AsyncAnthropic", return_value=fake_client):
        p = AnthropicProvider(api_key="sk-test")
        result = await p.complete("test", max_tokens=100)
    assert result == "hello world"


@pytest.mark.asyncio
async def test_anthropic_complete_wraps_errors():
    pytest.importorskip("anthropic")
    from claude_code_talker.providers.anthropic import AnthropicProvider

    fake_client = MagicMock()

    async def boom(**kwargs):
        raise RuntimeError("network error")

    fake_client.messages.create = boom

    with patch("claude_code_talker.providers.anthropic.AsyncAnthropic", return_value=fake_client):
        p = AnthropicProvider(api_key="sk-test")
        with pytest.raises(RuntimeError, match="anthropic"):
            await p.complete("test", max_tokens=100)


@pytest.mark.skipif(not os.environ.get("ANTHROPIC_API_KEY"), reason="no API key")
@pytest.mark.asyncio
async def test_anthropic_real_smoke():
    pytest.importorskip("anthropic")
    from claude_code_talker.providers.anthropic import AnthropicProvider
    p = AnthropicProvider(api_key=os.environ["ANTHROPIC_API_KEY"])
    result = await p.complete("Reply with exactly the word OK", max_tokens=10)
    assert result.strip().lower() in ("ok", "okay") or "ok" in result.lower()
