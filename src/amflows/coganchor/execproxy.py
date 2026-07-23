"""Standing in for a process that should have run on the target.

When a traced process calls ``execve``, coganchor does not let the new image
load.  It steals the process's three standard descriptors with
``pidfd_getfd``, runs the command on the target, and pumps the target's I/O
through those very descriptors.  The agent's pipe therefore carries machine
B's output, and once the command finishes the stalled ``execve`` is rewritten
into ``exit_group`` with the remote status.

From the agent's point of view a perfectly ordinary child process ran and
exited -- it just happened on another machine.
"""

from __future__ import annotations

import fcntl
import logging
import os
import queue
import selectors
import struct
import termios
import threading
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from typing import Any

from amflows.coganchor.proto import CHUNK_SIZE, Stream
from amflows.coganchor.remote import ExecHandle, RemoteClient

__all__ = ["ExecProxy", "ExecResult"]

log = logging.getLogger(__name__)

#: How often the stdin pump re-checks whether the command has finished.
_STDIN_POLL = 0.2

#: Warn once this many undelivered output chunks have piled up.
_BACKLOG_WARN_CHUNKS = 1024


@dataclass(slots=True)
class ExecResult:
    """Outcome of a remote command, in ``wait(2)`` terms."""

    exit_code: int | None = None
    signal: int | None = None

    @property
    def wait_status(self) -> int:
        """Status to report to the agent, following shell convention."""
        if self.signal is not None:
            return 128 + self.signal
        return self.exit_code if self.exit_code is not None else 1


