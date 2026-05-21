"""Tests for AudioQueue lifecycle."""
import time
from unittest.mock import MagicMock, patch
from claude_code_talker.audio import AudioJob, AudioQueue


# ─── skip_current — user-initiated narration interrupt (2026-05-21) ─────────


def test_skip_current_drains_full_queue_when_no_session_filter():
    """Global skip (session_id=None) drops every pending job."""
    state, _ = _state_with_engine()
    q = AudioQueue(state)
    # Submit three jobs across two sessions without starting the worker
    # so they sit in the queue.
    q.submit(AudioJob(text="one", voice="v", rate=1.0, session_id="sid-A"))
    q.submit(AudioJob(text="two", voice="v", rate=1.0, session_id="sid-B"))
    q.submit(AudioJob(text="three", voice="v", rate=1.0, session_id="sid-A"))
    # AudioQueue's drop-on-overlap will collapse "one" (older sid-A) when
    # "three" lands, so we expect 2 pending jobs at this point.
    assert len(q._queue) == 2

    result = q.skip_current(session_id=None)

    assert result["dropped"] == 2
    assert result["interrupted"] is True
    assert len(q._queue) == 0


def test_skip_current_filters_to_one_session():
    """Per-session skip drops only that session's jobs; others survive."""
    state, _ = _state_with_engine()
    q = AudioQueue(state)
    q.submit(AudioJob(text="A1", voice="v", rate=1.0, session_id="sid-A"))
    q.submit(AudioJob(text="B1", voice="v", rate=1.0, session_id="sid-B"))
    # After drop-on-overlap collapses each session to one entry, we have 2 in queue.
    assert len(q._queue) == 2

    result = q.skip_current(session_id="sid-A")

    assert result["dropped"] == 1
    # sid-B's job should still be in the queue.
    assert len(q._queue) == 1
    _, _, surviving = q._queue[0]
    assert surviving.session_id == "sid-B"


def test_skip_current_returns_zero_when_queue_empty():
    """No-op skip still reports interrupted=True (handle.stop is idempotent)."""
    state, _ = _state_with_engine()
    q = AudioQueue(state)
    result = q.skip_current(session_id=None)
    assert result == {"interrupted": True, "dropped": 0}


def _state_with_engine():
    state = MagicMock()
    engine = MagicMock()
    engine.synthesize = MagicMock(return_value=b"WAV")
    engine.list_voices = MagicMock(return_value=["jenny", "default"])
    state.engines = {"piper": engine}
    # 2026-05-11: TTS caching added. Mock the cache to return None on miss.
    state.tts_cache = None
    # 2026-05-11: backpressure logic requires either desktop_wanted or hub subscribers.
    # Set companion_suppress_desktop=False (default) so desktop is in audio_outputs.
    state.cfg = {"companion_suppress_desktop": False}
    return state, engine


def test_queue_constructs_with_state():
    state, _ = _state_with_engine()
    q = AudioQueue(state)
    assert q is not None  # constructed without error


def test_queue_start_idempotent_signal():
    state, _ = _state_with_engine()
    q = AudioQueue(state)
    q.start()
    # No second start; just confirm it runs cleanly and worker is alive
    assert q._worker.is_alive()
    q.shutdown(drain_timeout=2.0)


def test_queue_shutdown_stops_worker():
    state, _ = _state_with_engine()
    q = AudioQueue(state)
    q.start()
    q.shutdown(drain_timeout=2.0)
    # After shutdown, the worker thread should not be alive
    time.sleep(0.1)
    assert not q._worker.is_alive()


def test_worker_synthesizes_and_plays():
    state, engine = _state_with_engine()
    q = AudioQueue(state)

    with patch("claude_code_talker.audio.play_wav_bytes") as mock_play:
        q.start()
        q.submit(AudioJob(text="hello", voice="jenny", rate=1.0))
        q.join()  # wait for worker to drain
        q.shutdown(drain_timeout=2.0)

    engine.synthesize.assert_called_once_with("hello", "jenny", 1.0)
    args, _ = mock_play.call_args
    assert args[0] == b"WAV"


def test_worker_continues_after_synth_error():
    state, engine = _state_with_engine()
    # First call raises, second succeeds — worker must survive.
    engine.synthesize.side_effect = [RuntimeError("boom"), b"WAV2"]
    q = AudioQueue(state)

    with patch("claude_code_talker.audio.play_wav_bytes") as mock_play:
        q.start()
        q.submit(AudioJob(text="first", voice="jenny", rate=1.0))
        q.submit(AudioJob(text="second", voice="jenny", rate=1.0))
        q.join()
        q.shutdown(drain_timeout=2.0)

    assert engine.synthesize.call_count == 2
    assert mock_play.call_count == 1
    args, _ = mock_play.call_args
    assert args[0] == b"WAV2"  # only the successful one


def test_worker_continues_after_play_error():
    state, engine = _state_with_engine()
    q = AudioQueue(state)

    with patch("claude_code_talker.audio.play_wav_bytes") as mock_play:
        mock_play.side_effect = [OSError("device busy"), None]
        q.start()
        q.submit(AudioJob(text="first", voice="jenny", rate=1.0))
        q.submit(AudioJob(text="second", voice="jenny", rate=1.0))
        q.join()
        q.shutdown(drain_timeout=2.0)

    assert engine.synthesize.call_count == 2
    assert mock_play.call_count == 2  # both attempted; second succeeded
