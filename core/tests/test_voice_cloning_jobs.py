"""Phase 25c — voice cloning job tracker tests."""
from __future__ import annotations

from claude_code_talker.voice.cloning_jobs import CloneJobTracker


def test_create_job_queues_and_returns_id(tmp_path):
    t = CloneJobTracker(tmp_path)
    job = t.create("char-buddy", b"audio bytes", "audio/webm")
    assert job.status == "queued"
    assert job.character_id == "char-buddy"


def test_get_returns_persisted_job(tmp_path):
    t = CloneJobTracker(tmp_path)
    job = t.create("char-buddy", b"a", "audio/webm")
    same = t.get(job.job_id)
    assert same is not None
    assert same.job_id == job.job_id


def test_set_running_and_succeeded(tmp_path):
    t = CloneJobTracker(tmp_path)
    job = t.create("c", b"a", "audio/webm")
    t.set_running(job.job_id)
    assert t.get(job.job_id).status == "running"
    t.set_succeeded(job.job_id, voice_ref="char-c")
    assert t.get(job.job_id).status == "succeeded"
    assert t.get(job.job_id).voice_ref == "char-c"


def test_set_failed_records_error(tmp_path):
    t = CloneJobTracker(tmp_path)
    job = t.create("c", b"a", "audio/webm")
    t.set_failed(job.job_id, error="boom")
    j = t.get(job.job_id)
    assert j.status == "failed"
    assert j.error == "boom"


def test_get_unknown_job_returns_none(tmp_path):
    t = CloneJobTracker(tmp_path)
    assert t.get("nope") is None


def test_jobs_persist_across_tracker_instances(tmp_path):
    t1 = CloneJobTracker(tmp_path)
    job = t1.create("c", b"a", "audio/webm")
    t1.set_succeeded(job.job_id, voice_ref="char-c")
    t2 = CloneJobTracker(tmp_path)  # new instance
    assert t2.get(job.job_id).status == "succeeded"
