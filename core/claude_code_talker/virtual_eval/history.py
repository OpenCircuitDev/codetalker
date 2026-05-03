"""Append-only audit log for teacher-mode tuning changes."""
from __future__ import annotations

import json
import logging
import threading
import time
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path


DEFAULT_HISTORY_PATH = Path.home() / ".claude" / "scripts" / "codetalker" / "teacher-tuning-history.jsonl"


@dataclass
class TuningEntry:
    id: str
    timestamp: float
    before: dict
    after: dict
    reasoning: str
    applied: bool  # False = pending_approval (over max-divergence gate)


class TuningHistory:
    """Append-only JSONL of teacher_mode tuning changes.

    Supports listing, lookup by id, and computing the inverse diff for revert.
    """

    def __init__(self, log_path: Path | None = None):
        self._path = log_path if log_path is not None else DEFAULT_HISTORY_PATH
        self._lock = threading.RLock()

    @property
    def path(self) -> Path:
        return self._path

    def append(self, *, before: dict, after: dict, reasoning: str, applied: bool) -> TuningEntry:
        entry = TuningEntry(
            id=uuid.uuid4().hex[:12],
            timestamp=time.time(),
            before=dict(before),
            after=dict(after),
            reasoning=reasoning,
            applied=bool(applied),
        )
        line = json.dumps(asdict(entry), ensure_ascii=False) + "\n"
        try:
            with self._lock:
                self._path.parent.mkdir(parents=True, exist_ok=True)
                with self._path.open("a", encoding="utf-8") as f:
                    f.write(line)
        except OSError as e:
            logging.warning("tuning history write failed: %s", e)
        return entry

    def list_all(self) -> list[TuningEntry]:
        if not self._path.exists():
            return []
        out: list[TuningEntry] = []
        try:
            with self._lock:
                with self._path.open("r", encoding="utf-8") as f:
                    for raw in f:
                        raw = raw.strip()
                        if not raw:
                            continue
                        try:
                            d = json.loads(raw)
                        except (json.JSONDecodeError, ValueError):
                            continue
                        if isinstance(d, dict):
                            try:
                                out.append(TuningEntry(**d))
                            except TypeError:
                                continue
        except OSError:
            return []
        return out

    def get(self, entry_id: str) -> TuningEntry | None:
        for e in self.list_all():
            if e.id == entry_id:
                return e
        return None

    def revert_diff(self, entry_id: str) -> dict:
        """Return the inverse of an entry's diff so callers can apply it.

        Shape: {"fields_to_set": {<field>: <prior_value>, ...}}
        """
        entry = self.get(entry_id)
        if entry is None:
            raise KeyError(f"tuning entry not found: {entry_id}")
        return {"fields_to_set": dict(entry.before)}
