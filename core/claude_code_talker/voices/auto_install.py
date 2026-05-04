"""Auto-install ffmpeg / whisper.cpp model / WhisperX / gltf-pipeline into deps/.

v0.4.0 revised scope:
  - ffmpeg       — static binary per OS (BtbN builds / evermeet)
  - whisper.cpp  — model download (ggml-small.en.bin); binary via package manager
  - WhisperX     — pip install --target <deps>/whisperx/ (brings PyTorch)
  - gltf-pipeline — npm install if Node on PATH; else warn + continue

yt-dlp is intentionally excluded (optional v0.4.1 feature).
"""
from __future__ import annotations

import asyncio
import logging
import platform
import shutil
import sys
import tarfile
import urllib.request
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from claude_code_talker.voices.dependency_check import check_deps, DEPS_DIR


log = logging.getLogger(__name__)

_FFMPEG_BASE = "https://github.com/BtbN/FFmpeg-Builds/releases/latest/download/"
_WHISPER_MODEL_URL = (
    "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-small.en.bin"
)


# ---------------------------------------------------------------------------
# State dataclass
# ---------------------------------------------------------------------------


@dataclass
class InstallTaskState:
    """Tracks progress of a background install operation."""

    step: str = ""
    percent: int = 0
    error: str | None = None
    done: bool = False

    def update(self, *, step: str | None = None, percent: int | None = None) -> None:
        """Atomically update step and/or percent."""
        if step is not None:
            self.step = step
        if percent is not None:
            self.percent = percent


# ---------------------------------------------------------------------------
# Platform URL helpers
# ---------------------------------------------------------------------------


def _ffmpeg_archive_url_for_platform() -> str:
    """Return the BtbN (or evermeet on macOS) download URL for the current OS."""
    sysname = platform.system().lower()
    arch = platform.machine().lower()
    if sysname == "windows":
        return _FFMPEG_BASE + "ffmpeg-master-latest-win64-gpl.zip"
    if sysname == "darwin":
        # BtbN doesn't ship macOS builds; evermeet is the de-facto community build.
        return "https://evermeet.cx/ffmpeg/getrelease/zip"
    # Linux — pick arm64 or x86-64
    if "aarch64" in arch or "arm64" in arch:
        return _FFMPEG_BASE + "ffmpeg-master-latest-linuxarm64-gpl.tar.xz"
    return _FFMPEG_BASE + "ffmpeg-master-latest-linux64-gpl.tar.xz"


# ---------------------------------------------------------------------------
# Individual installers
# ---------------------------------------------------------------------------


async def _install_ffmpeg(state: InstallTaskState) -> None:
    """Download a static ffmpeg binary for the current platform."""
    state.update(step="ffmpeg", percent=10)
    url = _ffmpeg_archive_url_for_platform()
    target_dir = DEPS_DIR / "ffmpeg"
    target_dir.mkdir(parents=True, exist_ok=True)
    archive_path = target_dir / "archive"

    await asyncio.to_thread(urllib.request.urlretrieve, url, str(archive_path))

    state.update(percent=25)
    # Extract — detect format by URL suffix
    if url.endswith(".zip"):
        with zipfile.ZipFile(archive_path) as z:
            z.extractall(target_dir)
    else:
        with tarfile.open(archive_path) as t:
            t.extractall(target_dir)

    archive_path.unlink(missing_ok=True)

    # Locate the extracted binary and normalise to target_dir/ffmpeg(.exe)
    exe_name = "ffmpeg.exe" if sys.platform == "win32" else "ffmpeg"
    found = next(target_dir.rglob(exe_name), None)
    if found is None:
        raise RuntimeError(f"ffmpeg binary not found after extracting {url}")
    final = target_dir / exe_name
    if found != final:
        found.rename(final)
    try:
        final.chmod(0o755)
    except OSError:
        pass

    state.update(step="ffmpeg-done", percent=30)


async def _install_whisper(state: InstallTaskState) -> None:
    """Download whisper.cpp model and write installation instructions."""
    state.update(step="whisper", percent=35)
    target_dir = DEPS_DIR / "whisper.cpp"
    target_dir.mkdir(parents=True, exist_ok=True)
    model_path = target_dir / "ggml-small.en.bin"
    if not model_path.exists():
        await asyncio.to_thread(urllib.request.urlretrieve, _WHISPER_MODEL_URL, str(model_path))

    # whisper.cpp binary must be installed via the user's package manager or built
    # from source — we can't ship a universal static binary here.
    readme = target_dir / "README.txt"
    readme.write_text(
        "whisper.cpp model downloaded.\n"
        "To enable transcription, install the whisper.cpp binary:\n"
        "  brew install whisper-cpp          (macOS)\n"
        "  apt install whisper-cpp           (Ubuntu, if available)\n"
        "Or build from https://github.com/ggerganov/whisper.cpp\n"
        "and place the binary here as 'main' or 'whisper-cpp'.\n",
        encoding="utf-8",
    )
    state.update(step="whisper-done", percent=55)


