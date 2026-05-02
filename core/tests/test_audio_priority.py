"""Tests for AudioQueue priority ordering."""
from unittest.mock import MagicMock, patch
from claude_code_talker.audio import AudioJob, AudioQueue


def _state():
    s = MagicMock()
    eng = MagicMock()
    eng.synthesize = MagicMock(return_value=b"WAV")
    s.engines = {"piper": eng}
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
