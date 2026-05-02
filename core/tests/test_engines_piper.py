"""Tests for Piper engine adapter."""
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from codetalker.engines.base import TTSEngine
from codetalker.engines.piper import PiperEngine


def test_piper_engine_inherits_base():
    e = PiperEngine(piper_exe=Path("/fake"), voices_dir=Path("/fake"))
    assert isinstance(e, TTSEngine)
    assert e.name == "piper"


def test_piper_list_voices_scans_directory(tmp_path):
    (tmp_path / "voice_a.onnx").write_text("")
    (tmp_path / "voice_b.onnx").write_text("")
    (tmp_path / "ignored.txt").write_text("")
    e = PiperEngine(piper_exe=Path("/fake"), voices_dir=tmp_path)
    assert sorted(e.list_voices()) == ["voice_a", "voice_b"]


def test_piper_synthesize_calls_subprocess(tmp_path):
    voice_path = tmp_path / "test.onnx"
    voice_path.write_text("")  # placeholder

    e = PiperEngine(piper_exe=Path("/fake/piper.exe"), voices_dir=tmp_path)

    with patch("codetalker.engines.piper.subprocess.run") as mock_run, \
         patch("codetalker.engines.piper.tempfile.mkstemp") as mock_mkstemp, \
         patch("codetalker.engines.piper.Path.read_bytes") as mock_read, \
         patch("codetalker.engines.piper.os.close"), \
         patch("codetalker.engines.piper.os.unlink"):
        mock_mkstemp.return_value = (1, str(tmp_path / "out.wav"))
        mock_run.return_value = MagicMock(returncode=0, stderr=b"")
        mock_read.return_value = b"FAKE_WAV_BYTES"

        wav = e.synthesize("hello", "test", rate=1.0)

        assert wav == b"FAKE_WAV_BYTES"
        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        assert "/fake/piper.exe" in str(args[0]) or "piper.exe" in str(args[0])
        assert "-m" in args
        assert "--length-scale" in args


def test_piper_synthesize_raises_on_subprocess_failure(tmp_path):
    voice_path = tmp_path / "test.onnx"
    voice_path.write_text("")
    e = PiperEngine(piper_exe=Path("/fake/piper.exe"), voices_dir=tmp_path)

    with patch("codetalker.engines.piper.subprocess.run") as mock_run, \
         patch("codetalker.engines.piper.tempfile.mkstemp") as mock_mkstemp, \
         patch("codetalker.engines.piper.os.close"), \
         patch("codetalker.engines.piper.os.unlink"):
        mock_mkstemp.return_value = (1, str(tmp_path / "out.wav"))
        mock_run.return_value = MagicMock(returncode=1, stderr=b"boom")

        with pytest.raises(RuntimeError, match="piper failed"):
            e.synthesize("hello", "test", rate=1.0)


def test_piper_synthesize_unknown_voice_raises(tmp_path):
    e = PiperEngine(piper_exe=Path("/fake/piper.exe"), voices_dir=tmp_path)
    with pytest.raises(ValueError, match="unknown voice"):
        e.synthesize("hello", "doesnotexist", rate=1.0)


def test_piper_synthesize_raises_on_timeout(tmp_path):
    voice_path = tmp_path / "test.onnx"
    voice_path.write_text("")
    e = PiperEngine(piper_exe=Path("/fake/piper.exe"), voices_dir=tmp_path)

    with patch("codetalker.engines.piper.subprocess.run") as mock_run, \
         patch("codetalker.engines.piper.tempfile.mkstemp") as mock_mkstemp, \
         patch("codetalker.engines.piper.os.close"), \
         patch("codetalker.engines.piper.os.unlink"):
        import subprocess as sp
        mock_mkstemp.return_value = (1, str(tmp_path / "out.wav"))
        mock_run.side_effect = sp.TimeoutExpired(cmd="piper", timeout=120)

        with pytest.raises(RuntimeError, match="piper timed out"):
            e.synthesize("hello", "test", rate=1.0)


def test_piper_list_voices_returns_sorted(tmp_path):
    (tmp_path / "z_voice.onnx").write_text("")
    (tmp_path / "a_voice.onnx").write_text("")
    (tmp_path / "m_voice.onnx").write_text("")
    e = PiperEngine(piper_exe=Path("/fake"), voices_dir=tmp_path)
    assert e.list_voices() == ["a_voice", "m_voice", "z_voice"]
