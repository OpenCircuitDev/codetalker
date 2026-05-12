"""Abstract base class for LLM providers."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import AsyncIterator


class LLMProvider(ABC):
    """A pluggable LLM provider for brief generation.

    Subclasses must define `name` and implement async complete().
    Optionally override stream() for token-by-token streaming (Phase 10).
    """

    name: str = "base"
    supports_streaming: bool = False

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        if cls.name == "base":
            raise TypeError(f"{cls.__name__} must override the `name` class attribute")

    @abstractmethod
    async def complete(self, prompt: str, max_tokens: int, *, system: str | None = None) -> str:
        """Run a completion and return the generated text.

        Raises RuntimeError on provider failure.

        ``system`` is an OPTIONAL system-prompt prefix. Providers that
        support prompt caching (currently only Anthropic via
        ``cache_control: ephemeral``) put ``system`` in a separately-cached
        block. Providers that don't support caching should prepend ``system``
        to ``prompt`` as a backward-compatible fallback. Cache activation has
        a per-model token minimum (Haiku: 2048; Sonnet/Opus: 1024), so a
        short system prompt is functionally a no-op for caching but stays
        semantically correct.
        """

    async def stream(self, prompt: str, max_tokens: int, *, system: str | None = None) -> AsyncIterator[str]:
        """Stream text deltas as they arrive (Phase 10).

        Default implementation falls back to ``complete()`` and yields the
        whole result at once. Providers that support real streaming should
        override this and set ``supports_streaming = True``.
        """
        text = await self.complete(prompt, max_tokens, system=system)
        yield text
