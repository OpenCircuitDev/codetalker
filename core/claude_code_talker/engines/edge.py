"""Edge TTS engine adapter (Microsoft Edge browser TTS, free, no API key)."""
from __future__ import annotations

import asyncio

from claude_code_talker.engines.base import TTSEngine


# Lazy import shim — exposed so tests can patch claude_code_talker.engines.edge.edge_tts.Communicate
try:
    import edge_tts  # type: ignore
except ImportError:
    edge_tts = None  # type: ignore


class EdgeEngine(TTSEngine):
    """Synthesizes speech via the edge-tts package (Microsoft Edge TTS endpoint)."""

    name = "edge"
    audio_format = "mp3"  # Edge TTS returns MP3

    def __init__(self, default_voice: str = "en-US-AriaNeural"):
        self.default_voice = default_voice

    def list_voices(self) -> list[str]:
        if edge_tts is None:
            return []
        return asyncio.run(self._list_voices_async())

    async def _list_voices_async(self) -> list[str]:
        voices = await edge_tts.list_voices()
        return sorted(v["ShortName"] for v in voices)

    def synthesize(self, text: str, voice: str, rate: float) -> bytes:
        if edge_tts is None:
            raise RuntimeError("edge-tts not installed; pip install claude-code-talker[edge]")

        # Edge TTS rate format: "+0%", "-10%", "+20%"
        rate_pct = int((rate - 1.0) * 100)
        rate_str = f"{'+' if rate_pct >= 0 else ''}{rate_pct}%"

        communicate = edge_tts.Communicate(text, voice, rate=rate_str)

        async def collect():
            chunks = []
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    chunks.append(chunk["data"])
            return b"".join(chunks)

        return asyncio.run(collect())
