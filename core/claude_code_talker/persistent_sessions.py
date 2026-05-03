"""PersistentSessionStore: file-backed CRUD on ~/.claude/scripts/codetalker/sessions/*.yaml."""
from __future__ import annotations

import logging
import re
from pathlib import Path

import yaml


DEFAULT_SESSIONS_DIR = Path.home() / ".claude" / "scripts" / "codetalker" / "sessions"

_SESSION_ID_RE = re.compile(r"^[a-zA-Z0-9_-]{1,128}$")


class SessionIdError(ValueError):
    """Raised when a session_id fails validation."""


def is_valid_session_id(session_id: str) -> bool:
    return bool(_SESSION_ID_RE.match(session_id or ""))


def _require_valid_session_id(session_id: str) -> None:
    if not is_valid_session_id(session_id):
        raise SessionIdError(f"invalid session_id: {session_id!r}")


class PersistentSessionStore:
    """Atomic file-backed per-session settings storage."""

    def __init__(self, sessions_dir: Path | None = None):
        self._dir = sessions_dir if sessions_dir is not None else DEFAULT_SESSIONS_DIR

    def list(self) -> list[str]:
        if not self._dir.exists():
            return []
        return sorted(p.stem for p in self._dir.glob("*.yaml"))

    def exists(self, session_id: str) -> bool:
        _require_valid_session_id(session_id)
        return (self._dir / f"{session_id}.yaml").exists()

    def get(self, session_id: str) -> dict | None:
        _require_valid_session_id(session_id)
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
        _require_valid_session_id(session_id)
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
        _require_valid_session_id(session_id)
        path = self._dir / f"{session_id}.yaml"
        try:
            path.unlink()
        except FileNotFoundError:
            pass
