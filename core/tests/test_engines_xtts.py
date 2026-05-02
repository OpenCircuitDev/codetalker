"""Tests for XTTS engine adapter."""
import os
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from claude_code_talker.engines.base import TTSEngine


def test_xtts_inherits_base():
    from claude_code_talker.engines.xtts import XTTSEngine
    e = XTTSEngine(references_dir=Path("/fake"))
    assert isinstance(e, TTSEngine)
    assert e.name == "xtts"
    assert e.audio_format == "wav"


def test_xtts_list_voices_scans_references_dir(tmp_path):
    from claude_code_talker.engines.xtts import XTTSEngine
    (tmp_path / "marvin.wav").write_bytes(b"x")
    (tmp_path / "strong-bad.wav").write_bytes(b"y")
    (tmp_path / "ignored.txt").write_text("z")
    e = XTTSEngine(references_dir=tmp_path)
    assert sorted(e.list_voices()) == ["marvin", "strong-bad"]


def test_xtts_synthesize_unknown_voice_raises(tmp_path):
    from claude_code_talker.engines.xtts import XTTSEngine
    e = XTTSEngine(references_dir=tmp_path)
    with pytest.raises(ValueError, match="no reference"):
        e.synthesize("hi", "doesnotexist", rate=1.0)


def test_xtts_synthesize_calls_tts_api(tmp_path):
    from claude_code_talker.engines.xtts import XTTSEngine
    ref = tmp_path / "marvin.wav"
    ref.write_bytes(b"REFERENCE_WAV")

    fake_tts = MagicMock()
    def tts_to_file(text, speaker_wav, language, file_path):
        Path(file_path).write_bytes(b"SYNTHESIZED_WAV")
    fake_tts.tts_to_file = tts_to_file

    e = XTTSEngine(references_dir=tmp_path)
    e._tts = fake_tts  # bypass model load
    audio = e.synthesize("hi", "marvin", rate=1.0)
    assert audio == b"SYNTHESIZED_WAV"


@pytest.mark.skipif(os.environ.get("CCT_SKIP_XTTS_SMOKE", "1") == "1",
                    reason="XTTS smoke disabled (set CCT_SKIP_XTTS_SMOKE=0 to run)")
@pytest.mark.skipif(not Path.home().joinpath(".claude/scripts/voice-cloner/references").exists(),
                    reason="no references installed")
def test_xtts_real_synthesize_smoke():
    pytest.importorskip("TTS")
    from claude_code_talker.engines.xtts import XTTSEngine
    refs = Path.home() / ".claude" / "scripts" / "voice-cloner" / "references"
    voices = sorted(p.stem for p in refs.glob("*.wav"))
    if not voices:
        pytest.skip("no reference voices")
    e = XTTSEngine(references_dir=refs)
    audio = e.synthesize("hello world", voices[0], rate=1.0)
    assert len(audio) > 1000
