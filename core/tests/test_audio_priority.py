"""Tests for AudioQueue priority ordering."""
from unittest.mock import MagicMock, patch
from claude_code_talker.audio import AudioJob, AudioQueue


def _state():
    s = MagicMock()
    eng = MagicMock()
    eng.synthesize = MagicMock(return_value=b"WAV")
    eng.list_voices = MagicMock(return_value=["v", "default"])
    s.engines = {"piper": eng}
    # 2026-05-11: TTS caching added. Mock the cache to return None on miss.
    s.tts_cache = None
    # 2026-05-11: backpressure logic requires either desktop_wanted or hub subscribers.
    # Set companion_suppress_desktop=False (default) so desktop is in audio_outputs.
    s.cfg = {"companion_suppress_desktop": False}
    return s


def test_alert_jumps_normal():
    """An alert submitted after normal jobs is dispatched first."""
    state = _state()
    q = AudioQueue(state)
    played: list[bytes] = []

    def fake_play(wav):
        played.append(wav)
    with patch("claude_code_talker.audio.play_wav_bytes", side_effect=fake_play):
        # Don't start worker yet — submit jobs first then start so order is deterministic
        q.submit(AudioJob(text="normal-1", voice="v", rate=1.0, priority="normal"))
        q.submit(AudioJob(text="normal-2", voice="v", rate=1.0, priority="normal"))
        q.submit(AudioJob(text="alert-1", voice="v", rate=1.0, priority="alert"))
        q.start()
        q.join()
        q.shutdown(drain_timeout=2.0)

    # Verify alert played before normals (engine.synthesize call order)
    calls = [c.args[0] for c in state.engines["piper"].synthesize.call_args_list]
    # alert jumps the line: order is alert, normal-1, normal-2
    assert calls[0] == "alert-1"


import time


def test_drop_policy_keeps_alerts_drops_old_normals():
    state = _state()
    q = AudioQueue(state, max_depth=3, staleness_seconds=10.0)
    # 5 normals + 1 alert; queue depth should drop to 3 keeping the alert
    for i in range(5):
        q.submit(AudioJob(text=f"n{i}", voice="v", rate=1.0, priority="normal"))
    q.submit(AudioJob(text="alert", voice="v", rate=1.0, priority="alert"))
    # After submits, depth was capped: alerts always retained, oldest normals dropped
    with q._cv:
        depths_by_priority = sorted([j.priority for _, _, j in q._queue])
    assert "alert" in depths_by_priority
    assert depths_by_priority.count("normal") <= 3 - 1  # because alert took 1 slot


def test_stale_jobs_dropped_on_dispatch():
    state = _state()
    q = AudioQueue(state, max_depth=10, staleness_seconds=0.1)
    stale = AudioJob(text="stale", voice="v", rate=1.0, priority="normal")
    stale.enqueued_at = time.time() - 5  # 5s old, exceeds staleness
    q.submit(stale)
    q.submit(AudioJob(text="fresh", voice="v", rate=1.0, priority="normal"))
    q.start()
    q.join()
    q.shutdown()
    calls = [c.args[0] for c in state.engines["piper"].synthesize.call_args_list]
    assert "stale" not in calls
    assert "fresh" in calls


def test_alert_during_normal_calls_handle_stop():
    state = _state()
    q = AudioQueue(state)
    with patch.object(q._handle, "stop") as mock_stop:
        q.submit(AudioJob(text="normal", voice="v", rate=1.0, priority="normal"))
        q.submit(AudioJob(text="alert", voice="v", rate=1.0, priority="alert"))
    # The submit() of an alert should have invoked handle.stop()
    mock_stop.assert_called_once()
