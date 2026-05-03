"""ProfileStore: file-backed CRUD on ~/.claude/scripts/profiles/*.yaml."""
from __future__ import annotations

from pathlib import Path

import yaml


DEFAULT_PROFILES_DIR = Path.home() / ".claude" / "scripts" / "profiles"


class ProfileStore:
    """Atomic file-backed profile storage."""

    def __init__(self, profiles_dir: Path | None = None):
        self._dir = profiles_dir if profiles_dir is not None else DEFAULT_PROFILES_DIR

    def list(self) -> list[str]:
        if not self._dir.exists():
            return []
        return sorted(p.stem for p in self._dir.glob("*.yaml"))

    def exists(self, name: str) -> bool:
        return (self._dir / f"{name}.yaml").exists()

    def get(self, name: str) -> dict:
        path = self._dir / f"{name}.yaml"
        if not path.exists():
            raise FileNotFoundError(f"profile not found: {name}")
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}

    def save(self, name: str, content: dict) -> Path:
        """Atomic write: serialize to .tmp, then rename to .yaml."""
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
        path = self._dir / f"{name}.yaml"
        try:
            path.unlink()
        except FileNotFoundError:
            pass
