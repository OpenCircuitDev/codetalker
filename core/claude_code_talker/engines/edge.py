"""Edge TTS engine adapter (Microsoft Edge browser TTS, free, no API key)."""
from __future__ import annotations

import asyncio
import concurrent.futures
from typing import Coroutine, Any

from claude_code_talker.engines.base import TTSEngine


# Lazy import shim — exposed so tests can patch claude_code_talker.engines.edge.edge_tts.Communicate
try:
    import edge_tts  # type: ignore
except ImportError:
    edge_tts = None  # type: ignore


def _run_coro_safely(coro: Coroutine[Any, Any, Any]) -> Any:
    """Run an async coroutine to completion from sync code.

    Works in both contexts:
    - No running event loop (e.g., audio worker thread, CLI): asyncio.run() directly.
    - Running event loop (e.g., async REST handler calling engine.list_voices()):
      run the coroutine in a separate thread so asyncio.run() doesn't recurse
      into the active loop. This avoids the "asyncio.run() cannot be called
      from a running event loop" RuntimeError.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        # No running loop — safe to call asyncio.run directly.
        return asyncio.run(coro)
    # Running loop present — execute the coroutine in a worker thread.
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()


class EdgeEngine(TTSEngine):
    """Synthesizes speech via the edge-tts package (Microsoft Edge TTS endpoint)."""

    name = "edge"
    audio_format = "mp3"  # Edge TTS returns MP3

    def __init__(self, default_voice: str = "en-US-AriaNeural"):
        self.default_voice = default_voice

    def list_voices(self) -> list[str]:
        if edge_tts is None:
            return []
        return _run_coro_safely(self._list_voices_async())

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

        return _run_coro_safely(collect())
