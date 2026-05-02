"""Tests for SSE transport -- uses httpx ASGI transport (no real port bind)."""
import asyncio
import pytest
from claude_code_talker.server import build_asgi_app, build_server_state

# The MCP SDK's SSE transport validates the Host header for DNS rebinding
# protection.  When driving the app via httpx's ASGI transport there is no
# real TCP connection, so there is no meaningful Host to validate.  We disable
# transport security for these in-process unit tests.
_NO_SECURITY = {"disable_transport_security": True}
_BASE_URL = "http://test"


@pytest.mark.asyncio
async def test_asgi_app_responds_on_sse_endpoint():
    """The ASGI app should expose /sse and accept GET requests.

    An SSE GET holds the connection open indefinitely.  We probe the route with
    asyncio.wait_for so the test doesn't hang.  A TimeoutError means the stream
    opened (route exists); any other exception that is *not* a 404 also passes.
    """
    state = build_server_state()
    state.cfg["enabled"] = True
    app = build_asgi_app(state, **_NO_SECURITY)

    import httpx

    async def probe():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url=_BASE_URL
        ) as client:
            response = await client.get("/sse")
            # If we get a synchronous response, it must not be 404.
            assert response.status_code != 404

    try:
        # 1-second cap; TimeoutError means the SSE stream started (not 404).
        await asyncio.wait_for(probe(), timeout=1.0)
    except asyncio.TimeoutError:
        pass  # SSE stream held open -- route exists and the server is healthy.


@pytest.mark.asyncio
async def test_asgi_app_messages_route_exists():
    """The /messages/ POST route should exist (404 is the failure mode we're avoiding)."""
    state = build_server_state()
    app = build_asgi_app(state, **_NO_SECURITY)

    import httpx
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url=_BASE_URL
    ) as client:
        # POST without a session_id should not 404 -- it might 400 (bad request) or 200,
        # but not 404 (route missing). The SDK mounts at /messages (no trailing slash);
        # Starlette redirects /messages/ -> /messages for Mount routes, so we test /messages.
        response = await client.post("/messages", json={}, timeout=1.0)
        assert response.status_code != 404
