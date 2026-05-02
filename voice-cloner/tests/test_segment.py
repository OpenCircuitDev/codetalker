"""Tests for ffmpeg-based segment extraction."""
from unittest.mock import patch, MagicMock
from claude_code_voice_cloner.segment import extract_segment


def test_extract_segment_invokes_ffmpeg(tmp_path):
    src = tmp_path / "in.mp3"
    src.write_bytes(b"FAKE")
    out = tmp_path / "out.wav"

    with patch("claude_code_voice_cloner.segment.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        out.write_bytes(b"FAKE_WAV")
        result = extract_segment(src, out, start="1:23", duration=15)

    assert result == out
    args = mock_run.call_args[0][0]
    assert "ffmpeg" in args[0]
    assert "-ss" in args
    assert "1:23" in args
    assert "-t" in args
    assert "15" in args
    # Output format normalization
    assert "-ar" in args
    assert "22050" in args
    assert "-ac" in args
    assert "1" in args
