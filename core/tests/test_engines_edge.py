"""Tests for Edge TTS engine adapter."""
import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from claude_code_talker.engines.base import TTSEngine


def test_edge_engine_inherits_base():
    pytest.importorskip("edge_tts")
    from claude_code_talker.engines.edge import EdgeEngine
    e = EdgeEngine()
    assert isinstance(e, TTSEngine)
    assert e.name == "edge"


def test_edge_synthesize_returns_mp3():
    pytest.importorskip("edge_tts")
    from claude_code_talker.engines.edge import EdgeEngine
    e = EdgeEngine()

    fake_communicate = MagicMock()

    async def fake_stream():
        yield {"type": "audio", "data": b"MP3_CHUNK_1"}
        yield {"type": "audio", "data": b"MP3_CHUNK_2"}

    fake_communicate.stream = fake_stream

    with patch("claude_code_talker.engines.edge.edge_tts.Communicate", return_value=fake_communicate):
        audio = e.synthesize("hello", "en-US-AriaNeural", rate=1.0)

    assert audio == b"MP3_CHUNK_1MP3_CHUNK_2"


def test_edge_audio_format_is_mp3():
    pytest.importorskip("edge_tts")
    from claude_code_talker.engines.edge import EdgeEngine
    assert EdgeEngine.audio_format == "mp3"


@pytest.mark.skipif(
    os.environ.get("CCT_SKIP_REAL_API", "1") == "1",
    reason="real API skip (set CCT_SKIP_REAL_API=0 to run)",
)
def test_edge_real_synthesize_smoke():
    """Integration test: calls the real Microsoft Edge TTS endpoint.

    Skipped by default (CCT_SKIP_REAL_API=1). Enable with:
        set CCT_SKIP_REAL_API=0 && python -m pytest core/tests/test_engines_edge.py -v
    """
    pytest.importorskip("edge_tts")
    from claude_code_talker.engines.edge import EdgeEngine
    e = EdgeEngine()
    audio = e.synthesize("hello world", "en-US-AriaNeural", rate=1.0)
    assert len(audio) > 1000  # MP3 of "hello world" is > 1KB


# ---------------------------------------------------------------------------
# Phase 13.9b Task 5 — streaming synthesis tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_edge_synthesize_stream_yields_chunks(monkeypatch):
    """Edge engine streams chunks from Communicate.stream() rather than waiting.

    Three audio chunks are provided: chunk1 is large enough (>8KB) to trigger
    the early-dispatch threshold alone, so after the first yield the remaining
    chunks arrive individually.  All bytes must appear in the output.
    """
    pytest.importorskip("edge_tts")
    from claude_code_talker.engines.edge import EdgeEngine
    import claude_code_talker.engines.edge as edge_mod

    fake_chunks = [
        {"type": "audio", "data": b"chunk1" * 1000},  # 6000 bytes — triggers >8192 threshold with accumulation
        {"type": "audio", "data": b"chunk2" * 500},   # another 3000 bytes, threshold already crossed
        {"type": "audio", "data": b"chunk3"},
    ]

    class FakeCommunicate:
        def __init__(self, *a, **kw):
            pass

        async def stream(self):
            for c in fake_chunks:
                yield c

    monkeypatch.setattr(edge_mod.edge_tts, "Communicate", FakeCommunicate)
    engine = EdgeEngine()
    chunks = []
    async for chunk in engine.synthesize_stream("hello", "en-US-JennyNeural", 1.0):
        chunks.append(chunk)

    # Should have received at least 2 chunks (early-dispatch + remainder)
    assert len(chunks) >= 2

    # All bytes must be present in the concatenated output
    total = b"".join(chunks)
    assert b"chunk1" in total
    assert b"chunk2" in total
    assert b"chunk3" in total


@pytest.mark.asyncio
async def test_edge_synthesize_stream_single_small_chunk(monkeypatch):
    """When the cloud sends a single small chunk, it is flushed at stream end."""
    pytest.importorskip("edge_tts")
    from claude_code_talker.engines.edge import EdgeEngine
    import claude_code_talker.engines.edge as edge_mod

    class FakeCommunicate:
        def __init__(self, *a, **kw):
            pass

        async def stream(self):
            yield {"type": "audio", "data": b"small-audio"}

    monkeypatch.setattr(edge_mod.edge_tts, "Communicate", FakeCommunicate)
    engine = EdgeEngine()
    chunks = []
    async for chunk in engine.synthesize_stream("hi", "en-US-JennyNeural", 1.0):
        chunks.append(chunk)

    # At least one chunk must be emitted (the trailing flush)
    assert len(chunks) >= 1
    total = b"".join(chunks)
    assert b"small-audio" in total


@pytest.mark.asyncio
async def test_edge_synthesize_stream_skips_non_audio_chunks(monkeypatch):
    """Non-audio chunk types (metadata, WordBoundary) are silently ignored."""
    pytest.importorskip("edge_tts")
    from claude_code_talker.engines.edge import EdgeEngine
    import claude_code_talker.engines.edge as edge_mod

    class FakeCommunicate:
        def __init__(self, *a, **kw):
            pass

        async def stream(self):
            yield {"type": "WordBoundary", "data": b"ignored"}
            yield {"type": "audio", "data": b"real-audio" * 1000}
            yield {"type": "metadata", "value": "something"}
            yield {"type": "audio", "data": b"more-audio"}

    monkeypatch.setattr(edge_mod.edge_tts, "Communicate", FakeCommunicate)
    engine = EdgeEngine()
    chunks = []
    async for chunk in engine.synthesize_stream("test", "en-US-JennyNeural", 1.0):
        chunks.append(chunk)

    total = b"".join(chunks)
    assert b"real-audio" in total
    assert b"more-audio" in total
    assert b"ignored" not in total


@pytest.mark.asyncio
async def test_edge_synthesize_legacy_method_still_works(monkeypatch):
    """The non-streaming synthesize() method must still produce complete bytes
    for callers that don't use the streaming path (audit log, voice preview)."""
    pytest.importorskip("edge_tts")
    from claude_code_talker.engines.edge import EdgeEngine
    import claude_code_talker.engines.edge as edge_mod

    class FakeCommunicate:
        def __init__(self, *a, **kw):
            pass

        async def stream(self):
            yield {"type": "audio", "data": b"complete-audio-bytes"}

    monkeypatch.setattr(edge_mod.edge_tts, "Communicate", FakeCommunicate)
    engine = EdgeEngine()
    result = engine.synthesize("hello", "en-US-JennyNeural", 1.0)
    assert b"complete-audio-bytes" in result


@pytest.mark.asyncio
async def test_base_engine_default_synthesize_stream_fallback():
    """TTSEngine.synthesize_stream() default falls back to calling synthesize()
    and yielding the full bytes as a single chunk.  Any concrete engine that
    doesn't override synthesize_stream gets this behaviour for free."""
    from claude_code_talker.engines.base import TTSEngine

    class _MinimalEngine(TTSEngine):
        name = "minimal_test"

        def synthesize(self, text: str, voice: str, rate: float) -> bytes:
            return b"full-audio-" + text.encode()

        def list_voices(self) -> list[str]:
            return []

    engine = _MinimalEngine()
    chunks = []
    async for chunk in engine.synthesize_stream("world", "v1", 1.0):
        chunks.append(chunk)

    assert chunks == [b"full-audio-world"]
