"""Phase 25b — Tripo3D adapter tests."""
from __future__ import annotations

import httpx
import pytest
import respx

from claude_code_talker.mesh.tripo3d import Tripo3DProvider


@pytest.fixture
def provider():
    return Tripo3DProvider(api_key="t-test")


@respx.mock
def test_start_text_to_model(provider):
    respx.post("https://api.tripo3d.ai/v2/openapi/task").mock(
        return_value=httpx.Response(200, json={"data": {"task_id": "t-001"}})
    )
    job_id = provider.start(prompt="a sword")
    assert job_id == "t-001"


@respx.mock
def test_poll_running(provider):
    respx.get("https://api.tripo3d.ai/v2/openapi/task/t-001").mock(
        return_value=httpx.Response(200, json={"data": {"status": "running", "progress": 30}})
    )
    s = provider.poll("t-001")
    assert s.status == "running"
    assert s.progress == 0.3


@respx.mock
def test_poll_succeeded(provider):
    respx.get("https://api.tripo3d.ai/v2/openapi/task/t-001").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": {
                    "status": "success",
                    "output": {"model": "https://tripo.cdn/m.glb"},
                }
            },
        )
    )
    s = provider.poll("t-001")
    assert s.status == "succeeded"
    assert s.model_url == "https://tripo.cdn/m.glb"


@respx.mock
def test_poll_failed(provider):
    respx.get("https://api.tripo3d.ai/v2/openapi/task/t-001").mock(
        return_value=httpx.Response(
            200,
            json={"data": {"status": "failed", "error": "bad input"}},
        )
    )
    s = provider.poll("t-001")
    assert s.status == "failed"


@respx.mock
def test_start_with_image_url_uses_image_to_model(provider):
    captured = {}

    def cap(req):
        import json

        captured["body"] = json.loads(req.read())
        return httpx.Response(200, json={"data": {"task_id": "t-img"}})

    respx.post("https://api.tripo3d.ai/v2/openapi/task").mock(side_effect=cap)
    provider.start(prompt="x", image_url="https://img/x.png")
    assert captured["body"]["type"] == "image_to_model"
