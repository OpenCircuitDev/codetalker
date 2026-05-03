"""ProfileStore: file-backed CRUD on ~/.claude/scripts/profiles/*.yaml."""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

import yaml


DEFAULT_PROFILES_DIR = Path.home() / ".claude" / "scripts" / "profiles"

_PROFILE_NAME_RE = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")


class ProfileNameError(ValueError):
    """Raised when a profile name fails validation."""


def is_valid_profile_name(name: str) -> bool:
    return bool(_PROFILE_NAME_RE.match(name or ""))


def _require_valid_name(name: str) -> None:
    if not is_valid_profile_name(name):
        raise ProfileNameError(f"invalid profile name: {name!r}")


class ProfileStore:
    """Atomic file-backed profile storage."""

    def __init__(self, profiles_dir: Path | None = None):
        self._dir = profiles_dir if profiles_dir is not None else DEFAULT_PROFILES_DIR
        self._sessions_dir = self._dir.parent / "sessions"

    def list(self) -> list[str]:
        if not self._dir.exists():
            return []
        return sorted(p.stem for p in self._dir.glob("*.yaml"))

    def exists(self, name: str) -> bool:
        _require_valid_name(name)
        return (self._dir / f"{name}.yaml").exists()

    def get(self, name: str) -> dict:
        _require_valid_name(name)
        path = self._dir / f"{name}.yaml"
        if not path.exists():
            raise FileNotFoundError(f"profile not found: {name}")
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}

    def save(self, name: str, content: dict) -> Path:
        """Atomic write: serialize to .tmp, then rename to .yaml."""
        _require_valid_name(name)
        self._dir.mkdir(parents=True, exist_ok=True)
        target = self._dir / f"{name}.yaml"
        tmp = self._dir / f"{name}.yaml.tmp"
        try:
            tmp.write_text(yaml.safe_dump(content, sort_keys=False), encoding="utf-8")
            tmp.replace(target)
        except OSError:
            try:
                tmp.unlink()
            except FileNotFoundError:
                pass
            raise
        return target

    def delete(self, name: str) -> None:
        _require_valid_name(name)
        path = self._dir / f"{name}.yaml"
        try:
            path.unlink()
        except FileNotFoundError:
            pass

    def _cwd_hash(self, cwd: str) -> str:
        return hashlib.sha256(cwd.encode("utf-8")).hexdigest()[:16]

    def last_profile_for_cwd(self, cwd: str) -> str | None:
        path = self._sessions_dir / f"{self._cwd_hash(cwd)}.last_profile"
        if not path.exists():
            return None
        try:
            name = path.read_text(encoding="utf-8").strip()
        except OSError:
            return None
        return name if is_valid_profile_name(name) else None

    def set_last_profile_for_cwd(self, cwd: str, profile_name: str) -> None:
        _require_valid_name(profile_name)
        self._sessions_dir.mkdir(parents=True, exist_ok=True)
        path = self._sessions_dir / f"{self._cwd_hash(cwd)}.last_profile"
        path.write_text(profile_name, encoding="utf-8")

    def clear_last_profile_for_cwd(self, cwd: str) -> None:
        path = self._sessions_dir / f"{self._cwd_hash(cwd)}.last_profile"
        try:
            path.unlink()
        except FileNotFoundError:
            pass
