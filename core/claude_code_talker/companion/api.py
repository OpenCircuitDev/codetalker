"""CCT-31 — Companion REST endpoints.

These routes power the XREAL Android AR companion app. Every endpoint other
than `/api/companion/pair` requires the X-CCT-Pairing-Token header set to a
token previously issued by this daemon.
"""
from __future__ import annotations

from starlette.requests import Request
from starlette.responses import JSONResponse, Response, StreamingResponse
from starlette.routing import Route


def _require_token(request: Request, store) -> bool:
    tok = request.headers.get("X-CCT-Pairing-Token", "")
    return store.validate(tok)


def make_routes(state) -> list[Route]:
    async def pair(request: Request) -> Response:
        body = await request.json()
        label = body.get("label", "unknown")
        ttl = int(body.get("ttl_days", 30))
        t = state.pairing.issue(label=label, ttl_days=ttl)
        return JSONResponse({"token": t.token, "label": t.label, "expires_at": t.expires_at})

    async def list_sessions(request: Request) -> Response:
        if not _require_token(request, state.pairing):
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        catalog = state.catalog
        if catalog is None:
            return JSONResponse([])
        return JSONResponse([{
            "session_id": e.session_id,
            "display_name": (e.custom_title or e.vscode_label or e.title or e.project_slug),
            "is_live": False,
        } for e in catalog.entries()])

    async def start_buddy(request: Request) -> Response:
        if not _require_token(request, state.pairing):
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        body = await request.json()
        sid = body.get("user_session_id")
        if not sid:
            return JSONResponse({"error": "user_session_id required"}, status_code=400)
        api_key = state.secrets.get("anthropic_api_key") if state.secrets else None
        if not api_key:
            return JSONResponse({"error": "anthropic_api_key not set"}, status_code=400)
        # Re-create the BuddyManager with the live key if it was constructed
        # before the key was persisted (covers first-run boot order).
        if not getattr(state.buddy_manager, "api_key", None):
            state.buddy_manager.api_key = api_key
        state.buddy_manager.start(sid)
        return JSONResponse({"buddy_id": sid, "status": "ready"})

    async def inject(request: Request) -> Response:
        if not _require_token(request, state.pairing):
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        body = await request.json()
        bid = body.get("buddy_id")
        text = body.get("text", "")
        buddy = state.buddy_manager.get(bid) if bid else None
        if not buddy:
            return JSONResponse({"error": "buddy not started"}, status_code=404)
        # Stream events via SSE
        async def gen():
            async for ev in buddy.inject(text):
                yield f"event: {ev.kind}\ndata: {ev.text or ''}\n\n".encode()
        return StreamingResponse(gen(), media_type="text/event-stream")

    async def active_session(request: Request) -> Response:
        if not _require_token(request, state.pairing):
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        body = await request.json()
        state.companion_active_session = body.get("session_id")
        return JSONResponse({"ok": True, "active_session_id": state.companion_active_session})

    async def audio_stream(request: Request) -> Response:
        if not _require_token(request, state.pairing):
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        sid = request.path_params["session_id"]
        async def gen():
            async for frame in state.audio_hub.subscribe(sid):
                yield frame
        return StreamingResponse(gen(), media_type="audio/opus")

    async def screen_frame(request: Request) -> Response:
        if not _require_token(request, state.pairing):
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        kind = request.path_params["kind"]
        if kind == "fullscreen":
            jpg = state.screen_capture.capture_fullscreen()
        else:
            jpg = state.screen_capture.capture_window("Claude Code")
        if jpg is None:
            return JSONResponse({"error": "capture unavailable"}, status_code=503)
        return Response(jpg, media_type="image/jpeg")

    return [
        Route("/api/companion/pair", pair, methods=["POST"]),
        Route("/api/companion/sessions", list_sessions, methods=["GET"]),
        Route("/api/companion/start-buddy", start_buddy, methods=["POST"]),
        Route("/api/companion/inject", inject, methods=["POST"]),
        Route("/api/companion/active-session", active_session, methods=["POST"]),
        Route("/api/companion/audio-stream/{session_id}", audio_stream, methods=["GET"]),
        Route("/api/companion/screen-frame/{kind}", screen_frame, methods=["GET"]),
    ]
