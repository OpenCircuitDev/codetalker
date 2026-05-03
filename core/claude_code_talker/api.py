"""REST API routes mounted alongside the FastMCP SSE app."""
from __future__ import annotations

import json
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route
from claude_code_talker.profiles import is_valid_profile_name


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

    return [
        Route("/api/health", health, methods=["GET"]),
        Route("/api/sessions", list_sessions, methods=["GET"]),
        Route("/api/sessions/{session_id}", get_session, methods=["GET"]),
        Route("/api/sessions/{session_id}/overlay", put_overlay, methods=["PUT"]),
        Route("/api/sessions/{session_id}/overlay/{keypath:path}", delete_overlay_keypath, methods=["DELETE"]),
        Route("/api/sessions/{session_id}/attach-profile", attach_profile, methods=["POST"]),
        Route("/api/sessions/{session_id}/profile", detach_profile, methods=["DELETE"]),
        Route("/api/sessions/{session_id}/save-as-profile", save_as_profile, methods=["POST"]),
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
