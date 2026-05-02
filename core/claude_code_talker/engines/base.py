"""Abstract base class for TTS engines."""
from __future__ import annotations

from abc import ABC, abstractmethod


class TTSEngine(ABC):
    """A pluggable TTS engine.

    Subclasses must define `name` (str) and implement synthesize() + list_voices().
    """

    name: str = "base"

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        if cls.name == "base":
            raise TypeError(f"{cls.__name__} must override the `name` class attribute")

    @abstractmethod
    def synthesize(self, text: str, voice: str, rate: float) -> bytes:
        """Synthesize `text` with `voice` at `rate` and return WAV bytes.

        Raises RuntimeError on engine failure, ValueError on bad voice name.
        """

    @abstractmethod
    def list_voices(self) -> list[str]:
        """Return the names of voices currently installed/available."""
