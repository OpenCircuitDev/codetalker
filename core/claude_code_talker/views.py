"""
Shared row-builder for SessionView responses.

Both `/api/sessions` (api.py) and `/api/companion/sessions`
(companion/api.py) used to construct conceptually-identical row
dicts with two divergent implementations. This module is the single
source of that projection. Every field on SessionView is computed
here exactly once.

The function signature is intentionally state-aware: callers pass
the daemon ServerState and a session_id, and the helper does its
own lookups against:

  * state.sessions (in-memory SessionRegistry — transient flags,
    cwd, last_hook_at, is_speaking, last_user_interaction_at)
  * state.persistent_sessions (LegacyPersistentSessionAdapter —
    user-visible overlay: display_name, audio_outputs, pinned,
    workspace_group, attached_profile, attached_character, enabled,
    auto_mode_enabled, live_overlay.cadence)
  * state.catalog (transcript discovery — last_modified, title,
    custom_title, slug, vscode_label, project_slug, project_dir)
  * state.characters (resolve attached_character id → CharacterRef)
  * state.audio_hub (subscriber map — drives audio_misaligned)

The optional `companion_active_sids` parameter is the per-listener
input that distinguishes the two endpoints: companion/api.py passes
the daemon's `companion_active_sessions` set so its rows carry
`is_companion_active=True` for the right SID; api.py omits it (or
passes an empty set), so its rows always read False.

Adding a field requires editing SessionView, this builder, and
(once Phase 5 lands) regenerating client types. No other code path
should construct SessionView by hand.
"""
from __future__ import annotations

import time as _time
from typing import Any, Iterable, Optional

from claude_code_talker.schemas import CharacterRef, SessionView


TRANSCRIPT_LIVE_WINDOW_SEC = 300
SESSION_VISIBILITY_WINDOW_SEC = 30 * 24 * 3600


# ---------------------------------------------------------------------------
# Display-name resolution.
# ---------------------------------------------------------------------------


def _slug_to_display_name(slug: str) -> str:
    """Inline reimport guard — keeps the views module independent of catalog
    module import order during test collection."""
    if not slug:
        return ""
    from claude_code_talker.catalog import _slug_to_display_name as _impl
    return _impl(slug)


def _resolve_display_name(
    *,
    persistent: Optional[dict],
    catalog_entry: Any,
    fallback_sid: str,
) -> str:
    """Single display-name priority chain shared by every list handler.

    Precedence (first non-empty wins):

      1. persistent override (`display_name` key)
      2. CC `/title` custom title (catalog.custom_title)
      3. VS Code panel label (catalog.vscode_label)
      4. slug-derived (slug→Title Case)
      5. catalog auto-title (first-prompt snippet)
      6. project_slug fallback
      7. first 12 chars of session_id (last-resort fallback)
    """
    persistent_name = (
        (persistent.get("display_name") if persistent else None) or None
    )
    if persistent_name:
        return persistent_name
    if catalog_entry is not None:
        custom = getattr(catalog_entry, "custom_title", None) or None
        if custom:
            return custom
        vscode = getattr(catalog_entry, "vscode_label", None) or None
        if vscode:
            return vscode
        slug = getattr(catalog_entry, "slug", "") or ""
        slug_display = _slug_to_display_name(slug)
        if slug_display:
            return slug_display
        title = getattr(catalog_entry, "title", None) or None
        if title:
            return title
        project_slug = getattr(catalog_entry, "project_slug", "") or ""
        if project_slug:
            return project_slug
    return fallback_sid[:12]


# ---------------------------------------------------------------------------
# Character resolution.
# ---------------------------------------------------------------------------


