"""Phase 25a — Character data model + persistence.

A Character is a named bundle of voice + persona + (later) 3D model.
Persisted as one YAML file per character at
~/.claude/scripts/codetalker/characters/<id>.yaml.
"""
from __future__ import annotations

import re
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

import yaml


VALID_PERSONAS = {"methodical", "warm", "technical", "plain", "sarcastic", "energetic"}

_ID_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


class CharacterValidationError(ValueError):
    """Raised when a Character fails validation."""


@dataclass
class Character:
    id: str
    display_name: str
    voice_ref: str
    persona: str = "methodical"
    mesh_path: str | None = None
    mesh_provider: str | None = None
    mesh_prompt: str | None = None
    mesh_prompt_history: list[str] = field(default_factory=list)
    created_at: float = 0.0
    updated_at: float = 0.0

    def validate(self) -> None:
        """Raise CharacterValidationError on invalid state."""
        if not _ID_RE.match(self.id or ""):
            raise CharacterValidationError(f"id must be kebab-case lowercase: {self.id!r}")
        if not (self.display_name or "").strip():
            raise CharacterValidationError("display_name required")
        if not (self.voice_ref or "").strip():
            raise CharacterValidationError("voice_ref required")
        if self.persona not in VALID_PERSONAS:
            raise CharacterValidationError(
                f"persona must be one of {sorted(VALID_PERSONAS)}; got {self.persona!r}"
            )

    @classmethod
    def from_dict(cls, d: dict) -> "Character":
        """Construct from a dict, tolerating missing optional fields and dropping unknown ones."""
        known = set(cls.__dataclass_fields__.keys())
        kept = {k: v for k, v in (d or {}).items() if k in known}
        return cls(**kept)

    def to_dict(self) -> dict:
        return asdict(self)


DEFAULT_CHARACTERS_DIR = Path.home() / ".claude" / "scripts" / "codetalker" / "characters"


class CharacterStore:
    """File-backed character storage. Atomic writes via tmp + rename."""

    def __init__(self, characters_dir: Path | None = None):
        self._dir = characters_dir if characters_dir is not None else DEFAULT_CHARACTERS_DIR

    def _path(self, char_id: str) -> Path:
        return self._dir / f"{char_id}.yaml"

    def list(self) -> list[Character]:
        """Return all characters sorted by display_name (case-insensitive)."""
        if not self._dir.exists():
            return []
        chars: list[Character] = []
        for p in self._dir.glob("*.yaml"):
            try:
                d = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
                if not isinstance(d, dict):
                    continue
                chars.append(Character.from_dict(d))
            except (yaml.YAMLError, OSError, TypeError):
                continue
        chars.sort(key=lambda c: (c.display_name or "").lower())
        return chars

    def get(self, char_id: str) -> Character | None:
        if not _ID_RE.match(char_id or ""):
            return None
        path = self._path(char_id)
        if not path.exists():
            return None
        try:
            d = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            if not isinstance(d, dict):
                return None
            return Character.from_dict(d)
        except (yaml.YAMLError, OSError, TypeError):
            return None

    def save(self, character: Character) -> Path:
        """Validate and atomically write the character to disk.

        Sets created_at on first save (preserves it on subsequent saves);
        updates updated_at on every save.
        """
        character.validate()
        self._dir.mkdir(parents=True, exist_ok=True)
        target = self._path(character.id)
        now = time.time()
        if not character.created_at:
            existing = self.get(character.id)
            character.created_at = (
                existing.created_at if existing and existing.created_at else now
            )
        character.updated_at = now
        tmp = self._dir / f"{character.id}.yaml.tmp"
        try:
            tmp.write_text(
                yaml.safe_dump(character.to_dict(), sort_keys=False),
                encoding="utf-8",
            )
            tmp.replace(target)
        except OSError:
            try:
                tmp.unlink()
            except FileNotFoundError:
                pass
            raise
        return target

    def delete(self, char_id: str) -> bool:
        """Remove the character file. Returns True if it existed, False if not."""
        if not _ID_RE.match(char_id or ""):
            return False
        path = self._path(char_id)
        try:
            path.unlink()
            return True
        except FileNotFoundError:
            return False
