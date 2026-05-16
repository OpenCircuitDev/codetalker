"""
Legacy-shape adapter for SessionStore.

The existing codebase reads persistent session data as nested dicts
in the YAML shape:

    {
      "live_overlay": {"active_mode": "brief", "voice": {...}, "markup": {...}},
      "enabled": True,
      "display_name": "OCR-Web",
      "workspace_group": "OCRacing",
      "audio_outputs": ["phone"],
      ...
    }

This adapter presents that exact shape over a SessionStore. Two
functions:

  session_to_legacy_dict(session)  -> legacy nested dict
  legacy_dict_to_session(sid, payload) -> Session

Plus a drop-in replacement class, LegacyPersistentSessionAdapter,
which implements the same 5 methods that core/claude_code_talker/
persistent_sessions.py::PersistentSessionStore does — list / exists
/ get / save / delete. Plugging this into ServerState in place of
the YAML-file store gives every existing caller a SessionStore-backed
implementation without code changes.

The adapter is intentionally transitional. As phases 3-6 land, callers
move to SessionStore directly (typed access). When the last caller
migrates, this module disappears.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from claude_code_talker.schemas import (
    CharacterRef,
    MarkupTreatment,
    NarrationConfig,
    Session,
    VoiceConfig,
)

from .session_store import SessionStore

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Session ↔ legacy dict translation.
#
# Symmetric with yaml_to_session in migrate_yaml.py but works on
# in-memory dicts instead of YAML files. The two functions agree on
# field placement (which fields are top-level vs. nested under
# live_overlay) so a round-trip through them is lossless.
# ---------------------------------------------------------------------------


def session_to_legacy_dict(session: Session) -> Dict[str, Any]:
    """
    Project a Session into the legacy nested-dict shape. The result
    is what the old persistent_sessions YAMLs would have stored.

    Callers reading session.persistent.get("workspace_group"),
    persistent.get("live_overlay", {}).get("active_mode"), etc.
    get the same answers they got from the YAML store.
    """
    # Nested live_overlay — speaking mode + voice + cadence + markup
    # + paths + code_blocks. These were always nested in YAML.
    live_overlay: Dict[str, Any] = {
        "active_mode": session.active_mode,
    }
    # Voice — write the engine + model + rate in the legacy shape.
    voice_dict = session.voice.model_dump(exclude_unset=False)
    # Only include the voice block when at least one field differs
    # from defaults. Otherwise callers see noise.
    if voice_dict["model"] or voice_dict["rate"] != 1.0 or voice_dict["engine"] != "piper":
        live_overlay["voice"] = voice_dict

    # Cadence lives under live_overlay.live.cadence in the legacy shape.
    if session.cadence is not None:
        live_overlay["live"] = {"cadence": session.cadence}

    # Narration fields flattened into live_overlay.
    if session.narration.markup:
        live_overlay["markup"] = {
            form: {"kind": tr.kind, "params": tr.params}
            for form, tr in session.narration.markup.items()
        }
    if session.narration.paths_handling != "filename":
        live_overlay["paths"] = {"handling": session.narration.paths_handling}
    if session.narration.code_blocks != "stub":
        live_overlay["code_blocks"] = session.narration.code_blocks

    out: Dict[str, Any] = {
        "live_overlay": live_overlay,
        "enabled": session.enabled,
        "display_name": session.display_name,
        "last_modified": session.last_modified,
    }
    # Optional top-level fields — emitted only when set.
    if session.workspace_group is not None:
        out["workspace_group"] = session.workspace_group
    if session.auto_mode_enabled:
        out["auto_mode_enabled"] = True
    if session.audio_outputs and session.audio_outputs != ["desktop"]:
        out["audio_outputs"] = list(session.audio_outputs)
    if session.attached_profile is not None:
        out["attached_profile"] = session.attached_profile
    if session.attached_character is not None:
        out["attached_character"] = session.attached_character.model_dump()
    if session.cwd is not None:
        out["cwd"] = session.cwd
    if session.pinned:
        out["pinned"] = True
    return out


def legacy_dict_to_session(session_id: str, payload: Dict[str, Any]) -> Session:
    """
    Convert a legacy-shape dict into a Session. Used by save() to
    accept old-format writes from existing callers.

    Same logic as migrate_yaml.yaml_to_session but starts from a dict
    instead of parsing a YAML file. Drops unknown keys silently (the
    caller can't act on them anyway, since save() returns None in the
    old API).
    """
    live_overlay = payload.get("live_overlay") or {}
    if not isinstance(live_overlay, dict):
        live_overlay = {}

    # Voice
    voice_in = live_overlay.get("voice") or {}
    if isinstance(voice_in, dict):
        try:
            voice = VoiceConfig(
                engine=voice_in.get("engine", "piper"),
                model=voice_in.get("model", ""),
                rate=float(voice_in.get("rate", 1.0)),
            )
        except Exception:
            voice = VoiceConfig()
    else:
        voice = VoiceConfig()

    # Narration
    markup_in = live_overlay.get("markup") or {}
    markup: Dict[str, MarkupTreatment] = {}
    if isinstance(markup_in, dict):
        for form, raw in markup_in.items():
            if not isinstance(raw, dict):
                continue
            kind = raw.get("kind")
            if not kind:
                continue
            try:
                markup[form] = MarkupTreatment(
                    kind=kind, params=dict(raw.get("params") or {})
                )
            except Exception:
                continue

    paths_handling: Any = "filename"
    paths_in = live_overlay.get("paths") or {}
    if isinstance(paths_in, dict):
        h = paths_in.get("handling")
        if h in ("omit", "filename", "full"):
            paths_handling = h

    code_blocks: Any = "stub"
    cb = live_overlay.get("code_blocks")
    if cb in ("stub", "full", "summary"):
        code_blocks = cb

    try:
        narration = NarrationConfig(
            markup=markup,
            paths_handling=paths_handling,
            code_blocks=code_blocks,
        )
    except Exception as e:
        logger.warning("narration_config_invalid: %s — falling back to default", e)
        narration = NarrationConfig()

    # Audio outputs — filter invalid values.
    audio_out_in = payload.get("audio_outputs")
    audio_outputs: List[str] = []
    if isinstance(audio_out_in, (list, tuple)):
        for v in audio_out_in:
            if v in ("desktop", "phone", "glasses"):
                audio_outputs.append(v)
    if not audio_outputs:
        audio_outputs = ["desktop"]

    # Active mode
    am = live_overlay.get("active_mode", "brief")
    if am not in ("live", "brief", "direct"):
        am = "brief"

    # Cadence
    live = live_overlay.get("live") or {}
    cadence: Any = None
    if isinstance(live, dict):
        c = live.get("cadence")
        if c in (
            "periodic", "per_tool_call", "per_cluster",
            "significant_only", "hybrid",
        ):
            cadence = c

    # Attached character — accept dict shape only.
    attached_character: Optional[CharacterRef] = None
    ac = payload.get("attached_character")
    if isinstance(ac, dict):
        try:
            attached_character = CharacterRef.model_validate(ac)
        except Exception:
            attached_character = None

    return Session(
        session_id=session_id,
        display_name=payload.get("display_name") or session_id[:12],
        cwd=payload.get("cwd"),
        workspace_group=payload.get("workspace_group"),
        active_mode=am,  # type: ignore
        cadence=cadence,
        enabled=bool(payload.get("enabled", True)),
        auto_mode_enabled=bool(payload.get("auto_mode_enabled", False)),
        audio_outputs=audio_outputs,  # type: ignore
        voice=voice,
        narration=narration,
        attached_profile=payload.get("attached_profile"),
        attached_character=attached_character,
        last_modified=float(payload.get("last_modified", 0.0) or 0.0),
        pinned=bool(payload.get("pinned", False)),
    )


# ---------------------------------------------------------------------------
# Drop-in PersistentSessionStore replacement.
#
# Implements list/exists/get/save/delete with the same signatures as
# claude_code_talker.persistent_sessions.PersistentSessionStore. When
# ServerState constructs this in place of the YAML-backed one, every
# existing caller sees the same API and the same return shapes —
# they just happen to be served by SQLite under the hood.
# ---------------------------------------------------------------------------


class LegacyPersistentSessionAdapter:
    """
    Transitional adapter. Same 5 methods as PersistentSessionStore.

    Internally backed by SessionStore. Translation between legacy
    dict shape and Session schema happens at the boundary.

    The intent is for this class to disappear once every caller has
    been migrated to use SessionStore directly. Until then, this
    keeps the daemon working through the refactor.
    """

    def __init__(self, store: SessionStore) -> None:
        self._store = store

    # Same signatures as PersistentSessionStore -----------------------

    def list(self) -> List[str]:
        """Return all session_ids currently in the store, sorted."""
        # SessionStore.list returns full Session objects; we project
        # to just the IDs for legacy compatibility.
        return sorted([s.session_id for s in self._store.list()])

    def exists(self, session_id: str) -> bool:
        return self._store.exists(session_id)

    def get(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Return the legacy-shape dict, or None if not found."""
        session = self._store.get(session_id)
        if session is None:
            return None
        return session_to_legacy_dict(session)

    def save(self, session_id: str, payload: Dict[str, Any]) -> None:
        """Accept a legacy-shape dict, upsert into the store."""
        session = legacy_dict_to_session(session_id, payload)
        self._store.upsert(session)

    def delete(self, session_id: str) -> None:
        """Remove the session. Idempotent."""
        self._store.delete(session_id)
