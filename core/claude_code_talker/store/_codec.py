"""
Session ↔ SQLite row codec.

The Session Pydantic model is the schema. SQLite is just storage.
This module is the *only* place that knows how to translate
between the two — by keeping the translation centralized we
guarantee that every read and write follows the same conventions
(JSON encoding for nested fields, bool ↔ int casts, etc.).

If a new field is added to Session, add the column to the schema
(_codec.SCHEMA_SQL) and the corresponding mapping in row_to_session /
session_to_row. Migrations are versioned via _codec.SCHEMA_VERSION.
"""
from __future__ import annotations

import json
from typing import Any, Dict

from claude_code_talker.schemas import NarrationConfig, Session, VoiceConfig


# ---------------------------------------------------------------------------
# Schema version. Bump on every breaking schema change. Migration
# code reads the stored version and applies migrations forward.
# ---------------------------------------------------------------------------

SCHEMA_VERSION = 1


# ---------------------------------------------------------------------------
# DDL.
#
# Design choices:
#   - Scalars stored as native columns for query-ability.
#     (workspace_group, lifecycle, last_modified all indexed.)
#   - Nested objects (voice, attached_character) stored as JSON
#     because they're rarely filtered on. Reading them is one
#     json.loads per row.
#   - audio_outputs is a JSON array; SQLite can JSON-query it but
#     we rarely need to.
#   - BOOL columns stored as INTEGER 0/1 (SQLite convention).
#   - All timestamps are REAL (epoch seconds), 0.0 = never.
# ---------------------------------------------------------------------------

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS schema_meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    session_id              TEXT PRIMARY KEY,
    display_name            TEXT NOT NULL DEFAULT '',
    cwd                     TEXT,
    project_dir             TEXT,
    project_slug            TEXT,
    workspace_group         TEXT,
    active_mode             TEXT NOT NULL DEFAULT 'brief',
    cadence                 TEXT,
    enabled                 INTEGER NOT NULL DEFAULT 1,
    auto_mode_enabled       INTEGER NOT NULL DEFAULT 0,
    pinned                  INTEGER NOT NULL DEFAULT 0,
    lifecycle               TEXT NOT NULL DEFAULT 'DORMANT',
    last_hook_at            REAL NOT NULL DEFAULT 0,
    last_modified           REAL NOT NULL DEFAULT 0,
    last_user_interaction_at REAL NOT NULL DEFAULT 0,
    -- complex fields as JSON
    audio_outputs_json      TEXT NOT NULL DEFAULT '["desktop"]',
    voice_json              TEXT NOT NULL DEFAULT '{"engine":"piper","model":"","rate":1.0}',
    narration_json          TEXT NOT NULL DEFAULT '{"markup":{},"paths_handling":"filename","code_blocks":"stub"}',
    attached_profile        TEXT,
    attached_character_json TEXT,
    -- bookkeeping
    created_at              REAL NOT NULL,
    updated_at              REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_sessions_lifecycle
    ON sessions(lifecycle);
CREATE INDEX IF NOT EXISTS idx_sessions_workspace_group
    ON sessions(workspace_group);
CREATE INDEX IF NOT EXISTS idx_sessions_last_modified
    ON sessions(last_modified);
CREATE INDEX IF NOT EXISTS idx_sessions_enabled
    ON sessions(enabled);
"""


# ---------------------------------------------------------------------------
# Mappers.
#
# session_to_row produces a dict suitable for `executemany` or
# parameterized INSERT/UPDATE. row_to_session consumes a sqlite3.Row
# and produces a fully-validated Session.
# ---------------------------------------------------------------------------


def session_to_row(session: Session, *, now: float) -> Dict[str, Any]:
    """
    Convert a Session into a dict of column-name → value for SQL
    binding. Nested fields are JSON-encoded; bools become 0/1.

    `now` is supplied by the caller so updated_at is consistent
    with the transaction's wall clock.
    """
    return {
        "session_id": session.session_id,
        "display_name": session.display_name,
        "cwd": session.cwd,
        "project_dir": session.project_dir,
        "project_slug": session.project_slug,
        "workspace_group": session.workspace_group,
        "active_mode": session.active_mode,
        "cadence": session.cadence,
        "enabled": 1 if session.enabled else 0,
        "auto_mode_enabled": 1 if session.auto_mode_enabled else 0,
        "pinned": 1 if session.pinned else 0,
        "lifecycle": session.lifecycle,
        "last_hook_at": session.last_hook_at,
        "last_modified": session.last_modified,
        "last_user_interaction_at": session.last_user_interaction_at,
        "audio_outputs_json": json.dumps(list(session.audio_outputs)),
        "voice_json": session.voice.model_dump_json(),
        "narration_json": session.narration.model_dump_json(),
        "attached_profile": session.attached_profile,
        "attached_character_json": (
            session.attached_character.model_dump_json()
            if session.attached_character is not None
            else None
        ),
        "created_at": now,
        "updated_at": now,
    }


def row_to_session(row: Dict[str, Any]) -> Session:
    """
    Convert a sqlite3.Row (or dict) into a validated Session.
    Re-validation via the Pydantic constructor guarantees that
    corrupt or partially-migrated data is caught at read time.
    """
    voice_data = json.loads(row["voice_json"]) if row["voice_json"] else {}
    audio_outputs = json.loads(row["audio_outputs_json"]) if row["audio_outputs_json"] else ["desktop"]
    narration_data = json.loads(row["narration_json"]) if row["narration_json"] else {}
    attached_character_raw = row["attached_character_json"]

    kwargs: Dict[str, Any] = {
        "session_id": row["session_id"],
        "display_name": row["display_name"],
        "cwd": row["cwd"],
        "project_dir": row["project_dir"],
        "project_slug": row["project_slug"],
        "workspace_group": row["workspace_group"],
        "active_mode": row["active_mode"],
        "cadence": row["cadence"],
        "enabled": bool(row["enabled"]),
        "auto_mode_enabled": bool(row["auto_mode_enabled"]),
        "pinned": bool(row["pinned"]),
        "lifecycle": row["lifecycle"],
        "last_hook_at": row["last_hook_at"],
        "last_modified": row["last_modified"],
        "last_user_interaction_at": row["last_user_interaction_at"],
        "audio_outputs": audio_outputs,
        "voice": VoiceConfig.model_validate(voice_data) if voice_data else VoiceConfig(),
        "narration": (
            NarrationConfig.model_validate(narration_data)
            if narration_data
            else NarrationConfig()
        ),
        "attached_profile": row["attached_profile"],
    }
    if attached_character_raw:
        # Defer to Session's own validation. CharacterRef is imported
        # transitively from schemas.session.
        kwargs["attached_character"] = json.loads(attached_character_raw)

    return Session.model_validate(kwargs)
