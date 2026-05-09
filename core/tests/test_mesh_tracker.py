"""Phase 25b — MeshJobTracker tests."""
from __future__ import annotations

import pytest

from claude_code_talker.mesh.tracker import MeshJob, MeshJobTracker


def test_create_persists_a_job(tmp_path):
    t = MeshJobTracker(tmp_path)
    job = t.create(provider="hyper3d", character_id="char-buddy", prompt="a fox")
    assert job.status == "queued"
    assert job.provider == "hyper3d"
    assert job.character_id == "char-buddy"


def test_set_provider_job_id_updates_record(tmp_path):
    t = MeshJobTracker(tmp_path)
    job = t.create(provider="hyper3d", character_id="x", prompt="x")
    t.set_provider_job_id(job.job_id, "hyper3d-abc")
    assert t.get(job.job_id).provider_job_id == "hyper3d-abc"


def test_set_status_running(tmp_path):
    t = MeshJobTracker(tmp_path)
    job = t.create(provider="meshy", character_id="x", prompt="x")
    t.set_status(job.job_id, "running", progress=0.5)
    assert t.get(job.job_id).status == "running"
    assert t.get(job.job_id).progress == 0.5


def test_set_succeeded_records_model_path(tmp_path):
    t = MeshJobTracker(tmp_path)
    job = t.create(provider="meshy", character_id="x", prompt="x")
    t.set_succeeded(job.job_id, model_path=str(tmp_path / "x.glb"))
    j = t.get(job.job_id)
    assert j.status == "succeeded"
    assert j.model_path.endswith("x.glb")


def test_set_failed_records_error(tmp_path):
    t = MeshJobTracker(tmp_path)
    job = t.create(provider="meshy", character_id="x", prompt="x")
    t.set_failed(job.job_id, error="api down")
    j = t.get(job.job_id)
    assert j.status == "failed"
    assert j.error == "api down"


def test_persists_across_instances(tmp_path):
    t1 = MeshJobTracker(tmp_path)
    job = t1.create(provider="tripo3d", character_id="x", prompt="x")
    t2 = MeshJobTracker(tmp_path)
    assert t2.get(job.job_id) is not None


def test_list_returns_jobs_and_skips_corrupt(tmp_path):
    t = MeshJobTracker(tmp_path)
    t.create(provider="hyper3d", character_id="a", prompt="x")
    t.create(provider="meshy", character_id="b", prompt="y")
    # add a corrupt sidecar
    (tmp_path / "corrupt.json").write_text("not json", encoding="utf-8")
    jobs = t.list()
    assert len(jobs) == 2