def _resolve_character(state, value: Any) -> Optional[CharacterRef]:
    """Resolve attached_character (string ID, dict, or CharacterRef) → CharacterRef.

    Returns a minimal CharacterRef stub when the ID is stale (character
    was deleted but the session still references it) so the UI shows
    *something* rather than silently dropping the attachment.
    """
    if value is None or value == "":
        return None
    if isinstance(value, CharacterRef):
        return value
    if isinstance(value, dict):
        known = set(CharacterRef.model_fields.keys())
        filtered = {k: v for k, v in value.items() if k in known}
        filtered.setdefault("voice_ref", "")
        try:
            return CharacterRef.model_validate(filtered)
        except Exception:
            return CharacterRef(
                id=str(filtered.get("id", "")) or "unknown",
                display_name=str(filtered.get("display_name", "")) or "unknown",
                voice_ref="",
            )
    characters = getattr(state, "characters", None)
    if characters is None:
        return CharacterRef(
            id=str(value), display_name=str(value), voice_ref=""
        )
    try:
        char = characters.get(str(value))
        if char is None:
            return CharacterRef(
                id=str(value), display_name=str(value), voice_ref=""
            )
        d = char.to_dict() if hasattr(char, "to_dict") else {}
        # Character dataclass carries fields like mesh_prompt_history
        # that CharacterRef intentionally excludes (extra: forbid).
        # Filter to the schema's declared fields so validation passes.
        known = set(CharacterRef.model_fields.keys())
        filtered = {k: v for k, v in d.items() if k in known}
        # voice_ref is required by the schema — fill with empty string
        # if the Character record lacks one.
        filtered.setdefault("voice_ref", "")
        try:
            return CharacterRef.model_validate(filtered)
        except Exception:
            return CharacterRef(
                id=str(filtered.get("id", value)),
                display_name=str(filtered.get("display_name", value)),
                voice_ref="",
            )
    except Exception:
        return CharacterRef(
            id=str(value), display_name=str(value), voice_ref=""
        )


# ---------------------------------------------------------------------------
# audio_misaligned — same formula on both endpoints.
# ---------------------------------------------------------------------------


def _audio_misaligned(
    *,
    state,
    sid: str,
    audio_outputs: Optional[Iterable[str]],
) -> bool:
    """True iff the session has a companion sink (phone/glasses)
    configured but no audio_hub subscriber on that key. Drives the
    'configured but not receiving' badge on both surfaces."""
    if not audio_outputs:
        return False
    try:
        outs_lower = {str(o).lower() for o in audio_outputs}
    except Exception:
        return False
    if not (outs_lower & {"phone", "glasses"}):
        return False
    hub = getattr(state, "audio_hub", None)
    if hub is None:
        return False
    subs = getattr(hub, "_subscribers", {}).get(sid, [])
    return not subs


# ---------------------------------------------------------------------------
# active_mode + cadence resolution.
# ---------------------------------------------------------------------------


def _resolve_mode_and_cadence(
    *,
    state,
    sid: str,
    live_match: Any,
    persistent: Optional[dict],
) -> tuple[Optional[str], Optional[str]]:
    """Resolve active_mode + cadence in priority order:

      1. state.sessions.config_for(sid) (merged base+profile+overlay)
         — only when the session is live OR has a persistent overlay
         (skipping the expensive merge for dormant sessions cuts
         /api/sessions latency from ~3s to ~30ms on 85+ session sets).
      2. persistent.live_overlay.active_mode / .live.cadence
      3. daemon defaults (state.active_mode, state.cfg.live.cadence).
    """
    live_overlay = (persistent.get("live_overlay") if persistent else None) or {}
    active_mode: Optional[str] = None
    cadence: Optional[str] = None

    if live_match is not None or live_overlay:
        try:
            sessions = getattr(state, "sessions", None)
            resolved = sessions.config_for(sid) if sessions is not None else {}
        except Exception:
            resolved = {}
        active_mode = resolved.get("active_mode")
        cadence = (resolved.get("live") or {}).get("cadence")

    if not active_mode:
        active_mode = live_overlay.get("active_mode") if live_overlay else None
    if not active_mode:
        active_mode = getattr(state, "active_mode", None)

    if not cadence:
        cadence = ((live_overlay.get("live") or {}) if live_overlay else {}).get("cadence")
    if not cadence:
        cadence = ((getattr(state, "cfg", {}) or {}).get("live") or {}).get("cadence")

    return active_mode, cadence


# ---------------------------------------------------------------------------
# workspace_group fallback (auto-derive from display_name).
# ---------------------------------------------------------------------------


def _derive_workspace_group(display_name: Optional[str]) -> Optional[str]:
    """Auto-derive workspace_group from display_name patterns when the
    user hasn't set one explicitly. Keeps both endpoints in lock-step
    on the same set of patterns; api.py and companion/api.py imported
    this from each other before — now they both call into here.
    """
    if not display_name:
        return None
    name = display_name.lower().strip()
    if name.startswith("ocr") or name == "ocracing":
        return "OCRacing"
    if name in {"ocm", "codetalker", "ctdev", "ctweb"}:
        return "OCDev"
    if name == "blueprintforge" or name.startswith("blueprintforge"):
        return "BlueprintForge"
    if name.startswith("bpf-") or name.startswith("bpf "):
        return "BlueprintForge"
    if name.startswith("bpfrefactor") or name.startswith("bpfweb") or name.startswith("bpf"):
        return "BlueprintForge"
    if name in {"digitalwish", "digital-wish", "wish"} or name.startswith("wish-"):
        return "Clients"
    return None


