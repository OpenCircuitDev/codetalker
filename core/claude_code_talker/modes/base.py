"""Abstract base for mode strategies."""
from __future__ import annotations

from abc import ABC, abstractmethod


class ModeStrategy(ABC):
    """A strategy for turning a transcript turn into spoken text."""

    name: str = "base"

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        if cls.name == "base":
            raise TypeError(f"{cls.__name__} must override the `name` class attribute")

    @abstractmethod
    def build(
        self,
        prose_entries: list[str],
        tool_uses: list[dict],
        todos: list | None,
        cfg: dict,
    ) -> str:
        """Build the speakable text for this turn. Returns "" if nothing to say."""
