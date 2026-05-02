"""ffmpeg-based segment extraction with format normalization."""
from __future__ import annotations

import subprocess
from pathlib import Path


class SegmentError(Exception):
    pass


def extract_segment(src: Path, out_path: Path, start: str, duration: float) -> Path:
    """Extract a segment from src, normalize to 22050 Hz mono 16-bit WAV.

    start: "MM:SS" or "HH:MM:SS" or seconds
    duration: seconds
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg",
        "-y",                     # overwrite
        "-ss", str(start),
        "-t", str(duration),
        "-i", str(src),
        "-ac", "1",               # mono
        "-ar", "22050",           # 22050 Hz
        "-sample_fmt", "s16",     # 16-bit PCM
        "-loglevel", "error",
        str(out_path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise SegmentError(f"ffmpeg failed: {proc.stderr[:300]}")
    if not out_path.exists():
        raise SegmentError(f"ffmpeg succeeded but output not found at {out_path}")
    return out_path