# ---------------------------------------------------------------------------
# Main builder.
# ---------------------------------------------------------------------------


def build_session_view(
    state,
    sid: str,
    *,
    live_match: Any = None,
    catalog_entry: Any = None,
    persistent: Optional[dict] = None,
    companion_active_sids: Optional[set[str]] = None,
    live_custom_title: str = "",
    live_slug: str = "",
) -> SessionView:
    """
    Project the daemon's state for `sid` into a SessionView.

    All lookups have explicit pass-in overrides so list handlers can
    fetch the catalog and persistent dicts in batch (avoiding N+1
    queries against the persistent store) and feed them in. When an
    override is None, the function falls back to looking up against
    `state`.

    Parameters
    ----------
    state : ServerState
        The daemon's runtime state.
    sid : str
        Canonical session_id.
    live_match : SessionState | None
        In-memory SessionRegistry entry. None when the session is
        dormant (no recent hook).
    catalog_entry : CatalogEntry | None
        Transcript-discovery entry. None when the session is brand-new
        or never indexed.
    persistent : dict | None
        Legacy-shape persistent overlay dict. None when no overlay
        exists for this sid.
    companion_active_sids : set[str] | None
        Per-listener set of "active" session ids. When `sid` is in
        this set, the SessionView's `is_companion_active` is True.
        webui callers pass None (always False); companion/api.py
        passes the daemon's companion_active_sessions set.
    live_custom_title, live_slug : str
        Fresh transcript-tail reads for live sessions. The list
        handlers do these in a per-session refresh loop so /title
        renames appear within the next webui poll rather than waiting
        on the 30s catalog watcher.
    """
    if persistent is None and getattr(state, "persistent_sessions", None) is not None:
        try:
            persistent = state.persistent_sessions.get(sid)
        except Exception:
            persistent = None

    if companion_active_sids is None:
        companion_active_sids = set()

    # ---------------- display_name ----------------
    # Live-mode title overrides: if the list handler did a tail-read
    # and found a fresher custom_title or slug, splice those into a
    # shallow copy of the catalog entry. Keeps the resolution chain
    # simple downstream.
    effective_entry = catalog_entry
    if catalog_entry is not None and (live_custom_title or live_slug):

        class _ShimEntry:
            __slots__ = (
                "custom_title", "vscode_label", "slug", "title",
                "project_slug", "project_dir", "last_modified",
                "session_id", "transcript_path",
            )

        shim = _ShimEntry()
        shim.custom_title = live_custom_title or getattr(catalog_entry, "custom_title", "") or ""
        shim.vscode_label = getattr(catalog_entry, "vscode_label", "") or ""
        shim.slug = live_slug or getattr(catalog_entry, "slug", "") or ""
        shim.title = getattr(catalog_entry, "title", "") or ""
        shim.project_slug = getattr(catalog_entry, "project_slug", "") or ""
        shim.project_dir = getattr(catalog_entry, "project_dir", "") or ""
        shim.last_modified = getattr(catalog_entry, "last_modified", 0.0) or 0.0
        shim.session_id = getattr(catalog_entry, "session_id", sid) or sid
        shim.transcript_path = getattr(catalog_entry, "transcript_path", None)
        effective_entry = shim

    display_name = _resolve_display_name(
        persistent=persistent,
        catalog_entry=effective_entry,
        fallback_sid=sid,
    )

    # ---------------- project_dir / project_slug / title ----------------
    project_slug = ""
    project_dir = ""
    title: Optional[str] = None
    if catalog_entry is not None:
        project_slug = getattr(catalog_entry, "project_slug", "") or ""
        title = getattr(catalog_entry, "title", None) or None
        try:
            tp = getattr(catalog_entry, "transcript_path", None)
            if tp is not None:
                project_dir = tp.parent.name
        except Exception:
            project_dir = ""

    # ---------------- liveness ----------------
    catalog_last_modified = (
        float(getattr(catalog_entry, "last_modified", 0.0)) if catalog_entry is not None else 0.0
    )
    now = _time.time()
    transcript_is_fresh = (
        catalog_last_modified > 0.0
        and (now - catalog_last_modified) < TRANSCRIPT_LIVE_WINDOW_SEC
    )
    is_live = (live_match is not None) or transcript_is_fresh

    last_hook_at = float(getattr(live_match, "last_hook_at", 0.0) or 0.0) if live_match else 0.0
    last_modified = max(catalog_last_modified, last_hook_at)
    last_user_interaction_at = (
        float(getattr(live_match, "last_user_interaction_at", 0.0) or 0.0)
        if live_match else 0.0
    )

    cwd = (
        (live_match.cwd if live_match is not None and live_match.cwd else None)
        or (getattr(catalog_entry, "cwd", None) if catalog_entry is not None else None)
        or ""
    )

    # ---------------- mode + cadence ----------------
    active_mode, cadence = _resolve_mode_and_cadence(
        state=state,
        sid=sid,
        live_match=live_match,
        persistent=persistent,
    )

    # ---------------- per-session overlay fields ----------------
    enabled = bool(persistent.get("enabled", True)) if persistent else True
    auto_mode_enabled = bool(persistent.get("auto_mode_enabled", False)) if persistent else False
    pinned = bool(persistent.get("pinned", False)) if persistent else False

    # 2026-05-16 — provenance-aware read with lazy backfill.
    #
    # The previous `persistent.get(...) OR derive(...)` collapse caused the
    # user's explicit group choice to be silently overridden by auto-derive
    # whenever display_name changed (the derive function may bucket the
    # renamed session differently). It also re-derived on every poll if the
    # persisted value was empty string, so a "lock to Ungrouped" choice
    # could never persist.
    #
    # Now: if the persistent overlay's workspace_group_source is "user",
    # honor the stored value verbatim. An empty string locked by the user
    # emits the literal "Ungrouped" so the webui's fallback chain (which
    # would otherwise drop through to project_dir / cwd) renders the
    # explicit choice.
    #
    # Lazy backfill: overlays written before workspace_group_source existed
    # may have a non-null workspace_group but no source field. Treat those
    # as user-set so existing user choices survive the upgrade with no
    # migration script. (One extra in-memory read; no disk side effect.)
    ws_value = persistent.get("workspace_group") if persistent else None
    ws_source = persistent.get("workspace_group_source") if persistent else None
    if ws_value is not None and ws_source is None:
        ws_source = "user"
    if ws_source == "user":
        workspace_group = ws_value if (ws_value and ws_value.strip()) else "Ungrouped"
    else:
        workspace_group = _derive_workspace_group(display_name)

    audio_outputs_raw = persistent.get("audio_outputs") if persistent else None
    audio_outputs = None
    if audio_outputs_raw is not None and isinstance(audio_outputs_raw, (list, tuple)):
        valid = {"desktop", "phone", "glasses"}
        audio_outputs = [str(o) for o in audio_outputs_raw if str(o) in valid]  # type: ignore[assignment]

    # ---------------- attached_profile + attached_character ----------------
    attached_profile = (
        getattr(live_match, "attached_profile", None) if live_match is not None
        else (persistent.get("attached_profile") if persistent else None)
    )
    attached_character_raw = (
        getattr(live_match, "attached_character", None) if live_match is not None
        else (persistent.get("attached_character") if persistent else None)
    )
    attached_character = _resolve_character(state, attached_character_raw)

    # ---------------- transient + computed ----------------
    is_speaking = bool(getattr(live_match, "is_speaking", False)) if live_match is not None else False
    audio_misaligned = _audio_misaligned(state=state, sid=sid, audio_outputs=audio_outputs)
    is_companion_active = sid in companion_active_sids

    return SessionView(
        session_id=sid,
        display_name=display_name,
        cwd=cwd or "",
        project_slug=project_slug,
        project_dir=project_dir,
        workspace_group=workspace_group,
        title=title,
        active_mode=active_mode,  # type: ignore[arg-type]
        cadence=cadence,  # type: ignore[arg-type]
        enabled=enabled,
        auto_mode_enabled=auto_mode_enabled,
        audio_outputs=audio_outputs,  # type: ignore[arg-type]
        attached_profile=attached_profile,
        attached_character=attached_character,
        is_live=is_live,
        is_speaking=is_speaking,
        is_companion_active=is_companion_active,
        audio_misaligned=audio_misaligned,
        has_persistent_settings=persistent is not None,
        last_modified=last_modified,
        last_hook_at=last_hook_at,
        last_user_interaction_at=last_user_interaction_at,
        pinned=pinned,
    )
