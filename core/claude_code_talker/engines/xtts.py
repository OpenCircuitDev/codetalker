"""XTTS-v2 engine adapter (Coqui TTS package)."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

from claude_code_talker.engines.base import TTSEngine


class XTTSEngine(TTSEngine):
    name = "xtts"
    audio_format = "wav"

    def __init__(self, references_dir: Path,
                 model: str = "tts_models/multilingual/multi-dataset/xtts_v2"):
        self.references_dir = references_dir
        self.model_name = model
        self._tts = None  # lazy

    def _ensure_model(self):
        if self._tts is None:
            try:
                from TTS.api import TTS
            except ImportError as exc:
                raise RuntimeError("TTS package not installed; pip install claude-code-talker[xtts]") from exc
            self._tts = TTS(self.model_name)

    def list_voices(self) -> list[str]:
        if not self.references_dir.exists():
            return []
        return sorted(p.stem for p in self.references_dir.glob("*.wav"))

    def synthesize(self, text: str, voice: str, rate: float) -> bytes:
        ref_path = self.references_dir / f"{voice}.wav"
        if not ref_path.exists():
            raise ValueError(f"no reference WAV for voice '{voice}' (expected {ref_path})")
        self._ensure_model()

        fd, out_path = tempfile.mkstemp(suffix=".wav", prefix="claude_xtts_")
        os.close(fd)
        try:
            self._tts.tts_to_file(
                text=text,
                speaker_wav=str(ref_path),
                language="en",
                file_path=out_path,
            )
            return Path(out_path).read_bytes()
        except Exception as exc:
            raise RuntimeError(f"xtts synthesis failed: {exc}") from exc
        finally:
            try:
                os.unlink(out_path)
            except OSError:
                pass
