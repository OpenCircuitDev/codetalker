"""Phase 25b — Mesh3DProvider ABC tests."""
from __future__ import annotations

import pytest

from claude_code_talker.mesh.provider import Mesh3DProvider, MeshJobStatus


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
