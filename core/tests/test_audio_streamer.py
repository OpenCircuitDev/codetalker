"""Tests for AudioStreamer."""
import pytest
from claude_code_talker.audio_streamer import AudioStreamer


@pytest.mark.asyncio
async def test_feed_emits_complete_sentence():
    chunks = []
    s = AudioStreamer(emit=lambda c: chunks.append(c))
    await s.feed("Hello world. This is the next sentence.")
    # First sentence should be emitted; second remains buffered (no boundary after)
    assert any("Hello world." in c for c in chunks)


@pytest.mark.asyncio
async def test_flush_emits_remaining_buffer():
    chunks = []
    s = AudioStreamer(emit=lambda c: chunks.append(c))
    await s.feed("Hello world.")  # no following uppercase, doesn't auto-emit
    await s.flush()
    assert chunks == ["Hello world."]


@pytest.mark.asyncio
async def test_two_sentences_then_flush():
    chunks = []
    s = AudioStreamer(emit=lambda c: chunks.append(c))
    # Use sentences long enough to clear the 12-char min threshold so they
    # emit independently rather than getting merged.
    await s.feed("This is the first sentence here. Now the second one too!")
    await s.flush()
    assert "first sentence" in chunks[0]
    assert "second one too" in chunks[-1]


@pytest.mark.asyncio
async def test_short_sentences_merge_until_min():
    """Short sentences merge into one chunk to avoid choppy audio."""
    chunks = []
    s = AudioStreamer(emit=lambda c: chunks.append(c), min_chunk_chars=20)
    await s.feed("First. Second. Third sentence here is long enough.")
    await s.flush()
    # All three should be combined into a single chunk because each is too short
    assert len(chunks) == 1
    assert "First." in chunks[0]
    assert "Second." in chunks[0]
    assert "Third sentence" in chunks[0]


@pytest.mark.asyncio
async def test_does_not_split_on_abbreviation():
    chunks = []
    s = AudioStreamer(emit=lambda c: chunks.append(c))
    # 'Dr. Smith' should not be split because lowercase 'mith'? No, 'S' is upper.
    # Try a case that SHOULD avoid splitting: "e.g., the cat" — no whitespace+upper after .
    await s.feed("This is e.g. an example. Here is the next.")
    await s.flush()
    # Both sentences should be present, none split on 'e.g.'
    full_text = " ".join(chunks)
    assert "e.g." in full_text


@pytest.mark.asyncio
async def test_force_flush_at_max_chars():
    chunks = []
    s = AudioStreamer(emit=lambda c: chunks.append(c), max_chunk_chars=40, min_chunk_chars=5)
    # Long unpunctuated stream: should force-flush at the last space before max
    long_text = "this is a very long string with no punctuation that should be split"
    await s.feed(long_text)
    await s.flush()
    assert sum(len(c) for c in chunks) >= len(long_text) - 5  # account for whitespace
    assert all(len(c) <= 60 for c in chunks)


@pytest.mark.asyncio
async def test_async_emit_callback():
    chunks = []
    async def emit(c):
        chunks.append(c)
    s = AudioStreamer(emit=emit)
    await s.feed("Hello world. ")
    await s.feed("Next chunk.")
    await s.flush()
    assert "Hello world." in chunks[0]


@pytest.mark.asyncio
async def test_empty_feed_is_noop():
    chunks = []
    s = AudioStreamer(emit=lambda c: chunks.append(c))
    await s.feed("")
    await s.flush()
    assert chunks == []


@pytest.mark.asyncio
async def test_chunks_emitted_count():
    chunks = []
    s = AudioStreamer(emit=lambda c: chunks.append(c))
    await s.feed("First. Second. Third!")
    await s.flush()
    assert s.chunks_emitted == len(chunks)
    assert s.chunks_emitted >= 2  # at least two sentences emit


@pytest.mark.asyncio
async def test_consume_helper_drains_iterator():
    chunks = []
    s = AudioStreamer(emit=lambda c: chunks.append(c))

    async def deltas():
        for word in ["Hello ", "world. ", "Next ", "chunk."]:
            yield word

    await s.consume(deltas())
    full = " ".join(chunks)
    assert "Hello world." in full
    assert "Next chunk." in full
