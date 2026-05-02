"""yt-dlp wrapper for audio download."""
from __future__ import annotations

import subprocess
from pathlib import Path


class YoutubeDownloadError(Exception):
    """Raised when yt-dlp fails."""


def download_audio(url: str, out_path: Path) -> Path:
    """Download URL's audio as MP3 to out_path. Returns out_path on success.

    Raises YoutubeDownloadError on failure.
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "yt-dlp",
        "--extract-audio",
        "--audio-format", "mp3",
        "--audio-quality", "0",  # best
        "--quiet",
        "-o", str(out_path.with_suffix("")) + ".%(ext)s",
        url,
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise YoutubeDownloadError(f"yt-dlp failed: {proc.stderr[:300]}")
    if not out_path.exists():
        # yt-dlp writes <stem>.mp3 — adjust if needed
        candidate = out_path.parent / (out_path.stem + ".mp3")
        if candidate.exists():
            return candidate
        raise YoutubeDownloadError(f"yt-dlp succeeded but output not found at {out_path}")
    return out_path
