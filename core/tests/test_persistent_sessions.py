"""Tests for PersistentSessionStore."""
import pytest
from pathlib import Path
from claude_code_talker.persistent_sessions import (
    PersistentSessionStore,
    _migrate_promoted_keys,
    _PROMOTED_KEYS,
)


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


# --- Task 11: Schema-drift / unknown-keys preservation ---

def test_unknown_keys_preserved_on_roundtrip(store):
    """Schema drift: unknown top-level keys roundtrip via save → get."""
    payload = {
        "live_overlay": {"voice": {"model": "marvin"}},
        "enabled": True,
        "attached_profile": None,
        "display_name": None,
        "last_modified": 1.0,
        "future_field_we_dont_know_about": "preserved",
        "another_unknown": {"nested": "data"},
    }
    store.save("abc", payload)
    loaded = store.get("abc")
    assert loaded == payload
    assert loaded["future_field_we_dont_know_about"] == "preserved"
    assert loaded["another_unknown"]["nested"] == "data"


# --- v0.1.0 unification: self-healing migration of promoted keys ---

def test_migrate_lifts_pinned_from_live_overlay():
    """When `pinned` was orphaned under live_overlay (pre-fix daemon code),
    reading the overlay lifts it to top-level + strips the nested copy."""
    data = {
        "live_overlay": {"active_mode": "brief", "pinned": True},
        "display_name": None,
        "workspace_group": "OCDev",
    }
    out = _migrate_promoted_keys(data)
    assert out["pinned"] is True
    assert "pinned" not in out["live_overlay"]
    # Other live_overlay keys stay put.
    assert out["live_overlay"]["active_mode"] == "brief"


def test_migrate_lifts_all_promoted_keys():
    """All keys in _PROMOTED_KEYS get the same treatment."""
    nested = {k: f"value_{k}" for k in _PROMOTED_KEYS}
    nested["other_unknown"] = "stays_here"
    data = {"live_overlay": dict(nested), "enabled": True}
    out = _migrate_promoted_keys(data)
    for k in _PROMOTED_KEYS:
        assert out[k] == f"value_{k}", f"{k} should lift to top-level"
        assert k not in out["live_overlay"], f"{k} should be stripped from nested"
    # Non-promoted keys stay nested.
    assert out["live_overlay"]["other_unknown"] == "stays_here"


def test_migrate_top_level_wins_over_nested():
    """If both top-level and nested exist, top-level value is kept (newer
    write); nested is stripped."""
    data = {
        "live_overlay": {"pinned": False, "workspace_group": "OldGroup"},
        "pinned": True,
        "workspace_group": "NewGroup",
    }
    out = _migrate_promoted_keys(data)
    assert out["pinned"] is True
    assert out["workspace_group"] == "NewGroup"
    assert "pinned" not in out["live_overlay"]
    assert "workspace_group" not in out["live_overlay"]


def test_migrate_no_op_when_no_live_overlay():
    """Migration is a no-op when live_overlay is missing or non-dict."""
    data = {"display_name": "Test"}
    out = _migrate_promoted_keys(data)
    assert out == {"display_name": "Test"}


def test_migrate_no_op_when_no_promoted_keys_nested():
    """live_overlay exists but has no promoted keys — no-op."""
    data = {
        "live_overlay": {"active_mode": "brief", "voice": {"model": "x"}},
        "display_name": "Foo",
    }
    out = _migrate_promoted_keys(data)
    assert out == data


def test_get_applies_migration_transparently(store, tmp_path):
    """The store's get() applies the migration on read so callers
    never see the orphan shape, even on overlays written by old daemon
    code that didn't recognize the promoted keys."""
    # Simulate an old-daemon write where 'pinned' landed under live_overlay
    # because the merge fell through to the catch-all else-branch.
    raw = """\
live_overlay:
  active_mode: brief
  pinned: true
display_name: null
workspace_group: OCDev
"""
    (tmp_path / "legacy-sid.yaml").write_text(raw, encoding="utf-8")
    loaded = store.get("legacy-sid")
    assert loaded["pinned"] is True
    assert "pinned" not in loaded["live_overlay"]
    assert loaded["workspace_group"] == "OCDev"
