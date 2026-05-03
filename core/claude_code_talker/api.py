"""REST API routes mounted alongside the FastMCP SSE app."""
from __future__ import annotations

import json
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route


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

    return [
        Route("/api/health", health, methods=["GET"]),
        Route("/api/sessions", list_sessions, methods=["GET"]),
        Route("/api/sessions/{session_id}", get_session, methods=["GET"]),
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
