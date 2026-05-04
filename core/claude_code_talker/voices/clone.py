"""Voice clone pipeline — local file in (audio or video), cleaned WAV out.

v0.4.0: URL-based cloning (yt-dlp) is deferred to clone_from_url_optional.py.
This module handles:
  - clone_from_local_file()  — extract + clean audio from any local file
  - extract_face_frame()     — pull a still frame from video sources for avatar use
"""
from __future__ import annotations

import asyncio
import logging
import re
import sys
from pathlib import Path

from claude_code_talker.voices.dependency_check import DEPS_DIR

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MIN_DURATION_S: float = 4.0
MAX_DURATION_S: float = 12.0

_VIDEO_EXTENSIONS = frozenset({".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v"})
_AUDIO_EXTENSIONS = frozenset({".mp3", ".wav", ".m4a", ".flac", ".ogg", ".opus"})


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _ffmpeg_path() -> str:
    """Return the path to ffmpeg — cached deps/ first, then PATH."""
    exe = "ffmpeg.exe" if sys.platform == "win32" else "ffmpeg"
    local = DEPS_DIR / "ffmpeg" / exe
    return str(local) if local.exists() else "ffmpeg"


def _is_video(source: Path) -> bool:
    """Heuristic: classify source by file extension.

    Returns True for known video containers, False for audio or unknown.
    """
    return source.suffix.lower() in _VIDEO_EXTENSIONS


# ---------------------------------------------------------------------------
# Public helpers (also unit-tested directly)
# ---------------------------------------------------------------------------

def sanitize_voice_name(name: str, existing_dir: Path | None = None) -> str:
    """Strip dangerous characters from *name*; collide-resolve against *existing_dir*.

    Spaces → hyphens. Slash/backslash/dot → removed. Alphanumeric + ``_-`` kept.
    If *existing_dir* already contains ``<cleaned>.wav``, appends ``-2``, ``-3``, …
    """
    cleaned = re.sub(r"[^A-Za-z0-9_\-]", "", name.replace(" ", "-"))
    cleaned = cleaned.strip("-_") or "voice"
    if existing_dir is None:
        return cleaned
    candidate = cleaned
    suffix = 2
    while (existing_dir / f"{candidate}.wav").exists():
        candidate = f"{cleaned}-{suffix}"
        suffix += 1
    return candidate


def build_ffmpeg_clean_args(
    input_path: str,
    output_path: str,
    *,
    start: float | None = None,
    end: float | None = None,
) -> list[str]:
    """Build the ffmpeg argument list for the audio-clean pipeline.

    Pipeline: silence-trim → loudnorm → resample to 22 050 Hz mono WAV.
    If *start*/*end* are given, only that time range is processed.
    """
    args: list[str] = [_ffmpeg_path(), "-y", "-i", input_path]
    if start is not None:
        args += ["-ss", str(start)]
    if end is not None:
        args += ["-to", str(end)]
    args += [
        "-af",
        (
            "silenceremove=start_periods=1:start_duration=0.2:start_threshold=-40dB,"
            "loudnorm=I=-16:LRA=11:TP=-1.5,"
            "aresample=22050"
        ),
        "-ac", "1",
        output_path,
    ]
    return args


async def _probe_duration(path: Path) -> float:
    """Return the duration of *path* in seconds via ffprobe.

    Works for both audio and video files. Returns 0.0 on any error.
    """
    proc = await asyncio.create_subprocess_exec(
        "ffprobe",
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(path),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    out, _ = await proc.communicate()
    try:
        return float(out.decode().strip())
    except (ValueError, AttributeError):
        return 0.0


# ---------------------------------------------------------------------------
# Primary public API
# ---------------------------------------------------------------------------

async def clone_from_local_file(
    source: Path,
    *,
    name: str,
    references_dir: Path,
    start: float | None = None,
    end: float | None = None,
) -> Path:
    """Clone a voice from a local audio or video file.

    ffmpeg auto-detects the container format — no branching on file type needed.
    The audio track is extracted, silence-trimmed, loudness-normalised, and
    resampled to 22 050 Hz mono WAV, then saved to ``references_dir/<name>.wav``.

    Args:
        source: Path to the local audio or video file.
        name: Desired voice name (will be sanitized + collide-resolved).
        references_dir: Directory where cloned WAV files are stored.
        start: Optional start offset in seconds (passed to ffmpeg ``-ss``).
        end: Optional end offset in seconds (passed to ffmpeg ``-to``).

    Returns:
        Path to the written WAV file.

    Raises:
        RuntimeError: If ffmpeg exits non-zero.
        ValueError: If the cleaned audio is shorter than ``MIN_DURATION_S``.
    """
    references_dir.mkdir(parents=True, exist_ok=True)
    safe = sanitize_voice_name(name, existing_dir=references_dir)
    output = references_dir / f"{safe}.wav"

    args = build_ffmpeg_clean_args(str(source), str(output), start=start, end=end)
    proc = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()

    if proc.returncode != 0:
        output.unlink(missing_ok=True)
        raise RuntimeError(
            f"ffmpeg failed (exit {proc.returncode}): "
            f"{stderr.decode(errors='ignore')[:300]}"
        )

    duration = await _probe_duration(output)
    if duration < MIN_DURATION_S:
        output.unlink(missing_ok=True)
        raise ValueError(
            f"clip too short ({duration:.1f}s after silence-trim) — "
            f"please provide at least {MIN_DURATION_S}s of clean speech"
        )

    return output


async def extract_face_frame(
    source: Path,
    output_path: Path,
    *,
    at_seconds: float | None = None,
) -> Path | None:
    """Extract a single video frame from *source* and write it to *output_path*.

    When *source* is audio-only, returns ``None`` immediately without invoking
    ffmpeg — callers must handle the None case gracefully.

    When *at_seconds* is omitted, defaults to the video's midpoint duration / 2.

    The face frame is a best-effort auxiliary asset.  Any ffmpeg failure is
    logged as a warning and ``None`` is returned — this must never raise and
    must never crash the voice clone path.

    Args:
        source: Path to the local file (audio or video).
        output_path: Destination path for the extracted frame (e.g. face.png).
        at_seconds: Timestamp in the video to extract. Defaults to midpoint.

    Returns:
        *output_path* on success, ``None`` if source is audio-only or ffmpeg fails.
    """
    if not _is_video(source):
        return None

    try:
        ts = at_seconds
        if ts is None:
            duration = await _probe_duration(source)
            ts = duration / 2.0

        args = [
            _ffmpeg_path(),
            "-y",
            "-ss", str(ts),
            "-i", str(source),
            "-vframes", "1",
            str(output_path),
        ]
        proc = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()

        if proc.returncode != 0:
            log.warning(
                "extract_face_frame: ffmpeg exited %d — %s",
                proc.returncode,
                stderr.decode(errors="ignore")[:200],
            )
            return None

        return output_path

    except Exception as exc:  # noqa: BLE001
        log.warning("extract_face_frame: unexpected error — %s", exc)
        return None
