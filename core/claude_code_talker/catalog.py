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
        self._watcher_thread: threading.Thread | None = None
        self._watcher_stop = threading.Event()

    def entries(self) -> list[CatalogEntry]:
        with self._lock:
            return list(self._entries.values())

    def entry_for(self, session_id: str) -> CatalogEntry | None:
        with self._lock:
            return self._entries.get(session_id)

    def entries_for_project(self, project_slug: str) -> list[CatalogEntry]:
        with self._lock:
            return [e for e in self._entries.values() if e.project_slug == project_slug]

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
        # Apply max_entries cap by keeping the most-recent-mtime entries.
        if len(new_entries) > self._max_entries:
            sorted_entries = sorted(
                new_entries.values(), key=lambda e: e.last_modified, reverse=True
            )
            new_entries = {e.session_id: e for e in sorted_entries[: self._max_entries]}
        with self._lock:
            self._entries = new_entries
        return len(new_entries)

    def refresh(self) -> int:
        """Alias for scan(). Used by watcher loop and the API refresh endpoint."""
        return self.scan()

    def start_watcher(self, *, interval_seconds: float = 30.0) -> None:
        """Start a background thread that re-scans on a timer."""
        if self._watcher_thread is not None and self._watcher_thread.is_alive():
            return
        self._watcher_stop.clear()

        def _run():
            while not self._watcher_stop.wait(interval_seconds):
                try:
                    self.refresh()
                except Exception:
                    import logging
                    logging.warning("catalog watcher iteration failed", exc_info=True)

        self._watcher_thread = threading.Thread(
            target=_run, daemon=True, name="codetalker-catalog-watcher"
        )
        self._watcher_thread.start()

    def stop_watcher(self) -> None:
        self._watcher_stop.set()
        t = self._watcher_thread
        if t is not None:
            t.join(timeout=2.0)

    def _slug_from_folder(self, folder_name: str) -> str:
        """Derive a project display slug from the encoded folder name.

        Claude Code encodes the cwd path by replacing /, \\, :, and _ with -.
        We surface the trailing component (last hyphen-segment) as a short slug,
        e.g. 'C--Users-brand-Dropbox-OCR-Open-Circuit-BF-Workspace' -> 'Workspace'.
        """
        parts = folder_name.rsplit("-", 1)
        return parts[-1] if parts else folder_name
