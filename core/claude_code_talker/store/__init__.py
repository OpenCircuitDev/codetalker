"""
Codetalker storage layer.

This package owns persistent state for the daemon. Today it
contains:

  - SessionStore: SQLite-backed, single source of truth for all
    Session records. Replaces in-memory state.sessions dict,
    persistent_sessions YAML files, and the companion_active_sessions
    set. One read API, one write API, one observable stream.

Outside this package no code should know about SQLite, JSON
serialization for storage, schema migrations, or any storage
implementation detail. The store presents Pydantic models in and
out; the storage is opaque.

See docs/refactor-plan-2026-05-16.md for the full architecture.
"""
from __future__ import annotations

from .legacy_adapter import (
    LegacyPersistentSessionAdapter,
    legacy_dict_to_session,
    session_to_legacy_dict,
)
from .session_store import SessionStore, SessionStoreError

__all__ = [
    "SessionStore",
    "SessionStoreError",
    "LegacyPersistentSessionAdapter",
    "session_to_legacy_dict",
    "legacy_dict_to_session",
]
