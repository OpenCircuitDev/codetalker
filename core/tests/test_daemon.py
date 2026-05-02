"""Tests for daemon process management."""
import os
import pytest
from pathlib import Path
from claude_code_talker.daemon import (
    acquire_pidfile, read_pidfile, release_pidfile, PidfileLockedError,
)


def test_acquire_pidfile_writes_current_pid(tmp_path):
    pidfile = tmp_path / "codetalker.pid"
    acquire_pidfile(pidfile)
    assert pidfile.exists()
    assert pidfile.read_text().strip() == str(os.getpid())
    release_pidfile(pidfile)


def test_acquire_pidfile_raises_if_exists_and_alive(tmp_path):
    pidfile = tmp_path / "codetalker.pid"
    acquire_pidfile(pidfile)
    with pytest.raises(PidfileLockedError):
        acquire_pidfile(pidfile)
    release_pidfile(pidfile)


def test_release_pidfile_removes_file(tmp_path):
    pidfile = tmp_path / "codetalker.pid"
    acquire_pidfile(pidfile)
    release_pidfile(pidfile)
    assert not pidfile.exists()


def test_read_pidfile_returns_pid(tmp_path):
    pidfile = tmp_path / "codetalker.pid"
    acquire_pidfile(pidfile)
    assert read_pidfile(pidfile) == os.getpid()
    release_pidfile(pidfile)


def test_read_pidfile_returns_none_when_absent(tmp_path):
    pidfile = tmp_path / "codetalker.pid"
    assert read_pidfile(pidfile) is None