class ExecProxy:
    """Bridges one stalled tracee to one command running on the target."""

    def __init__(
        self,
        client: RemoteClient,
        pid: int,
        argv: list[str],
        cwd: str,
        env: dict[str, str],
        stdio: tuple[int, int, int],
        on_finish: Callable[[int, ExecResult], None],
        *,
        program: str | None = None,
        tty: bool = False,
    ) -> None:
        self._client = client
        self.pid = pid
        self._argv = argv
        self._program = program
        self._cwd = cwd
        self._env = env
        self._stdin_fd, self._stdout_fd, self._stderr_fd = stdio
        self._on_finish = on_finish
        self._tty = tty
        self._outbox: queue.SimpleQueue[tuple[Stream, bytes] | None] = (
            queue.SimpleQueue()
        )
        self._stop = threading.Event()
        self._result = ExecResult(exit_code=1)
        self._handle: ExecHandle | None = None
        self._forwarded: set[int] = set()
        self._warned_about_backlog = False
        self._stdin_thread: threading.Thread | None = None

    # ------------------------------------------------------------------ startup

    def start(self) -> None:
        """Launch the command, then start pumping its I/O.

        The request goes out first: if the connection is gone it raises here,
        before any thread or borrowed descriptor has to be cleaned up.  Output
        arriving in the meantime queues up safely.
        """
        try:
            self._handle = self._client.start_exec(
                self._argv,
                self._cwd,
                self._env,
                on_output=self._on_output,
                on_exit=self._on_exit,
                tty=self._tty,
                winsize=_window_size(self._stdin_fd) if self._tty else None,
                program=self._program,
            )
        except OSError:
            self._close_stdio()
            raise
        _spawn(self._pump_output, f"exec-out-{self.pid}")
        self._stdin_thread = _spawn(self._pump_stdin, f"exec-in-{self.pid}")

    def forward_signal(self, signum: int) -> None:
        """Relay a signal aimed at the stalled tracee to the remote command."""
        if signum in self._forwarded:
            return
        self._forwarded.add(signum)
        if self._handle is not None:
            log.debug(
                "forwarding signal %d to remote command for pid %d", signum, self.pid
            )
            self._handle.signal(signum)

    def abandon(self) -> None:
        """The tracee died; kill the remote command and stop pumping."""
        if self._handle is not None:
            self._handle.signal(9)
        self._stop.set()
        self._outbox.put(None)

    # ------------------------------------------------------- remote callbacks

    def _on_output(self, stream: Stream, data: bytes) -> None:
        self._outbox.put((stream, data))
        if (
            not self._warned_about_backlog
            and self._outbox.qsize() > _BACKLOG_WARN_CHUNKS
        ):
            self._warned_about_backlog = True
            log.warning(
                "the remote command for pid %d has produced far more output than "
                "the agent is reading; it is being buffered here",
                self.pid,
            )

    def _on_exit(self, result: dict[str, Any] | None, error: OSError | None) -> None:
        if error is not None:
            self._report_failure(error)
        elif result is not None:
            self._result = ExecResult(
                exit_code=result.get("exit_code"), signal=result.get("signal")
            )
        self._outbox.put(None)

    def _report_failure(self, error: OSError) -> None:
        message = (
            f"coganchor: {' '.join(self._argv[:1]) or 'command'}: {error.strerror}\n"
        )
        self._outbox.put((Stream.STDERR, message.encode()))
        # 126/127 match the shell's "found but not executable" / "not found".
        self._result = ExecResult(exit_code=127 if error.errno == 2 else 126)

    # ------------------------------------------------------------------- pumps

    def _pump_output(self) -> None:
        """Write remote output into the tracee's own descriptors, then finish."""
        targets = {Stream.STDOUT: self._stdout_fd, Stream.STDERR: self._stderr_fd}
        try:
            while (item := self._outbox.get()) is not None:
                stream, data = item
                fd = targets.get(stream, self._stdout_fd)
                if fd >= 0:
                    _write_all(fd, data)
        finally:
            # Stop and join the stdin pump before closing the borrowed
            # descriptors, or their numbers could be reused underneath it.
            self._stop.set()
            if self._stdin_thread is not None:
                self._stdin_thread.join(timeout=_STDIN_POLL * 5)
            self._close_stdio()
            self._on_finish(self.pid, self._result)

    def _pump_stdin(self) -> None:
        """Forward whatever the agent gave the command as stdin.

        A redirected file (``cmd < input``) cannot be watched with epoll, so in
        that case the descriptor is drained directly -- it is always readable
        and always reaches end of file.
        """
        handle = self._handle
        if self._stdin_fd < 0 or handle is None:
            return
        selector = _pollable(self._stdin_fd)
        try:
            while not self._stop.is_set():
                if selector is not None and (
                    not selector.select(_STDIN_POLL) or self._stop.is_set()
                ):
                    continue
                try:
                    data = os.read(self._stdin_fd, CHUNK_SIZE)
                except OSError:
                    break
                if not data:
                    break
                try:
                    handle.send_stdin(data)
                except OSError:
                    break  # the target is gone; the exit path reports it
        finally:
            if selector is not None:
                selector.close()
            if not self._stop.is_set():
                with suppress(OSError):
                    handle.close_stdin()

    def _close_stdio(self) -> None:
        for fd in (self._stdin_fd, self._stdout_fd, self._stderr_fd):
            if fd >= 0:
                with suppress(OSError):
                    os.close(fd)


def _spawn(target: Callable[[], None], name: str) -> threading.Thread:
    thread = threading.Thread(target=target, name=name, daemon=True)
    thread.start()
    return thread


def _window_size(fd: int) -> tuple[int, int] | None:
    """Rows and columns of the terminal on ``fd``.

    Without this the remote pty is created at 0x0, and anything that lays out
    its output -- a pager, a progress bar, ``ls`` -- gets the size wrong.
    """
    try:
        packed = fcntl.ioctl(fd, termios.TIOCGWINSZ, struct.pack("HHHH", 0, 0, 0, 0))
    except OSError:
        return None
    rows, columns = struct.unpack("HHHH", packed)[:2]
    return (rows, columns) if rows and columns else None


def _pollable(fd: int) -> selectors.BaseSelector | None:
    """Return a selector watching ``fd``, or ``None`` if it cannot be polled."""
    selector = selectors.DefaultSelector()
    try:
        selector.register(fd, selectors.EVENT_READ)
    except (OSError, ValueError):
        selector.close()
        return None
    return selector


def _write_all(fd: int, data: bytes) -> None:
    view = memoryview(data)
    while view:
        try:
            written = os.write(fd, view)
        except BrokenPipeError:
            return
        except OSError as exc:
            log.debug("dropping %d bytes of remote output: %s", len(view), exc)
            return
        view = view[written:]
