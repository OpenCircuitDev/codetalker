"""PersistentSessionStore: file-backed CRUD on ~/.claude/scripts/codetalker/sessions/*.yaml."""
from __future__ import annotations

import logging
from pathlib import Path

import yaml


DEFAULT_SESSIONS_DIR = Path.home() / ".claude" / "scripts" / "codetalker" / "sessions"


class PersistentSessionStore:
    """Atomic file-backed per-session settings storage."""

    def __init__(self, sessions_dir: Path | None = None):
        self._dir = sessions_dir if sessions_dir is not None else DEFAULT_SESSIONS_DIR

    def list(self) -> list[str]:
        if not self._dir.exists():
            return []
        return sorted(p.stem for p in self._dir.glob("*.yaml"))

    def exists(self, session_id: str) -> bool:
        return (self._dir / f"{session_id}.yaml").exists()

    def get(self, session_id: str) -> dict | None:
        path = self._dir / f"{session_id}.yaml"
        if not path.exists():
            return None
        try:
            return yaml.safe_load(path.read_text(encoding="utf-8")) or None
        except Exception as e:
            logging.warning("corrupted persistent session %s: %s", session_id, e)
            return None

    def save(self, session_id: str, payload: dict) -> Path:
        """Atomic write: serialize to .tmp, then rename to .yaml."""
        self._dir.mkdir(parents=True, exist_ok=True)
        target = self._dir / f"{session_id}.yaml"
        tmp = self._dir / f"{session_id}.yaml.tmp"
        try:
            tmp.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
            tmp.replace(target)
        except OSError:
            try:
                tmp.unlink()
            except FileNotFoundError:
                pass
            raise
        return target

    def delete(self, session_id: str) -> None:
        path = self._dir / f"{session_id}.yaml"
        try:
            path.unlink()
        except FileNotFoundError:
            pass
