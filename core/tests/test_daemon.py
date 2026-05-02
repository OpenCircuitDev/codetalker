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


from unittest.mock import patch, MagicMock
from claude_code_talker.daemon import spawn_detached


def test_spawn_detached_invokes_subprocess():
    with patch("claude_code_talker.daemon.subprocess.Popen") as mock_popen:
        mock_popen.return_value = MagicMock(pid=12345)
        pid = spawn_detached(["python", "-m", "claude_code_talker.server"])

    assert mock_popen.called
    args, kwargs = mock_popen.call_args
    # Ensure the command is passed
    assert args[0] == ["python", "-m", "claude_code_talker.server"]
    # Detached child — no stdin/stdout/stderr piping
    assert kwargs.get("stdin") is not None  # DEVNULL or similar
    assert kwargs.get("stdout") is not None
    assert kwargs.get("stderr") is not None
    assert pid == 12345


def test_stop_daemon_no_pidfile_prints_message(tmp_path, capsys):
    """If pidfile doesn't exist, stop_daemon should print 'not running' and exit."""
    with patch("claude_code_talker.daemon.DAEMON_PIDFILE", tmp_path / "no.pid"):
        from claude_code_talker.daemon import stop_daemon
        stop_daemon()
        captured = capsys.readouterr()
        assert "not running" in captured.out.lower()


def test_stop_daemon_calls_shutdown_tool(tmp_path):
    """If pidfile exists with live PID, stop_daemon should call _call_shutdown_tool."""
    pidfile = tmp_path / "codetalker.pid"
    pidfile.write_text(str(os.getpid()))

    with patch("claude_code_talker.daemon.DAEMON_PIDFILE", pidfile), \
         patch("claude_code_talker.daemon._call_shutdown_tool") as mock_call:
        from claude_code_talker.daemon import stop_daemon
        stop_daemon()
        mock_call.assert_called_once()


def test_stop_daemon_removes_stale_pidfile(tmp_path, capsys):
    """If pidfile exists but PID is dead, stop_daemon should remove it and report."""
    pidfile = tmp_path / "codetalker.pid"
    pidfile.write_text("999999")  # almost certainly dead

    with patch("claude_code_talker.daemon.DAEMON_PIDFILE", pidfile):
        from claude_code_talker.daemon import stop_daemon
        stop_daemon()
        captured = capsys.readouterr()
        assert "stale" in captured.out.lower()
        assert not pidfile.exists()
