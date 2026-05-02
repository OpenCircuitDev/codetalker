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


from claude_code_talker.daemon import is_process_alive


def test_is_process_alive_self():
    assert is_process_alive(os.getpid()) is True


def test_is_process_alive_unlikely_pid():
    # PID 999999 is almost certainly not running on a normal system.
    assert is_process_alive(999999) is False


def test_is_process_alive_invalid():
    assert is_process_alive(0) is False
    assert is_process_alive(-1) is False


def test_acquire_pidfile_replaces_stale(tmp_path):
    """If pidfile exists but PID is dead, acquire should replace it."""
    pidfile = tmp_path / "codetalker.pid"
    pidfile.write_text("999999")  # almost certainly dead

    acquire_pidfile(pidfile)  # should not raise
    assert pidfile.read_text().strip() == str(os.getpid())
    release_pidfile(pidfile)


from claude_code_talker.daemon import DAEMON_PORT, daemon_url


def test_daemon_constants():
    assert DAEMON_PORT == 17832


def test_daemon_url_has_sse_path():
    assert daemon_url() == "http://127.0.0.1:17832/sse"
