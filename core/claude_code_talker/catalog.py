"""SessionCatalog: filesystem scan of ~/.claude/projects/**/*.jsonl."""
from __future__ import annotations

import json
import os
import re
import shutil
import sqlite3
import sys
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path


DEFAULT_PROJECTS_DIR = Path.home() / ".claude" / "projects"


def _vscode_user_dirs() -> list[Path]:
    """Return likely VS Code user data root directories for this OS."""
    home = Path.home()
    if sys.platform == "win32":
        roaming = os.environ.get("APPDATA")
        roots = [Path(roaming) / "Code" / "User"] if roaming else []
    elif sys.platform == "darwin":
        roots = [home / "Library" / "Application Support" / "Code" / "User"]
    else:
        roots = [home / ".config" / "Code" / "User"]
    # Also include VS Code Insiders if present.
    extras = []
    for r in list(roots):
        ins = Path(str(r).replace("/Code/", "/Code - Insiders/"))
        if ins.exists() and ins != r:
            extras.append(ins)
    return [r for r in roots + extras if r.exists()]


def _read_vscode_session_labels() -> dict[str, str]:
    """Read user-set Claude Code session labels from VS Code workspace state DBs.

    The Claude Code VS Code extension stores its session list (with the names
    the user set in the panel) in each workspace's ``state.vscdb`` under the
    key ``agentSessions.model.cache``. The value is a JSON array; each entry's
    ``resource`` is a URL like ``claude-code:/<session_id>`` and ``label`` is
    the user-visible name.

    Returns ``{}`` on any failure (no VS Code, no DB, locked, schema change).
    Best-effort and forward-compatible — never raises.
    """
    out: dict[str, str] = {}
    for user_dir in _vscode_user_dirs():
        ws_root = user_dir / "workspaceStorage"
        if not ws_root.exists():
            continue
        for db in ws_root.glob("*/state.vscdb"):
            tmp = Path(tempfile.gettempdir()) / f"codetalker-vscdb-{os.getpid()}.db"
            try:
                shutil.copy(db, tmp)
                con = sqlite3.connect(str(tmp))
                try:
                    cur = con.cursor()
                    cur.execute(
                        "SELECT value FROM ItemTable WHERE key='agentSessions.model.cache'"
                    )
                    row = cur.fetchone()
                finally:
                    con.close()
            except (sqlite3.Error, OSError):
                continue
            finally:
                try:
                    tmp.unlink()
                except OSError:
                    pass
            if not row or not row[0]:
                continue
            raw = row[0]
            if isinstance(raw, bytes):
                try:
                    raw = raw.decode("utf-8", errors="replace")
                except Exception:
                    continue
            try:
                entries = json.loads(raw)
            except (json.JSONDecodeError, ValueError):
                continue
            if not isinstance(entries, list):
                continue
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                resource = entry.get("resource", "")
                if not isinstance(resource, str):
                    continue
                m = re.match(r"^claude-code:/+(.+)$", resource)
                if not m:
                    continue
                sid = m.group(1).strip()
                label = entry.get("label")
                if isinstance(label, str) and label.strip():
                    out[sid] = label.strip()
    return out

# Read up to this many leading lines of a transcript looking for ai-title /
# first user message. Claude Code typically emits ai-title within the first ~10
# lines; 50 is a safety margin across older transcript formats.
_TITLE_SCAN_MAX_LINES = 200
_TITLE_FIRST_USER_TRUNCATE = 80

# IDE / Claude Code system-injected wrappers that aren't user-authored prose.
# When the first user message is just one of these, keep scanning for real text.
_SYSTEM_USER_PREFIXES = (
    "<ide_opened_file>",
    "<ide_selection>",
    "<local-command-caveat>",
    "<local-command-stdout>",
    "<local-command-stderr>",
    "<command-name>",
    "<command-args>",
    "<command-stdout>",
    "<command-stderr>",
    "<system-reminder>",
    "<system>",
    "<bash-input>",
    "<bash-stdout>",
    "<bash-stderr>",
    "<task-notification>",
    "<user-prompt-submit-hook>",
    "Base directory for this skill:",  # skill-loader injects SKILL.md preface
    "Caveat: The messages below were generated",  # /resume caveat
)


