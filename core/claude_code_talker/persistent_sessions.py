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
    """Return True if `session_id` is a 1-128 char alnum/`_`/`-` string acceptable as a session key."""
    return bool(_SESSION_ID_RE.match(session_id or ""))


def _require_valid_session_id(session_id: str) -> None:
    if not is_valid_session_id(session_id):
        raise SessionIdError(f"invalid session_id: {session_id!r}")


# v0.1.0 unification — keys that have been PROMOTED from the catch-all
# `live_overlay` bucket to top-level recognized fields during this work.
# When loading an overlay written by an older daemon, lift any of these
# found in `live_overlay` to top-level so consumers see the canonical
# shape. Top-level wins when both exist (newer write).
#
# Important: this list is ONLY for keys that crossed the live_overlay
# boundary in v0.1.0. Long-standing top-level keys (`enabled`,
# `attached_profile`, `attached_character`) are NOT promoted because
# they were never nested — no migration needed. The api.py
# `_merge_into_persistent` handler recognizes a superset of keys at
# top-level; only this subset needs the lift-on-read behavior.
#
# When promoting a NEW key (e.g. v0.2.0 adds `archived: bool`):
#   1. Add it to the api.py `_merge_into_persistent` if/elif chain.
#   2. Add it to `_PROMOTED_KEYS` below so old overlays get migrated.
#   3. Add it to the SessionOverlayPatch type in webui types.ts.
_PROMOTED_KEYS = (
    "pinned",
    "workspace_group",
    "workspace_group_source",
    "audio_outputs",
    "auto_mode_enabled",
    "auto_mode_idle_threshold_secs",
    "display_name",
)


def _migrate_promoted_keys(data: dict) -> dict:
    """Lift `live_overlay.<promoted_key>` to top-level on read (mutates +
    returns `data`). No-op if `live_overlay` is missing or no promoted
    keys are nested. Top-level always wins over nested when both exist."""
    lo = data.get("live_overlay")
    if not isinstance(lo, dict):
        return data
    for key in _PROMOTED_KEYS:
        if key in lo:
            if key not in data:
                data[key] = lo[key]
            # Always strip the nested copy — even if top-level exists, the
            # nested one is dead state and would confuse future reads.
            del lo[key]
    return data


class PersistentSessionStore:
    """Atomic file-backed per-session settings storage."""

    def __init__(self, sessions_dir: Path | None = None):
        self._dir = sessions_dir if sessions_dir is not None else DEFAULT_SESSIONS_DIR

    def list(self) -> list[str]:
        """Return sorted session ids (file stems of `*.yaml` in the sessions dir)."""
        if not self._dir.exists():
            return []
        return sorted(p.stem for p in self._dir.glob("*.yaml"))

    def exists(self, session_id: str) -> bool:
        """Return True if a session record exists. Raises SessionIdError on invalid ids."""
        _require_valid_session_id(session_id)
        return (self._dir / f"{session_id}.yaml").exists()

    def get(self, session_id: str) -> dict | None:
        """Load and parse the session record. Returns None on missing/corrupt files (corruption is logged).

        v0.1.0 unification — self-healing migration. Earlier daemon code
        wrote some now-promoted top-level fields (e.g. `pinned`,
        `workspace_group`, `audio_outputs`, `auto_mode_enabled`) into the
        catch-all `live_overlay` bucket because the merge handler didn't
        recognize them yet. This migration lifts those keys to top-level
        on read so callers see the canonical shape regardless of when the
        overlay was written. The lift is non-destructive on disk — `save`
        will eventually persist the lifted form when the user next edits
        the overlay.
        """
        _require_valid_session_id(session_id)
        path = self._dir / f"{session_id}.yaml"
        if not path.exists():
            return None
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or None
        except Exception as e:
            logging.warning("corrupted persistent session %s: %s", session_id, e)
            return None
        return _migrate_promoted_keys(data) if isinstance(data, dict) else data

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
        """Remove the session record. Idempotent: silent on missing file. Raises SessionIdError on invalid ids."""
        _require_valid_session_id(session_id)
        path = self._dir / f"{session_id}.yaml"
        try:
            path.unlink()
        except FileNotFoundError:
            pass
