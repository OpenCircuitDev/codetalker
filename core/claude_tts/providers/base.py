"""Abstract base class for LLM providers."""
from __future__ import annotations

from abc import ABC, abstractmethod


class LLMProvider(ABC):
    """A pluggable LLM provider for brief generation.

    Subclasses must define `name` and implement async complete().
    """

    name: str = "base"

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        if cls.name == "base":
            raise TypeError(f"{cls.__name__} must override the `name` class attribute")

    @abstractmethod
    async def complete(self, prompt: str, max_tokens: int) -> str:
        """Run a completion and return the generated text.

        Raises RuntimeError on provider failure.
        """
