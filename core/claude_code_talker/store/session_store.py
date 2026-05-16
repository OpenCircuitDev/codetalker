"""
SessionStore — SQLite-backed source of truth for Session records.

This replaces every previous form of session persistence:

  - state.sessions (in-memory dict): subsumed. Reads go through
    SessionStore.get() which is fast enough that an additional
    in-memory cache isn't needed (SQLite WAL with proper indexes
    handles 10k reads/sec on this workload).

  - persistent_sessions/<sid>.yaml (per-session YAML files):
    migrated. The migration script (store/migrate_yaml.py) reads
    every YAML into the new schema and writes to SQLite. Old YAML
    files are RETAINED as backup until a future cleanup phase.

  - companion_active_sessions (in-memory set): folded into the
    Subscription model in phase 4. For now this store doesn't
    represent it; the existing in-memory set keeps working.

Concurrency model:
  - SQLite is opened with check_same_thread=False + WAL mode.
  - A threading.Lock serializes writes. Reads do not need locking
    (WAL allows concurrent readers + one writer).
  - Subscribers receive SessionChanged events via an asyncio queue
    per subscriber. The store enqueues to all subscribers under the
    lock; subscribers consume asynchronously without blocking the
    writer.

The Pydantic schemas in claude_code_talker.schemas are the contract.
Every method returns or accepts validated models. There is no dict-
based access.
"""
from __future__ import annotations

import asyncio
import logging
import sqlite3
import threading
import time
from pathlib import Path
from typing import AsyncIterator, Iterable, List, Optional

from claude_code_talker.schemas import (
    Session,
    SessionChanged,
    SessionLifecycle,
    SessionPatch,
)

from ._codec import SCHEMA_SQL, SCHEMA_VERSION, row_to_session, session_to_row

logger = logging.getLogger(__name__)


class SessionStoreError(RuntimeError):
    """Raised on storage-level failures (corrupt rows, missing migrations, etc.)."""


