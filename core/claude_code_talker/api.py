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


def build_routes(state) -> list[Route]:
    """Build the list of Starlette Route objects bound to this server state."""

    async def health(request: Request) -> JSONResponse:
        return JSONResponse({"ok": True})

    async def list_sessions(request: Request) -> JSONResponse:
        live = state.sessions.list_active()
        live_by_sid = {s.session_id: s for s in live}
        merged = []
        if state.catalog is not None:
            catalog_entries = state.catalog.entries()
        else:
            catalog_entries = []
        seen_sids = set()
        from claude_code_talker.catalog import _slug_to_display_name
        for c in catalog_entries:
            sid = c.session_id
            seen_sids.add(sid)
            live_match = live_by_sid.get(sid)
            persistent = state.persistent_sessions.get(sid) if state.persistent_sessions else None
            # Display priority:
            #   persistent display_name (codetalker-set)
            #   > Claude Code custom_title (user's /title rename — verbatim)
            #   > Claude Code panel label (vscode_label)
            #   > slug-derived display name (auto-generated, tracks renames)
            #   > catalog auto-title (cached first prompt)
            #   > project_slug
            slug_display = _slug_to_display_name(c.slug) if c.slug else ""
            display_name = (
                (persistent.get("display_name") if persistent else None)
                or (c.custom_title or None)
                or (c.vscode_label or None)
                or (slug_display or None)
                or (c.title or None)
                or c.project_slug
            )
            merged.append({
                "session_id": sid,
                "cwd": (live_match.cwd if live_match else "") or "",
                "project_slug": c.project_slug,
                "title": c.title,
                "display_name": display_name,
                "last_modified": max(
                    c.last_modified,
                    live_match.last_hook_at if live_match else 0.0,
                ),
                "is_live": live_match is not None,
                "enabled": (persistent.get("enabled", True) if persistent else True),
                "attached_profile": (
                    live_match.attached_profile if live_match else (
                        persistent.get("attached_profile") if persistent else None
                    )
                ),
                "attached_character": (
                    live_match.attached_character if live_match else (
                        persistent.get("attached_character") if persistent else None
                    )
                ),
                "has_persistent_settings": persistent is not None,
            })
        # Live sessions not in the catalog (newly created since last scan)
        for sid, live_match in live_by_sid.items():
            if sid in seen_sids:
                continue
            persistent = state.persistent_sessions.get(sid) if state.persistent_sessions else None
            merged.append({
                "session_id": sid,
                "cwd": live_match.cwd or "",
                "project_slug": "",
                "display_name": (persistent.get("display_name") if persistent else None) or sid[:12],
                "last_modified": live_match.last_hook_at,
                "is_live": True,
                "enabled": (persistent.get("enabled", True) if persistent else True),
                "attached_profile": live_match.attached_profile,
                "attached_character": live_match.attached_character,
                "has_persistent_settings": persistent is not None,
            })
        merged.sort(key=lambda e: e["last_modified"], reverse=True)
        return JSONResponse(merged)

    async def get_session(request: Request) -> JSONResponse:
        sid = request.path_params["session_id"]
        s = state.sessions.get(sid)
        if s is None:
            return _not_found(f"unknown session: {sid}")
        cfg = state.sessions.config_for(sid)
        return JSONResponse({
            "state": {
                "session_id": s.session_id,
                "cwd": s.cwd,
                "transcript_path": s.transcript_path,
                "last_hook_at": s.last_hook_at,
                "live_overlay": s.live_overlay,
                "attached_profile": s.attached_profile,
                "attached_character": s.attached_character,
            },
            "resolved_cfg": cfg,
        })

    async def put_overlay(request: Request) -> JSONResponse:
        sid = request.path_params["session_id"]
        if state.sessions.get(sid) is None:
            return _not_found(f"unknown session: {sid}")
        try:
            partial = await _read_json(request)
        except ValueError as e:
            return _bad_request(str(e))
        try:
            state.sessions.update_overlay(sid, partial)
        except KeyError:
            return _not_found(f"unknown session: {sid}")
        cfg = state.sessions.config_for(sid)
        state.sessions.invalidate(sid)  # keep cache cleared after resolving for response
        s = state.sessions.get(sid)
        return JSONResponse({
            "state": {
                "session_id": s.session_id,
                "live_overlay": s.live_overlay,
                "attached_profile": s.attached_profile,
            },
            "resolved_cfg": cfg,
        })

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

    async def characters_clone_voice(request: Request) -> JSONResponse:
        """Phase 25c — POST /api/characters/{char_id}/clone-voice.

        v1 stub clone path: creates a tracker job, immediately marks it
        succeeded with ``voice_ref = char-<character_id>``.  Phase 25b will
        replace the synchronous success with an async cloning pipeline.
        """
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
        job = state.clone_jobs.create(cid, audio_bytes, mime_type)
        # Phase 25c v1: stub clone — succeed immediately with placeholder voice_ref.
        state.clone_jobs.set_succeeded(job.job_id, voice_ref=f"char-{cid}")
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

    async def attach_character(request: Request) -> JSONResponse:
        if state.characters is None or state.sessions is None:
            return JSONResponse({"error": "character store unavailable"}, status_code=503)
        sid = request.path_params.get("session_id", "")
        if not is_valid_session_id(sid):
            return _bad_request(f"invalid session id: {sid!r}")
        s = state.sessions.get(sid)
        if s is None:
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
        # Phase 25c v1 stub-clone path: voice_refs of the form ``char-<id>`` are
        # produced by /api/characters/{id}/clone-voice as a placeholder until
        # Phase 25b's real cloner runs.  We allowlist them here so the wizard's
        # save-then-attach flow works end-to-end without bypassing the check
        # for arbitrary voices.
        voice_ok = False
        if char.voice_ref and char.voice_ref.startswith("char-"):
            # stub-clone placeholder: trust it (Phase 25b will replace with real ref)
            voice_ok = True
        else:
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
        s.attached_character = cid
        return JSONResponse({
            "state": {"session_id": s.session_id, "attached_character": s.attached_character}
        })

    async def detach_character(request: Request) -> JSONResponse:
        if state.sessions is None:
            return JSONResponse({"error": "session registry unavailable"}, status_code=503)
        sid = request.path_params.get("session_id", "")
        if not is_valid_session_id(sid):
            return _bad_request(f"invalid session id: {sid!r}")
        s = state.sessions.get(sid)
        if s is None:
            return JSONResponse({"error": "session not found"}, status_code=404)
        s.attached_character = None
        return JSONResponse({
            "state": {"session_id": s.session_id, "attached_character": None}
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

    async def narration_stream_route(request: Request) -> Response:
        """GET /api/narration-stream — Server-Sent Events feed of narrations."""
        from starlette.responses import StreamingResponse

        async def _gen():
            sub = state.narration_stream.subscribe()
            try:
                yield ": connected\n\n"
                async for ev in sub:
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

    # CCT-31 — Companion (XREAL Android AR) routes are built separately and appended.
    from claude_code_talker.companion.api import make_routes as _companion_routes

    routes = [
        Route("/api/health", health, methods=["GET"]),
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
        Route("/api/status", status, methods=["GET"]),
        Route("/api/mute", mute, methods=["POST"]),
        Route("/api/unmute", unmute, methods=["POST"]),
        Route("/api/hooks-status", hooks_status, methods=["GET"]),
        Route("/api/install-hooks", install_hooks, methods=["POST"]),
        Route("/api/virtual-eval/run", virtual_eval_run, methods=["POST"]),
        Route("/api/virtual-eval/latest", virtual_eval_latest, methods=["GET"]),
        Route("/api/virtual-eval/history", virtual_eval_history, methods=["GET"]),
        Route("/api/virtual-eval/revert/{entry_id}", virtual_eval_revert, methods=["POST"]),
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
