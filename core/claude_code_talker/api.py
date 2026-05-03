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

    return [
        Route("/api/health", health, methods=["GET"]),
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
