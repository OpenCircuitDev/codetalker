"""CCT-31 Task 5 — TTS frames fan out to AudioStreamHub when one is wired."""
from __future__ import annotations

import asyncio
import threading
from unittest.mock import MagicMock, patch

import pytest

from claude_code_talker.audio import AudioJob, AudioQueue
from claude_code_talker.companion.audio_stream import AudioStreamHub


def _state_with_engine(audio_hub=None):
    state = MagicMock()
    engine = MagicMock()
    engine.synthesize = MagicMock(return_value=b"WAV-BYTES")
    engine.list_voices = MagicMock(return_value=["jenny", "default-voice"])
    state.engines = {"piper": engine}
    state.audio_hub = audio_hub
    # 2026-05-11: TTS caching added. Mock the cache to return None on miss.
    state.tts_cache = None
    return state, engine


def test_audio_job_carries_session_id():
    job = AudioJob(text="hi", voice="jenny", rate=1.0, session_id="sid-1")
    assert job.session_id == "sid-1"


def test_audio_job_default_session_id_is_empty():
    job = AudioJob(text="hi", voice="jenny", rate=1.0)
    assert job.session_id == ""


def test_worker_fans_synthesized_audio_to_hub():
    """When state.audio_hub is set, synthesized bytes are also published to the hub."""
    # We use a real AudioStreamHub plus an explicitly-managed event loop
    # because the AudioQueue worker runs in a daemon thread.
    loop = asyncio.new_event_loop()
    loop_thread = threading.Thread(target=loop.run_forever, daemon=True)
    loop_thread.start()
    try:
        # Ensure the loop has time to start
        import time
        time.sleep(0.05)

        async def _make_hub():
            return AudioStreamHub()

        hub = asyncio.run_coroutine_threadsafe(_make_hub(), loop).result(timeout=2.0)
        state, _engine = _state_with_engine(audio_hub=hub)
        # Inject loop reference so the worker can dispatch publish() coroutines.
        state.audio_hub_loop = loop

        q = AudioQueue(state)
        # Subscribe BEFORE publishing so we don't miss frames.
        sub = hub.subscribe("sid-x")

        with patch("claude_code_talker.audio.play_wav_bytes"):
            q.start()
            q.submit(AudioJob(
                text="hello",
                voice="jenny",
                rate=1.0,
                session_id="sid-x",
            ))
            q.join()
            q.shutdown(drain_timeout=2.0)

        # Wait for the hub publish to land. Then close the sub.
        async def _drain():
            await asyncio.sleep(0.1)  # let the worker thread schedule its publish
            await hub.close("sid-x")
            return [f async for f in sub]

        frames = asyncio.run_coroutine_threadsafe(_drain(), loop).result(timeout=2.0)
        assert b"WAV-BYTES" in frames
    finally:
        loop.call_soon_threadsafe(loop.stop)
        loop_thread.join(timeout=2.0)


def test_worker_no_fanout_when_hub_is_none():
    """When state.audio_hub is None, the worker still plays normally (no error).

    2026-05-11: backpressure logic requires either desktop_wanted or hub subscribers.
    Set companion_suppress_desktop=False (default) so desktop is in audio_outputs.
    """
    state, engine = _state_with_engine(audio_hub=None)
    # Ensure desktop is wanted so synthesis isn't skipped by backpressure logic
    state.cfg = {"companion_suppress_desktop": False}
    q = AudioQueue(state)
    with patch("claude_code_talker.audio.play_wav_bytes") as mock_play:
        q.start()
        q.submit(AudioJob(text="hello", voice="jenny", rate=1.0, session_id="sid-y"))
        q.join()
        q.shutdown(drain_timeout=2.0)
    engine.synthesize.assert_called_once()
    args, _ = mock_play.call_args
    assert args[0] == b"WAV-BYTES"