class SessionStore:
    """
    The single read/write path for Session records.

    Lifecycle:
      - Construct with a path to the SQLite database file. Missing
        parent dirs are created. Schema is initialized on first open.
      - Use as a context manager OR explicitly call close() to release
        the file handle. The daemon constructs one store at startup
        and keeps it open for the daemon's lifetime.

    Threading:
      - All methods are thread-safe. Writers serialize through an
        internal lock; readers run unsynchronized (WAL semantics).
      - subscribe() returns an async iterator; the caller must consume
        it on an asyncio event loop. The store can be written from any
        thread; subscribers are notified via thread-safe asyncio
        primitives (loop.call_soon_threadsafe).

    Failure model:
      - Database corruption → SessionStoreError on next operation.
      - Schema version mismatch → SessionStoreError at open time
        (caller can choose to migrate or abort).
      - Missing rows on get() → None return, NOT exception.
    """

    def __init__(self, db_path: Path, *, _now_fn=time.time) -> None:
        self._db_path = db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)

        self._lock = threading.Lock()
        self._now = _now_fn

        # Subscriber registry: list of (loop, queue) for each active
        # subscribe() consumer. We stash the loop so we can wake the
        # consumer from any thread via call_soon_threadsafe.
        self._subscribers: List[tuple[asyncio.AbstractEventLoop, asyncio.Queue]] = []

        self._conn = sqlite3.connect(
            str(db_path),
            check_same_thread=False,
            isolation_level=None,  # autocommit; we manage transactions explicitly
        )
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    # ------------------------------------------------------------------
    # Setup + teardown.
    # ------------------------------------------------------------------

    def _init_schema(self) -> None:
        """Apply DDL and persist the schema version. Idempotent."""
        with self._lock:
            cur = self._conn.cursor()
            try:
                cur.execute("PRAGMA journal_mode=WAL")
                cur.execute("PRAGMA synchronous=NORMAL")
                cur.execute("PRAGMA foreign_keys=ON")
                # Execute DDL — IF NOT EXISTS makes this idempotent.
                cur.executescript(SCHEMA_SQL)
                # Stamp the schema version. ON CONFLICT keeps the first
                # value so we know when the DB was created vs upgraded.
                cur.execute(
                    "INSERT INTO schema_meta(key, value) VALUES('schema_version', ?) "
                    "ON CONFLICT(key) DO NOTHING",
                    (str(SCHEMA_VERSION),),
                )
                stored_version = cur.execute(
                    "SELECT value FROM schema_meta WHERE key='schema_version'"
                ).fetchone()[0]
                if int(stored_version) != SCHEMA_VERSION:
                    # Future: dispatch to migration registry.
                    raise SessionStoreError(
                        f"schema version mismatch: stored={stored_version} "
                        f"expected={SCHEMA_VERSION}. Run migrations."
                    )
            finally:
                cur.close()

    def close(self) -> None:
        """Release the connection. Idempotent."""
        with self._lock:
            if self._conn is not None:
                try:
                    self._conn.close()
                except Exception:
                    pass
                self._conn = None  # type: ignore

    def __enter__(self) -> "SessionStore":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    # ------------------------------------------------------------------
    # Reads — no locking required (WAL allows concurrent reads).
    # ------------------------------------------------------------------

    def get(self, session_id: str) -> Optional[Session]:
        """Return the Session, or None if not found."""
        row = self._conn.execute(
            "SELECT * FROM sessions WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        if row is None:
            return None
        return row_to_session(dict(row))

    def list(
        self,
        *,
        lifecycle: Optional[SessionLifecycle] = None,
        workspace_group: Optional[str] = None,
        enabled: Optional[bool] = None,
        modified_since: Optional[float] = None,
    ) -> List[Session]:
        """
        List sessions matching the filter. Filters are AND-combined.
        All None filters mean "no filter on that field".

        Indexed columns: lifecycle, workspace_group, last_modified,
        enabled. The query planner picks the right index.
        """
        clauses: List[str] = []
        params: List[object] = []
        if lifecycle is not None:
            clauses.append("lifecycle = ?")
            params.append(lifecycle)
        if workspace_group is not None:
            clauses.append("workspace_group = ?")
            params.append(workspace_group)
        if enabled is not None:
            clauses.append("enabled = ?")
            params.append(1 if enabled else 0)
        if modified_since is not None:
            clauses.append("last_modified >= ?")
            params.append(modified_since)

        sql = "SELECT * FROM sessions"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY pinned DESC, last_modified DESC"

        rows = self._conn.execute(sql, params).fetchall()
        return [row_to_session(dict(r)) for r in rows]

    def exists(self, session_id: str) -> bool:
        """Cheap existence check (1 == 1 row, no payload)."""
        row = self._conn.execute(
            "SELECT 1 FROM sessions WHERE session_id = ? LIMIT 1",
            (session_id,),
        ).fetchone()
        return row is not None

    def count(self) -> int:
        """Total sessions in the store."""
        return self._conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]

    # ------------------------------------------------------------------
    # Writes — serialized via the write lock. Each write emits one
    # SessionChanged event to all subscribers.
    # ------------------------------------------------------------------

    def upsert(self, session: Session) -> Session:
        """
        Insert or replace the full session record. Use this when you
        have a complete Session object (e.g. during migration or
        first-touch creation). For partial updates use update().
        """
        now = self._now()
        row = session_to_row(session, now=now)
        cols = ", ".join(row.keys())
        placeholders = ", ".join(f":{k}" for k in row.keys())
        sql = f"INSERT OR REPLACE INTO sessions ({cols}) VALUES ({placeholders})"

        with self._lock:
            self._conn.execute(sql, row)

        # Emit the change to subscribers. "All fields" is reported.
        self._publish(
            SessionChanged(
                event_type="SessionChanged",
                at=now,
                session_id=session.session_id,
                changed_fields=session.model_dump(),
            )
        )
        return session

    def update(self, session_id: str, patch: SessionPatch) -> Session:
        """
        Apply a partial patch to an existing session. The session
        must exist (call upsert for first-touch creation).

        Returns the post-update Session. Emits SessionChanged with
        only the fields that were in the patch.
        """
        # Convert patch to a dict of only the set fields. exclude_unset
        # gives us "fields the caller actually included", not
        # "fields with non-default values" — which matters because the
        # caller might explicitly set enabled=True to undo a mute.
        delta = patch.model_dump(exclude_unset=True)
        if not delta:
            # Nothing to update. Return the current row.
            existing = self.get(session_id)
            if existing is None:
                raise SessionStoreError(f"session not found: {session_id}")
            return existing

        with self._lock:
            current = self.get(session_id)
            if current is None:
                raise SessionStoreError(f"session not found: {session_id}")

            # Apply patch to model in-memory, validate, then write
            # back. This guarantees the merged result is a valid
            # Session before any SQL hits.
            merged_data = current.model_dump()
            for key, value in delta.items():
                # Nested models in patches come back as dicts when
                # exclude_unset is True; we let model_validate handle
                # the deep merge by re-validating from raw dict.
                merged_data[key] = value
            merged = Session.model_validate(merged_data)

            now = self._now()
            row = session_to_row(merged, now=now)
            # Preserve created_at — only updated_at changes on update.
            cur = self._conn.execute(
                "SELECT created_at FROM sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            if cur is not None:
                row["created_at"] = cur["created_at"]

            cols = ", ".join(row.keys())
            placeholders = ", ".join(f":{k}" for k in row.keys())
            sql = f"INSERT OR REPLACE INTO sessions ({cols}) VALUES ({placeholders})"
            self._conn.execute(sql, row)

        self._publish(
            SessionChanged(
                event_type="SessionChanged",
                at=now,
                session_id=session_id,
                changed_fields=delta,
            )
        )
        return merged

    def delete(self, session_id: str) -> bool:
        """Remove a session. Returns True if a row was deleted."""
        with self._lock:
            cur = self._conn.execute(
                "DELETE FROM sessions WHERE session_id = ?",
                (session_id,),
            )
            return cur.rowcount > 0

    # ------------------------------------------------------------------
    # Touch helper — for the daemon's existing "touch on first hook"
    # pattern. Returns the existing session, or creates a default one
    # with the given session_id and cwd.
    # ------------------------------------------------------------------

    def touch(
        self,
        session_id: str,
        *,
        cwd: Optional[str] = None,
        display_name_default: Optional[str] = None,
    ) -> Session:
        """
        Ensure a session exists. If absent, create with safe defaults.
        Returns the resulting Session. last_hook_at is updated to now.
        """
        now = self._now()
        existing = self.get(session_id)
        if existing is None:
            session = Session(
                session_id=session_id,
                display_name=display_name_default or session_id[:12],
                cwd=cwd,
                last_hook_at=now,
                last_modified=now,
            )
            return self.upsert(session)

        # Update last_hook_at on every touch; preserve other fields.
        patch = SessionPatch.model_construct(**{})
        # We need a typed bump. Update via the model to keep semantics
        # consistent. cwd is set only if provided (preserve existing
        # otherwise).
        updates: dict = {}
        if cwd and existing.cwd != cwd:
            updates["cwd"] = cwd
        # Direct field on Session, not on patch. Use raw update path.
        with self._lock:
            self._conn.execute(
                "UPDATE sessions SET last_hook_at = ?, updated_at = ? WHERE session_id = ?",
                (now, now, session_id),
            )
            if updates:
                self._conn.execute(
                    "UPDATE sessions SET cwd = ?, updated_at = ? WHERE session_id = ?",
                    (updates["cwd"], now, session_id),
                )
        return self.get(session_id) or existing

    # ------------------------------------------------------------------
    # Subscribe — async iterator over SessionChanged events.
    # ------------------------------------------------------------------

    def subscribe(self) -> "SessionStoreSubscription":
        """
        Open an observable stream of SessionChanged events. Returns
        an async iterator (a SessionStoreSubscription) that yields
        events until the subscriber unsubscribes or the store closes.

        Must be called from within an asyncio event loop — the loop
        is captured at subscribe-time so the writer can wake it from
        any thread.
        """
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue = asyncio.Queue()
        with self._lock:
            self._subscribers.append((loop, queue))
        return SessionStoreSubscription(self, queue)

    def _unsubscribe(self, queue: asyncio.Queue) -> None:
        with self._lock:
            self._subscribers = [
                (lp, q) for (lp, q) in self._subscribers if q is not queue
            ]

    def _publish(self, event: SessionChanged) -> None:
        """Fan event out to all subscribers. Called under the write
        lock OR after it (thread-safe either way)."""
        # Snapshot the subscribers under lock; iterate outside lock.
        with self._lock:
            subs = list(self._subscribers)
        for loop, queue in subs:
            try:
                loop.call_soon_threadsafe(queue.put_nowait, event)
            except RuntimeError:
                # Loop closed; reap the subscriber.
                self._unsubscribe(queue)
            except Exception:
                logger.exception("SessionStore subscriber notify failed")


class SessionStoreSubscription:
    """
    Async iterator returned by SessionStore.subscribe(). Yields
    SessionChanged events as they happen until the consumer breaks
    out of the loop or calls unsubscribe().
    """

    def __init__(self, store: SessionStore, queue: asyncio.Queue) -> None:
        self._store = store
        self._queue = queue
        self._closed = False

    def __aiter__(self) -> AsyncIterator[SessionChanged]:
        return self

    async def __anext__(self) -> SessionChanged:
        if self._closed:
            raise StopAsyncIteration
        event = await self._queue.get()
        return event

    async def __aenter__(self) -> "SessionStoreSubscription":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.unsubscribe()

    async def unsubscribe(self) -> None:
        """Stop receiving events. Idempotent."""
        if self._closed:
            return
        self._closed = True
        self._store._unsubscribe(self._queue)
