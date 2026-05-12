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

    @staticmethod
    def _system_blocks(system: str | None) -> list[dict] | None:
        """Build the system-message blocks list with ephemeral prompt caching.

        Caching activates when the system prefix exceeds the model's token
        minimum (Haiku: 2048, Sonnet/Opus: 1024). Below that, the
        ``cache_control`` field is accepted but has no effect — safe.
        Returns ``None`` when ``system`` is empty so the SDK omits the system
        param entirely (preserves pre-2026-05-11 single-message behavior).
        """
        if not system:
            return None
        return [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}]

    async def complete(self, prompt: str, max_tokens: int, *, system: str | None = None) -> str:
        if AsyncAnthropic is None:
            raise RuntimeError("anthropic SDK not installed; pip install claude-code-talker[anthropic]")
        try:
            client = AsyncAnthropic(api_key=self.api_key)
            kwargs: dict = {
                "model": self.model,
                "max_tokens": max_tokens,
                "messages": [{"role": "user", "content": prompt}],
            }
            sysblocks = self._system_blocks(system)
            if sysblocks is not None:
                kwargs["system"] = sysblocks
            msg = await client.messages.create(**kwargs)
            if msg.content and hasattr(msg.content[0], "text"):
                return msg.content[0].text
            return ""
        except Exception as exc:
            raise RuntimeError(f"anthropic request failed: {exc}") from exc

    async def stream(self, prompt: str, max_tokens: int, *, system: str | None = None) -> AsyncIterator[str]:
        """Stream text deltas via Anthropic's native SDK streaming."""
        if AsyncAnthropic is None:
            raise RuntimeError("anthropic SDK not installed; pip install claude-code-talker[anthropic]")
        try:
            client = AsyncAnthropic(api_key=self.api_key)
            kwargs: dict = {
                "model": self.model,
                "max_tokens": max_tokens,
                "messages": [{"role": "user", "content": prompt}],
            }
            sysblocks = self._system_blocks(system)
            if sysblocks is not None:
                kwargs["system"] = sysblocks
            async with client.messages.stream(**kwargs) as stream:
                async for chunk in stream.text_stream:
                    if chunk:
                        yield chunk
        except Exception as exc:
            raise RuntimeError(f"anthropic stream failed: {exc}") from exc
