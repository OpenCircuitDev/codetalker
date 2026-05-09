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


class CharacterStore:
    """Stub — full implementation in Task 2."""
    pass
