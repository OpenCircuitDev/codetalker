"""Abstract base class for TTS engines."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import AsyncIterator


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

    async def synthesize_stream(
        self, text: str, voice: str, rate: float
    ) -> AsyncIterator[bytes]:
        """Yield audio bytes in chunks as synthesis progresses.

        The default implementation calls synthesize() and yields the full result
        as a single chunk.  Engines that support native streaming (e.g. Edge TTS)
        override this to yield chunks as the cloud server produces them, enabling
        earlier playback start (first-chunk early dispatch).

        Callers that need complete audio (audit log, voice preview) should keep
        using synthesize() directly.
        """
        yield self.synthesize(text, voice, rate)
