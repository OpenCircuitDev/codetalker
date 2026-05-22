"""REST API routes mounted alongside the FastMCP SSE app."""
from __future__ import annotations

import asyncio
import json
import json as _json_lib
import re
import time as _rate_time
import uuid
from pathlib import Path
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route
from claude_code_talker.profiles import is_valid_profile_name
from claude_code_talker.persistent_sessions import is_valid_session_id
from claude_code_talker.secrets_store import KNOWN_KEYS as _SECRET_KEYS, SecretsStore as _SecretsStore
# Phase 25b — mesh providers (imported at module level so tests can monkeypatch
# claude_code_talker.api.make_provider).
from claude_code_talker.mesh.registry import PROVIDERS as _MESH_PROVIDERS, make_provider

# Voices references directory (same default as xtts engine, overridable via cfg)
_VOICES_REFS_DEFAULT = Path.home() / ".claude" / "scripts" / "voice-cloner" / "references"

# Phase 14.5 — cfg-overlay path for trigger config persistence (monkeypatchable in tests)
_TRIGGERS_OVERLAY_PATH = Path.home() / ".claude" / "scripts" / "codetalker" / "cfg-overlay.yaml"


CLAUDE_SETTINGS_PATH = Path.home() / ".claude" / "settings.json"

# SSE keepalive interval: ping every N seconds to detect broken pipes and prevent
# socket leaks from accumulating in CLOSE_WAIT / FIN_WAIT_2 states.
_SSE_KEEPALIVE_INTERVAL_SECONDS = 20.0

_PROJECT_RE = re.compile(r"^[a-zA-Z0-9_-]{1,128}$")

# Module-level rate-limit state, keyed on id(state) so tests with multiple
# state instances don't interfere with each other.
_REFRESH_LAST_AT: dict[int, float] = {}


def _rate_limit_check(state, key: str, min_interval: float) -> bool:
    """Returns True if allowed, False if rate-limited."""
    now = _rate_time.time()
    bucket_key = id(state)
    last = _REFRESH_LAST_AT.get(bucket_key, 0.0)
    if now - last < min_interval:
        return False
    _REFRESH_LAST_AT[bucket_key] = now
    return True


def _derive_workspace_group(display_name: str | None) -> str | None:
    """Best-effort default workspace_group from display_name pattern.

    Returns None when no pattern matches; caller treats that as Ungrouped.
    Explicit `persistent.workspace_group` overlay always wins over this
    derivation; this only fires when the overlay is absent.

    2026-05-12 introduced because the catalog accumulates session entries
    over time and the user's existing project structure (OCR-*, CodeTalker,
    OCM, etc.) would otherwise show as a wall of ungrouped sessions on
    the phone. Mirrored verbatim in companion/api.py — consolidate during
    P1-B api.py decomposition.
    """
    if not display_name:
        return None
    name = display_name.lower()
    if name.startswith("ocr-") or name == "ocr":
        return "OCRacing"
    if name in {"ocm", "codetalker", "ctdev", "ctweb"}:
        return "OCDev"
    # 2026-05-16 — keep companion/api.py copy in sync. BlueprintForge
    # family covers user display names "BPF-Web", "BPFRefactor", etc.,
    # and Clients bucket catches DigitalWish + future client projects.
    if name == "blueprintforge" or name.startswith("blueprintforge"):
        return "BlueprintForge"
    if name.startswith("bpf-") or name.startswith("bpf "):
        return "BlueprintForge"
    if name.startswith("bpfrefactor") or name.startswith("bpfweb") or name.startswith("bpf"):
        return "BlueprintForge"
    if name in {"digitalwish", "digital-wish", "wish"} or name.startswith("wish-"):
        return "Clients"
    return None

_HOOK_EVENT_NAMES = ["Stop", "Notification", "PreToolUse", "PostToolUse", "UserPromptSubmit"]
_HOOK_ENTRY = {
    "hooks": [
        {"type": "command", "shell": "powershell", "command": "claude-code-talker-hook", "async": True}
    ]
}


def _has_codetalker_hook(entries: list) -> bool:
    for e in entries:
        for h in e.get("hooks", []):
            if h.get("command") == "claude-code-talker-hook":
                return True
    return False


def _emit_session_changed(state, sid: str, changed_fields: dict) -> None:
    """Phase 4 — best-effort SessionChanged emit, shared between PATCH
    /api/sessions/{sid} and the legacy PUT /api/sessions/{sid}/overlay.

    Both writers route here so the SSE-driven webui stays in sync no
    matter which entry point the caller hit. Best-effort: an event-bus
    error must never break the underlying write.
    """
    bus = getattr(state, "event_bus", None)
    if bus is None or not changed_fields:
        return
    try:
        from claude_code_talker.schemas import SessionChanged
        import time as _t
        bus.publish_threadsafe(SessionChanged(
            at=_t.time(),
            session_id=sid,
            changed_fields=changed_fields,
        ))
    except Exception:
        pass


def _emit_master_changed(state, changed_fields: dict) -> None:
    """Phase 4 — best-effort MasterConfigChanged emit from a sync handler.

    The handler is async (so it could await publish) but
    publish_threadsafe is the safer call: it works whether or not
    a subscriber has registered yet, and never raises when the loop
    isn't running. Sync callers (rare; the mute/unmute MCP tools) can
    use the same entry point.
    """
    bus = getattr(state, "event_bus", None)
    if bus is None:
        return
    try:
        from claude_code_talker.schemas import MasterConfigChanged
        import time as _t
        bus.publish_threadsafe(MasterConfigChanged(
            at=_t.time(),
            changed_fields=changed_fields,
        ))
    except Exception:
        pass


def _merge_into_persistent(state, sid: str, partial: dict, live=None) -> None:
    """v0.1.0 polish — merge an overlay partial into persistent_sessions storage.

    Used by put_overlay to mirror Pro-companion + webui edits to disk so
    (a) the webui's catalog view sees the same state on its next poll,
    (b) the change survives daemon restart, and (c) dormant sessions can be
    edited at all (otherwise put_overlay would 404).

    The partial follows the same schema the in-memory overlay does. Top-level
    keys we recognize: ``enabled``, ``active_mode``, ``voice`` (dict),
    ``live`` (dict with cadence), ``markup`` (dict). Anything we don't
    recognize is preserved verbatim under ``live_overlay``.
    """
    if state.persistent_sessions is None:
        return
    existing = state.persistent_sessions.get(sid) or {}
    existing.setdefault("live_overlay", {})
    # The in-memory overlay structure is partial[key] = new value; mirror
    # that into the persisted shape.
    for key, value in partial.items():
        if key == "enabled":
            existing["enabled"] = bool(value)
        elif key == "active_mode":
            existing["live_overlay"]["active_mode"] = value
        elif key == "live" and isinstance(value, dict):
            sub = existing["live_overlay"].setdefault("live", {})
            sub.update(value)
        elif key == "voice" and isinstance(value, dict):
            existing["live_overlay"].setdefault("voice", {}).update(value)
        elif key == "markup" and isinstance(value, dict):
            existing["live_overlay"].setdefault("markup", {}).update(value)
        elif key == "attached_profile":
            existing["attached_profile"] = value
        elif key == "attached_character":
            existing["attached_character"] = value
        elif key == "workspace_group":
            # v0.1.0 polish — user-defined workspace grouping (separate from
            # cwd-derived project_dir).
            #
            # 2026-05-16 provenance fix — any write that arrives here is by
            # definition the user's explicit choice (PATCH or PUT /overlay
            # initiated by a UI action). Stamp source="user" so the read
            # path in views.py honors it verbatim instead of re-deriving
            # from display_name on the next poll.
            #
            # Semantics:
            #   - value is None  → unlock: pop both value and source so the
            #                       read path falls back to auto-derive.
            #   - value == ""    → lock to "Ungrouped": pop the stored
            #                       value but keep source="user" so the
            #                       view emits the literal Ungrouped.
            #   - value == "X"   → lock to X: store value, set source="user".
            if value is None:
                existing.pop("workspace_group", None)
                existing.pop("workspace_group_source", None)
            elif value == "":
                existing.pop("workspace_group", None)
                existing["workspace_group_source"] = "user"
            else:
                existing["workspace_group"] = str(value)
                existing["workspace_group_source"] = "user"
        elif key == "workspace_group_source":
            # 2026-05-16 — explicit provenance override. Callers can set
            # this independently of workspace_group (e.g. to "auto" to
            # re-enable auto-derive without changing the current group
            # value). Anything other than "user" / "auto" drops the field.
            if value in ("user", "auto"):
                existing["workspace_group_source"] = value
            else:
                existing.pop("workspace_group_source", None)
        elif key == "audio_outputs":
            # v0.1.0 unification — multi-select audio destinations. List of
            # strings from {"desktop", "phone", "glasses"}. Empty list or
            # null = no audio (silenced everywhere).
            if value is None:
                existing.pop("audio_outputs", None)
            elif isinstance(value, (list, tuple)):
                valid = {"desktop", "phone", "glasses"}
                cleaned = sorted(
                    {str(v).lower() for v in value if str(v).lower() in valid}
                )
                existing["audio_outputs"] = cleaned
        elif key == "auto_mode_enabled":
            # v0.1.0 unification — opt-in auto-switch between live/brief
            # active_mode based on user-interaction recency.
            existing["auto_mode_enabled"] = bool(value)
        elif key == "auto_mode_idle_threshold_secs":
            if value is None:
                existing.pop("auto_mode_idle_threshold_secs", None)
            else:
                try:
                    existing["auto_mode_idle_threshold_secs"] = float(value)
                except (TypeError, ValueError):
                    pass
        elif key == "display_name":
            # v0.1.0 polish — user-facing rename of a session, sync'd
            # between Pro app and webui.
            if value is None or value == "":
                existing.pop("display_name", None)
            else:
                existing["display_name"] = str(value)
        elif key == "pinned":
            # v0.1.0 unification — pin-to-top within the session's group.
            # Stored as bool; truthy = pinned. Webui SessionGrid sorts
            # pinned-first within each workspace_group section.
            if value:
                existing["pinned"] = True
            else:
                existing.pop("pinned", None)
        else:
            existing["live_overlay"][key] = value
    if live is not None:
        # Carry forward useful identity fields for the webui's catalog row.
        existing.setdefault("display_name", None)
        existing.setdefault("cwd", getattr(live, "cwd", "") or "")
    state.persistent_sessions.save(sid, existing)


def _read_pinned(persistent: dict | None) -> bool:
    """v0.1.0 unification — read the pinned flag defensively from a
    persistent overlay dict. Older overlays (from daemons predating the
    pinned-key-handling commit) may have `pinned: true` nested under
    `live_overlay` instead of at the top level, because the merge
    fell through to the catch-all else-branch. Treat both shapes as
    truthy so existing pins survive the daemon restart that activates
    the new code path."""
    if not persistent:
        return False
    if persistent.get("pinned"):
        return True
    lo = persistent.get("live_overlay")
    if isinstance(lo, dict) and lo.get("pinned"):
        return True
    return False


