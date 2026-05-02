"""Tests for SSE transport -- uses httpx ASGI transport (no real port bind)."""
import asyncio
import socket
import threading
import time
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


def _free_port() -> int:
    """Find an unused localhost port for the test daemon."""
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.mark.asyncio
async def test_mcp_client_roundtrip_tts_status():
    """Real MCP client over SSE invokes tts_status through the FastMCP wrapper.

    This is the canonical exercise for the hand-crafted open-schema tool
    registration in _register_tools_fastmcp.  Route-existence tests above can't
    catch wrapper regressions because they never dispatch a tool call.  This
    test proves: (1) the wrapper accepts a call_tool request with empty args,
    (2) the in-process handler runs, (3) the response text round-trips back
    through SSE to the client.
    """
    import uvicorn
    from mcp import ClientSession
    from mcp.client.sse import sse_client

    port = _free_port()
    state = build_server_state()
    state.cfg["enabled"] = True

    app = build_asgi_app(state, disable_transport_security=True)
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error")
    server = uvicorn.Server(config)

    thread = threading.Thread(target=lambda: asyncio.run(server.serve()), daemon=True)
    thread.start()

    # Wait for the server to bind.
    deadline = time.time() + 5.0
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                break
        except OSError:
            time.sleep(0.1)
    else:
        pytest.fail("daemon did not become ready in 5 seconds")

    try:
        url = f"http://127.0.0.1:{port}/sse"
        async with sse_client(url) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                result = await session.call_tool("tts_status", {})
                text_parts = [c.text for c in result.content if hasattr(c, "text")]
                assert text_parts, "expected text content in tool response"
                response = text_parts[0]
                # tts_status response format: "mode=..., enabled, engines=..., providers=..."
                assert "mode=" in response
                assert "enabled" in response
                assert "engines=" in response
    finally:
        server.should_exit = True
        thread.join(timeout=5.0)
