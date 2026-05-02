"""Tests for YouTube download wrapper."""
import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path
from claude_code_voice_cloner.youtube import download_audio, YoutubeDownloadError


def test_download_audio_invokes_yt_dlp(tmp_path):
    with patch("claude_code_voice_cloner.youtube.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        # Pretend yt-dlp wrote the file
        out_path = tmp_path / "audio.mp3"
        out_path.write_bytes(b"FAKE_MP3")
        result = download_audio("https://youtu.be/x", out_path)
    assert result == out_path
    mock_run.assert_called_once()
    args = mock_run.call_args[0][0]
    assert "yt-dlp" in args[0]
    assert "https://youtu.be/x" in args


def test_download_audio_raises_on_failure(tmp_path):
    with patch("claude_code_voice_cloner.youtube.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=1, stderr="some error")
        with pytest.raises(YoutubeDownloadError):
            download_audio("https://youtu.be/bad", tmp_path / "out.mp3")
