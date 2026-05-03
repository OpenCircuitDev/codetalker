"""REST API routes mounted alongside the FastMCP SSE app."""
from __future__ import annotations

import json
import json as _json_lib
import re
import time as _rate_time
from pathlib import Path
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route
from claude_code_talker.profiles import is_valid_profile_name
from claude_code_talker.persistent_sessions import is_valid_session_id


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

_HOOK_EVENT_NAMES = ["Stop", "Notification", "PreToolUse", "PostToolUse"]
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
        out = []
        for s in state.sessions.list_active():
            out.append({
                "session_id": s.session_id,
                "cwd": s.cwd,
                "transcript_path": s.transcript_path,
                "last_hook_at": s.last_hook_at,
                "attached_profile": s.attached_profile,
            })
        return JSONResponse(out)

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
        return JSONResponse({"saved": True, "session_id": sid})

    async def delete_persistent_session(request: Request) -> JSONResponse:
        sid = request.path_params["session_id"]
        if not is_valid_session_id(sid):
            return _bad_request(f"invalid session_id: {sid!r}")
        existed = state.persistent_sessions.exists(sid)
        state.persistent_sessions.delete(sid)
        return JSONResponse({"deleted": existed})

    return [
        Route("/api/health", health, methods=["GET"]),
        Route("/api/catalog", list_catalog, methods=["GET"]),
        Route("/api/catalog/refresh", refresh_catalog, methods=["POST"]),
        Route("/api/persistent-sessions/{session_id}", get_persistent_session, methods=["GET"]),
        Route("/api/persistent-sessions/{session_id}", put_persistent_session, methods=["PUT"]),
        Route("/api/persistent-sessions/{session_id}", delete_persistent_session, methods=["DELETE"]),
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
        Route("/api/voices", list_voices, methods=["GET"]),
        Route("/api/status", status, methods=["GET"]),
        Route("/api/mute", mute, methods=["POST"]),
        Route("/api/unmute", unmute, methods=["POST"]),
        Route("/api/install-hooks", install_hooks, methods=["POST"]),
    ]


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
