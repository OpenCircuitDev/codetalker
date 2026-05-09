"""Phase 25b — Hyper3D Rodin Gen-2 adapter tests."""
from __future__ import annotations

from pathlib import Path

import httpx
import pytest
import respx

from claude_code_talker.mesh.hyper3d import Hyper3DProvider


@pytest.fixture
def provider():
    return Hyper3DProvider(api_key="test-key")


@respx.mock
def test_start_posts_to_rodin_with_prompt(provider):
    route = respx.post("https://hyperhuman.deemos.com/api/v2/rodin").mock(
        return_value=httpx.Response(200, json={"uuid": "abc-123", "subscription_key": "sub-456"})
    )
    job_id = provider.start(prompt="a fox sitting on a log")
    assert job_id == "abc-123"
    assert route.called


@respx.mock
def test_start_passes_image_url_when_provided(provider):
    captured = {}

    def cap(req):
        captured["body"] = req.read()
        return httpx.Response(200, json={"uuid": "abc"})

    respx.post("https://hyperhuman.deemos.com/api/v2/rodin").mock(side_effect=cap)
    provider.start(prompt="x", image_url="https://img/foo.png")
    assert b"image" in captured["body"]


@respx.mock
def test_poll_returns_running(provider):
    respx.post("https://hyperhuman.deemos.com/api/v2/status").mock(
        return_value=httpx.Response(200, json={"jobs": [{"uuid": "abc", "status": "Generating"}]})
    )
    s = provider.poll("abc")
    assert s.status == "running"


@respx.mock
def test_poll_returns_succeeded_with_model_url(provider):
    respx.post("https://hyperhuman.deemos.com/api/v2/status").mock(
        return_value=httpx.Response(200, json={"jobs": [{"uuid": "abc", "status": "Done"}]})
    )
    respx.post("https://hyperhuman.deemos.com/api/v2/download").mock(
        return_value=httpx.Response(
            200, json={"list": [{"name": "model.glb", "url": "https://cdn/x.glb"}]}
        )
    )
    s = provider.poll("abc")
    assert s.status == "succeeded"
    assert s.model_url == "https://cdn/x.glb"


@respx.mock
def test_poll_failure_status(provider):
    respx.post("https://hyperhuman.deemos.com/api/v2/status").mock(
        return_value=httpx.Response(
            200, json={"jobs": [{"uuid": "abc", "status": "Failed", "msg": "bad prompt"}]}
        )
    )
    s = provider.poll("abc")
    assert s.status == "failed"
    assert "bad prompt" in (s.error or "")


@respx.mock
def test_download_streams_to_disk(tmp_path, provider):
    # Stub download URL to return bytes
    respx.get("https://cdn/x.glb").mock(return_value=httpx.Response(200, content=b"GLB-BYTES"))
    p = provider._fetch_url("https://cdn/x.glb", tmp_path / "out.glb")
    assert p.exists()
    assert p.read_bytes() == b"GLB-BYTES"
