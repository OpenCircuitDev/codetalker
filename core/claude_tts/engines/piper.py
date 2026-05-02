"""Piper TTS engine adapter (local subprocess)."""
from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

from claude_tts.engines.base import TTSEngine


class PiperEngine(TTSEngine):
    """Invoke the Piper binary via subprocess to synthesize speech."""

    name = "piper"

    def __init__(self, piper_exe: Path, voices_dir: Path):
        self.piper_exe = piper_exe
        self.voices_dir = voices_dir

    def list_voices(self) -> list[str]:
        if not self.voices_dir.exists():
            return []
        return sorted(p.stem for p in self.voices_dir.glob("*.onnx"))

    def synthesize(self, text: str, voice: str, rate: float) -> bytes:
        model_path = self.voices_dir / f"{voice}.onnx"
        if not model_path.exists():
            raise ValueError(f"unknown voice: {voice}")

        length_scale = 1.0 / max(rate, 0.1)

        fd, wav_path = tempfile.mkstemp(suffix=".wav", prefix="claude_tts_")
        os.close(fd)
        try:
            try:
                proc = subprocess.run(
                    [
                        str(self.piper_exe),
                        "-m", str(model_path),
                        "-f", wav_path,
                        "--length-scale", str(length_scale),
                    ],
                    input=text.encode("utf-8"),
                    capture_output=True,
                    timeout=120,
                )
            except subprocess.TimeoutExpired as exc:
                raise RuntimeError(f"piper timed out after {exc.timeout}s") from exc
            if proc.returncode != 0:
                raise RuntimeError(f"piper failed (rc={proc.returncode}): {proc.stderr[:300].decode('utf-8', errors='replace')}")
            return Path(wav_path).read_bytes()
        finally:
            try:
                os.unlink(wav_path)
            except OSError:
                pass
