"""Tests for ProfileStore."""
import pytest
from pathlib import Path
from claude_code_talker.profiles import ProfileStore


@pytest.fixture
def store(tmp_path):
    return ProfileStore(profiles_dir=tmp_path)


def test_save_creates_yaml_file(store, tmp_path):
    store.save("verbose-marvin", {"voice": {"model": "marvin"}, "active_mode": "live"})
    assert (tmp_path / "verbose-marvin.yaml").exists()


def test_get_round_trips(store):
    payload = {"voice": {"model": "marvin", "rate": 1.2}, "active_mode": "live"}
    store.save("verbose-marvin", payload)
    assert store.get("verbose-marvin") == payload


def test_get_missing_raises(store):
    with pytest.raises(FileNotFoundError):
        store.get("nope")


def test_list_returns_names_sorted(store):
    store.save("alpha", {"x": 1})
    store.save("zeta", {"x": 1})
    store.save("middle", {"x": 1})
    assert store.list() == ["alpha", "middle", "zeta"]


def test_list_empty_when_no_dir(tmp_path):
    s = ProfileStore(profiles_dir=tmp_path / "does-not-exist")
    assert s.list() == []


def test_delete_removes_file(store, tmp_path):
    store.save("temp", {"x": 1})
    store.delete("temp")
    assert not (tmp_path / "temp.yaml").exists()


def test_delete_missing_is_noop(store):
    store.delete("nope")  # must not raise


def test_exists(store):
    assert not store.exists("x")
    store.save("x", {"y": 1})
    assert store.exists("x")


def test_save_atomic_no_partial_file_on_interrupt(store, tmp_path, monkeypatch):
    """If write is interrupted, the .yaml file must not exist (only the .tmp could)."""
    real_replace = Path.replace
    def fail_replace(self, target):
        raise OSError("simulated rename failure")
    monkeypatch.setattr(Path, "replace", fail_replace)
    with pytest.raises(OSError):
        store.save("doomed", {"x": 1})
    assert not (tmp_path / "doomed.yaml").exists()


def test_list_skips_corrupted_files(store, tmp_path):
    store.save("good", {"x": 1})
    (tmp_path / "bad.yaml").write_text("{not valid yaml: [unclosed")
    # list() doesn't parse, just lists files
    assert sorted(store.list()) == ["bad", "good"]
