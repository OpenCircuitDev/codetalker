"""Anthropic Claude provider (Haiku for speed, others for quality)."""
from __future__ import annotations

from typing import AsyncIterator

from claude_code_talker.providers.base import LLMProvider


# Lazy import shim so providers/__init__.py doesn't crash if anthropic isn't installed.
try:
    from anthropic import AsyncAnthropic  # type: ignore
except ImportError:
    AsyncAnthropic = None  # type: ignore


class AnthropicProvider(LLMProvider):
    name = "anthropic"
    supports_streaming = True

    def __init__(self, api_key: str, model: str = "claude-haiku-4-5-20251001"):
        if not api_key:
            raise ValueError("AnthropicProvider requires api_key")
        self.api_key = api_key
        self.model = model

    async def complete(self, prompt: str, max_tokens: int) -> str:
        if AsyncAnthropic is None:
            raise RuntimeError("anthropic SDK not installed; pip install claude-code-talker[anthropic]")
        try:
            client = AsyncAnthropic(api_key=self.api_key)
            msg = await client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                messages=[{"role": "user", "content": prompt}],
            )
            if msg.content and hasattr(msg.content[0], "text"):
                return msg.content[0].text
            return ""
        except Exception as exc:
            raise RuntimeError(f"anthropic request failed: {exc}") from exc

    async def stream(self, prompt: str, max_tokens: int) -> AsyncIterator[str]:
        """Stream text deltas via Anthropic's native SDK streaming."""
        if AsyncAnthropic is None:
            raise RuntimeError("anthropic SDK not installed; pip install claude-code-talker[anthropic]")
        try:
            client = AsyncAnthropic(api_key=self.api_key)
            async with client.messages.stream(
                model=self.model,
                max_tokens=max_tokens,
                messages=[{"role": "user", "content": prompt}],
            ) as stream:
                async for chunk in stream.text_stream:
                    if chunk:
                        yield chunk
        except Exception as exc:
            raise RuntimeError(f"anthropic stream failed: {exc}") from exc
