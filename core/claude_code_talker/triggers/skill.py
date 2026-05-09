"""SKILL.md writer for codetalker-narration. Atomic write via tmp + rename."""
from __future__ import annotations

import os
from pathlib import Path


_SKILLS_ROOT = Path.home() / ".claude" / "skills"
_PLUGIN_MARKER = Path.home() / ".claude" / "plugins" / "codetalker" / "plugin.json"
SKILL_DIR_NAME = "codetalker-narration"


def skill_path() -> Path:
    return _SKILLS_ROOT / SKILL_DIR_NAME / "SKILL.md"


def is_skill_installed() -> bool:
    return skill_path().exists()


def is_plugin_installed() -> bool:
    """True if the Claude Code plugin (which ships its own daemon-aware SKILL.md) is present."""
    return _PLUGIN_MARKER.exists()


def install_skill(content: str) -> Path:
    """Write the legacy SKILL.md to ~/.claude/skills/.

    Suppressed when the Claude Code plugin is installed — the plugin ships its
    own daemon-aware SKILL.md that pulls live state from /api/triggers/skill-body,
    and a parallel write at ~/.claude/skills/ would drift from the live config.
    """
    p = skill_path()
    if is_plugin_installed():
        return p
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    os.replace(tmp, p)
    return p
