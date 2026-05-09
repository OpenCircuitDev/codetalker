"""Phase 25b — Mesh3DProvider ABC tests."""
from __future__ import annotations

import pytest

from claude_code_talker.mesh.provider import (
    Mesh3DProvider,
    MeshJobStatus,
    extension_from_url,
)


def test_provider_is_abstract():
    with pytest.raises(TypeError):
        Mesh3DProvider()  # cannot instantiate


def test_mesh_job_status_default_status_is_queued():
    s = MeshJobStatus(provider="x", job_id="j", status="queued")
    assert s.status == "queued"
    assert s.model_url is None


def test_mesh_job_status_terminal_helpers():
    queued = MeshJobStatus("x", "j", "queued")
    running = MeshJobStatus("x", "j", "running")
    succeeded = MeshJobStatus("x", "j", "succeeded", model_url="https://...")
    failed = MeshJobStatus("x", "j", "failed", error="boom")
    assert not queued.is_terminal
    assert not running.is_terminal
    assert succeeded.is_terminal
    assert failed.is_terminal


# Regression tests for the signed-URL bug discovered during Meshy smoke test.
# Real CDN URLs come signed with `?expires=...&signature=...&key-pair-id=...`
# tails — naive rsplit('.', 1) would swallow that into the file extension.

def test_extension_from_url_strips_query_string():
    url = (
        "https://assets.meshy.ai/abc/tasks/019e/output/model.glb"
        "?expires=4931884800&signature=abc123&key-pair-id=K1V"
    )
    assert extension_from_url(url) == "glb"


def test_extension_from_url_clean_url():
    assert extension_from_url("https://cdn.example.com/path/m.fbx") == "fbx"


def test_extension_from_url_known_extensions():
    for ext in ("glb", "gltf", "fbx", "obj", "usdz", "stl", "ply"):
        assert extension_from_url(f"https://x/y.{ext}?sig=x") == ext


def test_extension_from_url_unknown_extension_falls_back():
    # Unknown suffix shouldn't leak into the filesystem path.
    assert extension_from_url("https://x/file.exe") == "glb"


def test_extension_from_url_no_extension_falls_back():
    assert extension_from_url("https://x/no-extension?sig=x") == "glb"


def test_extension_from_url_none_or_empty():
    assert extension_from_url(None) == "glb"
    assert extension_from_url("") == "glb"


def test_extension_from_url_custom_default():
    assert extension_from_url(None, default="fbx") == "fbx"
