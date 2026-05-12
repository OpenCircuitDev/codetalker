"""First-run setup wizard.

Run after `pip install claude-code-talker` to scaffold config, verify Piper, and
print hook integration instructions.
"""
from __future__ import annotations

import os
import socket
import sys
from pathlib import Path

GLOBAL_CONFIG_PATH = Path.home() / ".claude" / "scripts" / "tts_config.yaml"
PIPER_DIR = Path.home() / ".claude" / "scripts" / "piper" / "piper"
VOICES_DIR = Path.home() / ".claude" / "scripts" / "piper" / "voices"


DEFAULT_GLOBAL_CONFIG = """\
# Claude Code Talker — global config. See docs for the full schema.
enabled: true
preset: brief
voice:
  model: en_GB-jenny_dioco-medium
  rate: 1.05
"""


HOOK_INSTRUCTIONS = """
# Add to ~/.claude/settings.json under "hooks":
{
  "hooks": {
    "Stop":          [{"hooks": [{"type": "command", "shell": "powershell", "command": "claude-code-talker-hook", "async": true}]}],
    "Notification":  [{"hooks": [{"type": "command", "shell": "powershell", "command": "claude-code-talker-hook", "async": true}]}],
    "PreToolUse":    [{"hooks": [{"type": "command", "shell": "powershell", "command": "claude-code-talker-hook", "async": true}]}],
    "PostToolUse":   [{"hooks": [{"type": "command", "shell": "powershell", "command": "claude-code-talker-hook", "async": true}]}]
  }
}
"""


def _section(title: str) -> None:
    """Print a section header."""
    print(f"\n> {title}")


def _ok(msg: str) -> None:
    """Print a success status line."""
    print(f"  [+] {msg}")


def _fail(msg: str) -> None:
    """Print a failure status line."""
    print(f"  [-] {msg}")


def ensure_directories():
    GLOBAL_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    PIPER_DIR.mkdir(parents=True, exist_ok=True)
    VOICES_DIR.mkdir(parents=True, exist_ok=True)


def scaffold_global_config():
    if GLOBAL_CONFIG_PATH.exists():
        return False
    GLOBAL_CONFIG_PATH.write_text(DEFAULT_GLOBAL_CONFIG, encoding="utf-8")
    return True


def piper_installed() -> bool:
    exe = PIPER_DIR / "piper.exe" if sys.platform == "win32" else PIPER_DIR / "piper"
    return exe.exists()


def installed_voices() -> list[str]:
    if not VOICES_DIR.exists():
        return []
    return [p.stem for p in VOICES_DIR.glob("*.onnx")]


def _check_ollama_running() -> bool:
    """Best-effort check: is something listening on localhost:11434?"""
    try:
        with socket.create_connection(("127.0.0.1", 11434), timeout=0.5):
            return True
    except OSError:
        return False


def main():
    print("== Claude Code Talker setup ==")

    _section("Setting up directories")
    try:
        ensure_directories()
        _ok("directories ready")
    except Exception as e:
        _fail(f"directory setup failed: {e}")
        return

    _section("Scaffolding global config")
    if scaffold_global_config():
        _ok(f"wrote default config to {GLOBAL_CONFIG_PATH}")
    else:
        _ok(f"config already exists at {GLOBAL_CONFIG_PATH} (left untouched)")

    _section("Verifying Piper TTS")
    if piper_installed():
        _ok(f"piper binary present at {PIPER_DIR}")
    else:
        _fail(f"piper NOT installed at {PIPER_DIR}")
        print("    download from https://github.com/rhasspy/piper/releases and extract there")

    _section("Checking installed voices")
    voices = installed_voices()
    if voices:
        voice_list = ', '.join(voices[:3]) + ('...' if len(voices) > 3 else '')
        _ok(f"{len(voices)} voice(s) installed: {voice_list}")
    else:
        _fail("no voices installed")
        print("    download voices from https://huggingface.co/rhasspy/piper-voices into")
        print(f"      {VOICES_DIR}")

    print()
    _section("Daemon")
    print("Phase 2A introduces a long-running daemon on localhost:17832.")
    print("Hooks auto-spawn the daemon on first use; you don't need to start it manually.")
    print("Manual control:")
    print("  claude-code-talker serve  - foreground daemon (Ctrl+C to stop)")
    print("  claude-code-talker stop   - graceful shutdown of running daemon")

    print()
    _section("Modes")
    print("  direct     - read each turn aloud (regex-cleaned)")
    print("  brief      - LLM-translated turn summary at end of each turn")
    print("  live       - sportscaster narration as Claude works (Phase 2B)")
    print("Switch via the workspace config (mode: live) or the tts_set_mode MCP tool.")

    print()
    _section("LLM Providers")
    ollama_running = _check_ollama_running()
    print(f"  ollama (local, free):       {'running on localhost:11434' if ollama_running else 'not detected on localhost:11434'}")

    if os.environ.get("ANTHROPIC_API_KEY"):
        print("  anthropic (Haiku, premium): ANTHROPIC_API_KEY set")
    else:
        print("  anthropic (Haiku, premium): ANTHROPIC_API_KEY not set")

    if os.environ.get("OPENROUTER_API_KEY"):
        print("  openrouter (any model):     OPENROUTER_API_KEY set")
    else:
        print("  openrouter (any model):     OPENROUTER_API_KEY not set")

    print()
    print("Recommendation:")
    print("  Mode B brief:   anthropic if available (premium quality, low frequency)")
    print("  Mode C live:    ollama (high frequency; cloud adds up fast)")

    print()
    _section("Voice cloning (optional)")
    print("Clone any voice via the voice-cloner sub-project:")
    print("  pip install claude-code-talker-voice-cloner")
    print("  claude-code-talker-voice-cloner from-youtube --url <YT URL> --start 1:23 --duration 15 --name marvin")
    print("Then in your workspace config: voice: marvin, engine: xtts")
    print("Note: XTTS is GPU-accelerated; CPU synthesis is 3-8s per phrase.")

    print()
    _section("Web UI")
    print("Open the multi-session control panel in any browser:")
    print("  http://127.0.0.1:17832/ui-react/")
    print("From there: see active Claude sessions, tune voice/mode/cadence per session,")
    print("save settings as named profiles, install hooks with one click.")
    print("(Legacy /ui/ now 302-redirects to /ui-react/ — retired 2026-05-11)")

    print()
    _section("Hook integration")
    print("(Optional — the Web UI's 'install hooks' link does this for you, idempotently.)")
    print(HOOK_INSTRUCTIONS)


if __name__ == "__main__":
    main()
