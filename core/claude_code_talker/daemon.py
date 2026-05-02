"""Daemon process management — pidfile, port, spawn-detached, PID-alive checks."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


class PidfileLockedError(Exception):
    """Raised when a pidfile is already held by a live process."""


def acquire_pidfile(path: Path) -> None:
    """Atomically create the pidfile with the current PID.

    Raises PidfileLockedError if a live process already holds it.
    Stale pidfiles (process not alive) are replaced silently.
    """
    if path.exists():
        existing_pid = read_pidfile(path)
        if existing_pid is not None and is_process_alive(existing_pid):
            raise PidfileLockedError(f"pidfile held by live PID {existing_pid}")
        # Stale; remove and proceed.
        try:
            path.unlink()
        except OSError:
            pass

    # Atomic create: O_EXCL | O_CREAT prevents races.
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL)
    try:
        os.write(fd, str(os.getpid()).encode("utf-8"))
    finally:
        os.close(fd)


def release_pidfile(path: Path) -> None:
    """Remove the pidfile. No-op if it doesn't exist."""
    try:
        path.unlink()
    except FileNotFoundError:
        pass


def read_pidfile(path: Path) -> int | None:
    """Return the PID stored in the pidfile, or None if absent/invalid."""
    try:
        text = path.read_text().strip()
    except (FileNotFoundError, OSError):
        return None
    try:
        return int(text)
    except ValueError:
        return None


def is_process_alive(pid: int) -> bool:
    """Cross-platform PID-alive check."""
    if pid <= 0:
        return False
    if sys.platform == "win32":
        import ctypes
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        STILL_ACTIVE = 259
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            return False
        try:
            exit_code = ctypes.c_ulong()
            ok = kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code))
            return bool(ok) and exit_code.value == STILL_ACTIVE
        finally:
            kernel32.CloseHandle(handle)
    else:
        try:
            os.kill(pid, 0)
            return True
        except ProcessLookupError:
            return False
        except PermissionError:
            return True  # exists but not ours — still alive


DAEMON_PORT = 17832
DAEMON_PIDFILE = Path.home() / ".claude" / "scripts" / "codetalker.pid"
DAEMON_LOGFILE = Path.home() / ".claude" / "scripts" / "codetalker.log"
DAEMON_HOST = "127.0.0.1"


def daemon_url() -> str:
    """Return the SSE endpoint URL for the daemon."""
    return f"http://{DAEMON_HOST}:{DAEMON_PORT}/sse"


def spawn_detached(cmd: list[str], log_path: Path | None = None) -> int:
    """Spawn a fully detached background process.

    The child process becomes session leader (Unix) or detached (Windows) so
    it survives the parent exiting. stdin is /dev/null; stdout and stderr
    redirect to log_path (or /dev/null if not provided).
    """
    log_path = log_path or DAEMON_LOGFILE
    log_path.parent.mkdir(parents=True, exist_ok=True)

    log_fd = open(str(log_path), "ab", buffering=0)
    devnull_in = open(os.devnull, "rb")

    if sys.platform == "win32":
        # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
        flags = 0x00000008 | 0x00000200
        kwargs = dict(
            creationflags=flags,
            close_fds=True,
        )
    else:
        # New session leader so signals to parent don't propagate.
        kwargs = dict(
            start_new_session=True,
            close_fds=True,
        )

    proc = subprocess.Popen(
        cmd,
        stdin=devnull_in,
        stdout=log_fd,
        stderr=log_fd,
        **kwargs,
    )
    return proc.pid


import asyncio


async def _call_shutdown_tool() -> None:
    """Connect to the running daemon's MCP endpoint and call tts_shutdown."""
    from mcp import ClientSession
    from mcp.client.sse import sse_client

    try:
        async with sse_client(daemon_url()) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                await session.call_tool("tts_shutdown", {})
                print("shutdown signal sent")
    except Exception as e:
        print(f"shutdown failed: {e}", file=sys.stderr)


def stop_daemon():
    """CLI entry point for `claude-code-talker stop`."""
    pid = read_pidfile(DAEMON_PIDFILE)
    if pid is None:
        print("daemon is not running (no pidfile)")
        return
    if not is_process_alive(pid):
        print(f"stale pidfile (PID {pid} not alive); removing")
        release_pidfile(DAEMON_PIDFILE)
        return
    print(f"requesting shutdown of daemon PID {pid}...")
    asyncio.run(_call_shutdown_tool())


def serve_foreground():
    """Run the daemon in the foreground until shutdown signal.

    Acquires the pidfile, builds the ASGI app with the 9 MCP tools registered,
    then drives uvicorn on DAEMON_HOST:DAEMON_PORT.  MCP clients connect via
    the SSE endpoint at http://DAEMON_HOST:DAEMON_PORT/sse.
    """
    from claude_code_talker.server import build_server_state, build_asgi_app
    import uvicorn

    try:
        acquire_pidfile(DAEMON_PIDFILE)
    except PidfileLockedError as e:
        print(f"daemon already running: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"claude-code-talker daemon starting (pid {os.getpid()})")
    print(f"  pidfile: {DAEMON_PIDFILE}")
    print(f"  endpoint: {daemon_url()}")

    state = build_server_state()
    app = build_asgi_app(state)

    config = uvicorn.Config(
        app,
        host=DAEMON_HOST,
        port=DAEMON_PORT,
        log_level="warning",
    )
    server = uvicorn.Server(config)
    state.uvicorn_server = server  # so tts_shutdown can signal it

    try:
        server.run()
    except KeyboardInterrupt:
        print("interrupted")
    finally:
        if state.audio_queue is not None:
            state.audio_queue.shutdown(drain_timeout=5.0)
        release_pidfile(DAEMON_PIDFILE)
        print("daemon stopped cleanly")
