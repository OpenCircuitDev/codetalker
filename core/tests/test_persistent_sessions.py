"""Tests for PersistentSessionStore."""
import pytest
from pathlib import Path
from claude_code_talker.persistent_sessions import PersistentSessionStore


@pytest.fixture
def store(tmp_path):
    return PersistentSessionStore(sessions_dir=tmp_path)


def test_save_creates_yaml_file(store, tmp_path):
    store.save("abc-123", {"live_overlay": {"voice": {"model": "marvin"}},
                            "enabled": True, "attached_profile": None,
                            "display_name": None, "last_modified": 1.0})
    assert (tmp_path / "abc-123.yaml").exists()


def test_get_round_trips(store):
    payload = {"live_overlay": {"voice": {"model": "marvin"}},
               "enabled": True, "attached_profile": "verbose",
               "display_name": "MDCycle", "last_modified": 1.0}
    store.save("abc-123", payload)
    assert store.get("abc-123") == payload


def test_get_missing_returns_none(store):
    assert store.get("nope") is None


def test_list_returns_session_ids_sorted(store):
    for sid in ["zeta", "alpha", "middle"]:
        store.save(sid, {"live_overlay": {}, "enabled": True,
                         "attached_profile": None, "display_name": None,
                         "last_modified": 1.0})
    assert store.list() == ["alpha", "middle", "zeta"]


def test_list_empty_when_no_dir(tmp_path):
    s = PersistentSessionStore(sessions_dir=tmp_path / "does-not-exist")
    assert s.list() == []


def test_delete_removes_file(store, tmp_path):
    store.save("temp", {"live_overlay": {}, "enabled": True,
                        "attached_profile": None, "display_name": None,
                        "last_modified": 1.0})
    store.delete("temp")
    assert not (tmp_path / "temp.yaml").exists()


def test_delete_missing_is_noop(store):
    store.delete("nope")  # must not raise


def test_exists(store):
    assert not store.exists("x")
    store.save("x", {"live_overlay": {}, "enabled": True,
                     "attached_profile": None, "display_name": None,
                     "last_modified": 1.0})
    assert store.exists("x")


def test_save_atomic_no_partial_file_on_rename_fail(store, tmp_path, monkeypatch):
    """If rename fails, no .yaml file should exist."""
    def fail_replace(self, target):
        raise OSError("simulated rename failure")
    monkeypatch.setattr(Path, "replace", fail_replace)
    with pytest.raises(OSError):
        store.save("doomed", {"live_overlay": {}, "enabled": True,
                              "attached_profile": None, "display_name": None,
                              "last_modified": 1.0})
    assert not (tmp_path / "doomed.yaml").exists()


def test_get_corrupted_yaml_returns_none(store, tmp_path):
    """Corrupted YAML on disk → log warn, return None."""
    (tmp_path / "bad.yaml").write_text("{not valid yaml: [unclosed")
    assert store.get("bad") is None


# --- Task 10: session_id validation ---

from claude_code_talker.persistent_sessions import is_valid_session_id, SessionIdError


def test_valid_session_ids():
    for sid in ["abc", "abc-123", "ae140158-bc1d-4289-a60a-a9be18359937", "a" * 128]:
        assert is_valid_session_id(sid)


def test_invalid_session_ids():
    for sid in ["", "  ", "../etc/passwd", "name/with/slash", "a" * 129,
                "name.with.dot", "café", "💀"]:
        assert not is_valid_session_id(sid)


def test_save_rejects_invalid_session_id(store):
    with pytest.raises(SessionIdError):
        store.save("../etc/passwd", {"live_overlay": {}, "enabled": True,
                                      "attached_profile": None, "display_name": None,
                                      "last_modified": 1.0})


def test_get_rejects_invalid_session_id(store):
    with pytest.raises(SessionIdError):
        store.get("../etc/passwd")


def test_delete_rejects_invalid_session_id(store):
    with pytest.raises(SessionIdError):
        store.delete("../etc/passwd")
