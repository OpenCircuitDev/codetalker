"""SessionCatalog: filesystem scan of ~/.claude/projects/**/*.jsonl."""
from __future__ import annotations

import threading
from dataclasses import dataclass
from pathlib import Path


DEFAULT_PROJECTS_DIR = Path.home() / ".claude" / "projects"


@dataclass
class CatalogEntry:
    session_id: str
    project_slug: str
    transcript_path: Path
    last_modified: float
    line_count: int = 0


class SessionCatalog:
    """In-memory catalog of all Claude Code transcripts on disk."""

    def __init__(self, projects_dir: Path | None = None, max_entries: int = 500):
        self._projects_dir = projects_dir if projects_dir is not None else DEFAULT_PROJECTS_DIR
        self._max_entries = max_entries
        self._entries: dict[str, CatalogEntry] = {}
        self._lock = threading.RLock()

    def entries(self) -> list[CatalogEntry]:
        with self._lock:
            return list(self._entries.values())

    def entry_for(self, session_id: str) -> CatalogEntry | None:
        with self._lock:
            return self._entries.get(session_id)