def build_routes(state) -> list[Route]:
    """Build the list of Starlette Route objects bound to this server state."""

    async def master_enabled_get(request: Request) -> JSONResponse:
        """GET /api/master-enabled -- return the global narration master switch.
        Mirrors the value the hook handlers read; webui + Pro app surface it
        as a single toggle so the user never has to edit tts_config.yaml by
        hand to silence/unsilence narration across the fleet."""
        return JSONResponse({"enabled": bool(state.cfg.get("enabled", True))})

    async def master_enabled_put(request: Request) -> JSONResponse:
        """PUT /api/master-enabled {enabled: bool}
        Toggle the master narration switch. Persists to
        ~/.claude/scripts/tts_config.yaml so daemon restarts honor it."""
        try:
            payload = await _read_json(request)
        except ValueError as e:
            return _bad_request(str(e))
        if not isinstance(payload, dict):
            return _bad_request("body must be a JSON object")
        if "enabled" not in payload:
            return _bad_request("missing 'enabled' field")
        new_enabled = bool(payload["enabled"])
        # Update in-memory cfg so the next hook fires immediately with the
        # new value (no daemon restart required).
        state.cfg["enabled"] = new_enabled
        # Persist to tts_config.yaml so daemon restart preserves it.
        from claude_code_talker.config import DEFAULT_GLOBAL_PATH
        import yaml as _yaml
        try:
            if DEFAULT_GLOBAL_PATH.exists():
                with open(DEFAULT_GLOBAL_PATH, encoding="utf-8") as f:
                    data = _yaml.safe_load(f) or {}
            else:
                data = {}
            if not isinstance(data, dict):
                data = {}
            data["enabled"] = new_enabled
            DEFAULT_GLOBAL_PATH.parent.mkdir(parents=True, exist_ok=True)
            with open(DEFAULT_GLOBAL_PATH, "w", encoding="utf-8") as f:
                _yaml.safe_dump(data, f, sort_keys=False)
        except Exception as e:
            # In-memory change is already live; disk persist is best-effort
            # but the user should know if it didn't stick.
            _emit_master_changed(state, {"enabled": new_enabled})
            return JSONResponse({"enabled": new_enabled, "warning": f"in-memory only: {e}"})
        _emit_master_changed(state, {"enabled": new_enabled})
        return JSONResponse({"enabled": new_enabled})

    async def health(request: Request) -> JSONResponse:
        # 2026-05-16 -- surface narration-pipeline gates so a silent
        # audio drought caused by tts_config.yaml's `enabled: false` is
        # one curl away. Diagnostic UIs (Pro Android, webui) read
        # `narration_enabled` to render a visible warning when the
        # master switch is off so the user never has to debug 5 days
        # of silence wondering why hook events look fine.
        narration_enabled = bool(state.cfg.get("enabled", True))
        return JSONResponse({
            "ok": True,
            "narration_enabled": narration_enabled,
            # 2026-05-16 -- only surface this when False to keep the
            # default response lean. Truthy `narration_enabled` is the
            # healthy case; the warning blob exists for the broken one.
            "narration_warning": (
                None
                if narration_enabled
                else "Master narration switch is off (~/.claude/scripts/tts_config.yaml enabled: false). No hook-driven TTS will play until set to true."
            ),
        })

    # ───────────────────────────────────────────────────────────────────
    # X-1 license verification — Stripe-backed Pro entitlement check.
    # See docs/superpowers/decisions/x-1-license-verification.md.
    # ───────────────────────────────────────────────────────────────────

    async def audio_skip(request: Request) -> JSONResponse:
        """POST /api/audio/skip — user-initiated narration interrupt.

        Stops the currently-playing audio AND drains the pending queue
        so the next narration starts genuinely fresh. Closes a real
        user-feedback request ("I've got it, stop talking" / "wait,
        that's wrong, jumping in").

        Body (optional):
            {"session_id": "..."}  → drop only that session's jobs
            {} or no body          → drop everything (global skip)

        Response:
            {"interrupted": bool, "dropped": int}
            "dropped" is the count of pending jobs removed from the
            queue. The currently-playing job (if any) is interrupted
            via the same _PlaybackHandle mechanism alerts use.
        """
        sid: str | None = None
        try:
            body = await request.json()
            if isinstance(body, dict) and body.get("session_id"):
                sid = str(body["session_id"]).strip() or None
        except Exception:
            # No body / not JSON — global skip.
            pass
        queue = getattr(state, "audio_queue", None)
        if queue is None:
            return JSONResponse(
                {"error": "audio queue not available"}, status_code=503,
            )
        try:
            result = queue.skip_current(session_id=sid)
        except Exception as e:
            return JSONResponse({"error": str(e)}, status_code=500)
        return JSONResponse(result)

    async def audio_rewind(request: Request) -> JSONResponse:
        """POST /api/audio/rewind — re-narrate the last N seconds of log.

        Body (optional):
            {"seconds": 30, "session_id": "..."}
            seconds defaults to 30; session_id filters to that session (otherwise
            all sessions in the window).

        Response:
            {"requeued": int, "skipped_dupes": int}

        Mechanism: read narration_log for entries within the window, filter to
        live-stream / brief / live / direct modes (the things the user actually
        heard), and re-submit each as a fresh AudioJob via the audio_queue.
        Drop-on-overlap will collapse stale older replays naturally.
        """
        import time as _time
        from claude_code_talker.schemas.audio_job import AudioJob

        seconds = 30.0
        session_id: str | None = None
        try:
            body = await request.json()
            if isinstance(body, dict):
                seconds = float(body.get("seconds", 30.0))
                sid = (body.get("session_id") or "").strip()
                if sid:
                    session_id = sid
        except Exception:
            pass
        if state.narration_log is None or state.audio_queue is None:
            return JSONResponse({"error": "narration log or audio queue unavailable"}, status_code=503)

        cutoff = _time.time() - max(1.0, seconds)
        # Read recent entries from the JSONL log directly.
        entries = []
        try:
            if state.narration_log.path.exists():
                for raw in state.narration_log.path.read_text(encoding="utf-8").splitlines()[-300:]:
                    try:
                        e = json.loads(raw)
                    except Exception:
                        continue
                    if e.get("timestamp", 0) < cutoff:
                        continue
                    if (e.get("mode") or "").lower() not in ("live-stream", "brief", "live", "direct"):
                        continue
                    if session_id and e.get("session_id") != session_id:
                        continue
                    entries.append(e)
        except Exception as exc:
            return JSONResponse({"error": f"narration log read failed: {exc}"}, status_code=500)

        if not entries:
            return JSONResponse({"requeued": 0, "skipped_dupes": 0, "message": "no entries in window"})

        from claude_code_talker.schemas.voice import VoiceConfig

        requeued = 0
        for e in entries:
            try:
                # Determine audio format based on engine
                engine = e.get("engine") or "piper"

                state.audio_queue.submit(AudioJob(
                    job_id=str(uuid.uuid4()),
                    text=e.get("text", ""),
                    voice=VoiceConfig(engine=engine, model=e.get("voice") or "", rate=1.0),
                    session_id=e.get("session_id") or "",
                    state="created",
                    created_at=_time.time(),
                    bytes_synthesized=None,
                ))
                requeued += 1
            except Exception:
                continue
        return JSONResponse({"requeued": requeued, "skipped_dupes": 0})

    async def license_status(request: Request) -> JSONResponse:
        """GET /api/license/status — current entitlement snapshot.

        The webui's Preferences/Account tab polls this to render the
        "Pro Active / Basic" badge + the "Activate License" button.
        """
        ls = getattr(state, "licensing", None)
        if ls is None:
            return JSONResponse({
                "configured": False,
                "pro_active": False,
                "last_validated_at": 0,
                "last_error": "license client not started",
            })
        return JSONResponse({
            "configured": bool(ls.key),
            "pro_active": bool(ls.pro_active),
            "user_id": ls.user_id,
            "machine_id": ls.machine_id,
            "last_validated_at": ls.last_validated_at,
            "last_attempt_at": ls.last_attempt_at,
            "last_error": ls.last_error,
        })

    async def license_activate(request: Request) -> JSONResponse:
        """POST /api/license/activate { license_key } — persist + validate.

        Body: {"license_key": "CT-XXXX-XXXX-XXXX-XXXX-SSSS"}

        Response mirrors the website's /api/licenses/validate response,
        plus a top-level `pro_active` reflecting state.licensing after
        the validate. Pass empty/missing key to clear the activation.
        """
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"error": "Invalid JSON"}, status_code=400)
        key = str(body.get("license_key") or "").strip()
        client = getattr(state, "license_client", None)
        if client is None:
            return JSONResponse(
                {"error": "license client not started"}, status_code=503
            )
        try:
            payload = client.activate(key)
        except Exception as e:
            return JSONResponse({"error": str(e)}, status_code=500)
        return JSONResponse({
            **payload,
            "pro_active": bool(state.licensing.pro_active),
            "configured": bool(state.licensing.key),
        })

    def _audio_misaligned(sid: str, audio_outputs) -> bool:
        """Tier-A.2 (2026-05-11) — True iff this session has a companion
        sink configured (phone/glasses) but no live audio_hub subscriber.
        UIs use this to render a 'configured but not receiving' badge so
        the dual-state alignment trap surfaces visually instead of as
        silent dead air.
        """
        if not audio_outputs:
            return False
        try:
            outs = {str(o).lower() for o in audio_outputs}
        except Exception:
            return False
        if not (outs & {"phone", "glasses"}):
            return False
        hub = getattr(state, "audio_hub", None)
        if hub is None:
            return True
        try:
            subs = getattr(hub, "_subscribers", {}).get(sid, [])
        except Exception:
            return True
        return not subs

    async def list_sessions(request: Request) -> JSONResponse:
        """GET /api/sessions — merged catalog + live + persistent.

        Phase 3 (2026-05-16): row construction delegated to the shared
        `views.build_session_view` so /api/sessions and /api/companion/
        sessions emit identical SessionView shapes. This handler only
        does the catalog scan + live-tail refresh; everything else is
        the shared builder.
        """
        import time as _time
        from claude_code_talker.views import (
            SESSION_VISIBILITY_WINDOW_SEC,
            TRANSCRIPT_LIVE_WINDOW_SEC,
            build_session_view,
        )
        from claude_code_talker.catalog import _read_transcript_tail_names

        live_by_sid = {s.session_id: s for s in state.sessions.list_active()}
        catalog_entries = (
            state.catalog.entries() if state.catalog is not None else []
        )
        now = _time.time()
        # Dedup-by-recency: drop entries that haven't been touched within
        # the visibility window. Direct session_id lookups still work via
        # /api/sessions/{sid} for accessing history.
        visible_entries = [
            e for e in catalog_entries
            if (now - e.last_modified) < SESSION_VISIBILITY_WINDOW_SEC
        ]

        views = []
        seen_sids: set[str] = set()
        for entry in visible_entries:
            sid = entry.session_id
            seen_sids.add(sid)
            live_match = live_by_sid.get(sid)
            persistent = (
                state.persistent_sessions.get(sid)
                if state.persistent_sessions else None
            )
            # Live-session refresh: re-read transcript tail so /title
            # renames appear within the webui's next poll rather than
            # waiting on the 30s catalog watcher. Best-effort.
            live_custom_title = ""
            live_slug = ""
            transcript_is_fresh = (now - entry.last_modified) < TRANSCRIPT_LIVE_WINDOW_SEC
            if live_match is not None or transcript_is_fresh:
                try:
                    live_custom_title, live_slug = _read_transcript_tail_names(
                        entry.transcript_path
                    )
                except Exception:
                    pass
            views.append(build_session_view(
                state,
                sid,
                live_match=live_match,
                catalog_entry=entry,
                persistent=persistent,
                live_custom_title=live_custom_title,
                live_slug=live_slug,
            ))

        # Live sessions not yet in the catalog (newly created since last
        # 30s watcher tick).
        for sid, live_match in live_by_sid.items():
            if sid in seen_sids:
                continue
            persistent = (
                state.persistent_sessions.get(sid)
                if state.persistent_sessions else None
            )
            views.append(build_session_view(
                state,
                sid,
                live_match=live_match,
                persistent=persistent,
            ))

        views.sort(key=lambda v: v.last_modified, reverse=True)
        return JSONResponse([v.model_dump(mode="json") for v in views])

    async def get_session(request: Request) -> JSONResponse:
        sid = request.path_params["session_id"]
        s = state.sessions.get(sid)
        if s is not None:
            cfg = state.sessions.config_for(sid)
            # 2026-05-16 root-cause fix for "mute toggle didn't persist
            # to the list view":
            #   - SessionRow.tsx reads `config?.enabled === false` to
            #     decide if a session shows the muted indicator
            #   - That config comes from useSessionConfig -> /api/sessions/{id}
            #     -> resolved_cfg
            #   - But resolve_for_session() merges base+profile+overlay
            #     into a config dict that NEVER includes `enabled`
            #     (it's a session-state attribute, not a config key)
            # Expose `enabled` in resolved_cfg so the webui's SessionRow
            # and the Pro app's mute indicator both see the canonical
            # value. The list endpoint already returns it per-session;
            # this is the missing twin on the single-session endpoint.
            cfg_with_enabled = dict(cfg) if isinstance(cfg, dict) else {}
            cfg_with_enabled["enabled"] = bool(s.enabled)
            return JSONResponse({
                "state": {
                    "session_id": s.session_id,
                    "cwd": s.cwd,
                    "transcript_path": s.transcript_path,
                    "last_hook_at": s.last_hook_at,
                    "live_overlay": s.live_overlay,
                    "attached_profile": s.attached_profile,
                    "attached_character": s.attached_character,
                    "enabled": bool(s.enabled),
                },
                "resolved_cfg": cfg_with_enabled,
            })
        # v0.1.0 unification — dormant fallback. Without this, opening the
        # detail panel for a session that's `is_live` via transcript-mtime
        # (no in-memory SessionState since restart) returned 404, leaving
        # ModePicker/VoicePicker/CadencePicker stuck on "(unknown)" with
        # no way to save. Same gating as put_overlay's dormant branch:
        # the SID must be known via persistent overlay or catalog.
        if state.persistent_sessions is None:
            return _not_found(f"unknown session: {sid}")
        try:
            persistent = state.persistent_sessions.get(sid)
        except Exception:
            persistent = None
        catalog_entry = (
            state.catalog.entry_for(sid) if state.catalog is not None else None
        )
        if persistent is None and catalog_entry is None:
            return _not_found(f"unknown session: {sid}")
        # Build a synthetic resolved_cfg by merging persistent overlay
        # onto base cfg, mirroring SessionRegistry.config_for() but
        # without requiring an in-memory SessionState.
        from claude_code_talker.config import resolve_for_session
        from claude_code_talker.sessions import SessionState as _SS
        synthetic = _SS(session_id=sid)
        if persistent is not None:
            synthetic.live_overlay = dict(persistent.get("live_overlay") or {})
            synthetic.attached_profile = persistent.get("attached_profile")
            synthetic.attached_character = persistent.get("attached_character")
            synthetic.enabled = bool(persistent.get("enabled", True))
        try:
            cfg = resolve_for_session(
                state.cfg if hasattr(state, "cfg") else {},
                synthetic,
                state.profiles,
                state.characters if hasattr(state, "characters") else None,
            )
        except Exception:
            cfg = (persistent or {}) if isinstance(persistent, dict) else {}
        # Mirror the live-branch fix: expose `enabled` in resolved_cfg so
        # the webui's SessionRow muted indicator works for dormant
        # sessions too.
        cfg_with_enabled = dict(cfg) if isinstance(cfg, dict) else {}
        cfg_with_enabled["enabled"] = bool(synthetic.enabled)
        return JSONResponse({
            "state": {
                "session_id": sid,
                "cwd": (persistent or {}).get("cwd", "") if persistent else "",
                "transcript_path": "",
                "last_hook_at": 0.0,
                "live_overlay": synthetic.live_overlay,
                "attached_profile": synthetic.attached_profile,
                "attached_character": synthetic.attached_character,
                "enabled": bool(synthetic.enabled),
                "persistent_only": True,
            },
            "resolved_cfg": cfg_with_enabled,
        })

    async def put_overlay(request: Request) -> JSONResponse:
        sid = request.path_params["session_id"]
        try:
            partial = await _read_json(request)
        except ValueError as e:
            return _bad_request(str(e))
        # v0.1.0 polish — accept overlay edits for dormant sessions too, so
        # mute/mode/character changes made on the Pro Sessions list survive
        # the session's eviction from state.sessions AND are visible to the
        # webui (which reads persistent overlays for catalog rows). For live
        # sessions, also update in-memory state.sessions so Claude Code's
        # next hook sees the change immediately.
        live = state.sessions.get(sid)
        if live is not None:
            try:
                state.sessions.update_overlay(sid, partial)
            except KeyError:
                return _not_found(f"unknown session: {sid}")
            cfg = state.sessions.config_for(sid)
            state.sessions.invalidate(sid)
            s = state.sessions.get(sid)
            # Mirror the change into persistent storage so the webui's
            # /api/persistent-sessions/<sid> view (and a subsequent daemon
            # restart) sees the same state — Pro app ↔ webui cross-sync.
            try:
                if state.persistent_sessions is not None:
                    _merge_into_persistent(state, sid, partial, s)
            except Exception:
                pass
            # Phase 4 — SSE consumers (webui useDaemonEvents + future
            # Pro Android EventSource) merge changed_fields into their
            # local session snapshot, so cross-tab + cross-device sync
            # converges within ~50ms instead of the next poll.
            _emit_session_changed(state, sid, partial)
            return JSONResponse({
                "state": {
                    "session_id": s.session_id,
                    "live_overlay": s.live_overlay,
                    "attached_profile": s.attached_profile,
                },
                "resolved_cfg": cfg,
            })
        # Dormant session — write directly to persistent overlay so the
        # change is preserved and the next live boot of this session
        # reads it on resume. Gated on the SID being known via persistent
        # storage or catalog so a typo'd/stale SID doesn't silently create
        # a ghost entry; use POST /api/persistent-sessions/<sid> to create.
        if state.persistent_sessions is None:
            return _not_found(f"unknown session: {sid}")
        try:
            has_persistent = state.persistent_sessions.exists(sid)
        except Exception:
            return _not_found(f"unknown session: {sid}")
        has_catalog = (
            state.catalog is not None
            and state.catalog.entry_for(sid) is not None
        )
        if not (has_persistent or has_catalog):
            return _not_found(f"unknown session: {sid}")
        try:
            _merge_into_persistent(state, sid, partial, None)
        except Exception as e:
            return _bad_request(f"persistent overlay write failed: {e}")
        merged = state.persistent_sessions.get(sid) or {}
        # Phase 4 — dormant overlay edits ALSO get a SessionChanged so
        # the webui's catalog row updates in real time even when the
        # session has no live in-memory state.
        _emit_session_changed(state, sid, partial)
        return JSONResponse({
            "state": {
                "session_id": sid,
                "live_overlay": merged.get("live_overlay", {}),
                "attached_profile": merged.get("attached_profile"),
                "persistent_only": True,
            },
            "resolved_cfg": merged,
        })

    async def patch_session(request: Request) -> JSONResponse:
        """PATCH /api/sessions/{sid} — typed partial update.

        Phase 3 (2026-05-16): the canonical entry point for editing a
        session. Accepts a SessionPatch (Pydantic-validated; unknown
        fields rejected with 400). Translates to the legacy partial
        shape understood by `_merge_into_persistent` and the in-memory
        registry's `update_overlay`, then returns the fresh SessionView.

        The older PUT /api/sessions/{sid}/overlay still works for
        backward compatibility (webui's existing client.ts uses it),
        and is slated for removal in Phase 6. New clients should
        prefer PATCH.
        """
        from claude_code_talker.schemas import SessionPatch
        from claude_code_talker.views import build_session_view
        from pydantic import ValidationError

        sid = request.path_params["session_id"]
        try:
            body = await _read_json(request)
        except ValueError as e:
            return _bad_request(str(e))
        if not isinstance(body, dict):
            return _bad_request("body must be a JSON object")
        try:
            patch = SessionPatch.model_validate(body)
        except ValidationError as e:
            return _bad_request(f"invalid SessionPatch: {e.errors()}")

        # Translate SessionPatch into the partial-dict shape that
        # _merge_into_persistent + state.sessions.update_overlay accept.
        # Both surfaces expect cadence under `live.cadence` rather than
        # top-level; voice/character round-trip as dicts.
        partial: dict = {}
        for field_name, value in patch.model_dump(exclude_none=True).items():
            if field_name == "cadence":
                partial.setdefault("live", {})["cadence"] = value
            elif field_name == "voice":
                partial["voice"] = value if isinstance(value, dict) else dict(value)
            elif field_name == "attached_character":
                partial["attached_character"] = value
            else:
                partial[field_name] = value

        # Live session path: mirror to in-memory + persistent.
        live = state.sessions.get(sid)
        if live is not None:
            try:
                state.sessions.update_overlay(sid, partial)
            except KeyError:
                return _not_found(f"unknown session: {sid}")
            state.sessions.invalidate(sid)
            if state.persistent_sessions is not None:
                try:
                    _merge_into_persistent(state, sid, partial, state.sessions.get(sid))
                except Exception:
                    pass
        else:
            # Dormant path: write directly to persistent overlay. Gated
            # on the SID being known so typos don't create ghost entries.
            if state.persistent_sessions is None:
                return _not_found(f"unknown session: {sid}")
            try:
                has_persistent = state.persistent_sessions.exists(sid)
            except Exception:
                return _not_found(f"unknown session: {sid}")
            has_catalog = (
                state.catalog is not None
                and state.catalog.entry_for(sid) is not None
            )
            if not (has_persistent or has_catalog):
                return _not_found(f"unknown session: {sid}")
            try:
                _merge_into_persistent(state, sid, partial, None)
            except Exception as e:
                return _bad_request(f"persistent overlay write failed: {e}")

        # Return the fresh SessionView so the caller sees the new state
        # without a follow-up GET. Same projection as /api/sessions
        # rows, so clients can drop it straight into their session list
        # cache.
        persistent = (
            state.persistent_sessions.get(sid)
            if state.persistent_sessions is not None
            else None
        )
        live_match = state.sessions.get(sid)
        catalog_entry = (
            state.catalog.entry_for(sid) if state.catalog is not None else None
        )
        view = build_session_view(
            state,
            sid,
            live_match=live_match,
            catalog_entry=catalog_entry,
            persistent=persistent,
        )

        # Phase 4 — SessionChanged emit (shared with PUT /overlay so
        # both writers produce the same wire event). Payload is the
        # diff: only the fields the caller patched.
        _emit_session_changed(state, sid, patch.model_dump(exclude_none=True))

        return JSONResponse(view.model_dump(mode="json"))

    async def delete_overlay_keypath(request: Request) -> JSONResponse:
        sid = request.path_params["session_id"]
        keypath = request.path_params["keypath"]
        if state.sessions.get(sid) is None:
            return _not_found(f"unknown session: {sid}")
        try:
            state.sessions.remove_overlay_keypath(sid, keypath)
        except KeyError:
            return _not_found(f"unknown session: {sid}")
        cfg = state.sessions.config_for(sid)
        s = state.sessions.get(sid)
        return JSONResponse({
            "state": {"session_id": s.session_id, "live_overlay": s.live_overlay},
            "resolved_cfg": cfg,
        })

    async def attach_profile(request: Request) -> JSONResponse:
        sid = request.path_params["session_id"]
        s = state.sessions.get(sid)
        if s is None:
            return _not_found(f"unknown session: {sid}")
        try:
            body = await _read_json(request)
        except ValueError as e:
            return _bad_request(str(e))
        name = body.get("name", "")
        if not is_valid_profile_name(name):
            return _bad_request(f"invalid profile name: {name!r}")
        if not state.profiles.exists(name):
            return _bad_request(f"profile not found: {name}")
        state.sessions.attach_profile(sid, name)
        if s.cwd:
            state.profiles.set_last_profile_for_cwd(s.cwd, name)
        cfg = state.sessions.config_for(sid)
        return JSONResponse({
            "state": {"session_id": s.session_id, "attached_profile": s.attached_profile},
            "resolved_cfg": cfg,
        })

    async def detach_profile(request: Request) -> JSONResponse:
        sid = request.path_params["session_id"]
        s = state.sessions.get(sid)
        if s is None:
            return _not_found(f"unknown session: {sid}")
        prev_cwd = s.cwd
        state.sessions.detach_profile(sid)
        if prev_cwd:
            state.profiles.clear_last_profile_for_cwd(prev_cwd)
        cfg = state.sessions.config_for(sid)
        return JSONResponse({
            "state": {"session_id": s.session_id, "attached_profile": None},
            "resolved_cfg": cfg,
        })

    async def save_as_profile(request: Request) -> JSONResponse:
        sid = request.path_params["session_id"]
        s = state.sessions.get(sid)
        if s is None:
            return _not_found(f"unknown session: {sid}")
        try:
            body = await _read_json(request)
        except ValueError as e:
            return _bad_request(str(e))
        name = body.get("name", "")
        if not is_valid_profile_name(name):
            return _bad_request(f"invalid profile name: {name!r}")
        path = state.profiles.save(name, dict(s.live_overlay))
        return JSONResponse({"name": name, "path": str(path)})

    async def hooks_status(request: Request) -> JSONResponse:
        path = CLAUDE_SETTINGS_PATH
        missing = list(_HOOK_EVENT_NAMES)
        if path.exists():
            try:
                data = _json_lib.loads(path.read_text(encoding="utf-8"))
            except Exception:
                data = {}
            if isinstance(data, dict):
                hooks = data.get("hooks") or {}
                if isinstance(hooks, dict):
                    missing = [
                        ev for ev in _HOOK_EVENT_NAMES
                        if not _has_codetalker_hook(hooks.get(ev) or [])
                    ]
        return JSONResponse({
            "installed": len(missing) == 0,
            "settings_path": str(path),
            "missing_events": missing,
        })

    async def hooks_dispatch(request: Request) -> JSONResponse:
        """v1.0 — REST entry point for Claude Code hooks. Replaces the
        MCP SSE path that hook_cli.py used to take; the SSE handshake
        from the Windows .exe wrapper was adding 10-22s per hook,
        causing them to silently time out before the tool dispatch ran.

        Body: the raw hook payload from Claude Code (must include
        ``hook_event_name`` + ``session_id``; additional fields depend
        on the event).
        """
        try:
            payload = await _read_json(request)
        except ValueError as exc:
            return _bad_request(str(exc))
        if not isinstance(payload, dict):
            return _bad_request("body must be a JSON object")
        event = payload.get("hook_event_name") or ""
        handlers = getattr(state, "hook_handlers_async", {}) or {}
        handler = handlers.get(event)
        if handler is None:
            return _bad_request(f"unknown or unsupported hook event: {event!r}")
        # Build the args dict the same way hook_cli.dispatch_hook did
        # for MCP; the underlying tts_handle_* functions all read these
        # specific keys (others are ignored).
        common = {
            "session_id": payload.get("session_id", ""),
            "cwd": payload.get("cwd", ""),
        }
        if event == "Stop":
            args = {**common, "transcript_path": payload.get("transcript_path", "")}
        elif event == "Notification":
            args = {**common, "message": payload.get("message", "")}
        elif event == "UserPromptSubmit":
            args = {**common, "prompt": payload.get("prompt", "")}
        elif event == "PreToolUse":
            args = {
                **common,
                "tool_name": payload.get("tool_name", ""),
                "tool_input": payload.get("tool_input", {}),
            }
        elif event == "PostToolUse":
            args = {
                **common,
                "tool_name": payload.get("tool_name", ""),
                "tool_input": payload.get("tool_input", {}),
                "tool_response": payload.get("tool_response", {}),
            }
        else:
            args = common
        try:
            result = await handler(args)
        except Exception as exc:
            return JSONResponse(
                {"error": f"handler raised: {exc}", "event": event},
                status_code=500,
            )
        return JSONResponse({"event": event, "result": result})

    async def install_hooks(request: Request) -> JSONResponse:
        path = CLAUDE_SETTINGS_PATH
        if path.exists():
            try:
                data = _json_lib.loads(path.read_text(encoding="utf-8"))
                if not isinstance(data, dict):
                    data = {}
            except Exception:
                data = {}
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            data = {}
        data.setdefault("hooks", {})
        added = 0
        for ev in _HOOK_EVENT_NAMES:
            entries = data["hooks"].setdefault(ev, [])
            if not _has_codetalker_hook(entries):
                entries.append(dict(_HOOK_ENTRY))
                added += 1
        path.write_text(_json_lib.dumps(data, indent=2), encoding="utf-8")
        return JSONResponse({"installed": True, "hooks_added": added})

    async def mute(request: Request) -> JSONResponse:
        state.cfg["enabled"] = False
        return JSONResponse({"enabled": False})

    async def unmute(request: Request) -> JSONResponse:
        state.cfg["enabled"] = True
        return JSONResponse({"enabled": True})

    async def list_voices(request: Request) -> JSONResponse:
        engine_name = request.query_params.get("engine")
        if not engine_name:
            return _bad_request("query param 'engine' is required")
        engine = state.engines.get(engine_name)
        if engine is None:
            return _bad_request(f"unknown engine: {engine_name}")
        try:
            voices = engine.list_voices()
        except Exception as e:
            return JSONResponse({"error": f"engine list_voices failed: {e}"}, status_code=500)
        return JSONResponse(list(voices))

    async def status(request: Request) -> JSONResponse:
        active_modes = {}
        for s in state.sessions.list_active():
            cfg = state.sessions.config_for(s.session_id)
            active_modes[s.session_id] = cfg.get("active_mode", state.active_mode)
        return JSONResponse({
            "enabled": state.cfg.get("enabled", True),
            "session_count": len(state.sessions.list_active()),
            "active_modes": active_modes,
            "engines": list(state.engines),
            "providers": list(state.providers),
        })

    async def list_profiles(request: Request) -> JSONResponse:
        names = state.profiles.list()
        out = []
        for name in names:
            try:
                content = state.profiles.get(name)
                out.append({"name": name, "key_count": len(content)})
            except Exception:
                out.append({"name": name, "key_count": 0, "corrupted": True})
        return JSONResponse(out)

    _CHARACTER_ID_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")

    def _bad_character_id(cid: str) -> JSONResponse:
        return JSONResponse(
            {"error": f"invalid character id: {cid!r}"}, status_code=400
        )

    async def list_characters(request: Request) -> JSONResponse:
        if state.characters is None:
            return JSONResponse([])
        chars = state.characters.list()
        return JSONResponse([c.to_dict() for c in chars])

    async def get_character(request: Request) -> JSONResponse:
        cid = request.path_params.get("char_id", "")
        if not _CHARACTER_ID_RE.match(cid):
            return _bad_character_id(cid)
        if state.characters is None:
            return JSONResponse({"error": "character store unavailable"}, status_code=503)
        c = state.characters.get(cid)
        if c is None:
            return JSONResponse({"error": "character not found"}, status_code=404)
        return JSONResponse(c.to_dict())

    async def create_character(request: Request) -> JSONResponse:
        if state.characters is None:
            return JSONResponse({"error": "character store unavailable"}, status_code=503)
        try:
            body = await request.json()
        except (json.JSONDecodeError, ValueError):
            return JSONResponse({"error": "invalid JSON"}, status_code=400)
        if not isinstance(body, dict):
            return JSONResponse({"error": "body must be a JSON object"}, status_code=400)
        cid = body.get("id", "")
        if not _CHARACTER_ID_RE.match(cid):
            return _bad_character_id(cid)
        if state.characters.get(cid) is not None:
            return JSONResponse({"error": f"character {cid!r} already exists"}, status_code=409)
        from claude_code_talker.characters import Character, CharacterValidationError
        try:
            c = Character.from_dict(body)
            state.characters.save(c)
        except CharacterValidationError as e:
            return JSONResponse({"error": str(e)}, status_code=400)
        return JSONResponse(state.characters.get(cid).to_dict())

    async def put_character(request: Request) -> JSONResponse:
        if state.characters is None:
            return JSONResponse({"error": "character store unavailable"}, status_code=503)
        cid = request.path_params.get("char_id", "")
        if not _CHARACTER_ID_RE.match(cid):
            return _bad_character_id(cid)
        if state.characters.get(cid) is None:
            return JSONResponse({"error": "character not found"}, status_code=404)
        try:
            body = await request.json()
        except (json.JSONDecodeError, ValueError):
            return JSONResponse({"error": "invalid JSON"}, status_code=400)
        if not isinstance(body, dict):
            return JSONResponse({"error": "body must be a JSON object"}, status_code=400)
        if body.get("id") != cid:
            return JSONResponse(
                {"error": f"id in body ({body.get('id')!r}) must match URL ({cid!r})"},
                status_code=400,
            )
        from claude_code_talker.characters import Character, CharacterValidationError
        try:
            c = Character.from_dict(body)
            state.characters.save(c)
        except CharacterValidationError as e:
            return JSONResponse({"error": str(e)}, status_code=400)
        return JSONResponse(state.characters.get(cid).to_dict())

    async def delete_character(request: Request) -> JSONResponse:
        if state.characters is None:
            return JSONResponse({"error": "character store unavailable"}, status_code=503)
        cid = request.path_params.get("char_id", "")
        if not _CHARACTER_ID_RE.match(cid):
            return _bad_character_id(cid)
        if state.characters.get(cid) is None:
            return JSONResponse({"error": "character not found"}, status_code=404)
        # Cascade: detach this character from any session that has it attached.
        if state.sessions is not None:
            for s in state.sessions.list_active():
                if getattr(s, "attached_character", None) == cid:
                    s.attached_character = None
        state.characters.delete(cid)
        return JSONResponse({"deleted": True})

    async def generate_character_for_session(request: Request) -> JSONResponse:
        """POST /api/sessions/{session_id}/generate-character — use the
        configured LLM to invent a Character tailored to this session.

        Modes:
        - `?preview=true` — return the LLM draft (display_name, persona,
          mesh_prompt, emotive_states) WITHOUT saving or attaching. UI
          opens an editor with the draft pre-filled so the user can tweak
          fields before committing.
        - default (no query) — save the character to the store and
          attach it to the session in one call (legacy one-click flow).

        The LLM is told about the session display_name and project_dir
        and asked to return a JSON document. voice_ref defaults to a
        known piper voice; the user can swap it later in the Voice
        picker or attach a cloned voice.
        """
        preview_only = request.query_params.get("preview", "").lower() in (
            "1", "true", "yes"
        )
        if state.characters is None:
            return JSONResponse({"error": "character store unavailable"}, status_code=503)
        sid = request.path_params.get("session_id", "")
        if not sid:
            return _bad_request("session_id is required")
        # Read session context for the LLM prompt.
        sess = state.sessions.get(sid) if state.sessions is not None else None
        persistent = (
            state.persistent_sessions.get(sid)
            if getattr(state, "persistent_sessions", None) is not None
            else {}
        ) or {}
        display_name = (
            persistent.get("display_name")
            or (getattr(sess, "live_overlay", {}) or {}).get("display_name")
            or sid[:8]
        )
        project_dir = (
            (getattr(sess, "cwd", "") if sess is not None else "")
            or persistent.get("cwd")
            or ""
        )
        # Last segment of project_dir is a useful project name proxy.
        import os as _os
        project_label = _os.path.basename(project_dir.replace("\\", "/")) or "the project"

        from claude_code_talker.server import _select_provider
        provider = _select_provider(state, "brief")
        if provider is None:
            return JSONResponse(
                {"error": "no LLM provider configured (set openrouter or anthropic key)"},
                status_code=503,
            )

        prompt = f"""You are designing a TTS narrator character for a coding session named "{display_name}" working on project "{project_label}".

The character will narrate Claude Code's progress aloud as work happens. The persona should suit the work being done — analytical for systems work, warm for creative work, technical for infra, etc.

VISUAL FORMAT — CRITICAL: the character is rendered as a TALKING-HEAD PORTRAIT with the body visible from the WAIST UP and ARMS in-frame. All visual prompts (mesh_prompt + emotive_states) must describe poses, gestures, and expressions that work within this framing. Do NOT describe full-body or legs/feet motion. Arms and hands are always part of every pose. Camera frames torso + head.

Output ONLY valid JSON matching this exact schema (no markdown, no commentary, no code fences):

{{
  "display_name": "short readable name like 'Maya' or 'Atlas' (1-3 words)",
  "persona": "one of: methodical, warm, technical, plain, sarcastic, energetic",
  "mesh_prompt": "single sentence visual description, WAIST-UP PORTRAIT with arms visible: attire, hair, expression, era/style, arm position, framing should clearly state 'waist-up portrait' or 'bust shot'",
  "emotive_states": {{
    "idle": "character-specific baseline waist-up pose with arm/hand position, 5-15 words",
    "listening": "attentive forward lean with hands/arms gesture specific to this character",
    "speaking": "expressive talking gesture with hand/arm motion specific to this character",
    "researching": "studying or reading pose with arms/hands engaged specific to this character",
    "working": "focused task-doing pose with hands active specific to this character",
    "questioning": "inquiring head-tilt with hand/arm position specific to this character",
    "thinking": "contemplative pose with hand near face/chin specific to this character",
    "confirming": "satisfied affirming pose with arm/hand gesture specific to this character",
    "concluding": "settled wrap-up pose with hands relaxed specific to this character",
    "alerted": "alert or concerned reaction with arms/hands raised specific to this character"
  }}
}}

Each emotive_states value: single short phrase describing pose + expression + arm/hand gesture, rooted in the character's visual identity, framing always waist-up."""

        try:
            raw = await provider.complete(prompt, max_tokens=900)
        except Exception as exc:
            return JSONResponse({"error": f"LLM call failed: {exc}"}, status_code=502)
        text = (raw or "").strip()
        # Trim common LLM artifacts (markdown fences, leading commentary).
        if text.startswith("```"):
            # strip ```json ... ``` fences
            text = text.lstrip("`")
            if text.lower().startswith("json"):
                text = text[4:]
            text = text.strip().rstrip("`").strip()
        # Find the first { ... last } to be lenient with leading prose.
        first = text.find("{")
        last = text.rfind("}")
        if first == -1 or last == -1 or last <= first:
            return JSONResponse(
                {"error": "LLM did not return JSON", "raw": raw[:500]},
                status_code=502,
            )
        try:
            data = json.loads(text[first : last + 1])
        except json.JSONDecodeError as exc:
            return JSONResponse(
                {"error": f"LLM JSON parse failed: {exc}", "raw": raw[:500]},
                status_code=502,
            )
        if not isinstance(data, dict):
            return JSONResponse(
                {"error": "LLM JSON was not an object", "raw": raw[:500]},
                status_code=502,
            )

        # Slug-ify the display_name into a kebab-case character id, dedup
        # if the slug already exists in the store.
        import re as _re
        ai_display = (data.get("display_name") or "").strip() or "agent"
        base_slug = _re.sub(r"[^a-z0-9-]+", "-", ai_display.lower()).strip("-") or "agent"
        slug = base_slug
        n = 2
        while state.characters.get(slug) is not None:
            slug = f"{base_slug}-{n}"
            n += 1

        # Default voice: pick the first installed piper voice, fall back to
        # a known good one. Per-character voice clones come later.
        piper = state.engines.get("piper")
        voices = piper.list_voices() if piper is not None else []
        default_voice = voices[0] if voices else "en_GB-jenny_dioco-medium"

        emotive = data.get("emotive_states") or {}
        if not isinstance(emotive, dict):
            emotive = {}
        # Coerce non-string emotive values defensively.
        emotive = {k: str(v).strip() for k, v in emotive.items() if isinstance(k, str) and v}

        persona = (data.get("persona") or "").strip().lower()
        if persona not in {"methodical", "warm", "technical", "plain", "sarcastic", "energetic"}:
            persona = "technical"

        now_ts = __import__("time").time()
        from claude_code_talker.characters import Character, CharacterValidationError
        char = Character(
            id=slug,
            display_name=ai_display,
            voice_ref=default_voice,
            persona=persona,
            mesh_prompt=(data.get("mesh_prompt") or "").strip() or None,
            emotive_states=emotive,
            created_at=now_ts,
            updated_at=now_ts,
        )

        # Preview mode: return the draft without saving or attaching so
        # the user can edit fields in the UI before committing. The slug
        # is offered as a SUGGESTED id (which the UI may regenerate if
        # the user changes display_name).
        if preview_only:
            return JSONResponse({
                "preview": True,
                "draft": char.to_dict(),
                "session_id": sid,
                "session_label": display_name,
            })

        try:
            char.validate()
            state.characters.save(char)
        except CharacterValidationError as exc:
            return JSONResponse(
                {"error": f"validation failed: {exc}", "raw": raw[:500]},
                status_code=502,
            )
        # Attach to the session (mirrors attach_character logic). Persists
        # to the overlay so it survives daemon restart.
        if state.sessions is not None:
            s = state.sessions.get(sid)
            if s is not None:
                s.attached_character = slug
            try:
                _merge_into_persistent(state, sid, {"attached_character": slug}, s)
            except Exception:
                pass

        return JSONResponse({"character": char.to_dict(), "attached_to": sid})

    async def characters_clone_voice(request: Request) -> JSONResponse:
        """Phase 25c — POST /api/characters/{char_id}/clone-voice.

        Accept a wav/webm upload, clone the voice via XTTS (real pipeline, not v1 stub),
        register the reference as a usable XTTS voice for narration.
        2026-05-11 vNext P0-A: replaces the stub that discarded audio bytes and
        synchronously marked the job succeeded with a fake voice_ref.

        X-1 (2026-05-18): gated as a Pro feature — XTTS cloning is one of
        the headline Pro differentiators. Free users can still preview
        and use the pre-built Piper voices.
        """
        from claude_code_talker.licensing import pro_gate_payload
        gate = pro_gate_payload("voice_clone_create", state)
        if gate is not None:
            return JSONResponse(gate, status_code=402)

        if state.characters is None:
            return JSONResponse({"error": "character store unavailable"}, status_code=503)
        if getattr(state, "clone_jobs", None) is None:
            return JSONResponse({"error": "clone-job tracker unavailable"}, status_code=503)
        cid = request.path_params.get("char_id", "")
        if not _CHARACTER_ID_RE.match(cid):
            return _bad_character_id(cid)
        if state.characters.get(cid) is None:
            return JSONResponse({"error": "character not found"}, status_code=404)
        try:
            form = await request.form()
        except Exception as e:  # pragma: no cover - hard to unit-test bad multipart
            return JSONResponse({"error": f"invalid form: {e}"}, status_code=400)
        audio = form.get("audio")
        mime_type = str(form.get("mime_type") or "audio/webm")
        if audio is None:
            return JSONResponse({"error": "audio field required"}, status_code=400)
        # UploadFile has .read(); a plain str/bytes form value does not.
        if hasattr(audio, "read"):
            audio_bytes = await audio.read()
        else:
            audio_bytes = bytes(audio) if isinstance(audio, (bytes, bytearray)) else str(audio).encode()

        if not audio_bytes:
            return JSONResponse({"error": "audio file is empty"}, status_code=400)

        # Persist the upload to a tmp wav file the cloner can read.
        import tempfile
        from pathlib import Path
        suffix = ".webm" if "webm" in mime_type else ".wav"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix, prefix=f"cct-clone-{cid}-") as tmp:
            tmp.write(audio_bytes)
            tmp_path = Path(tmp.name)

        # Resolve the XTTS references dir (used by engines/xtts.py:list_voices to discover voices).
        xtts_cfg = (state.cfg.get("engines") or {}).get("xtts") or {}
        refs_dir = Path(
            xtts_cfg.get("references_dir")
            or (Path.home() / ".claude" / "scripts" / "voice-cloner" / "references")
        )
        refs_dir.mkdir(parents=True, exist_ok=True)

        # Open a job for the UI to poll.
        job = state.clone_jobs.create(cid, audio_bytes, mime_type)

        # Run the real clone pipeline. clone_from_local_file writes `<name>.wav` into
        # references_dir; we use cid as the name so engines/xtts.py lists it as the
        # voice for this character.
        try:
            from claude_code_talker.voices.clone import clone_from_local_file
            await clone_from_local_file(tmp_path, name=cid, references_dir=refs_dir)
        except Exception as exc:
            state.clone_jobs.set_failed(job.job_id, error=str(exc)[:300])
            return JSONResponse(
                {"job_id": job.job_id, "status": "failed", "error": str(exc)[:300]},
                status_code=500
            )
        finally:
            try:
                tmp_path.unlink(missing_ok=True)
            except OSError:
                # Best-effort cleanup; don't let temp-file removal mask real errors.
                pass

        voice_ref = cid  # the real reference filename on disk is <cid>.wav
        # Mark job as succeeded with the character id (which is the voice filename stem).
        state.clone_jobs.set_succeeded(job.job_id, voice_ref=voice_ref)

        body = state.clone_jobs.get(job.job_id)
        return JSONResponse(
            {
                "job_id": body.job_id,
                "status": body.status,
                "voice_ref": body.voice_ref,
            },
            status_code=202,
        )

    async def voice_clone_job_get(request: Request) -> JSONResponse:
        """Phase 25c — GET /api/voice-clone-jobs/{job_id}."""
        if getattr(state, "clone_jobs", None) is None:
            return JSONResponse({"error": "clone-job tracker unavailable"}, status_code=503)
        job_id = request.path_params.get("job_id", "")
        job = state.clone_jobs.get(job_id)
        if job is None:
            return JSONResponse({"error": "job not found"}, status_code=404)
        return JSONResponse(
            {
                "job_id": job.job_id,
                "status": job.status,
                "voice_ref": job.voice_ref,
                "error": job.error,
            }
        )

    async def character_mesh_file(request: Request):
        """v0.1.0 unification — GET /api/characters/{char_id}/mesh-file.

        Serves the character's .glb mesh from disk so the webui can
        render it in a 3D viewer (model-viewer / three.js) instead of
        the persona-tinted fallback circle. Returns 404 if the character
        doesn't exist or has no mesh.

        Why not StaticFiles: mesh_path is per-character and not under a
        single shared dir — the character store may have models split
        across `~/.claude/scripts/codetalker/models/<id>/` AND uploaded
        files elsewhere. A per-character route keeps the path mapping
        in one place (the Character record's `mesh_path`).
        """
        from starlette.responses import FileResponse
        from pathlib import Path as _P

        if state.characters is None:
            return JSONResponse({"error": "character store unavailable"}, status_code=503)
        cid = request.path_params.get("char_id", "")
        if not _CHARACTER_ID_RE.match(cid):
            return _bad_character_id(cid)
        char = state.characters.get(cid)
        if char is None or not char.mesh_path:
            return JSONResponse({"error": "no mesh"}, status_code=404)
        mesh = _P(char.mesh_path)
        if not mesh.exists() or not mesh.is_file():
            return JSONResponse({"error": "mesh file missing"}, status_code=404)
        # Detect content type by extension. GLB is the binary glTF format
        # most browsers + <model-viewer> understand natively.
        suffix = mesh.suffix.lower()
        media_type = {
            ".glb": "model/gltf-binary",
            ".gltf": "model/gltf+json",
            ".obj": "model/obj",
        }.get(suffix, "application/octet-stream")
        return FileResponse(
            mesh,
            media_type=media_type,
            headers={
                # Allow long browser caching since meshes are immutable
                # per character record (mesh_path changes when regen'd).
                "Cache-Control": "public, max-age=300",
            },
        )

    async def attach_character(request: Request) -> JSONResponse:
        # X-1 — character_attach is a Pro feature. Gate at the route
        # boundary so an OSS-only daemon (no license, or license invalid)
        # returns a clean 402 with the Pro upsell URL instead of the
        # character actually attaching. Free users can still BROWSE
        # the character library — only the attach action requires Pro.
        from claude_code_talker.licensing import pro_gate_payload
        gate = pro_gate_payload("character_attach", state)
        if gate is not None:
            return JSONResponse(gate, status_code=402)

        if state.characters is None or state.sessions is None:
            return JSONResponse({"error": "character store unavailable"}, status_code=503)
        sid = request.path_params.get("session_id", "")
        if not is_valid_session_id(sid):
            return _bad_request(f"invalid session id: {sid!r}")
        s = state.sessions.get(sid)
        # v0.1.0 unification — dormant fallback for sessions that have no
        # in-memory SessionState (transcript-mtime live OR fully dormant).
        # Without this, attaching a character to a session you haven't
        # poked since daemon restart 404'd. Gate on the SID being known
        # via persistent or catalog so a typo doesn't ghost-create.
        if s is None:
            known = False
            if state.persistent_sessions is not None:
                try:
                    known = state.persistent_sessions.exists(sid)
                except Exception:
                    pass
            if not known and state.catalog is not None:
                known = state.catalog.entry_for(sid) is not None
            if not known:
                return JSONResponse({"error": "session not found"}, status_code=404)
        try:
            body = await request.json()
        except (json.JSONDecodeError, ValueError):
            return JSONResponse({"error": "invalid JSON"}, status_code=400)
        cid = (body or {}).get("character_id", "")
        if not _CHARACTER_ID_RE.match(cid or ""):
            return _bad_character_id(cid)
        char = state.characters.get(cid)
        if char is None:
            return JSONResponse({"error": f"character not found: {cid}"}, status_code=400)
        # Phase 25a — validate voice_ref resolves to a voice in some registered engine.
        voice_ok = False
        for engine in (state.engines or {}).values():
            try:
                if char.voice_ref in (engine.list_voices() or []):
                    voice_ok = True
                    break
            except Exception:
                continue
        if not voice_ok:
            return JSONResponse(
                {"error": f"character voice_ref not found in any engine: {char.voice_ref!r}"},
                status_code=400,
            )
        if s is not None:
            s.attached_character = cid
        # v0.1.0 unification — persist the attach so it survives daemon
        # restart AND so the API's list_sessions reads the correct
        # attached_character even when this session is later transcript-
        # mtime-live without an in-memory SessionState. Without this,
        # the picker shows the selection (cached client-side) but the
        # CharacterStage / next-load reads None.
        try:
            if state.persistent_sessions is not None:
                _merge_into_persistent(state, sid, {"attached_character": cid}, s)
        except Exception:
            pass
        return JSONResponse({
            "state": {"session_id": sid, "attached_character": cid}
        })

    async def detach_character(request: Request) -> JSONResponse:
        if state.sessions is None:
            return JSONResponse({"error": "session registry unavailable"}, status_code=503)
        sid = request.path_params.get("session_id", "")
        if not is_valid_session_id(sid):
            return _bad_request(f"invalid session id: {sid!r}")
        s = state.sessions.get(sid)
        # v0.1.0 unification — dormant fallback (mirrors attach_character).
        if s is None:
            known = False
            if state.persistent_sessions is not None:
                try:
                    known = state.persistent_sessions.exists(sid)
                except Exception:
                    pass
            if not known and state.catalog is not None:
                known = state.catalog.entry_for(sid) is not None
            if not known:
                return JSONResponse({"error": "session not found"}, status_code=404)
        if s is not None:
            s.attached_character = None
        # Clear from persistent overlay too so the detach survives restart.
        try:
            if state.persistent_sessions is not None:
                _merge_into_persistent(state, sid, {"attached_character": None}, s)
        except Exception:
            pass
        return JSONResponse({
            "state": {"session_id": sid, "attached_character": None}
        })

    async def get_profile(request: Request) -> JSONResponse:
        name = request.path_params["name"]
        if not is_valid_profile_name(name):
            return _bad_request(f"invalid profile name: {name!r}")
        try:
            content = state.profiles.get(name)
        except FileNotFoundError:
            return _not_found(f"profile not found: {name}")
        return JSONResponse({"name": name, "content": content})

    async def put_profile(request: Request) -> JSONResponse:
        name = request.path_params["name"]
        if not is_valid_profile_name(name):
            return _bad_request(f"invalid profile name: {name!r}")
        try:
            body = await _read_json(request)
        except ValueError as e:
            return _bad_request(str(e))
        state.profiles.save(name, body)
        return JSONResponse({"name": name, "content": body})

    async def delete_profile(request: Request) -> JSONResponse:
        name = request.path_params["name"]
        if not is_valid_profile_name(name):
            return _bad_request(f"invalid profile name: {name!r}")
        if not state.profiles.exists(name):
            return _not_found(f"profile not found: {name}")
        # Detach from any sessions that have it attached
        detached = 0
        for s in state.sessions.list_active():
            if s.attached_profile == name:
                state.sessions.detach_profile(s.session_id)
                detached += 1
        state.profiles.delete(name)
        return JSONResponse({"deleted": True, "detached_from_sessions": detached})

    async def list_catalog(request: Request) -> JSONResponse:
        project = request.query_params.get("project")
        if project is not None and not _PROJECT_RE.match(project):
            return _bad_request(f"invalid project: {project!r}")
        if state.catalog is None:
            return JSONResponse([])
        if project:
            entries = state.catalog.entries_for_project(project)
        else:
            entries = state.catalog.entries()
        out = [
            {
                "session_id": e.session_id,
                "project_slug": e.project_slug,
                "transcript_path": str(e.transcript_path),
                "last_modified": e.last_modified,
                "title": e.title,
                "vscode_label": e.vscode_label,
            }
            for e in entries
        ]
        return JSONResponse(out)

    async def refresh_catalog(request: Request) -> JSONResponse:
        if not _rate_limit_check(state, "catalog_refresh", 5.0):
            return JSONResponse({"error": "rate limited (1 refresh per 5s)"}, status_code=429)
        if state.catalog is None:
            return JSONResponse({"scanned": 0})
        scanned = state.catalog.refresh()
        return JSONResponse({"scanned": scanned})

    async def get_persistent_session(request: Request) -> JSONResponse:
        sid = request.path_params["session_id"]
        if not is_valid_session_id(sid):
            return _bad_request(f"invalid session_id: {sid!r}")
        payload = state.persistent_sessions.get(sid)
        if payload is None:
            return _not_found(f"no persistent settings for session: {sid}")
        return JSONResponse(payload)

    async def put_persistent_session(request: Request) -> JSONResponse:
        sid = request.path_params["session_id"]
        if not is_valid_session_id(sid):
            return _bad_request(f"invalid session_id: {sid!r}")
        try:
            body = await _read_json(request)
        except ValueError as e:
            return _bad_request(str(e))
        live_overlay = body.get("live_overlay")
        if live_overlay is not None and not isinstance(live_overlay, dict):
            return _bad_request("live_overlay must be a JSON object")
        enabled = body.get("enabled")
        if enabled is not None and not isinstance(enabled, bool):
            return _bad_request("enabled must be a boolean")
        # Build canonical payload — preserve any unknown keys for schema-drift forward-compat
        payload = dict(body)
        payload.setdefault("live_overlay", {})
        payload.setdefault("enabled", True)
        payload.setdefault("attached_profile", None)
        payload.setdefault("display_name", None)
        payload["last_modified"] = _rate_time.time()
        state.persistent_sessions.save(sid, payload)
        # Phase 13.6d: also update the in-memory SessionRegistry so the
        # mute toggle takes effect WITHOUT a daemon restart. The bulk
        # endpoint (api.py:641) already does this; the per-session PUT
        # was missing the live mirror, so mutes persisted to disk but
        # didn't actually mute the running session.
        if state.sessions is not None:
            live_session = state.sessions.get(sid)
            if live_session is not None:
                if isinstance(payload.get("enabled"), bool):
                    live_session.enabled = payload["enabled"]
            else:
                # Phase 13.7d: cold-start path — session is in catalog/persistent
                # storage but not yet in the live registry (typical right after a
                # daemon bounce). Auto-register it so the mute toggle takes effect
                # immediately without waiting for the next hook fire.
                cwd = ""
                if state.catalog is not None:
                    entry = state.catalog.entry_for(sid)
                    if entry is not None:
                        # cwd isn't stored on CatalogEntry; leave empty — still
                        # better than leaving the session absent from the registry.
                        cwd = ""
                state.sessions.touch(sid, cwd=cwd)
                live_session = state.sessions.get(sid)
                if live_session is not None and isinstance(payload.get("enabled"), bool):
                    live_session.enabled = payload["enabled"]
        return JSONResponse({"saved": True, "session_id": sid})

    async def delete_persistent_session(request: Request) -> JSONResponse:
        sid = request.path_params["session_id"]
        if not is_valid_session_id(sid):
            return _bad_request(f"invalid session_id: {sid!r}")
        existed = state.persistent_sessions.exists(sid)
        state.persistent_sessions.delete(sid)
        return JSONResponse({"deleted": existed})

    async def get_secrets(request: Request) -> JSONResponse:
        """Return all known API keys, redacted (last 4 chars). Source-of-truth
        per key (env vs file) is included so the user knows where it's coming
        from."""
        if state.secrets is None:
            return JSONResponse({})
        on_disk = state.secrets.load()
        out: dict[str, dict] = {}
        import os as _os
        for env_name, file_key in [
            ("ANTHROPIC_API_KEY", "anthropic_api_key"),
            ("OPENAI_API_KEY", "openai_api_key"),
            ("OPENROUTER_API_KEY", "openrouter_api_key"),
            ("ELEVENLABS_API_KEY", "elevenlabs_api_key"),
            # Phase 25b — 3D mesh provider API keys.
            ("HYPER3D_API_KEY", "hyper3d_api_key"),
            ("MESHY_API_KEY", "meshy_api_key"),
            ("TRIPO3D_API_KEY", "tripo3d_api_key"),
        ]:
            env_val = _os.environ.get(env_name)
            if env_val:
                out[file_key] = {"set": True, "redacted": _SecretsStore.redact(env_val), "source": "env"}
            elif file_key in on_disk:
                out[file_key] = {"set": True, "redacted": _SecretsStore.redact(on_disk[file_key]), "source": "file"}
            else:
                out[file_key] = {"set": False, "redacted": None, "source": None}
        return JSONResponse(out)

    async def put_secrets(request: Request) -> JSONResponse:
        """Update one or more API keys. Empty-string deletes a key. Body shape:
        {"openai_api_key": "sk-...", "anthropic_api_key": ""}"""
        if state.secrets is None:
            return _bad_request("secrets store not configured")
        try:
            body = await _read_json(request)
        except ValueError as e:
            return _bad_request(str(e))
        partial: dict[str, str] = {}
        for k, v in body.items():
            if k not in _SECRET_KEYS:
                return _bad_request(f"unknown secret key: {k!r}")
            if not isinstance(v, str):
                return _bad_request(f"value for {k} must be a string")
            partial[k] = v
        state.secrets.update(partial)
        return JSONResponse({"saved": True, "note": "Restart daemon for changes to take effect"})

    # Curated cost-effective default model lists per provider. Used for the UI
    # dropdown when the provider doesn't expose a /models endpoint or when an
    # offline / cached list is sufficient.
    _CURATED_MODELS: dict[str, list[dict]] = {
        "ollama": [
            {"id": "llama3.2", "label": "llama3.2 (3B, default)", "tier": "local"},
            {"id": "qwen2.5:3b", "label": "qwen2.5:3b", "tier": "local"},
            {"id": "phi3.5", "label": "phi3.5", "tier": "local"},
        ],
        "anthropic": [
            {"id": "claude-haiku-4-5-20251001", "label": "Claude Haiku 4.5 (fast/cheap)", "tier": "cheap"},
            {"id": "claude-sonnet-4-6", "label": "Claude Sonnet 4.6 (balanced)", "tier": "mid"},
            {"id": "claude-opus-4-7", "label": "Claude Opus 4.7 (premium)", "tier": "premium"},
        ],
        "openai": [
            {"id": "gpt-4o-mini", "label": "GPT-4o mini (cheap default)", "tier": "cheap"},
            {"id": "gpt-5-mini", "label": "GPT-5 mini", "tier": "cheap"},
            {"id": "gpt-4o", "label": "GPT-4o", "tier": "mid"},
            {"id": "gpt-5", "label": "GPT-5 (premium)", "tier": "premium"},
        ],
        "openrouter": [
            {"id": "google/gemini-2.0-flash-001", "label": "Gemini 2.0 Flash (cheapest, default)", "tier": "cheap"},
            {"id": "openai/gpt-4o-mini", "label": "GPT-4o mini via OpenRouter", "tier": "cheap"},
            {"id": "anthropic/claude-haiku-4-5", "label": "Claude Haiku 4.5 via OpenRouter", "tier": "cheap"},
            {"id": "meta-llama/llama-3.3-70b-instruct", "label": "Llama 3.3 70B (cheap+capable)", "tier": "cheap"},
            {"id": "anthropic/claude-sonnet-4-6", "label": "Claude Sonnet 4.6 via OpenRouter", "tier": "mid"},
        ],
    }

    # Cache OpenRouter's live /models response so the dropdown doesn't refetch
    # every page load.
    _openrouter_models_cache: dict = {"data": None, "fetched_at": 0.0}

    async def list_llm_models(request: Request) -> JSONResponse:
        """Return curated + (optionally cached) model list per provider.

        Response shape: {provider: {default: <model_id>, models: [...]}}
        """
        out: dict[str, dict] = {}
        # Pull configured-default model from cfg per provider so the UI shows
        # the right "current" item.
        cfg_providers = (state.cfg.get("providers") or {})
        for provider, models in _CURATED_MODELS.items():
            cfg_model = (cfg_providers.get(provider) or {}).get("model")
            if provider == "openrouter":
                default = cfg_model or "google/gemini-2.0-flash-001"
                live = _openrouter_models_cache["data"]
                merged = list(models)
                if live:
                    seen = {m["id"] for m in merged}
                    for m in live:
                        if m["id"] not in seen:
                            merged.append(m)
            elif provider == "openai":
                default = cfg_model or "gpt-4o-mini"
                merged = list(models)
            elif provider == "anthropic":
                default = cfg_model or "claude-haiku-4-5-20251001"
                merged = list(models)
            else:  # ollama
                default = cfg_model or "llama3.2"
                merged = list(models)
            available = provider in (state.providers or {})
            out[provider] = {
                "default": default,
                "models": merged,
                "available": available,
            }
        return JSONResponse(out)

    async def get_narration_log(request: Request) -> JSONResponse:
        """Phase 11: return the last N narrated lines, optionally filtered by session."""
        if state.narration_log is None:
            return JSONResponse([])
        try:
            limit = int(request.query_params.get("limit", 100))
        except ValueError:
            return _bad_request("limit must be an integer")
        limit = max(1, min(1000, limit))
        sid = request.query_params.get("session_id")
        if sid:
            if not is_valid_session_id(sid):
                return _bad_request(f"invalid session_id: {sid!r}")
            entries = state.narration_log.find_for_session(sid, limit=limit)
        else:
            entries = state.narration_log.tail(n=limit)
        return JSONResponse(entries)

    async def get_usage(request: Request) -> JSONResponse:
        """Phase 12: return token + cost rollup, optionally since a unix timestamp."""
        if state.token_tracker is None:
            return JSONResponse({})
        since_str = request.query_params.get("since")
        since = None
        if since_str:
            try:
                since = float(since_str)
            except ValueError:
                return _bad_request("since must be a unix timestamp")
        return JSONResponse(state.token_tracker.rollup(since=since))

    async def get_tts_cache_stats(request: Request) -> JSONResponse:
        """Phase 10: TTS cache stats (entries, bytes, hit ratio)."""
        if state.tts_cache is None:
            return JSONResponse({})
        return JSONResponse(state.tts_cache.stats())

    async def clear_tts_cache(request: Request) -> JSONResponse:
        """Phase 10: clear the TTS cache (returns count of files removed)."""
        if state.tts_cache is None:
            return JSONResponse({"deleted": 0})
        deleted = state.tts_cache.clear()
        return JSONResponse({"deleted": deleted})

    async def reload_config(request: Request) -> JSONResponse:
        """Phase 12: hot-reload state.cfg from disk without restarting the daemon.

        Re-runs load_full_config() and replaces state.cfg in place. Cached per-
        session resolved configs are invalidated so the new values flow on the
        next narration tick.
        """
        if not _rate_limit_check(state, "config_reload", 2.0):
            return JSONResponse({"error": "rate limited"}, status_code=429)
        from claude_code_talker.config import load_full_config
        try:
            new_cfg = load_full_config()
        except Exception as e:
            return JSONResponse({"error": f"reload failed: {e}"}, status_code=500)
        # Mutate in place so all callers holding a ref to state.cfg see the new values.
        state.cfg.clear()
        state.cfg.update(new_cfg)
        for s in state.sessions.list_active():
            state.sessions.invalidate(s.session_id)
        return JSONResponse({"reloaded": True, "key_count": len(state.cfg)})

    async def bulk_session_op(request: Request) -> JSONResponse:
        """Phase 11: bulk operations on sessions matching a filter.

        Body: {"action": "disable"|"enable", "filter": {"project_slug": str}}
        Writes to PersistentSessionStore so changes survive restart.
        """
        try:
            body = await _read_json(request)
        except ValueError as e:
            return _bad_request(str(e))
        action = body.get("action")
        if action not in ("disable", "enable"):
            return _bad_request("action must be 'disable' or 'enable'")
        flt = body.get("filter") or {}
        if not isinstance(flt, dict):
            return _bad_request("filter must be a JSON object")
        project_slug = flt.get("project_slug")
        if not project_slug or not isinstance(project_slug, str):
            return _bad_request("filter.project_slug is required")
        if state.catalog is None or state.persistent_sessions is None:
            return _bad_request("catalog or persistent store unavailable")
        targets = state.catalog.entries_for_project(project_slug)
        new_enabled = (action == "enable")
        modified = 0
        import time as _t
        for entry in targets:
            sid = entry.session_id
            current = state.persistent_sessions.get(sid) or {
                "live_overlay": {}, "attached_profile": None, "enabled": True,
                "display_name": None, "last_modified": 0.0,
            }
            if current.get("enabled") != new_enabled:
                current["enabled"] = new_enabled
                current["last_modified"] = _t.time()
                state.persistent_sessions.save(sid, current)
                # If the session is currently live, also flip the in-memory state.
                live = state.sessions.get(sid)
                if live is not None:
                    live.enabled = new_enabled
                modified += 1
        return JSONResponse({
            "action": action, "project_slug": project_slug,
            "matched": len(targets), "modified": modified,
        })

    async def chat_with_session(request: Request) -> JSONResponse:
        """Phase 9: ask the LLM a question about a session.

        Body: {"question": str, "narrate": bool (optional), "max_tokens": int (optional)}
        Picks the provider/model from cfg.modes.live (same as live narration).
        Honors teacher_mode (global + per-session overlay).
        """
        sid = request.path_params["session_id"]
        if not is_valid_session_id(sid):
            return _bad_request(f"invalid session_id: {sid!r}")
        try:
            body = await _read_json(request)
        except ValueError as e:
            return _bad_request(str(e))
        question = (body.get("question") or "").strip()
        if not question:
            return _bad_request("question must be a non-empty string")
        narrate = bool(body.get("narrate", False))
        max_tokens = int(body.get("max_tokens", 400))

        from claude_code_talker.chat_panel import gather_session_context, answer_question
        from pathlib import Path as _P
        s = state.sessions.get(sid)
        # Pull resolved cfg so per-session teacher_mode wins
        try:
            cfg = state.sessions.config_for(sid)
        except Exception:
            cfg = state.cfg
        teacher_cfg = cfg.get("teacher_mode")
        # Pick provider — same logic as live mode
        from claude_code_talker.server import _select_provider
        provider = _select_provider(state, "live")
        if provider is None:
            return JSONResponse({"error": "no LLM provider available"}, status_code=503)
        # Gather context
        transcript_path = None
        events = []
        if s is not None and s.transcript_path:
            transcript_path = _P(s.transcript_path)
        elif state.catalog is not None:
            entry = state.catalog.entry_for(sid)
            if entry is not None:
                transcript_path = entry.transcript_path
        if state.event_buffer is not None:
            events = state.event_buffer.recent(40)
        ctx = gather_session_context(
            transcript_path=transcript_path, events=events,
        )
        answer = await answer_question(
            question=question, context=ctx, provider=provider,
            teacher_cfg=teacher_cfg, max_tokens=max_tokens,
        )
        result = {"answer": answer, "session_id": sid}
        # Optionally narrate the response
        if narrate and answer and not answer.startswith("(provider error"):
            from claude_code_talker.audio import AudioJob
            voice_cfg = cfg.get("voice") or {}
            engine_name = voice_cfg.get("engine", "piper")
            engine = state.engines.get(engine_name)
            voice = voice_cfg.get("model")
            if engine is not None and voice:
                state.audio_queue.submit(AudioJob(
                    text=answer,
                    voice=voice,
                    rate=float(voice_cfg.get("rate", 1.0)),
                    engine_name=engine_name,
                    audio_format=getattr(engine, "audio_format", "wav"),
                    session_id=sid or "",
                ))
                result["narrated"] = True
        return JSONResponse(result)

    async def get_teacher(request: Request) -> JSONResponse:
        """Return the global teacher_mode cfg block (with defaults filled in)."""
        from claude_code_talker.teacher_mode import DEFAULT_TEACHER_CONFIG
        current = state.cfg.get("teacher_mode") or {}
        merged = {**DEFAULT_TEACHER_CONFIG, **current}
        return JSONResponse(merged)

    async def put_teacher(request: Request) -> JSONResponse:
        """Update the global teacher_mode cfg block. Per-session overrides set
        via the existing /api/sessions/<sid>/overlay endpoint with key
        'teacher_mode'.

        Accepts: enabled, depth_level (1-5), substitution, glossary, reframe,
        verbosity (concise|standard|expanded), granularity (combined|per-file).
        """
        try:
            body = await _read_json(request)
        except ValueError as e:
            return _bad_request(str(e))
        for key in ("enabled", "substitution", "glossary", "reframe"):
            if key in body and not isinstance(body[key], bool):
                return _bad_request(f"{key} must be a boolean")
        if "depth_level" in body:
            try:
                depth = int(body["depth_level"])
            except (TypeError, ValueError):
                return _bad_request("depth_level must be an integer 1-5")
            if not 1 <= depth <= 5:
                return _bad_request("depth_level must be 1-5")
            body["depth_level"] = depth
        if "verbosity" in body and body["verbosity"] not in ("concise", "standard", "expanded"):
            return _bad_request("verbosity must be concise/standard/expanded")
        if "granularity" in body and body["granularity"] not in ("combined", "per-file"):
            return _bad_request("granularity must be combined/per-file")
        current = state.cfg.get("teacher_mode") or {}
        current.update({k: v for k, v in body.items()
                       if k in ("enabled", "depth_level", "substitution",
                                "glossary", "reframe", "verbosity", "granularity")})
        state.cfg["teacher_mode"] = current
        # Persist to overlay so it survives daemon restart.
        try:
            import yaml as _yaml
            from pathlib import Path as _P
            p = _P.home() / ".claude" / "scripts" / "codetalker" / "cfg-overlay.yaml"
            p.parent.mkdir(parents=True, exist_ok=True)
            existing = {}
            if p.exists():
                try:
                    existing = _yaml.safe_load(p.read_text(encoding="utf-8")) or {}
                except Exception:
                    existing = {}
            if not isinstance(existing, dict):
                existing = {}
            existing["teacher_mode"] = current
            p.write_text(_yaml.safe_dump(existing, sort_keys=True), encoding="utf-8")
        except Exception:
            pass
        # Invalidate per-session cached cfgs so the new teacher block flows.
        for s in state.sessions.list_active():
            state.sessions.invalidate(s.session_id)
        return JSONResponse(current)

    async def put_llm_default(request: Request) -> JSONResponse:
        """Set the default LLM provider + model for narration AND chat.

        Body: {"provider": "openrouter", "model": "google/gemini-2.0-flash-001"}

        Optional field: "mode" — if provided, only update that specific mode's
        provider+model (one of "live", "brief", "chat", "prompt-brief").
        If omitted, updates ALL of live/brief (existing behavior).

        Updates:
          - state.cfg.providers.<provider>.model — model chosen for that provider
          - state.cfg.modes.<mode>.{provider, model} — per-mode overrides
          - the live provider instance's model attribute (immediate effect, all-modes only)
          - per-session resolved cfg caches are invalidated

        Daemon restart reverts to whatever's in cfg on disk; for permanent
        changes also edit ~/.claude/scripts/tts_config.yaml or call
        /api/config/reload after editing.
        """
        try:
            body = await _read_json(request)
        except ValueError as e:
            return _bad_request(str(e))
        provider = body.get("provider")
        model = body.get("model")
        mode_scope = body.get("mode")  # optional — None = all modes
        if not provider or not isinstance(provider, str):
            return _bad_request("provider is required")
        if not model or not isinstance(model, str):
            return _bad_request("model is required")
        if provider not in (state.providers or {}):
            return _bad_request(f"provider '{provider}' not registered (check API key, then restart daemon)")
        if mode_scope is not None and not isinstance(mode_scope, str):
            return _bad_request("mode must be a string or omitted")
        cfg_providers = state.cfg.setdefault("providers", {})
        cfg_providers.setdefault(provider, {})["model"] = model
        cfg_modes = state.cfg.setdefault("modes", {})

        if mode_scope:
            # Per-mode: only update that mode's provider and model
            cfg_modes.setdefault(mode_scope, {})["provider"] = provider
            cfg_modes.setdefault(mode_scope, {})["model"] = model
            updated_modes = [mode_scope]
        else:
            # All-modes (existing behavior): update live + brief
            # CRITICAL: also flip which provider live/brief modes use, otherwise
            # _select_provider keeps falling back to ollama and live narration
            # silently 404s when the user expected OpenRouter / OpenAI / Anthropic.
            cfg_modes.setdefault("live", {})["provider"] = provider
            cfg_modes.setdefault("brief", {})["provider"] = provider
            updated_modes = ["live", "brief"]
            # Update live provider instance's model attribute so the change takes
            # effect immediately for in-flight calls.
            prov_obj = (state.providers or {}).get(provider)
            if prov_obj is not None and hasattr(prov_obj, "model"):
                prov_obj.model = model

        # Re-bind LiveMode + BriefMode to the new provider instance so future
        # narrations use it (don't keep using the old ollama instance).
        if hasattr(state, "modes") and state.modes:
            from claude_code_talker.server import _select_provider
            new_prov = _select_provider(state, "live")
            if state.modes.get("live") is not None:
                state.modes["live"].provider = new_prov
            new_prov_brief = _select_provider(state, "brief")
            if state.modes.get("brief") is not None:
                state.modes["brief"].provider = new_prov_brief
            if state.modes.get("teacher") is not None:
                state.modes["teacher"].provider = new_prov_brief
        # Invalidate per-session caches so resolved cfg picks up the new values.
        for s in state.sessions.list_active():
            state.sessions.invalidate(s.session_id)
        # Persist to disk so the change survives daemon restart.
        _persist_default_provider(provider, model, mode=mode_scope)
        result: dict = {
            "saved": True, "provider": provider, "model": model,
            "updated_modes": updated_modes,
            "persisted": True,
        }
        if not mode_scope:
            result["live_uses"] = provider
            result["brief_uses"] = provider
        return JSONResponse(result)

    async def refresh_openrouter_models(request: Request) -> JSONResponse:
        """Fetch fresh model list from OpenRouter's public /models endpoint.

        Cached for the daemon's lifetime once fetched (call again to refresh).
        Doesn't require an API key — the OpenRouter /models endpoint is public.
        """
        if not _rate_limit_check(state, "openrouter_refresh", 30.0):
            return JSONResponse({"error": "rate limited (1 refresh per 30s)"}, status_code=429)
        import httpx
        try:
            async with httpx.AsyncClient(timeout=10.0) as c:
                r = await c.get("https://openrouter.ai/api/v1/models")
                r.raise_for_status()
                payload = r.json()
        except (httpx.HTTPError, ValueError) as e:
            return JSONResponse({"error": f"openrouter fetch failed: {e}"}, status_code=502)
        data = payload.get("data") or []
        models = []
        for m in data:
            mid = m.get("id")
            if not isinstance(mid, str):
                continue
            pricing = m.get("pricing") or {}
            try:
                prompt_price = float(pricing.get("prompt", 0))
                comp_price = float(pricing.get("completion", 0))
            except (TypeError, ValueError):
                prompt_price = comp_price = 0.0
            # Tier classification: 'cheap' if both <= $1/M tokens, else 'mid'/'premium'.
            per_million_in = prompt_price * 1_000_000
            per_million_out = comp_price * 1_000_000
            if per_million_in <= 1.0 and per_million_out <= 5.0:
                tier = "cheap"
            elif per_million_in <= 5.0 and per_million_out <= 15.0:
                tier = "mid"
            else:
                tier = "premium"
            models.append({
                "id": mid,
                "label": f"{mid} (${per_million_in:.2f}/$ {per_million_out:.2f}/M)",
                "tier": tier,
                "prompt_per_million": per_million_in,
                "completion_per_million": per_million_out,
            })
        # Sort cheap first
        tier_order = {"cheap": 0, "mid": 1, "premium": 2}
        models.sort(key=lambda m: (tier_order.get(m["tier"], 3), m["prompt_per_million"]))
        _openrouter_models_cache["data"] = models
        import time as _t
        _openrouter_models_cache["fetched_at"] = _t.time()
        return JSONResponse({"refreshed": True, "model_count": len(models)})

    async def virtual_eval_run(request: Request) -> JSONResponse:
        """Phase-13: kick off a virtual user eval and return the report."""
        if not _rate_limit_check(state, "virtual_eval_run", 10.0):
            return JSONResponse({"error": "rate limited (1 run per 10s)"}, status_code=429)
        from claude_code_talker.virtual_eval import run_eval as _run
        from pathlib import Path as _P
        from claude_code_talker.server import _select_provider
        provider = _select_provider(state, "live")
        if provider is None:
            return JSONResponse({"error": "no LLM provider available"}, status_code=503)
        current_teacher_cfg = state.cfg.get("teacher_mode") or {}
        deployed_at = float((state.cfg.get("virtual_eval") or {}).get("deployed_at", 0.0))
        max_narrations = int((state.cfg.get("virtual_eval") or {}).get("max_narrations", 50))
        overlay_path = _P.home() / ".claude" / "scripts" / "codetalker" / "cfg-overlay.yaml"
        try:
            report = await _run(
                narration_log=state.narration_log, history=state.tuning_history,
                current_cfg=current_teacher_cfg, provider=provider,
                overlay_path=overlay_path, catalog=state.catalog,
                deployed_at=deployed_at, max_narrations=max_narrations,
            )
        except Exception as e:
            return JSONResponse({"error": f"eval failed: {e}"}, status_code=500)
        state.virtual_eval_latest = report
        if report.get("applied"):
            state.cfg.setdefault("teacher_mode", {}).update(
                report["proposal"]["fields_to_set"]
            )
            for s in state.sessions.list_active():
                state.sessions.invalidate(s.session_id)
        return JSONResponse(report)

    async def virtual_eval_latest(request: Request) -> JSONResponse:
        return JSONResponse({"latest": getattr(state, "virtual_eval_latest", None)})

    async def virtual_eval_history(request: Request) -> JSONResponse:
        if state.tuning_history is None:
            return JSONResponse([])
        from dataclasses import asdict
        entries = state.tuning_history.list_all()
        return JSONResponse([asdict(e) for e in entries])

    async def virtual_eval_revert(request: Request) -> JSONResponse:
        from claude_code_talker.virtual_eval import revert_tuning
        from pathlib import Path as _P
        entry_id = request.path_params["entry_id"]
        overlay_path = _P.home() / ".claude" / "scripts" / "codetalker" / "cfg-overlay.yaml"
        ok = revert_tuning(history=state.tuning_history, entry_id=entry_id, overlay_path=overlay_path)
        if not ok:
            return _not_found(f"tuning entry not found or not applied: {entry_id}")
        for s in state.sessions.list_active():
            state.sessions.invalidate(s.session_id)
        return JSONResponse({"reverted": True})

    # -----------------------------------------------------------------
    # Phase 14 v0.4.0 — Voice clone / CRUD endpoints
    # -----------------------------------------------------------------

    def _voices_refs_dir() -> Path:
        """Return the references dir, from cfg if set, else default."""
        xtts_cfg = (state.cfg.get("engines") or {}).get("xtts") or {}
        configured = xtts_cfg.get("references_dir") or None
        return Path(configured) if configured else _VOICES_REFS_DEFAULT

    def _voice_info(name: str, refs_dir: Path) -> dict:
        """Build the per-voice dict for GET /api/voices responses."""
        from claude_code_talker.voices.metadata import read_metadata
        import dataclasses
        wav = refs_dir / f"{name}.wav"
        face_frame = refs_dir / f"{name}-frame.jpg"
        avatar_glb = refs_dir / f"{name}.glb"
        duration_s: float | None = None
        try:
            import wave
            with wave.open(str(wav), "rb") as wf:
                duration_s = wf.getnframes() / max(wf.getframerate(), 1)
        except Exception:
            pass
        meta = read_metadata(refs_dir, name)
        return {
            "name": name,
            "duration_s": duration_s,
            "has_face_frame": face_frame.exists(),
            "has_avatar": avatar_glb.exists(),
            "metadata": dataclasses.asdict(meta) if meta else None,
        }

    async def voices_list(request: Request) -> JSONResponse:
        """GET /api/voices/list — list all cloned XTTS voices with metadata."""
        refs_dir = _voices_refs_dir()
        if not refs_dir.exists():
            return JSONResponse({"voices": []})
        voices = []
        for wav in sorted(refs_dir.glob("*.wav")):
            voices.append(_voice_info(wav.stem, refs_dir))
        return JSONResponse({"voices": voices})

    async def voices_dependency_status(request: Request) -> JSONResponse:
        """GET /api/voices/dependency-status."""
        from claude_code_talker.voices.dependency_check import check_deps
        deps = check_deps()
        # yt_dlp is informational only in v0.4.0 — don't count it against all_present
        result = {
            "yt_dlp": deps.get("yt_dlp", False),
            "ffmpeg": deps.get("ffmpeg", False),
            "whisper": deps.get("whisper", False),
            "all_present": deps.get("ffmpeg", False) and deps.get("whisper", False),
            "install_hint": deps.get("install_hint", ""),
        }
        return JSONResponse(result)

    async def voices_install_dependencies(request: Request) -> JSONResponse:
        """POST /api/voices/install-dependencies — kick off background install."""
        from claude_code_talker.voices.auto_install import InstallTaskState, install_deps_async
        task_id = str(uuid.uuid4())
        task_state = InstallTaskState()
        state.voice_install_tasks[task_id] = task_state

        import asyncio
        asyncio.get_event_loop().create_task(install_deps_async(task_state))
        return JSONResponse({"task_id": task_id})

    async def voices_install_status(request: Request) -> JSONResponse:
        """GET /api/voices/install-status/<task_id>."""
        task_id = request.path_params["task_id"]
        task_state = state.voice_install_tasks.get(task_id)
        if task_state is None:
            return _not_found(f"task not found: {task_id}")
        import dataclasses
        return JSONResponse(dataclasses.asdict(task_state))

    async def voices_clone_from_file(request: Request) -> JSONResponse:
        """POST /api/voices/clone-from-file — multipart upload, audio or video."""
        from claude_code_talker.voices.clone import clone_from_local_file, extract_face_frame, _is_video
        from claude_code_talker.voices.metadata import new_metadata, write_metadata
        import dataclasses, tempfile

        form = await request.form()
        audio_field = form.get("audio")
        if audio_field is None:
            return _bad_request("multipart field 'audio' is required")

        name = (form.get("name") or "").strip()
        if not name:
            return _bad_request("form field 'name' is required")

        start_raw = form.get("start") or ""
        end_raw = form.get("end") or ""
        try:
            start = float(start_raw) if start_raw else None
            end = float(end_raw) if end_raw else None
        except ValueError:
            return _bad_request("'start' and 'end' must be numeric seconds")

        refs_dir = _voices_refs_dir()

        # Write uploaded file to a temp location
        suffix = Path(getattr(audio_field, "filename", "") or "upload.wav").suffix or ".wav"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp_f:
            tmp_path = Path(tmp_f.name)
            content = await audio_field.read()
            tmp_f.write(content)

        try:
            voice_path = await clone_from_local_file(
                tmp_path,
                name=name,
                references_dir=refs_dir,
                start=start,
                end=end,
            )
        except (RuntimeError, ValueError) as exc:
            tmp_path.unlink(missing_ok=True)
            return JSONResponse({"error": str(exc)}, status_code=422)
        except Exception as exc:
            tmp_path.unlink(missing_ok=True)
            return JSONResponse({"error": f"clone failed: {exc}"}, status_code=500)

        # Extract face frame for video sources
        safe_name = voice_path.stem
        face_frame_path: Path | None = None
        is_vid = _is_video(tmp_path)
        if is_vid:
            frame_out = refs_dir / f"{safe_name}-frame.jpg"
            midpoint = ((start or 0.0) + (end or 0.0)) / 2 if (start or end) else 0.0
            face_frame_path = await extract_face_frame(tmp_path, frame_out, at_seconds=midpoint)

        tmp_path.unlink(missing_ok=True)

        # Write metadata sidecar
        meta = new_metadata(
            safe_name,
            source_path=getattr(audio_field, "filename", "") or "",
            source_type="video" if is_vid else "audio",
            clip_start=start or 0.0,
            clip_end=end or 0.0,
        )
        write_metadata(refs_dir, meta)

        return JSONResponse({
            "name": safe_name,
            "voice_path": str(voice_path),
            "face_frame_path": str(face_frame_path) if face_frame_path else None,
            "metadata": dataclasses.asdict(meta),
        })

    async def voices_preview_extract(request: Request) -> JSONResponse:
        """POST /api/voices/preview-extract — transcribe a local file for the preview wizard."""
        from claude_code_talker.voices.transcribe import transcribe_audio
        import dataclasses, shutil, tempfile

        try:
            body = await _read_json(request)
        except ValueError as exc:
            return _bad_request(str(exc))
        source_path_str = body.get("source_path") or ""
        if not source_path_str:
            return _bad_request("'source_path' is required")

        source_path = Path(source_path_str)
        if not source_path.exists():
            return _not_found(f"file not found: {source_path_str}")

        # Copy audio to a tmp WAV for whisper (ffmpeg extracts audio)
        token = str(uuid.uuid4())
        tmp_wav = Path(tempfile.gettempdir()) / f"preview-{token}.wav"
        try:
            # Use ffmpeg to extract/convert to wav so whisper can process
            import asyncio, sys
            ffmpeg_exe = "ffmpeg.exe" if sys.platform == "win32" else "ffmpeg"
            proc = await asyncio.create_subprocess_exec(
                ffmpeg_exe, "-y", "-i", str(source_path),
                "-ac", "1", "-ar", "16000", str(tmp_wav),
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            )
            await proc.communicate()
        except Exception as exc:
            return JSONResponse({"error": f"audio extraction failed: {exc}"}, status_code=500)

        try:
            segments = await transcribe_audio(tmp_wav)
        except Exception as exc:
            tmp_wav.unlink(missing_ok=True)
            return JSONResponse({"error": f"transcription failed: {exc}"}, status_code=500)

        # Store the tmp wav keyed by token so preview-audio can serve it
        state.voice_preview_audio[token] = tmp_wav

        return JSONResponse({
            "token": token,
            "audio_url": f"/api/voices/preview-audio/{token}",
            "segments": [dataclasses.asdict(s) for s in segments],
        })

    async def voices_preview_audio(request: Request) -> Response:
        """GET /api/voices/preview-audio/<token> — serve the extracted preview WAV."""
        token = request.path_params["token"]
        wav_path = state.voice_preview_audio.get(token)
        if wav_path is None or not wav_path.exists():
            return _not_found(f"preview token not found: {token}")
        # NOTE: TTL/cleanup of tmp files is deferred to v1; files live until daemon restarts.
        return Response(
            content=wav_path.read_bytes(),
            media_type="audio/wav",
        )

    async def voices_clone_from_preview(request: Request) -> JSONResponse:
        """POST /api/voices/clone-from-preview — clip an already-extracted preview WAV."""
        from claude_code_talker.voices.clone import clone_from_local_file
        from claude_code_talker.voices.metadata import new_metadata, write_metadata
        import dataclasses

        try:
            body = await _read_json(request)
        except ValueError as exc:
            return _bad_request(str(exc))

        token = body.get("token") or ""
        name = (body.get("name") or "").strip()
        if not token:
            return _bad_request("'token' is required")
        if not name:
            return _bad_request("'name' is required")

        wav_path = state.voice_preview_audio.get(token)
        if wav_path is None or not wav_path.exists():
            return _not_found(f"preview token not found: {token}")

        start_raw = body.get("start")
        end_raw = body.get("end")
        start = float(start_raw) if start_raw is not None else None
        end = float(end_raw) if end_raw is not None else None

        refs_dir = _voices_refs_dir()
        try:
            voice_path = await clone_from_local_file(
                wav_path, name=name, references_dir=refs_dir, start=start, end=end
            )
        except (RuntimeError, ValueError) as exc:
            return JSONResponse({"error": str(exc)}, status_code=422)
        except Exception as exc:
            return JSONResponse({"error": f"clone failed: {exc}"}, status_code=500)

        safe_name = voice_path.stem
        meta = new_metadata(safe_name, source_type="audio", clip_start=start or 0.0, clip_end=end or 0.0)
        write_metadata(refs_dir, meta)

        return JSONResponse({
            "name": safe_name,
            "voice_path": str(voice_path),
            "metadata": dataclasses.asdict(meta),
        })

    async def voices_preview_voice(request: Request) -> Response:
        """POST /api/voices/preview/<name> — synthesise a short XTTS preview."""
        name = request.path_params["name"]
        engine = state.engines.get("xtts")
        if engine is None:
            return JSONResponse({"error": "xtts engine unavailable"}, status_code=503)
        try:
            audio_bytes = await engine.synthesise(
                f"Hello, this is a preview of {name}.", voice=name
            )
        except Exception as exc:
            return JSONResponse({"error": f"synthesis failed: {exc}"}, status_code=500)
        return Response(content=audio_bytes, media_type="audio/wav")

    # ---------------- Piper voice manager (v0.1.x) ----------------
    # Curated subset of rhasspy/piper-voices. The full HuggingFace catalog
    # has 100+ voices across many languages; this list intentionally stays
    # small and English-focused as a starter set. Users who want more can
    # drop .onnx + .onnx.json into the voices dir manually.
    _PIPER_CATALOG = [
        {"name": "en_US-amy-medium",                        "lang": "en_US", "speaker": "amy",                        "gender": "female", "quality": "medium", "size_mb": 63},
        {"name": "en_US-danny-low",                         "lang": "en_US", "speaker": "danny",                      "gender": "male",   "quality": "low",    "size_mb": 23},
        {"name": "en_US-hfc_female-medium",                 "lang": "en_US", "speaker": "hfc_female",                 "gender": "female", "quality": "medium", "size_mb": 63},
        {"name": "en_US-hfc_male-medium",                   "lang": "en_US", "speaker": "hfc_male",                   "gender": "male",   "quality": "medium", "size_mb": 63},
        {"name": "en_US-joe-medium",                        "lang": "en_US", "speaker": "joe",                        "gender": "male",   "quality": "medium", "size_mb": 63},
        {"name": "en_US-kristin-medium",                    "lang": "en_US", "speaker": "kristin",                    "gender": "female", "quality": "medium", "size_mb": 63},
        {"name": "en_US-lessac-medium",                     "lang": "en_US", "speaker": "lessac",                     "gender": "female", "quality": "medium", "size_mb": 63},
        {"name": "en_US-ryan-high",                         "lang": "en_US", "speaker": "ryan",                       "gender": "male",   "quality": "high",   "size_mb": 110},
        {"name": "en_GB-alan-medium",                       "lang": "en_GB", "speaker": "alan",                       "gender": "male",   "quality": "medium", "size_mb": 63},
        {"name": "en_GB-cori-medium",                       "lang": "en_GB", "speaker": "cori",                       "gender": "female", "quality": "medium", "size_mb": 63},
        {"name": "en_GB-jenny_dioco-medium",                "lang": "en_GB", "speaker": "jenny_dioco",                "gender": "female", "quality": "medium", "size_mb": 63},
        {"name": "en_GB-northern_english_male-medium",      "lang": "en_GB", "speaker": "northern_english_male",      "gender": "male",   "quality": "medium", "size_mb": 63},
    ]

    def _piper_voice_url(name: str, ext: str) -> str:
        """Build the rhasspy/piper-voices HuggingFace download URL for a
        voice file. Voice names follow `<lang_locale>-<speaker>-<quality>`
        and live at `<lang_short>/<lang_locale>/<speaker>/<quality>/<name><ext>`
        in the repo."""
        parts = name.split("-")
        if len(parts) < 3:
            raise ValueError(f"invalid piper voice name: {name}")
        lang_locale = parts[0]
        quality = parts[-1]
        speaker = "-".join(parts[1:-1])
        lang_short = lang_locale.split("_")[0]
        return f"https://huggingface.co/rhasspy/piper-voices/resolve/main/{lang_short}/{lang_locale}/{speaker}/{quality}/{name}{ext}"

    def _piper_voices_dir() -> "Path":
        from pathlib import Path
        return Path.home() / ".claude" / "scripts" / "piper" / "voices"

    async def piper_catalog(request: Request) -> JSONResponse:
        """GET /api/piper/catalog — curated list of installable piper voices.

        Each entry is annotated with `installed: bool` so the UI can render
        installed vs available without a second roundtrip."""
        voices_dir = _piper_voices_dir()
        installed: set[str] = set()
        if voices_dir.exists():
            installed = {p.stem for p in voices_dir.glob("*.onnx")}
        out = [{**v, "installed": v["name"] in installed} for v in _PIPER_CATALOG]
        # Also surface voices on disk that AREN'T in the curated catalog so
        # the UI doesn't hide them. They get a `curated: false` marker.
        catalog_names = {v["name"] for v in _PIPER_CATALOG}
        for name in installed - catalog_names:
            out.append({
                "name": name, "lang": "", "speaker": "", "gender": "",
                "quality": "", "size_mb": 0, "installed": True, "curated": False,
            })
        for entry in out:
            entry.setdefault("curated", True)
        return JSONResponse(out)

    async def piper_install(request: Request) -> JSONResponse:
        """POST /api/piper/install body={"name": "..."} — download voice
        files from HuggingFace into the local voices dir. Runs the network
        I/O in a thread so the event loop stays responsive (each file is
        20-110 MB)."""
        try:
            body = await request.json()
        except (json.JSONDecodeError, ValueError):
            return _bad_request("invalid JSON")
        if not isinstance(body, dict):
            return _bad_request("body must be a JSON object")
        name = (body.get("name") or "").strip()
        if not name:
            return _bad_request("'name' is required")
        if name not in {v["name"] for v in _PIPER_CATALOG}:
            return _bad_request(f"voice not in catalog: {name}")
        voices_dir = _piper_voices_dir()
        voices_dir.mkdir(parents=True, exist_ok=True)

        def _download() -> tuple[bool, str]:
            import urllib.request
            try:
                for ext in (".onnx", ".onnx.json"):
                    url = _piper_voice_url(name, ext)
                    dst = voices_dir / f"{name}{ext}"
                    with urllib.request.urlopen(url, timeout=120) as r:
                        dst.write_bytes(r.read())
                return True, ""
            except Exception as exc:
                return False, str(exc)

        ok, err = await asyncio.to_thread(_download)
        if not ok:
            return JSONResponse({"error": f"download failed: {err}"}, status_code=502)
        return JSONResponse({"installed": name})

    async def piper_uninstall(request: Request) -> JSONResponse:
        """DELETE /api/piper/voices/{name} — remove voice files from disk."""
        name = request.path_params.get("name", "")
        voices_dir = _piper_voices_dir()
        onnx = voices_dir / f"{name}.onnx"
        cfg = voices_dir / f"{name}.onnx.json"
        if not onnx.exists() and not cfg.exists():
            return _not_found(f"voice not installed: {name}")
        for p in (onnx, cfg):
            if p.exists():
                try:
                    p.unlink()
                except OSError as exc:
                    return JSONResponse({"error": str(exc)}, status_code=500)
        return JSONResponse({"uninstalled": name})

    async def piper_preview(request: Request) -> Response:
        """POST /api/piper/preview/{name} — synthesise a short sample via
        piper and play it on the desktop. Returns the wav bytes so the
        caller can also play in-browser if desired."""
        name = request.path_params.get("name", "")
        engine = state.engines.get("piper")
        if engine is None:
            return JSONResponse({"error": "piper engine unavailable"}, status_code=503)
        if name not in engine.list_voices():
            return _not_found(f"voice not installed: {name}")
        text = f"Hello, this is a sample of the {name} voice."

        def _synth() -> bytes:
            return engine.synthesize(text, name, 1.0)

        try:
            wav = await asyncio.to_thread(_synth)
        except Exception as exc:
            return JSONResponse({"error": f"synthesis failed: {exc}"}, status_code=500)
        # Best-effort desktop playback — don't fail the response if the
        # audio handle isn't available (e.g. headless server).
        try:
            from claude_code_talker.audio import play_audio_bytes
            await asyncio.to_thread(play_audio_bytes, wav, "wav")
        except Exception:
            pass
        return Response(content=wav, media_type="audio/wav")

    async def voices_rename(request: Request) -> JSONResponse:
        """PATCH /api/voices/<name> — rename a voice (WAV + metadata sidecar)."""
        from claude_code_talker.voices.metadata import read_metadata, write_metadata
        import dataclasses, shutil

        old_name = request.path_params["name"]
        try:
            body = await _read_json(request)
        except ValueError as exc:
            return _bad_request(str(exc))
        new_name = (body.get("new_name") or "").strip()
        if not new_name:
            return _bad_request("'new_name' is required")

        refs_dir = _voices_refs_dir()
        old_wav = refs_dir / f"{old_name}.wav"
        if not old_wav.exists():
            return _not_found(f"voice not found: {old_name}")

        new_wav = refs_dir / f"{new_name}.wav"
        if new_wav.exists():
            return JSONResponse({"error": f"voice already exists: {new_name}"}, status_code=409)

        old_wav.rename(new_wav)

        # Move sidecar + face frame if present
        old_json = refs_dir / f"{old_name}.json"
        if old_json.exists():
            new_json = refs_dir / f"{new_name}.json"
            old_json.rename(new_json)
            # Update the name field inside the sidecar
            meta = read_metadata(refs_dir, new_name)
            if meta:
                meta.name = new_name
                write_metadata(refs_dir, meta)

        old_frame = refs_dir / f"{old_name}-frame.jpg"
        if old_frame.exists():
            old_frame.rename(refs_dir / f"{new_name}-frame.jpg")

        old_glb = refs_dir / f"{old_name}.glb"
        if old_glb.exists():
            old_glb.rename(refs_dir / f"{new_name}.glb")

        return JSONResponse({"old_name": old_name, "new_name": new_name})

    async def voices_replace_source(request: Request) -> JSONResponse:
        """POST /api/voices/<name>/replace-source — re-clone an existing voice slot."""
        from claude_code_talker.voices.clone import clone_from_local_file, _is_video, extract_face_frame
        from claude_code_talker.voices.metadata import update_metadata
        import dataclasses, tempfile

        name = request.path_params["name"]
        refs_dir = _voices_refs_dir()
        old_wav = refs_dir / f"{name}.wav"
        if not old_wav.exists():
            return _not_found(f"voice not found: {name}")

        form = await request.form()
        audio_field = form.get("audio")
        if audio_field is None:
            return _bad_request("multipart field 'audio' is required")

        start_raw = form.get("start") or ""
        end_raw = form.get("end") or ""
        try:
            start = float(start_raw) if start_raw else None
            end = float(end_raw) if end_raw else None
        except ValueError:
            return _bad_request("'start' and 'end' must be numeric seconds")

        suffix = Path(getattr(audio_field, "filename", "") or "upload.wav").suffix or ".wav"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp_f:
            tmp_path = Path(tmp_f.name)
            content = await audio_field.read()
            tmp_f.write(content)

        # Delete the existing WAV so clone_from_local_file doesn't collision-resolve the name
        old_wav.unlink(missing_ok=True)

        try:
            voice_path = await clone_from_local_file(
                tmp_path, name=name, references_dir=refs_dir, start=start, end=end
            )
        except Exception as exc:
            tmp_path.unlink(missing_ok=True)
            return JSONResponse({"error": f"replace failed: {exc}"}, status_code=500)

        is_vid = _is_video(tmp_path)
        if is_vid:
            frame_out = refs_dir / f"{name}-frame.jpg"
            midpoint = ((start or 0.0) + (end or 0.0)) / 2 if (start or end) else 0.0
            await extract_face_frame(tmp_path, frame_out, at_seconds=midpoint)

        tmp_path.unlink(missing_ok=True)

        meta = update_metadata(
            refs_dir, name,
            source_path=getattr(audio_field, "filename", "") or "",
            source_type="video" if is_vid else "audio",
            clip_start=start or 0.0,
            clip_end=end or 0.0,
        )

        return JSONResponse({
            "name": name,
            "voice_path": str(voice_path),
            "metadata": dataclasses.asdict(meta),
        })

    async def voices_delete(request: Request) -> JSONResponse:
        """DELETE /api/voices/<name> — remove all files for a voice."""
        name = request.path_params["name"]
        refs_dir = _voices_refs_dir()
        old_wav = refs_dir / f"{name}.wav"
        if not old_wav.exists():
            return _not_found(f"voice not found: {name}")

        old_wav.unlink(missing_ok=True)
        (refs_dir / f"{name}.json").unlink(missing_ok=True)
        (refs_dir / f"{name}-frame.jpg").unlink(missing_ok=True)
        (refs_dir / f"{name}.glb").unlink(missing_ok=True)

        return JSONResponse({"deleted": True})

    # -----------------------------------------------------------------
    # v0.1.0 unification — fleet audio-routing defaults endpoint.
    # Provides the third "obvious toggle" called out in the unification
    # spec: a global default that applies to sessions without an explicit
    # `audio_outputs` override. Backed by `companion_suppress_desktop`
    # in cfg-overlay (the single fleet flag `_resolve_audio_outputs`
    # honors). When True the default becomes {phone, glasses}; when
    # False it's {desktop, phone, glasses}.
    # -----------------------------------------------------------------

    async def audio_defaults_get(request: Request) -> JSONResponse:
        """GET /api/cfg/audio-defaults — current fleet default."""
        suppress = bool(state.cfg.get("companion_suppress_desktop", False))
        return JSONResponse(
            {
                "companion_suppress_desktop": suppress,
                "default_outputs": ["phone", "glasses"]
                if suppress
                else ["desktop", "phone", "glasses"],
            }
        )

    async def audio_defaults_put(request: Request) -> JSONResponse:
        """PUT /api/cfg/audio-defaults — update the fleet default.

        Body: {"companion_suppress_desktop": bool}. Mirrors the value
        into in-memory cfg (so it takes effect immediately without
        daemon restart) and persists to cfg-overlay so it survives
        the next restart.
        """
        try:
            body = await _read_json(request)
        except ValueError as e:
            return _bad_request(str(e))
        if "companion_suppress_desktop" not in body:
            return _bad_request("missing 'companion_suppress_desktop'")
        suppress = bool(body["companion_suppress_desktop"])
        state.cfg["companion_suppress_desktop"] = suppress
        overlay = _read_overlay()
        overlay["companion_suppress_desktop"] = suppress
        _write_overlay(overlay)
        return JSONResponse({"ok": True, "companion_suppress_desktop": suppress})

    # -----------------------------------------------------------------
    # Phase 14.5 — Trigger-mode configuration + tag CRUD endpoints
    # -----------------------------------------------------------------

    async def triggers_get_config(request: Request) -> JSONResponse:
        """GET /api/triggers/config — current trigger mode settings."""
        from claude_code_talker.triggers.skill import is_skill_installed
        trig = state.cfg.get("triggers") or {}
        return JSONResponse({
            "mode": trig.get("mode", state.cfg.get("live", {}).get("mode", "llm")),
            "teacher_level": trig.get("teacher_level", "standard"),
            "persona": trig.get("persona", "methodical"),
            "skill_installed": is_skill_installed(),
        })

    async def triggers_put_config(request: Request) -> JSONResponse:
        """PUT /api/triggers/config — update mode/teacher_level/persona."""
        try:
            body = await _read_json(request)
        except ValueError as e:
            return _bad_request(str(e))
        overlay = _read_overlay()
        trig_block = overlay.setdefault("triggers", {})
        for key in ("mode", "teacher_level", "persona"):
            if key in body:
                trig_block[key] = body[key]
        # Mirror mode into live.mode so the trigger handler reads it immediately
        if "mode" in body:
            overlay.setdefault("live", {})["mode"] = body["mode"]
            # Also update in-memory cfg so it takes effect without restart
            state.cfg.setdefault("live", {})["mode"] = body["mode"]
            state.cfg.setdefault("triggers", {})["mode"] = body["mode"]
        for key in ("teacher_level", "persona"):
            if key in body:
                state.cfg.setdefault("triggers", {})[key] = body[key]
        _write_overlay(overlay)
        # Invalidate per-session cfg caches
        for s in state.sessions.list_active():
            state.sessions.invalidate(s.session_id)
        return JSONResponse({"ok": True})

    def _get_tag_library():
        """Build a TagLibrary from current cfg state."""
        from claude_code_talker.triggers.tags import TagLibrary
        tags_cfg = (state.cfg.get("triggers") or {}).get("tags") or {}
        return TagLibrary.from_cfg(tags_cfg)

    def _save_tag_library(lib) -> None:
        """Persist the library's tags back to cfg-overlay and state.cfg."""
        overlay = _read_overlay()
        overlay.setdefault("triggers", {})["tags"] = lib.to_cfg()
        _write_overlay(overlay)
        # Reflect in live cfg so GET immediately returns updated state
        state.cfg.setdefault("triggers", {})["tags"] = lib.to_cfg()

    async def triggers_list_tags(request: Request) -> JSONResponse:
        """GET /api/triggers/tags — list all tags (id included as field)."""
        from dataclasses import asdict
        lib = _get_tag_library()
        tags = [{**asdict(t)} for t in lib.list()]
        return JSONResponse({"tags": tags})

    async def triggers_create_tag(request: Request) -> JSONResponse:
        """POST /api/triggers/tags — create a new tag."""
        from claude_code_talker.triggers.tags import Tag, TagLibrary
        from claude_code_talker.triggers.parser import normalize_tag_id
        from dataclasses import asdict
        try:
            body = await _read_json(request)
        except ValueError as e:
            return _bad_request(str(e))
        display_name = (body.get("display_name") or "").strip()
        if not display_name:
            return _bad_request("display_name is required and must be non-empty")
        tag_id = normalize_tag_id(display_name)
        lib = _get_tag_library()
        tag = Tag(
            id=tag_id,
            display_name=display_name,
            enabled=bool(body.get("enabled", False)),
            editor_mode=str(body.get("editor_mode", "structured")),
            when_to_trigger=str(body.get("when_to_trigger", "")),
            format_template=str(body.get("format_template", "")),
            example=str(body.get("example", "")),
            freeform_text=str(body.get("freeform_text", "")),
        )
        lib.add(tag)
        _save_tag_library(lib)
        return JSONResponse(asdict(tag))

    async def triggers_get_tag(request: Request) -> JSONResponse:
        """GET /api/triggers/tags/<id> — single tag."""
        from dataclasses import asdict
        tag_id = request.path_params["tag_id"]
        lib = _get_tag_library()
        tag = lib.get(tag_id)
        if tag is None:
            return _not_found(f"tag not found: {tag_id}")
        return JSONResponse(asdict(tag))

    async def triggers_put_tag(request: Request) -> JSONResponse:
        """PUT /api/triggers/tags/<id> — partial update."""
        from dataclasses import asdict
        tag_id = request.path_params["tag_id"]
        try:
            body = await _read_json(request)
        except ValueError as e:
            return _bad_request(str(e))
        lib = _get_tag_library()
        if lib.get(tag_id) is None:
            return _not_found(f"tag not found: {tag_id}")
        allowed = {"enabled", "editor_mode", "when_to_trigger", "format_template",
                   "example", "freeform_text", "display_name"}
        changes = {k: v for k, v in body.items() if k in allowed}
        updated = lib.update(tag_id, **changes)
        _save_tag_library(lib)
        return JSONResponse(asdict(updated))

    async def triggers_delete_tag(request: Request) -> JSONResponse:
        """DELETE /api/triggers/tags/<id> — remove tag."""
        tag_id = request.path_params["tag_id"]
        lib = _get_tag_library()
        deleted = lib.delete(tag_id)
        if not deleted:
            return _not_found(f"tag not found: {tag_id}")
        _save_tag_library(lib)
        return JSONResponse({"deleted": True})

    async def triggers_skill_install(request: Request) -> JSONResponse:
        """POST /api/triggers/skill-install — compose + write SKILL.md."""
        from claude_code_talker.triggers.tags import TagLibrary, compose_skill_content
        from claude_code_talker.triggers.skill import install_skill
        trig = state.cfg.get("triggers") or {}
        lib = TagLibrary.from_cfg(trig.get("tags") or {})
        content = compose_skill_content(
            lib,
            teacher_level=trig.get("teacher_level", "standard"),
            persona=trig.get("persona", "methodical"),
        )
        installed_path = install_skill(content)
        enabled_count = len(lib.enabled_ids())
        return JSONResponse({
            "installed_at": str(installed_path),
            "enabled_count": enabled_count,
        })

    async def triggers_skill_preview(request: Request) -> Response:
        """GET /api/triggers/skill-preview — composed SKILL.md text, no write."""
        from claude_code_talker.triggers.tags import TagLibrary, compose_skill_content
        trig = state.cfg.get("triggers") or {}
        lib = TagLibrary.from_cfg(trig.get("tags") or {})
        content = compose_skill_content(
            lib,
            teacher_level=trig.get("teacher_level", "standard"),
            persona=trig.get("persona", "methodical"),
        )
        return Response(content=content, media_type="text/plain")

    async def triggers_skill_body(request: Request) -> Response:
        """GET /api/triggers/skill-body — dynamic body only (trigger blocks + style guidance).

        Consumed by the Claude Code plugin's SKILL.md bash injection so the
        skill always reflects current cfg without a file write.
        """
        from claude_code_talker.triggers.tags import TagLibrary, compose_skill_body
        trig = state.cfg.get("triggers") or {}
        lib = TagLibrary.from_cfg(trig.get("tags") or {})
        content = compose_skill_body(
            lib,
            teacher_level=trig.get("teacher_level", "standard"),
            persona=trig.get("persona", "methodical"),
        )
        return Response(content=content, media_type="text/plain")

    # ------------------------------------------------------------------
    # Phase 26 — markup config endpoints
    # ------------------------------------------------------------------

    async def markup_config_get(request: Request) -> JSONResponse:
        """GET /api/markup/config — current per-form treatments.

        Returns the resolved treatment table for the active mode (preset
        overlaid with user values), keyed by form name with ``{kind, params}``.
        """
        from claude_code_talker.markup.forms import load_treatments
        treatments = load_treatments(state.cfg)
        body = {
            form: {"kind": t.kind, "params": dict(t.params)}
            for form, t in treatments.items()
        }
        return JSONResponse(body)

    async def markup_config_put(request: Request) -> JSONResponse:
        """PUT /api/markup/config — overlay per-form treatment overrides.

        Body shape: ``{<form>: {kind: <kind>, params: {...}}, ...}``.
        Validates each (form, kind) pair before persisting.
        """
        from claude_code_talker.markup.forms import (
            FORM_KINDS,
            Treatment,
            validate_treatment,
        )
        try:
            body = await _read_json(request)
        except ValueError as e:
            return _bad_request(str(e))
        if not isinstance(body, dict):
            return _bad_request("expected a JSON object")
        # Validate every form/kind before any persistence happens
        for form, node in body.items():
            if form not in FORM_KINDS:
                return _bad_request(f"unknown form: {form}")
            if not isinstance(node, dict):
                return _bad_request(f"{form}: expected object")
            kind = node.get("kind")
            if kind is None:
                continue
            params = node.get("params") or {}
            if not isinstance(params, dict):
                return _bad_request(f"{form}.params must be an object")
            try:
                validate_treatment(form, Treatment(kind=str(kind), params=dict(params)))
            except ValueError as e:
                return _bad_request(str(e))
        # Persist to overlay so it survives restart
        overlay = _read_overlay()
        markup_block = overlay.setdefault("markup", {})
        for form, node in body.items():
            entry = dict(markup_block.get(form) or {})
            if "kind" in node:
                entry["kind"] = node["kind"]
            if "params" in node:
                entry["params"] = dict(node.get("params") or {})
            markup_block[form] = entry
        _write_overlay(overlay)
        # Mirror into in-memory cfg so subsequent transforms see the change
        cfg_markup = state.cfg.setdefault("markup", {})
        for form, node in body.items():
            entry = dict(cfg_markup.get(form) or {})
            if "kind" in node:
                entry["kind"] = node["kind"]
            if "params" in node:
                entry["params"] = dict(node.get("params") or {})
            cfg_markup[form] = entry
        return JSONResponse({"ok": True})

    async def audio_jobs_recent(request: Request) -> JSONResponse:
        """GET /api/audio-jobs/recent?limit=50&session_id=... — Phase 2 audit trail.

        Returns recent AudioJob records from the in-memory ring buffer.
        Each record carries `state_history` — the full gate-by-gate
        trace of every decision the audio chain made. Use this to
        debug "I didn't hear that" reports: scan the most-recent jobs,
        find the one with text matching the expected narration, and
        the terminal state + reason names the gate that dropped it.

        Query params:
          limit       — max jobs to return (default 50, max 200).
          session_id  — filter to one session.
        """
        registry = getattr(state, "audio_job_registry", None)
        if registry is None:
            return JSONResponse(
                {"error": "audio_job_registry not initialized"}, status_code=503
            )
        try:
            limit = int(request.query_params.get("limit", "50"))
        except ValueError:
            limit = 50
        limit = max(1, min(limit, 200))
        sid = request.query_params.get("session_id", "").strip()
        if sid:
            jobs = registry.recent_for_session(sid, limit=limit)
        else:
            jobs = registry.recent(limit=limit)
        return JSONResponse(
            [j.model_dump(mode="json") for j in jobs]
        )

    async def audio_jobs_one(request: Request) -> JSONResponse:
        """GET /api/audio-jobs/{job_id} — single-job trace.

        Returns 404 when the job has been evicted from the ring buffer.
        """
        registry = getattr(state, "audio_job_registry", None)
        if registry is None:
            return JSONResponse(
                {"error": "audio_job_registry not initialized"}, status_code=503
            )
        job_id = request.path_params["job_id"]
        job = registry.get(job_id)
        if job is None:
            return _not_found(f"unknown audio job: {job_id}")
        return JSONResponse(job.model_dump(mode="json"))

    async def events_stream_route(request: Request) -> Response:
        """GET /api/events — SSE feed of every daemon-emitted Event.

        Phase 4 (2026-05-16): single push channel that replaces the 8
        polling loops. Both webui and Pro Android subscribe; cross-
        device sync latency drops from multi-second to ~50ms.

        Query params:
          topics  — comma-separated list of event_type values to filter
                    (e.g. "SessionChanged,MasterConfigChanged"). Omit
                    to receive every event the daemon emits.

        Wire format: standard SSE. Each line is
          event: <event_type>
          data: <json blob with the full Event payload>

        Clients dispatch on `event` and merge `data` into local state.
        The connection stays open until the client disconnects; on
        disconnect, Starlette closes the async generator which triggers
        the EventBus's deregistration finally clause.
        """
        from starlette.responses import StreamingResponse

        if state.event_bus is None:
            return JSONResponse({"error": "event bus not initialized"}, status_code=503)

        topics_param = request.query_params.get("topics", "") or ""
        topics = [t.strip() for t in topics_param.split(",") if t.strip()] or None

        async def _gen():
            sub = state.event_bus.subscribe(topics=topics)
            try:
                yield ": connected\n\n"
                while True:
                    try:
                        ev = await asyncio.wait_for(
                            sub.__anext__(),
                            timeout=_SSE_KEEPALIVE_INTERVAL_SECONDS,
                        )
                    except asyncio.TimeoutError:
                        # Keepalive ping — also detects broken pipes immediately
                        # when the client has silently disconnected.
                        yield ": ping\n\n"
                        continue
                    except StopAsyncIteration:
                        return
                    payload = ev.model_dump_json()
                    yield f"event: {ev.event_type}\ndata: {payload}\n\n"
            except (asyncio.CancelledError, GeneratorExit):
                return
            finally:
                await sub.aclose()

        return StreamingResponse(
            _gen(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache, no-transform",
                "X-Accel-Buffering": "no",
            },
        )

    async def narration_stream_route(request: Request) -> Response:
        """GET /api/narration-stream — Server-Sent Events feed of narrations."""
        from starlette.responses import StreamingResponse

        async def _gen():
            sub = state.narration_stream.subscribe()
            try:
                yield ": connected\n\n"
                while True:
                    try:
                        ev = await asyncio.wait_for(
                            sub.__anext__(),
                            timeout=_SSE_KEEPALIVE_INTERVAL_SECONDS,
                        )
                    except asyncio.TimeoutError:
                        # Keepalive ping — also detects broken pipes immediately
                        # when the client has silently disconnected.
                        yield ": ping\n\n"
                        continue
                    except StopAsyncIteration:
                        return
                    payload = json.dumps({
                        "session_id": ev.session_id,
                        "timestamp": ev.timestamp,
                        "text": ev.text,
                        "voice": ev.voice,
                        "mode": ev.mode,
                        "status": ev.status,
                    })
                    yield f"data: {payload}\n\n"
            except (asyncio.CancelledError, GeneratorExit):
                return
            finally:
                await sub.aclose()

        return StreamingResponse(
            _gen(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache, no-transform",
                "X-Accel-Buffering": "no",
            },
        )

    # ---------------- Phase 25b — 3D mesh REST endpoints ----------------

    async def mesh_providers_list(request: Request) -> JSONResponse:
        out = []
        for name in _MESH_PROVIDERS:
            configured = bool(state.secrets.get(f"{name}_api_key")) if state.secrets else False
            out.append({"name": name, "configured": configured})
        return JSONResponse(out)

    async def mesh_jobs_post(request: Request) -> JSONResponse:
        if state.characters is None:
            return JSONResponse({"error": "character store unavailable"}, status_code=503)
        if getattr(state, "mesh_jobs", None) is None:
            return JSONResponse({"error": "mesh job tracker unavailable"}, status_code=503)
        try:
            body = await request.json()
        except (json.JSONDecodeError, ValueError):
            return JSONResponse({"error": "invalid JSON"}, status_code=400)
        if not isinstance(body, dict):
            return JSONResponse({"error": "body must be a JSON object"}, status_code=400)
        cid = body.get("character_id") or ""
        provider_name = body.get("provider") or ""
        prompt = body.get("prompt") or ""
        image_url = body.get("image_url")
        if not cid or not provider_name or not prompt:
            return JSONResponse(
                {"error": "character_id, provider, prompt required"}, status_code=400
            )
        if provider_name not in _MESH_PROVIDERS:
            return JSONResponse(
                {"error": f"unknown provider: {provider_name}"}, status_code=400
            )
        char = state.characters.get(cid)
        if char is None:
            return JSONResponse({"error": "character not found"}, status_code=404)
        api_key = state.secrets.get(f"{provider_name}_api_key") if state.secrets else None
        if not api_key:
            return JSONResponse(
                {"error": f"missing {provider_name}_api_key in keychain"},
                status_code=400,
            )

        # Use module-level make_provider so tests can monkeypatch
        # ``claude_code_talker.api.make_provider``.
        import claude_code_talker.api as _self
        provider_factory = getattr(_self, "make_provider")

        job = state.mesh_jobs.create(provider=provider_name, character_id=cid, prompt=prompt)
        try:
            provider = provider_factory(provider_name, api_key)
            pjid = provider.start(prompt=prompt, image_url=image_url)
            state.mesh_jobs.set_provider_job_id(job.job_id, pjid)
            # Update prompt history on character (cap 20)
            char.mesh_prompt = prompt
            history = list(char.mesh_prompt_history or [])
            history.append(
                {"prompt": prompt, "provider": provider_name, "ts": _rate_time.time()}
            )
            char.mesh_prompt_history = history[-20:]
            try:
                state.characters.save(char)
            except Exception:
                pass
        except Exception as e:
            state.mesh_jobs.set_failed(job.job_id, error=str(e))
            return JSONResponse({"error": str(e)}, status_code=502)
        return JSONResponse(
            {"job_id": job.job_id, "status": "queued"}, status_code=202
        )

    async def mesh_jobs_list(request: Request) -> JSONResponse:
        if getattr(state, "mesh_jobs", None) is None:
            return JSONResponse([])
        from dataclasses import asdict as _asdict
        return JSONResponse([_asdict(j) for j in state.mesh_jobs.list()])

    async def mesh_jobs_get(request: Request) -> JSONResponse:
        if getattr(state, "mesh_jobs", None) is None:
            return JSONResponse({"error": "mesh job tracker unavailable"}, status_code=503)
        job_id = request.path_params["job_id"]
        job = state.mesh_jobs.get(job_id)
        if job is None:
            return JSONResponse({"error": "job not found"}, status_code=404)
        from dataclasses import asdict as _asdict
        return JSONResponse(_asdict(job))

    async def mesh_jobs_poll(request: Request) -> JSONResponse:
        if state.characters is None:
            return JSONResponse({"error": "character store unavailable"}, status_code=503)
        if getattr(state, "mesh_jobs", None) is None:
            return JSONResponse({"error": "mesh job tracker unavailable"}, status_code=503)
        job_id = request.path_params["job_id"]
        job = state.mesh_jobs.get(job_id)
        if job is None or not job.provider_job_id:
            return JSONResponse({"error": "job not ready to poll"}, status_code=404)
        api_key = state.secrets.get(f"{job.provider}_api_key") if state.secrets else None
        if not api_key:
            return JSONResponse({"error": "missing api key"}, status_code=400)

        import claude_code_talker.api as _self
        provider_factory = getattr(_self, "make_provider")
        try:
            provider = provider_factory(job.provider, api_key)
            status = provider.poll(job.provider_job_id)
        except Exception as e:
            state.mesh_jobs.set_failed(job.job_id, error=str(e))
            from dataclasses import asdict as _asdict
            return JSONResponse(_asdict(state.mesh_jobs.get(job.job_id)), status_code=502)

        if status.status == "running":
            state.mesh_jobs.set_status(job.job_id, "running", progress=status.progress)
        elif status.status == "queued":
            state.mesh_jobs.set_status(job.job_id, "queued", progress=status.progress)
        elif status.status == "succeeded":
            models_root = getattr(state, "mesh_models_root", None) or (
                Path.home() / ".claude" / "scripts" / "codetalker" / "models"
            )
            char_dir = Path(models_root) / job.character_id
            char_dir.mkdir(parents=True, exist_ok=True)
            from claude_code_talker.mesh.provider import extension_from_url
            ext = extension_from_url(status.model_url)
            dest = char_dir / f"{job.job_id}.{ext}"
            try:
                final_path = provider.download(job.provider_job_id, dest)
            except Exception as e:
                state.mesh_jobs.set_failed(job.job_id, error=str(e))
                from dataclasses import asdict as _asdict
                return JSONResponse(_asdict(state.mesh_jobs.get(job.job_id)), status_code=502)
            state.mesh_jobs.set_succeeded(job.job_id, model_path=str(final_path))
            char = state.characters.get(job.character_id)
            if char is not None:
                char.mesh_path = str(final_path)
                char.mesh_provider = job.provider
                try:
                    state.characters.save(char)
                except Exception:
                    pass
        elif status.status == "failed":
            state.mesh_jobs.set_failed(job.job_id, error=status.error or "failed")

        from dataclasses import asdict as _asdict
        return JSONResponse(_asdict(state.mesh_jobs.get(job.job_id)))

    async def list_analysis_reports(request: Request) -> JSONResponse:
        """GET /api/analysis-reports — list MARKET_ANALYSIS_*.md files at repo root.

        Returns:
          [
            {"filename": "MARKET_ANALYSIS_2026-05-21.md", "label": null,
             "size": 6738, "modified": 1779415xxx},
            {"filename": "MARKET_ANALYSIS_2026-05-21-iter2.md", "label": "iter2", ...},
            ...
          ]

        Sorted newest first (by modified time).
        """
        # repo root = parent of `core/`
        repo_root = Path(__file__).resolve().parent.parent.parent
        out = []
        for path in repo_root.glob("MARKET_ANALYSIS_*.md"):
            try:
                st = path.stat()
                # Extract label from filename like MARKET_ANALYSIS_2026-05-21-iter2.md
                #   MARKET_ANALYSIS_2026-05-21       → 3 parts, no label
                #   MARKET_ANALYSIS_2026-05-21-iter4 → 4 parts, label = "iter4"
                stem = path.stem
                parts = stem.split("-")
                label = parts[-1] if len(parts) >= 4 else None
                out.append({
                    "filename": path.name,
                    "label": label,
                    "size": st.st_size,
                    "modified": st.st_mtime,
                })
            except Exception:
                pass
        out.sort(key=lambda x: x["modified"], reverse=True)
        return JSONResponse(out)

    async def get_analysis_report(request: Request) -> Response:
        """GET /api/analysis-reports/{filename} — return raw markdown.

        Filename validation rejects path-traversal attempts (must match
        MARKET_ANALYSIS_*.md pattern exactly).
        """
        from starlette.responses import PlainTextResponse
        filename = request.path_params.get("filename", "")
        if not re.fullmatch(r"MARKET_ANALYSIS_[\w\-\.]+\.md", filename):
            return JSONResponse({"error": "invalid filename"}, status_code=400)
        repo_root = Path(__file__).resolve().parent.parent.parent
        path = repo_root / filename
        if not path.exists():
            return JSONResponse({"error": "not found"}, status_code=404)
        return PlainTextResponse(path.read_text(encoding="utf-8"), media_type="text/markdown")

    # CCT-31 — Companion (XREAL Android AR) routes are built separately and appended.
    from claude_code_talker.companion.api import make_routes as _companion_routes

    routes = [
        Route("/api/health", health, methods=["GET"]),
        Route("/api/analysis-reports", list_analysis_reports, methods=["GET"]),
        Route("/api/analysis-reports/{filename}", get_analysis_report, methods=["GET"]),
        Route("/api/master-enabled", master_enabled_get, methods=["GET"]),
        Route("/api/master-enabled", master_enabled_put, methods=["PUT"]),
        Route("/api/license/status", license_status, methods=["GET"]),
        Route("/api/license/activate", license_activate, methods=["POST"]),
        Route("/api/audio/skip", audio_skip, methods=["POST"]),
        Route("/api/audio/rewind", audio_rewind, methods=["POST"]),
        Route("/api/catalog", list_catalog, methods=["GET"]),
        Route("/api/catalog/refresh", refresh_catalog, methods=["POST"]),
        Route("/api/persistent-sessions/{session_id}", get_persistent_session, methods=["GET"]),
        Route("/api/persistent-sessions/{session_id}", put_persistent_session, methods=["PUT"]),
        Route("/api/persistent-sessions/{session_id}", delete_persistent_session, methods=["DELETE"]),
        Route("/api/secrets", get_secrets, methods=["GET"]),
        Route("/api/secrets", put_secrets, methods=["PUT"]),
        Route("/api/llm-models", list_llm_models, methods=["GET"]),
        Route("/api/llm-models/default", put_llm_default, methods=["PUT"]),
        Route("/api/llm-models/openrouter/refresh", refresh_openrouter_models, methods=["POST"]),
        Route("/api/teacher", get_teacher, methods=["GET"]),
        Route("/api/teacher", put_teacher, methods=["PUT"]),
        Route("/api/sessions/{session_id}/chat", chat_with_session, methods=["POST"]),
        Route("/api/narration-log", get_narration_log, methods=["GET"]),
        Route("/api/usage", get_usage, methods=["GET"]),
        Route("/api/tts-cache", get_tts_cache_stats, methods=["GET"]),
        Route("/api/tts-cache", clear_tts_cache, methods=["DELETE"]),
        Route("/api/config/reload", reload_config, methods=["POST"]),
        Route("/api/sessions/bulk", bulk_session_op, methods=["POST"]),
        Route("/api/sessions", list_sessions, methods=["GET"]),
        Route("/api/sessions/{session_id}", get_session, methods=["GET"]),
        Route("/api/sessions/{session_id}", patch_session, methods=["PATCH"]),
        Route("/api/sessions/{session_id}/overlay", put_overlay, methods=["PUT"]),
        Route("/api/sessions/{session_id}/overlay/{keypath:path}", delete_overlay_keypath, methods=["DELETE"]),
        Route("/api/sessions/{session_id}/attach-profile", attach_profile, methods=["POST"]),
        Route("/api/sessions/{session_id}/profile", detach_profile, methods=["DELETE"]),
        Route("/api/sessions/{session_id}/save-as-profile", save_as_profile, methods=["POST"]),
        Route("/api/profiles", list_profiles, methods=["GET"]),
        Route("/api/profiles/{name}", get_profile, methods=["GET"]),
        Route("/api/profiles/{name}", put_profile, methods=["PUT"]),
        Route("/api/profiles/{name}", delete_profile, methods=["DELETE"]),
        Route("/api/characters", list_characters, methods=["GET"]),
        Route("/api/characters/{char_id}", get_character, methods=["GET"]),
        Route("/api/characters", create_character, methods=["POST"]),
        Route("/api/characters/{char_id}", put_character, methods=["PUT"]),
        Route("/api/characters/{char_id}", delete_character, methods=["DELETE"]),
        # Phase 25c — voice cloning kickoff + job status
        Route("/api/characters/{char_id}/clone-voice", characters_clone_voice, methods=["POST"]),
        # v0.1.x — auto-generate a character tailored to a session via LLM
        Route("/api/sessions/{session_id}/generate-character", generate_character_for_session, methods=["POST"]),
        Route("/api/characters/{char_id}/mesh-file", character_mesh_file, methods=["GET"]),
        Route("/api/voice-clone-jobs/{job_id}", voice_clone_job_get, methods=["GET"]),
        Route("/api/sessions/{session_id}/attach-character", attach_character, methods=["POST"]),
        Route("/api/sessions/{session_id}/character", detach_character, methods=["DELETE"]),
        Route("/api/voices", list_voices, methods=["GET"]),
        # Phase 14 v0.4.0 — voice clone CRUD (order matters: specific before wildcard)
        Route("/api/voices/list", voices_list, methods=["GET"]),
        Route("/api/voices/dependency-status", voices_dependency_status, methods=["GET"]),
        Route("/api/voices/install-dependencies", voices_install_dependencies, methods=["POST"]),
        Route("/api/voices/install-status/{task_id}", voices_install_status, methods=["GET"]),
        Route("/api/voices/clone-from-file", voices_clone_from_file, methods=["POST"]),
        Route("/api/voices/preview-extract", voices_preview_extract, methods=["POST"]),
        Route("/api/voices/preview-audio/{token}", voices_preview_audio, methods=["GET"]),
        Route("/api/voices/clone-from-preview", voices_clone_from_preview, methods=["POST"]),
        Route("/api/voices/preview/{name}", voices_preview_voice, methods=["POST"]),
        Route("/api/voices/{name}", voices_rename, methods=["PATCH"]),
        Route("/api/voices/{name}/replace-source", voices_replace_source, methods=["POST"]),
        Route("/api/voices/{name}", voices_delete, methods=["DELETE"]),
        # Piper voice manager (v0.1.x) — local TTS voice catalog/install/preview
        Route("/api/piper/catalog", piper_catalog, methods=["GET"]),
        Route("/api/piper/install", piper_install, methods=["POST"]),
        Route("/api/piper/voices/{name}", piper_uninstall, methods=["DELETE"]),
        Route("/api/piper/preview/{name}", piper_preview, methods=["POST"]),
        Route("/api/status", status, methods=["GET"]),
        Route("/api/mute", mute, methods=["POST"]),
        Route("/api/unmute", unmute, methods=["POST"]),
        Route("/api/hooks-status", hooks_status, methods=["GET"]),
        Route("/api/install-hooks", install_hooks, methods=["POST"]),
        # v1.0 — REST hook dispatch (replaces MCP SSE path for the
        # Windows .exe wrapper which was costing 10-22s per hook).
        Route("/api/hooks/dispatch", hooks_dispatch, methods=["POST"]),
        Route("/api/virtual-eval/run", virtual_eval_run, methods=["POST"]),
        Route("/api/virtual-eval/latest", virtual_eval_latest, methods=["GET"]),
        Route("/api/virtual-eval/history", virtual_eval_history, methods=["GET"]),
        Route("/api/virtual-eval/revert/{entry_id}", virtual_eval_revert, methods=["POST"]),
        # v0.1.0 unification — fleet audio defaults
        Route("/api/cfg/audio-defaults", audio_defaults_get, methods=["GET"]),
        Route("/api/cfg/audio-defaults", audio_defaults_put, methods=["PUT"]),
        # Phase 14.5 — trigger-mode config + tag CRUD (specific routes before wildcard)
        Route("/api/triggers/config", triggers_get_config, methods=["GET"]),
        Route("/api/triggers/config", triggers_put_config, methods=["PUT"]),
        Route("/api/triggers/tags", triggers_list_tags, methods=["GET"]),
        Route("/api/triggers/tags", triggers_create_tag, methods=["POST"]),
        Route("/api/triggers/skill-install", triggers_skill_install, methods=["POST"]),
        Route("/api/triggers/skill-preview", triggers_skill_preview, methods=["GET"]),
        Route("/api/triggers/skill-body", triggers_skill_body, methods=["GET"]),
        # Phase 26 — markup config
        Route("/api/markup/config", markup_config_get, methods=["GET"]),
        Route("/api/markup/config", markup_config_put, methods=["PUT"]),
        Route("/api/narration-stream", narration_stream_route, methods=["GET"]),
        Route("/api/events", events_stream_route, methods=["GET"]),
        Route("/api/audio-jobs/recent", audio_jobs_recent, methods=["GET"]),
        Route("/api/audio-jobs/{job_id}", audio_jobs_one, methods=["GET"]),
        Route("/api/triggers/tags/{tag_id}", triggers_get_tag, methods=["GET"]),
        Route("/api/triggers/tags/{tag_id}", triggers_put_tag, methods=["PUT"]),
        Route("/api/triggers/tags/{tag_id}", triggers_delete_tag, methods=["DELETE"]),
        # Phase 25b — 3D mesh routes
        Route("/api/mesh-providers", mesh_providers_list, methods=["GET"]),
        Route("/api/mesh-jobs", mesh_jobs_post, methods=["POST"]),
        Route("/api/mesh-jobs", mesh_jobs_list, methods=["GET"]),
        Route("/api/mesh-jobs/{job_id}", mesh_jobs_get, methods=["GET"]),
        Route("/api/mesh-jobs/{job_id}/poll", mesh_jobs_poll, methods=["POST"]),
    ]
    routes.extend(_companion_routes(state))
    return routes


