"""voice-cloner CLI — argparse-driven."""
from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

from claude_code_voice_cloner.youtube import download_audio, YoutubeDownloadError
from claude_code_voice_cloner.segment import extract_segment, SegmentError
from claude_code_voice_cloner.registry import (
    save_reference, list_references, remove_reference,
)


def _check_ffmpeg() -> None:
    """Verify ffmpeg is on PATH; exit with a helpful message if not."""
    try:
        result = subprocess.run(
            ["ffmpeg", "-version"], capture_output=True, check=False
        )
    except FileNotFoundError:
        sys.exit("ffmpeg is required but not found on PATH. See README §Prerequisites.")
    if result.returncode != 0:
        sys.exit("ffmpeg is required but not found on PATH. See README §Prerequisites.")


def main():
    _check_ffmpeg()
    parser = argparse.ArgumentParser(prog="claude-code-talker-voice-cloner")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_yt = sub.add_parser("from-youtube", help="Clone from a YouTube URL")
    p_yt.add_argument("--url", required=True)
    p_yt.add_argument("--start", required=True, help="e.g., 1:23 or 83")
    p_yt.add_argument("--duration", type=float, default=15.0)
    p_yt.add_argument("--name", required=True)

    p_file = sub.add_parser("from-file", help="Clone from a local audio file")
    p_file.add_argument("--file", required=True)
    p_file.add_argument("--start", required=True)
    p_file.add_argument("--duration", type=float, default=15.0)
    p_file.add_argument("--name", required=True)

    sub.add_parser("list", help="List installed reference voices")

    p_rm = sub.add_parser("remove", help="Remove a reference voice")
    p_rm.add_argument("--name", required=True)

    args = parser.parse_args()

    if args.cmd == "from-youtube":
        return _cmd_from_youtube(args)
    if args.cmd == "from-file":
        return _cmd_from_file(args)
    if args.cmd == "list":
        return _cmd_list()
    if args.cmd == "remove":
        return _cmd_remove(args)
    parser.print_help()
    return 1


def _cmd_from_youtube(args) -> int:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        try:
            mp3 = download_audio(args.url, tmp_path / "audio.mp3")
        except YoutubeDownloadError as e:
            print(f"download failed: {e}", file=sys.stderr)
            return 1
        out_wav = tmp_path / "segment.wav"
        try:
            extract_segment(mp3, out_wav, start=args.start, duration=args.duration)
        except SegmentError as e:
            print(f"segment extraction failed: {e}", file=sys.stderr)
            return 1
        wav_bytes = out_wav.read_bytes()
        path = save_reference(
            args.name,
            wav_bytes,
            source_url=args.url,
            start=args.start,
            duration=args.duration,
        )
    print(f"saved reference: {path}")
    print(f"try: claude-code-talker tts_speak --voice {args.name} --engine xtts")
    return 0


def _cmd_from_file(args) -> int:
    src = Path(args.file)
    if not src.exists():
        print(f"file not found: {src}", file=sys.stderr)
        return 1
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        out_wav = tmp_path / "segment.wav"
        try:
            extract_segment(src, out_wav, start=args.start, duration=args.duration)
        except SegmentError as e:
            print(f"segment extraction failed: {e}", file=sys.stderr)
            return 1
        wav_bytes = out_wav.read_bytes()
        path = save_reference(
            args.name,
            wav_bytes,
            source_file=str(src),
            start=args.start,
            duration=args.duration,
        )
    print(f"saved reference: {path}")
    return 0


def _cmd_list() -> int:
    names = list_references()
    if not names:
        print("(no reference voices installed)")
    else:
        for n in names:
            print(n)
    return 0


def _cmd_remove(args) -> int:
    remove_reference(args.name)
    print(f"removed: {args.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
