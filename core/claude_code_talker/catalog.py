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

    def scan(self) -> int:
        """Scan projects_dir for transcript files. Returns the number of entries."""
        new_entries: dict[str, CatalogEntry] = {}
        if not self._projects_dir.exists():
            with self._lock:
                self._entries = new_entries
            return 0
        for project_dir in self._projects_dir.iterdir():
            if not project_dir.is_dir():
                continue
            project_slug = self._slug_from_folder(project_dir.name)
            for transcript in project_dir.glob("*.jsonl"):
                try:
                    stat = transcript.stat()
                except OSError:
                    continue
                sid = transcript.stem
                new_entries[sid] = CatalogEntry(
                    session_id=sid,
                    project_slug=project_slug,
                    transcript_path=transcript,
                    last_modified=stat.st_mtime,
                )
        with self._lock:
            self._entries = new_entries
        return len(new_entries)

    def _slug_from_folder(self, folder_name: str) -> str:
        """Derive a project display slug from the encoded folder name.

        Claude Code encodes the cwd path by replacing /, \\, :, and _ with -.
        We surface the trailing component (last hyphen-segment) as a short slug,
        e.g. 'C--Users-brand-Dropbox-OCR-Open-Circuit-BF-Workspace' -> 'Workspace'.
        """
        parts = folder_name.rsplit("-", 1)
        return parts[-1] if parts else folder_name