async def _install_whisperx(state: InstallTaskState) -> None:
    """pip install whisperx --target <deps>/whisperx/.

    WhisperX pulls PyTorch + CUDA detection (~1-2 GB on first run).
    On CPU-only systems it falls back to slower CPU alignment.
    """
    state.update(step="whisperx", percent=60)
    target = DEPS_DIR / "whisperx"
    target.mkdir(parents=True, exist_ok=True)
    proc = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m", "pip", "install",
        "--target", str(target),
        "--upgrade",
        "whisperx",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(
            f"whisperx pip install failed: {stderr.decode(errors='ignore')[:300]}"
        )
    state.update(step="whisperx-done", percent=80)


async def _install_gltf_pipeline(state: InstallTaskState) -> None:
    """Install @gltf-transform/cli via npm if Node is on PATH; otherwise warn + continue.

    FBX→GLB conversion will fail later if Node is absent, but all other features
    (ffmpeg, whisper, voice clone) still work — so we must NOT raise here.
    """
    state.update(step="gltf-pipeline", percent=85)
    node_exe = shutil.which("node") or shutil.which("node.exe")
    npm_exe = shutil.which("npm") or shutil.which("npm.cmd")

    if node_exe is None or npm_exe is None:
        log.warning(
            "Node / npm not found on PATH — skipping gltf-pipeline install. "
            "FBX→GLB avatar conversion will be unavailable until Node is installed "
            "(https://nodejs.org). All other codetalker features work without it."
        )
        state.update(step="gltf-pipeline-skipped", percent=90)
        return

    target_dir = DEPS_DIR / "gltf-pipeline"
    target_dir.mkdir(parents=True, exist_ok=True)

    proc = await asyncio.create_subprocess_exec(
        npm_exe,
        "install",
        "--prefix", str(target_dir),
        "@gltf-transform/cli",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()
    if proc.returncode != 0:
        # Non-fatal — log and continue, same as Node-absent case.
        log.warning(
            "npm install @gltf-transform/cli failed (exit %d): %s. "
            "FBX→GLB conversion will be unavailable.",
            proc.returncode,
            stderr.decode(errors="ignore")[:200],
        )
        state.update(step="gltf-pipeline-failed", percent=90)
        return

    state.update(step="gltf-pipeline-done", percent=95)


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


async def install_deps_async(state: InstallTaskState) -> None:
    """Install all missing required deps, updating *state* throughout.

    Required deps for v0.4.0: ffmpeg, whisper.cpp model, WhisperX, gltf-pipeline.
    yt-dlp is optional (v0.4.1) and is NOT installed here.

    On any fatal install failure the error is recorded in state.error and the
    function returns (doesn't re-raise). state.done is ALWAYS set True on exit.
    """
    try:
        DEPS_DIR.mkdir(parents=True, exist_ok=True)
        deps = check_deps()
        if deps.get("all_present"):
            state.update(step="all-present", percent=100)
            state.done = True
            return

        if not deps.get("ffmpeg"):
            await _install_ffmpeg(state)

        if not deps.get("whisper"):
            await _install_whisper(state)

        # WhisperX and gltf-pipeline are always installed (not tracked by check_deps yet)
        await _install_whisperx(state)
        await _install_gltf_pipeline(state)

        state.update(step="done", percent=100)
    except Exception as exc:
        state.error = str(exc)
        log.warning("voice deps install failed: %s", exc)
    finally:
        state.done = True


# ---------------------------------------------------------------------------
# Optional yt-dlp installer (v0.4.1 — not called automatically)
# ---------------------------------------------------------------------------


async def install_optional_deps_async(state: InstallTaskState) -> None:
    """Install optional deps (yt-dlp). Called explicitly by v0.4.1 UI."""
    try:
        DEPS_DIR.mkdir(parents=True, exist_ok=True)
        state.update(step="yt-dlp", percent=10)
        target = DEPS_DIR / "yt-dlp"
        target.mkdir(parents=True, exist_ok=True)
        proc = await asyncio.create_subprocess_exec(
            sys.executable,
            "-m", "pip", "install",
            "--target", str(target),
            "--upgrade",
            "yt-dlp",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(
                f"yt-dlp pip install failed: {stderr.decode(errors='ignore')[:300]}"
            )
        state.update(step="done", percent=100)
    except Exception as exc:
        state.error = str(exc)
        log.warning("optional deps install failed: %s", exc)
    finally:
        state.done = True
