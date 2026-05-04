"""Edge TTS engine adapter (Microsoft Edge browser TTS, free, no API key)."""
from __future__ import annotations

import asyncio
import concurrent.futures
from typing import AsyncIterator, Coroutine, Any

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

    async def synthesize_stream(
        self, text: str, voice: str, rate: float
    ) -> AsyncIterator[bytes]:
        """Yield MP3 audio bytes as they arrive from the Edge TTS cloud endpoint.

        Implements first-chunk early dispatch: once ~8 KB of audio has buffered
        (roughly 200 ms of speech), the accumulated bytes are yielded immediately
        rather than waiting for the full sentence to synthesize.  Subsequent
        cloud chunks are yielded individually.  Any residual bytes at end-of-stream
        are flushed as a final yield.

        This cuts time-to-first-audio from ~2-4 s (full-sentence wait) to ~500 ms
        for typical 60-word narration sentences.

        Callers that need a single contiguous buffer (audit log, voice preview)
        should continue using synthesize() which returns complete bytes.
        """
        if edge_tts is None:
            raise RuntimeError("edge-tts not installed; pip install claude-code-talker[edge]")

        rate_pct = int((rate - 1.0) * 100)
        rate_str = f"{'+' if rate_pct >= 0 else ''}{rate_pct}%"

        communicate = edge_tts.Communicate(text, voice, rate=rate_str)

        # _EARLY_DISPATCH_THRESHOLD: number of bytes to accumulate before the
        # first yield (~200 ms of MP3 audio at 64 kbps).
        _EARLY_DISPATCH_THRESHOLD = 8192

        buffer = b""
        started = False
        async for chunk in communicate.stream():
            if chunk["type"] != "audio":
                continue
            data: bytes = chunk["data"]
            if started:
                # After first dispatch, pass subsequent chunks straight through.
                yield data
            else:
                buffer += data
                if len(buffer) >= _EARLY_DISPATCH_THRESHOLD:
                    # Enough audio buffered — dispatch early and switch to
                    # pass-through mode for all remaining chunks.
                    yield buffer
                    buffer = b""
                    started = True

        # Flush any bytes that never crossed the threshold (short utterances,
        # or a cloud response that arrived in a single large chunk).
        if buffer:
            yield buffer
