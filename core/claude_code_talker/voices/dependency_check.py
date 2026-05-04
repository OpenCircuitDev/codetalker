"""Detect yt-dlp, ffmpeg, and whisper.cpp on PATH or in cached deps dir."""
from __future__ import annotations

import shutil
import sys
from pathlib import Path


DEPS_DIR = Path.home() / ".claude" / "scripts" / "codetalker" / "deps"


def _local_binary(name: str) -> bool:
    """Check if a binary exists in our cached deps dir."""
    # Check both with and without .exe so tests and cross-platform use work.
    bare = DEPS_DIR / name / name
    exe = DEPS_DIR / name / (name + ".exe")
    return (bare.exists() and bare.is_file()) or (exe.exists() and exe.is_file())


def _on_path(name: str) -> bool:
    """Check if a binary is on PATH."""
    return shutil.which(name) is not None


def check_deps() -> dict:
    """Return per-dep presence + an install hint for the missing ones."""
    yt_dlp = _local_binary("yt-dlp") or _on_path("yt-dlp")
    ffmpeg = _local_binary("ffmpeg") or _on_path("ffmpeg")
    whisper = _local_binary("whisper.cpp") or _on_path("whisper-cpp") or _on_path("main")

    missing = [name for name, present in [
        ("yt-dlp", yt_dlp), ("ffmpeg", ffmpeg), ("whisper", whisper),
    ] if not present]

    if not missing:
        install_hint = ""
    else:
        install_hint = (
            "Missing: " + ", ".join(missing) + ". "
            "Click 'Install Now' in the Voices tab to auto-download, "
            "or install manually: pip install yt-dlp; brew install ffmpeg whisper-cpp"
        )

    return {
        "yt_dlp": yt_dlp,
        "ffmpeg": ffmpeg,
        "whisper": whisper,
        "all_present": len(missing) == 0,
        "install_hint": install_hint,
    }
