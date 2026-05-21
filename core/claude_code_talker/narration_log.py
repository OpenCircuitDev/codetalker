"""Phase 11: spoken-narration audit log.

Append-only JSONL at ~/.claude/scripts/codetalker/narration-log.jsonl. Records
every line codetalker has spoken aloud (text + session_id + timestamp + voice
+ engine). Lets the user later ask "what did codetalker say earlier?" and
gives downstream tooling a structured stream to analyze.

Includes a built-in size cap with rotation (Phase 12 log-rotation feature).
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path


DEFAULT_LOG_PATH = Path.home() / ".claude" / "scripts" / "codetalker" / "narration-log.jsonl"
DEFAULT_MAX_BYTES = 10 * 1024 * 1024  # 10 MB
DEFAULT_MAX_BACKUPS = 5


HEDGE_PREFIX = "[UNSURE]"


def parse_hedge_prefix(text: str) -> tuple[str, str]:
    """Strip an [UNSURE] hedge prefix and report confidence.

    Returns (cleaned_text, confidence). confidence is "low" when the
    prefix was present (it's been stripped from cleaned_text);
    "normal" otherwise. Whitespace around the prefix is normalized.
    """
    stripped = text.lstrip()
    if stripped.startswith(HEDGE_PREFIX):
        return stripped[len(HEDGE_PREFIX):].lstrip(), "low"
    return text, "normal"


@dataclass
class NarrationEntry:
    timestamp: float
    session_id: str
    text: str
    voice: str = ""
    engine: str = ""
    mode: str = ""
    priority: str = ""
    cached: bool = False
    extra: dict = field(default_factory=dict)


class NarrationLog:
    """Append-only JSONL with size-based rotation.

    Thread-safe (file-level lock). Best-effort: any I/O failure is logged but
    never propagated, so an unwritable log can't break narration.
    """

    def __init__(
        self,
        log_path: Path | None = None,
        *,
        max_bytes: int = DEFAULT_MAX_BYTES,
        max_backups: int = DEFAULT_MAX_BACKUPS,
    ):
        self._path = log_path if log_path is not None else DEFAULT_LOG_PATH
        self._max_bytes = max_bytes
        self._max_backups = max_backups
        self._lock = threading.RLock()

    @property
    def path(self) -> Path:
        """Path of the JSONL log this NarrationLog appends to."""
        return self._path

    def append(self, entry: NarrationEntry | dict) -> None:
        """Append one entry to the log. Rotates if log exceeds max_bytes."""
        if isinstance(entry, NarrationEntry):
            payload = asdict(entry)
        elif isinstance(entry, dict):
            payload = dict(entry)
            payload.setdefault("timestamp", time.time())
        else:
            return
        line = json.dumps(payload, ensure_ascii=False, default=str) + "\n"
        try:
            with self._lock:
                self._path.parent.mkdir(parents=True, exist_ok=True)
                with self._path.open("a", encoding="utf-8") as f:
                    f.write(line)
                if self._max_bytes and self._path.stat().st_size > self._max_bytes:
                    self._rotate_locked()
        except OSError as e:
            logging.warning("narration log write failed: %s", e)

    def tail(self, n: int = 50) -> list[dict]:
        """Return the last ``n`` parseable entries."""
        if not self._path.exists():
            return []
        try:
            with self._lock:
                with self._path.open("r", encoding="utf-8") as f:
                    lines = f.readlines()
        except OSError:
            return []
        out: list[dict] = []
        for raw in lines[-n * 2:]:  # over-read to tolerate parse errors
            raw = raw.strip()
            if not raw:
                continue
            try:
                d = json.loads(raw)
            except (json.JSONDecodeError, ValueError):
                continue
            if isinstance(d, dict):
                out.append(d)
        return out[-n:]

    def find_for_session(self, session_id: str, limit: int = 50) -> list[dict]:
        """Return up to ``limit`` recent entries for a specific session."""
        all_entries = self.tail(limit * 4)
        matched = [e for e in all_entries if e.get("session_id") == session_id]
        return matched[-limit:]

    def stats(self) -> dict:
        """Return log size + entry count: {entries, bytes, exists, max_bytes, path}."""
        with self._lock:
            if not self._path.exists():
                return {"entries": 0, "bytes": 0, "exists": False}
            try:
                size = self._path.stat().st_size
            except OSError:
                size = 0
            try:
                with self._path.open("r", encoding="utf-8") as f:
                    entries = sum(1 for _ in f)
            except OSError:
                entries = 0
            return {"entries": entries, "bytes": size, "exists": True,
                    "max_bytes": self._max_bytes, "path": str(self._path)}

    def _rotate_locked(self) -> None:
        """Caller holds self._lock. Rotate <log>.N for N=max_backups..1, then
        rename current log to <log>.1.
        """
        if self._max_backups <= 0:
            try:
                self._path.unlink()
            except FileNotFoundError:
                pass
            return
        # Drop the oldest backup if it would exceed max_backups.
        oldest = self._path.with_suffix(self._path.suffix + f".{self._max_backups}")
        if oldest.exists():
            try:
                oldest.unlink()
            except OSError:
                pass
        # Shift the rest up: <log>.N → <log>.(N+1)
        for n in range(self._max_backups - 1, 0, -1):
            src = self._path.with_suffix(self._path.suffix + f".{n}")
            dst = self._path.with_suffix(self._path.suffix + f".{n + 1}")
            if src.exists():
                try:
                    src.replace(dst)
                except OSError:
                    pass
        # Move current to .1
        rotated = self._path.with_suffix(self._path.suffix + ".1")
        try:
            self._path.replace(rotated)
        except OSError:
            pass
