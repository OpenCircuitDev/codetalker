"""First-run setup wizard.

Run after `pip install claude-code-talker` to scaffold config, verify Piper, and
print hook integration instructions.
"""
from __future__ import annotations

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
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "shell": "powershell",
            "command": "claude-code-talker-hook",
            "async": true
          }
        ]
      }
    ],
    "Notification": [
      {
        "hooks": [
          {
            "type": "command",
            "shell": "powershell",
            "command": "claude-code-talker-hook",
            "async": true
          }
        ]
      }
    ]
  }
}
"""


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


def main():
    print("== Claude Code Talker setup ==")
    ensure_directories()
    if scaffold_global_config():
        print(f"  wrote default config to {GLOBAL_CONFIG_PATH}")
    else:
        print(f"  config already exists at {GLOBAL_CONFIG_PATH} (left untouched)")

    if piper_installed():
        print(f"  piper binary present at {PIPER_DIR}")
    else:
        print(f"  piper NOT installed at {PIPER_DIR}")
        print("  download from https://github.com/rhasspy/piper/releases and extract there")

    voices = installed_voices()
    if voices:
        print(f"  voices installed: {', '.join(voices)}")
    else:
        print("  no voices installed")
        print("  download voices from https://huggingface.co/rhasspy/piper-voices into")
        print(f"    {VOICES_DIR}")

    print()
    print("== Hook integration ==")
    print(HOOK_INSTRUCTIONS)


if __name__ == "__main__":
    main()
