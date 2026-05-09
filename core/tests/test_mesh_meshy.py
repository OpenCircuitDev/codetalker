"""Phase 25b — Meshy v2 adapter tests."""
from __future__ import annotations

import httpx
import pytest
import respx

from claude_code_talker.mesh.meshy import MeshyProvider


@pytest.fixture
def provider():
    return MeshyProvider(api_key="m-test")


@respx.mock
def test_start_text_to_3d(provider):
    respx.post("https://api.meshy.ai/openapi/v2/text-to-3d").mock(
        return_value=httpx.Response(200, json={"result": "task-789"})
    )
    job_id = provider.start(prompt="a robot")
    assert job_id == "task-789"


@respx.mock
def test_poll_running(provider):
    respx.get("https://api.meshy.ai/openapi/v2/text-to-3d/task-789").mock(
        return_value=httpx.Response(200, json={"status": "IN_PROGRESS", "progress": 42})
    )
    s = provider.poll("task-789")
    assert s.status == "running"
    assert s.progress == 0.42


@respx.mock
def test_poll_succeeded_extracts_glb_url(provider):
    respx.get("https://api.meshy.ai/openapi/v2/text-to-3d/task-789").mock(
        return_value=httpx.Response(
            200,
            json={
                "status": "SUCCEEDED",
                "model_urls": {
                    "glb": "https://meshy.cdn/m.glb",
                    "fbx": "https://meshy.cdn/m.fbx",
                },
            },
        )
    )
    s = provider.poll("task-789")
    assert s.status == "succeeded"
    assert s.model_url == "https://meshy.cdn/m.glb"


@respx.mock
def test_poll_failed(provider):
    respx.get("https://api.meshy.ai/openapi/v2/text-to-3d/task-789").mock(
        return_value=httpx.Response(
            200,
            json={"status": "FAILED", "task_error": {"message": "rate limit"}},
        )
    )
    s = provider.poll("task-789")
    assert s.status == "failed"
    assert "rate limit" in (s.error or "")


@respx.mock
def test_start_passes_negative_prompt(provider):
    captured = {}

    def cap(req):
        import json

        captured["body"] = json.loads(req.read())
        return httpx.Response(200, json={"result": "x"})

    respx.post("https://api.meshy.ai/openapi/v2/text-to-3d").mock(side_effect=cap)
    provider.start(prompt="hero", negative_prompt="ugly")
    assert captured["body"]["negative_prompt"] == "ugly"
