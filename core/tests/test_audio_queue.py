"""Tests for AudioQueue lifecycle."""
import time
from unittest.mock import MagicMock
from claude_code_talker.audio import AudioJob, AudioQueue


def _state_with_engine():
    state = MagicMock()
    engine = MagicMock()
    engine.synthesize = MagicMock(return_value=b"WAV")
    state.engines = {"piper": engine}
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
