"""CLI entry point invoked by Claude Code hooks.

Claude Code's settings.json points hook commands at this script. The script
reads JSON payload from stdin, identifies the event, and dispatches.
"""
from __future__ import annotations

import asyncio
import json
import sys

from claude_code_talker.audio import play_wav_bytes
from claude_code_talker.config import load_full_config
from claude_code_talker.engines.piper import PiperEngine
from claude_code_talker.hooks import handle_notification, handle_stop
from claude_code_talker.modes.brief import BriefMode
from claude_code_talker.modes.direct import DirectMode
from claude_code_talker.providers.ollama import OllamaProvider
from claude_code_talker.server import PIPER_DIR, VOICES_DIR


async def dispatch_hook(payload: dict) -> None:
    event = payload.get("hook_event_name", "")
    cwd = payload.get("cwd")
    cfg = load_full_config(cwd=cwd)

    if not cfg.get("enabled", True):
        return

    text = ""
    if event == "Stop":
        mode_a = DirectMode()
        mode_b = BriefMode(provider=OllamaProvider())
        active_mode = (cfg.get("active_mode") or "direct")
        text = await handle_stop(payload, cfg, mode_a, mode_b, active_mode)
    elif event == "Notification":
        text = handle_notification(payload, cfg)
    else:
        return

    if not text:
        return

    voice_cfg = cfg.get("voice") or {}
    voice_model = voice_cfg.get("model")
    rate = float(voice_cfg.get("rate", 1.0))
    engine = PiperEngine(piper_exe=PIPER_DIR / "piper.exe", voices_dir=VOICES_DIR)
    if not voice_model:
        voices = engine.list_voices()
        if not voices:
            return
        voice_model = voices[0]
    try:
        wav = engine.synthesize(text, voice_model, rate)
        play_wav_bytes(wav)
    except (RuntimeError, ValueError):
        return


def main():
    """Entry point: read JSON from stdin, dispatch."""
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return
    asyncio.run(dispatch_hook(payload))


if __name__ == "__main__":
    main()
