"""Tests for audio playback."""
import pytest
from pathlib import Path
from unittest.mock import patch
from claude_code_talker.audio import play_wav_bytes


def test_play_wav_bytes_writes_temp_and_plays():
    with patch("claude_code_talker.audio.tempfile.mkstemp") as mock_mkstemp, \
         patch("claude_code_talker.audio.os.close"), \
         patch("claude_code_talker.audio.os.unlink"), \
         patch("claude_code_talker.audio.Path") as mock_path_cls, \
         patch("claude_code_talker.audio._play_file") as mock_play:
        mock_mkstemp.return_value = (1, "/tmp/x.wav")
        mock_path_instance = mock_path_cls.return_value
        mock_path_instance.write_bytes = lambda b: None

        play_wav_bytes(b"FAKE_WAV")

        mock_play.assert_called_once_with("/tmp/x.wav")


def test_play_wav_bytes_handles_empty():
    # Empty bytes should be a no-op (no exception)
    play_wav_bytes(b"")  # should not raise


from claude_code_talker.audio import AudioJob


def test_audio_job_defaults():
    job = AudioJob(text="hi", voice="jenny", rate=1.0)
    assert job.text == "hi"
    assert job.voice == "jenny"
    assert job.rate == 1.0
    assert job.engine_name == "piper"


def test_audio_job_explicit_engine():
    job = AudioJob(text="hi", voice="ryan", rate=1.2, engine_name="elevenlabs")
    assert job.engine_name == "elevenlabs"