def _is_system_injected(text: str) -> bool:
    stripped = text.lstrip()
    return any(stripped.startswith(p) for p in _SYSTEM_USER_PREFIXES)


def _read_transcript_title(transcript: Path) -> str:
    """Best-effort: extract a friendly title from a Claude Code transcript.

    Prefers ``{"type":"ai-title","aiTitle":"..."}`` lines (Claude Code's
    auto-generated session title). Falls back to the first user message that
    isn't an IDE/Claude Code system-injected wrapper. Returns "" if nothing
    suitable is found or the file can't be read.
    """
    first_user: str = ""
    try:
        with transcript.open(encoding="utf-8") as f:
            for i, raw in enumerate(f):
                if i >= _TITLE_SCAN_MAX_LINES:
                    break
                try:
                    d = json.loads(raw)
                except (json.JSONDecodeError, ValueError):
                    continue
                if not isinstance(d, dict):
                    continue
                if d.get("type") == "ai-title":
                    title = d.get("aiTitle")
                    if isinstance(title, str) and title.strip():
                        return title.strip()
                if not first_user and d.get("type") == "user":
                    msg = d.get("message")
                    text = ""
                    if isinstance(msg, dict):
                        content = msg.get("content")
                        if isinstance(content, str):
                            text = content
                        elif isinstance(content, list) and content:
                            head = content[0]
                            if isinstance(head, dict):
                                text = head.get("text") or ""
                    text = text.strip()
                    if text and not _is_system_injected(text):
                        first_user = text
    except OSError:
        return ""
    if first_user:
        first_user = " ".join(first_user.split())
        if len(first_user) > _TITLE_FIRST_USER_TRUNCATE:
            first_user = first_user[: _TITLE_FIRST_USER_TRUNCATE - 1] + "…"
    return first_user


def _read_transcript_tail_names(transcript: Path) -> tuple[str, str]:
    """Best-effort: read the latest `customTitle` and `slug` from a transcript.

    Claude Code records the session slug on every JSONL line, and emits
    `type: "custom-title"` events with a `customTitle` field when the user
    runs `/title <name>`. We want the LATEST values for both, so we read a
    tail chunk of the file and walk lines from end to start.

    Returns (custom_title, slug). Either or both may be "" if not found.
    custom_title is the user's explicit rename (highest precedence for
    display); slug is Claude Code's auto-derived kebab-case identifier.
    """
    try:
        size = transcript.stat().st_size
    except OSError:
        return "", ""
    if size == 0:
        return "", ""
    chunk_size = min(size, 16384)
    try:
        with transcript.open("rb") as f:
            f.seek(size - chunk_size)
            tail = f.read(chunk_size)
    except OSError:
        return "", ""
    try:
        text = tail.decode("utf-8", errors="ignore")
    except UnicodeDecodeError:
        return "", ""
    custom_title = ""
    slug = ""
    for line in reversed(text.split("\n")):
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            d = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            continue
        if not custom_title:
            ct = d.get("customTitle")
            if isinstance(ct, str) and ct.strip():
                custom_title = ct.strip()
            elif d.get("type") == "custom-title":
                ct = d.get("title") or d.get("customTitle")
                if isinstance(ct, str) and ct.strip():
                    custom_title = ct.strip()
        if not slug:
            s = d.get("slug")
            if isinstance(s, str) and s.strip():
                slug = s.strip()
        if custom_title and slug:
            break
    return custom_title, slug


