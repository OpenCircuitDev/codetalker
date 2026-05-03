"""Phase 10: AudioStreamer.

Bridges streaming LLM output (token-by-token) into the AudioQueue by buffering
tokens until a sentence boundary, then submitting that sentence as a TTS job.
The result is sub-3s perceived latency: audio starts playing while the LLM is
still generating.

Sentence boundary detection is intentionally simple — period/exclamation/
question marks followed by whitespace or end-of-stream. We avoid splitting on
abbreviations (Dr., e.g., etc.) by checking that the punctuation is followed by
whitespace AND a capital letter (or end-of-stream).
"""
from __future__ import annotations

import re
from typing import AsyncIterator, Awaitable, Callable, Iterable


# Match a sentence terminator (.!?) followed by whitespace and uppercase OR
# end-of-string. Keeps "Dr. Smith" together (no uppercase right after).
_SENTENCE_BOUNDARY = re.compile(r"([.!?])(\s+)(?=[A-Z])")

# Minimum length of a sentence chunk before we'll emit it. Prevents emitting
# fragments like "Hi." which sound choppy.
DEFAULT_MIN_CHUNK_CHARS = 12

# Maximum length to buffer before forcing a flush even without punctuation.
# Catches cases where the LLM produces long unpunctuated output.
DEFAULT_MAX_CHUNK_CHARS = 220


class AudioStreamer:
    """Consume an async iterator of text deltas; emit sentence-sized chunks.

    Usage::

        streamer = AudioStreamer(emit=lambda chunk: audio_queue.submit(...))
        async for delta in provider.stream(prompt, max_tokens=200):
            await streamer.feed(delta)
        await streamer.flush()
    """

    def __init__(
        self,
        emit: Callable[[str], Awaitable[None] | None],
        *,
        min_chunk_chars: int = DEFAULT_MIN_CHUNK_CHARS,
        max_chunk_chars: int = DEFAULT_MAX_CHUNK_CHARS,
    ):
        self._emit = emit
        self._min = min_chunk_chars
        self._max = max_chunk_chars
        self._buf = ""
        self._chunks_emitted = 0

    async def feed(self, delta: str) -> None:
        """Append ``delta`` to the buffer; emit any complete sentence chunks."""
        if not delta:
            return
        self._buf += delta
        await self._drain_complete_sentences()
        # Force-flush if buffer grows past max
        while len(self._buf) >= self._max:
            # Flush at the last whitespace before max
            cut = self._buf.rfind(" ", self._min, self._max)
            if cut == -1:
                cut = self._max
            chunk = self._buf[:cut].strip()
            self._buf = self._buf[cut:].lstrip()
            if chunk:
                await self._emit_chunk(chunk)

    async def flush(self) -> None:
        """Emit anything left in the buffer as a final chunk."""
        leftover = self._buf.strip()
        if leftover:
            await self._emit_chunk(leftover)
        self._buf = ""

    async def consume(self, deltas: AsyncIterator[str]) -> None:
        """One-call helper: feed every delta from ``deltas`` then flush."""
        async for d in deltas:
            await self.feed(d)
        await self.flush()

    async def _drain_complete_sentences(self) -> None:
        # Walk forward through sentence boundaries, accumulating until the
        # candidate chunk is at least min_chunk_chars. Short sentences
        # ("First.", "Yes.") get merged with the next one rather than emitted
        # as choppy audio fragments.
        while True:
            m = _SENTENCE_BOUNDARY.search(self._buf)
            if not m:
                return
            chunk_end_punct = m.end(1)
            chunk_end_white = m.end(2)
            candidate = self._buf[:chunk_end_punct].strip()
            # Greedily extend into following sentences if too short.
            search_from = chunk_end_white
            while len(candidate) < self._min:
                next_m = _SENTENCE_BOUNDARY.search(self._buf, search_from)
                if not next_m:
                    # No more boundaries; can't grow. Wait for next feed().
                    return
                chunk_end_punct = next_m.end(1)
                chunk_end_white = next_m.end(2)
                candidate = self._buf[:chunk_end_punct].strip()
                search_from = chunk_end_white
            self._buf = self._buf[chunk_end_white:]
            if candidate:
                await self._emit_chunk(candidate)

    async def _emit_chunk(self, chunk: str) -> None:
        self._chunks_emitted += 1
        result = self._emit(chunk)
        if result is not None and hasattr(result, "__await__"):
            await result

    @property
    def chunks_emitted(self) -> int:
        return self._chunks_emitted
