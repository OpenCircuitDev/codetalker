"""SKILL.md writer for codetalker-narration. Atomic write via tmp + rename."""
from __future__ import annotations

import os
from pathlib import Path


_SKILLS_ROOT = Path.home() / ".claude" / "skills"
SKILL_DIR_NAME = "codetalker-narration"


def skill_path() -> Path:
    return _SKILLS_ROOT / SKILL_DIR_NAME / "SKILL.md"


def is_skill_installed() -> bool:
    return skill_path().exists()


def install_skill(content: str) -> Path:
    p = skill_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    os.replace(tmp, p)
    return p