def _persist_default_provider(provider: str, model: str, *, mode: str | None = None) -> None:
    """Write the user's chosen LLM default to a small overlay YAML at
    ~/.claude/scripts/codetalker/cfg-overlay.yaml so it survives restarts.

    The daemon's config loader merges this overlay on top of the base cfg.
    Best-effort: any I/O failure is silenced (the in-memory PUT still works).

    Args:
        provider: Provider name (e.g. "openrouter").
        model: Model ID (e.g. "google/gemini-2.0-flash-001").
        mode: If provided, only update that mode's {provider, model} entry.
              If None (default), update live + brief (existing all-modes behavior).
    """
    try:
        import yaml as _yaml
        from pathlib import Path as _P
        p = _P.home() / ".claude" / "scripts" / "codetalker" / "cfg-overlay.yaml"
        p.parent.mkdir(parents=True, exist_ok=True)
        existing = {}
        if p.exists():
            try:
                existing = _yaml.safe_load(p.read_text(encoding="utf-8")) or {}
            except Exception:
                existing = {}
        if not isinstance(existing, dict):
            existing = {}
        existing.setdefault("providers", {}).setdefault(provider, {})["model"] = model
        if mode:
            # Per-mode: write provider + model into that specific mode block
            existing.setdefault("modes", {}).setdefault(mode, {})["provider"] = provider
            existing.setdefault("modes", {}).setdefault(mode, {})["model"] = model
        else:
            # All-modes: update live + brief (existing behavior)
            existing.setdefault("modes", {}).setdefault("live", {})["provider"] = provider
            existing.setdefault("modes", {}).setdefault("brief", {})["provider"] = provider
        p.write_text(_yaml.safe_dump(existing, sort_keys=True), encoding="utf-8")
    except Exception:
        pass


def _read_overlay() -> dict:
    """Read the cfg-overlay.yaml, returning a dict (empty on error/missing)."""
    import yaml as _yaml
    p = _TRIGGERS_OVERLAY_PATH
    if not p.exists():
        return {}
    try:
        data = _yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _write_overlay(data: dict) -> None:
    """Atomically write *data* to cfg-overlay.yaml via tmp + os.replace."""
    import os as _os
    import yaml as _yaml
    p = _TRIGGERS_OVERLAY_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(_yaml.safe_dump(data, sort_keys=True), encoding="utf-8")
    _os.replace(tmp, p)


def _bad_request(message: str) -> JSONResponse:
    return JSONResponse({"error": message}, status_code=400)


def _not_found(message: str) -> JSONResponse:
    return JSONResponse({"error": message}, status_code=404)


async def _read_json(request: Request) -> dict:
    """Parse JSON body or raise ValueError."""
    raw = await request.body()
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"malformed JSON: {e}") from e
    if not isinstance(data, dict):
        raise ValueError("body must be a JSON object")
    return data
