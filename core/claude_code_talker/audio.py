"""WAV playback utilities. Phase 1 is synchronous; Phase 2 adds the async queue."""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path


def _play_file(wav_path: str) -> None:
    """Platform-specific synchronous WAV playback."""
    if sys.platform == "win32":
        import winsound
        winsound.PlaySound(wav_path, winsound.SND_FILENAME)
    elif sys.platform == "darwin":
        import subprocess
        subprocess.run(["afplay", wav_path], check=False)
    else:
        import subprocess
        subprocess.run(["aplay", "-q", wav_path], check=False)


def play_wav_bytes(wav: bytes) -> None:
    """Play WAV-encoded audio synchronously (blocks until playback completes)."""
    if not wav:
        return
    fd, wav_path = tempfile.mkstemp(suffix=".wav", prefix="claude_tts_play_")
    os.close(fd)
    try:
        Path(wav_path).write_bytes(wav)
        _play_file(wav_path)
    finally:
        try:
            os.unlink(wav_path)
        except OSError:
            pass