def _scan_full_for_custom_title(transcript: Path) -> str:
    """Scan the entire transcript file for the LAST customTitle event.

    Used as a fallback when `_read_transcript_tail_names` returns "" but
    we suspect the customTitle exists earlier in the file (e.g. the user
    ran `/title <name>` early in the session and the event has since been
    pushed past the 16KB tail buffer by subsequent activity). Cost is
    proportional to file size — only call once per session and cache the
    result. For 6MB transcripts this is ~50-200ms.

    Returns "" if no customTitle event is found anywhere in the file.
    """
    custom_title = ""
    try:
        with transcript.open("r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                line = line.strip()
                if not line.startswith("{"):
                    continue
                try:
                    d = json.loads(line)
                except (json.JSONDecodeError, ValueError):
                    continue
                ct = d.get("customTitle")
                if isinstance(ct, str) and ct.strip():
                    custom_title = ct.strip()
                elif d.get("type") == "custom-title":
                    ct = d.get("title") or d.get("customTitle")
                    if isinstance(ct, str) and ct.strip():
                        custom_title = ct.strip()
    except OSError:
        pass
    return custom_title


def _read_transcript_latest_slug(transcript: Path) -> str:
    """Backwards-compat shim: returns just the slug from _read_transcript_tail_names."""
    _, slug = _read_transcript_tail_names(transcript)
    return slug


def _slug_to_display_name(slug: str) -> str:
    """Convert kebab-case slug to Title Case display name.

    'i-would-like-to-modular-fog' -> 'I Would Like To Modular Fog'
    'fluffy-tickling-hamming' -> 'Fluffy Tickling Hamming'
    """
    if not slug:
        return ""
    return " ".join(word.capitalize() for word in slug.split("-") if word)


@dataclass
class CatalogEntry:
    session_id: str
    project_slug: str
    transcript_path: Path
    last_modified: float
    line_count: int = 0
    title: str = ""
    vscode_label: str = ""  # user-set label from Claude Code's VS Code panel
    slug: str = ""           # latest slug Claude Code wrote (kebab-case)
    custom_title: str = ""   # latest user-set title from Claude Code /title command


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
        """Scan projects_dir for transcript files. Returns the number of entries.

        Titles are derived from each transcript on first sight and carried
        forward across re-scans (titles don't change once Claude Code assigns
        one), so re-scanning a large catalog stays fast.
        """
        new_entries: dict[str, CatalogEntry] = {}
        if not self._projects_dir.exists():
            with self._lock:
                self._entries = new_entries
            return 0
        # Snapshot existing titles + custom_titles so re-scans don't
        # re-read every transcript.
        # v0.1.0 unification — custom_title now carries forward across
        # re-scans like `title` does. Reason: long sessions (>16KB of
        # transcript activity past the customTitle event) push the event
        # past the tail-read buffer, so subsequent tail-only reads return
        # "" and we'd fall back to slug-derived display. Carry-forward
        # preserves the once-seen value forever; tail-read overrides
        # only when it actually finds a newer customTitle event.
        with self._lock:
            prior_titles = {sid: e.title for sid, e in self._entries.items() if e.title}
            prior_custom_titles = {
                sid: e.custom_title
                for sid, e in self._entries.items()
                if e.custom_title
            }
        # Best-effort: pull user-set labels from the VS Code Claude Code panel.
        vscode_labels = _read_vscode_session_labels()
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
                title = prior_titles.get(sid) or _read_transcript_title(transcript)
                # Tail-read first (cheap). If the tail returned a customTitle,
                # use it — it's the freshest. Otherwise carry forward the
                # cached value. If neither exists AND this is a session we
                # haven't scanned before, do a one-time full-file scan to
                # catch customTitle events that have been pushed past the
                # 16KB tail buffer by subsequent activity.
                tail_custom_title, slug = _read_transcript_tail_names(transcript)
                if tail_custom_title:
                    custom_title = tail_custom_title
                elif sid in prior_custom_titles:
                    custom_title = prior_custom_titles[sid]
                else:
                    # 2026-05-11 — only do the slow full-file scan when the
                    # transcript was modified recently (≤7 days). py-spy
                    # diagnosis 2026-05-11: cold-start with ~89 sessions on
                    # disk was firing _scan_full_for_custom_title for ALL
                    # of them inside the request handler, parking the
                    # asyncio loop for tens of seconds. Most older sessions
                    # never had a /title applied — tail-read covers the
                    # 16KB window and is the right cost ceiling. Recent
                    # sessions still get the full scan so a /title set
                    # early in a long session still surfaces. Sessions
                    # outside the 7-day window keep "" custom_title until
                    # a subsequent tail-read picks one up.
                    import time
                    if (time.time() - stat.st_mtime) <= 7 * 86400:
                        custom_title = _scan_full_for_custom_title(transcript)
                    else:
                        custom_title = ""
                new_entries[sid] = CatalogEntry(
                    session_id=sid,
                    project_slug=project_slug,
                    transcript_path=transcript,
                    last_modified=stat.st_mtime,
                    title=title,
                    vscode_label=vscode_labels.get(sid, ""),
                    slug=slug,
                    custom_title=custom_title,
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
        with self._lock:
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
        with self._lock:
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
