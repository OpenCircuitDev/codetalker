"""whisper.cpp wrapper + WhisperX forced-alignment for voice pipeline.

Two distinct concerns:
  Segment     — whisper.cpp transcription segments (preview wizard, Phase 14)
  WordTime    — WhisperX word-level timestamps (character lip-sync, Phase 16)

whisperx is NEVER imported at module load time — it pulls PyTorch which is
heavy and may not be installed. All WhisperX interaction happens via a
subprocess call to ``python -m whisperx`` or an inline helper script.
"""
from __future__ import annotations

import asyncio
import json
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

from claude_code_talker.voices.dependency_check import DEPS_DIR


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class Segment:
    """Single transcription segment from whisper.cpp output (milliseconds → seconds)."""

    start: float  # seconds
    end: float    # seconds
    text: str


@dataclass
class WordTime:
    """Word-level timestamp produced by WhisperX forced alignment (for lip-sync)."""

    text: str
    start: float  # seconds
    end: float    # seconds


# ---------------------------------------------------------------------------
# whisper.cpp helpers
# ---------------------------------------------------------------------------


def _whisper_binary() -> str:
    """Return path to whisper.cpp main binary (deps/ first, then PATH)."""
    for name in ("main", "whisper-cpp", "whisper.cpp"):
        local = DEPS_DIR / "whisper.cpp" / name
        if local.exists():
            return str(local)
    for name in ("whisper-cpp", "main"):
        which = shutil.which(name)
        if which:
            return which
    raise RuntimeError("whisper.cpp binary not found in deps/ or on PATH")


def _whisper_model() -> str:
    """Return path to ggml-small.en.bin (downloaded by auto_install)."""
    model = DEPS_DIR / "whisper.cpp" / "ggml-small.en.bin"
    if not model.exists():
        raise RuntimeError(f"whisper model missing at {model}")
    return str(model)


def parse_whisper_output(raw: str) -> list[Segment]:
    """Parse whisper.cpp JSON output into a list of Segment objects.

    whisper.cpp emits offsets in milliseconds; we convert to seconds.
    Returns empty list on empty/invalid input.
    """
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return []
    segs: list[Segment] = []
    for item in data.get("transcription", []):
        off = item.get("offsets", {})
        start_ms = off.get("from")
        end_ms = off.get("to")
        text = (item.get("text") or "").strip()
        if start_ms is None or end_ms is None or not text:
            continue
        segs.append(Segment(start=start_ms / 1000.0, end=end_ms / 1000.0, text=text))
    return segs


async def transcribe_audio(audio_path: Path) -> list[Segment]:
    """Run whisper.cpp on *audio_path* and return a list of Segment objects.

    Raises RuntimeError if the subprocess exits non-zero.
    The JSON sidecar file produced by whisper is cleaned up afterwards.
    """
    binary = _whisper_binary()
    model = _whisper_model()
    output_json = audio_path.with_suffix(".json")
    args = [
        binary,
        "-m", model,
        "-f", str(audio_path),
        "--output-json-full",
        "-of", str(audio_path.with_suffix("")),
    ]
    proc = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(f"whisper failed: {stderr.decode(errors='ignore')[:300]}")
    raw = output_json.read_text(encoding="utf-8") if output_json.exists() else ""
    output_json.unlink(missing_ok=True)
    return parse_whisper_output(raw)


# ---------------------------------------------------------------------------
# WhisperX forced-alignment
# ---------------------------------------------------------------------------

# Inline Python helper script executed in a subprocess.  We pass this as a
# ``-c`` string so we do NOT need whisperx on the daemon's sys.path.
_WHISPERX_ALIGN_SCRIPT = """\
import sys, json, whisperx, torch

audio_path = sys.argv[1]
text       = sys.argv[2]
language   = sys.argv[3] if len(sys.argv) > 3 else "en"

device = "cuda" if torch.cuda.is_available() else "cpu"
audio  = whisperx.load_audio(audio_path)
model_a, metadata = whisperx.load_align_model(language_code=language, device=device)
result = whisperx.align(
    [{"text": text, "start": 0.0, "end": 9999.0}],
    model_a,
    metadata,
    audio,
    device,
    return_char_alignments=False,
)
words = result.get("word_segments", [])
print(json.dumps([
    {"text": w.get("word", ""), "start": w.get("start", 0.0), "end": w.get("end", 0.0)}
    for w in words
]))
"""


def _whisperx_python() -> str:
    """Return the Python executable that has whisperx installed.

    Prefers the whisperx pip-target install in deps/.  Falls back to the
    current interpreter (which may or may not have it).
    """
    # whisperx was pip-installed with --target into DEPS_DIR/whisperx/
    # We just run the current interpreter with PYTHONPATH augmented to include
    # that directory; the inline script handles the import.
    return sys.executable


async def align_words(audio_path: Path, text: str) -> list[WordTime]:
    """Run WhisperX forced alignment and return word-level timestamps.

    Uses a subprocess so whisperx (+ PyTorch) is never imported into the
    daemon process.  The subprocess receives an inline ``-c`` script via
    ``asyncio.create_subprocess_exec``.

    Args:
        audio_path: Path to the WAV file to align.
        text:       Full transcript text to force-align against the audio.

    Returns:
        List of WordTime objects, one per recognised word.

    Raises:
        RuntimeError: WhisperX not installed, or alignment subprocess failed.
    """
    # Fast-path: empty text → no words to align.
    if not text.strip():
        return []

    python_exe = _whisperx_python()

    # Build PYTHONPATH so the whisperx pip-target dir is visible to the child.
    whisperx_target = DEPS_DIR / "whisperx"
    import os
    env = os.environ.copy()
    if whisperx_target.exists():
        old_pp = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = str(whisperx_target) + (os.pathsep + old_pp if old_pp else "")

    proc = await asyncio.create_subprocess_exec(
        python_exe,
        "-c", _WHISPERX_ALIGN_SCRIPT,
        str(audio_path),
        text,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
    )
    stdout, stderr = await proc.communicate()

    if proc.returncode != 0:
        err_text = stderr.decode(errors="ignore")
        # Surface a friendly error when whisperx simply isn't installed.
        if "No module named whisperx" in err_text or "whisperx" in err_text.lower():
            raise RuntimeError(
                "WhisperX not installed; lip-sync timestamps unavailable. "
                "Run auto_install to install WhisperX, or use wawa-lipsync as fallback."
            )
        raise RuntimeError(
            f"WhisperX align subprocess failed (exit {proc.returncode}): "
            f"{err_text[:300]}"
        )

    try:
        raw_words: list[dict] = json.loads(stdout.decode())
    except (json.JSONDecodeError, ValueError) as exc:
        raise RuntimeError(f"WhisperX produced invalid JSON: {exc}") from exc

    return [
        WordTime(
            text=w.get("text", ""),
            start=float(w.get("start", 0.0)),
            end=float(w.get("end", 0.0)),
        )
        for w in raw_words
    ]
