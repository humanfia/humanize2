"""Long-lived remote sessions: process execution and TCP tunnels.

A session owns one protocol ``msg id`` for its whole lifetime.  It streams
:class:`~humanize.coganchor.proto.Kind.CHUNK` frames as output arrives and closes the exchange
with a single :class:`~humanize.coganchor.proto.Kind.RSP`, so the server's reader loop is never
blocked by a slow command.
"""

from __future__ import annotations

import errno
import fcntl
import logging
import os
import pty
import queue
import selectors
import signal
import socket
import struct
import subprocess
import termios
import threading
from contextlib import suppress
from typing import IO, TYPE_CHECKING, Any

from humanize.coganchor.proto import CHUNK_SIZE, Channel, Frame, Stream

if TYPE_CHECKING:
    from humanize.coganchor.serve.exports import ExportTable

__all__ = ["ExecSession", "Session", "TunnelSession", "compose_env"]

log = logging.getLogger(__name__)

#: Environment variables that describe the *client's* machine and must not
#: leak here.  Everything else the agent set (API keys, GIT_*, project
#: variables) passes through, layered on top of this machine's environment.
HOST_SPECIFIC_ENV = frozenset(
    {
        "DISPLAY",
        "HOME",
        "HOSTNAME",
        "HOSTTYPE",
        "LOGNAME",
        "MACHTYPE",
        "MAIL",
        "OLDPWD",
        "OSTYPE",
        "PATH",
        "PWD",
        "SHELL",
        "SHLVL",
        "TEMP",
        "TMP",
        "TMPDIR",
        "USER",
        "WAYLAND_DISPLAY",
        "_",
    }
)

#: Prefixes of variables that are host-specific or belong to coganchor itself.
HOST_SPECIFIC_PREFIXES = ("LD_", "SSH_", "XDG_", "HUMANIZE_")


def compose_env(remote_env: dict[str, str], cwd: str, *, tty: bool) -> dict[str, str]:
    """Build the environment for a remote command.

    Starts from this machine's environment -- so ``PATH``, ``HOME`` and friends
    describe this machine -- and overlays the variables the caller chose.
    """
    env = dict(os.environ)
    for name, value in remote_env.items():
        if name in HOST_SPECIFIC_ENV or name.startswith(HOST_SPECIFIC_PREFIXES):
            continue
        env[name] = value
    env["PWD"] = cwd
    if tty:
        env.setdefault("TERM", "xterm-256color")
    return env


class Session:
    """Base class for a streaming exchange bound to one ``msg id``."""

    def __init__(self, msg_id: int, channel: Channel) -> None:
        self.msg_id = msg_id
        self._channel = channel
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._thread = threading.Thread(
            target=self._guarded_run, name=f"session-{self.msg_id}", daemon=True
        )
        self._thread.start()

    def feed(self, stream: Stream, data: bytes) -> None:
        """Deliver an inbound CHUNK frame."""

    def end_input(self, stream: Stream) -> None:
        """Deliver an inbound END frame."""

    def shutdown(self) -> None:
        """Tear the session down because the connection is going away."""

    def join(self, timeout: float | None = None) -> None:
        if self._thread is not None:
            self._thread.join(timeout)

    def _run(self) -> dict[str, Any]:
        raise NotImplementedError

    def _guarded_run(self) -> None:
        try:
            result = self._run()
        except OSError as exc:
            self._send(Frame.error(self.msg_id, exc))
        except Exception as exc:
            log.exception("session %d failed", self.msg_id)
            self._send(Frame.error(self.msg_id, OSError(errno.EIO, str(exc))))
        else:
            self._send(Frame.reply(self.msg_id, **result))

    def _send(self, frame: Frame) -> None:
        with suppress(Exception):
            self._channel.send(frame)

    def _emit(self, stream: Stream, data: bytes) -> None:
        self._send(Frame.chunk(self.msg_id, stream, data))


class ExecSession(Session):
    """Runs one command on this machine and streams its I/O back."""

    def __init__(
        self,
        msg_id: int,
        channel: Channel,
        table: ExportTable,
        request: dict[str, Any],
    ) -> None:
        super().__init__(msg_id, channel)
        self._table = table
        self._argv: list[str] = list(request["argv"])
        self._program: str | None = request.get("program")
        self._cwd_virtual: str = request["cwd"]
        self._env: dict[str, str] = dict(request.get("env") or {})
        self._tty: bool = bool(request.get("tty"))
        self._winsize: list[int] | None = request.get("winsize")
        self._stdin: queue.Queue[bytes | None] = queue.Queue()
        self._process: subprocess.Popen[bytes] | None = None
        self._started = threading.Event()

    def feed(self, stream: Stream, data: bytes) -> None:
        if stream is Stream.STDIN:
            self._stdin.put(data)

    def end_input(self, stream: Stream) -> None:
        if stream is Stream.STDIN:
            self._stdin.put(None)

    def signal(self, signum: int) -> None:
        """Forward a signal to the remote process group."""
        if not self._started.wait(timeout=5.0):
            return
        process = self._process
        if process is None or process.poll() is not None:
            return
        with suppress(OSError):
            os.killpg(process.pid, signum)

    def shutdown(self) -> None:
        self.signal(signal.SIGKILL)
        self._stdin.put(None)

    def _run(self) -> dict[str, Any]:
        cwd = self._resolve_cwd()
        self._argv = [self._table.rewrite(item) for item in self._argv]
        self._program = self._table.rewrite(self._program) if self._program else None
        self._env = {name: self._table.rewrite(v) for name, v in self._env.items()}
        env = compose_env(self._env, cwd, tty=self._tty)
        master, slave = pty.openpty() if self._tty else (None, None)
        if master is not None and self._winsize:
            rows, cols = self._winsize
            with suppress(OSError):
                fcntl.ioctl(
                    master, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0)
                )
        try:
            process = self._spawn(cwd, env, slave)
        finally:
            if slave is not None:
                os.close(slave)
        self._process = process
        self._started.set()

        writer = threading.Thread(
            target=self._pump_stdin,
            args=(master, process.stdin),
            name=f"stdin-{self.msg_id}",
            daemon=True,
        )
        writer.start()
        try:
            self._pump_output(process, master)
        finally:
            self._stdin.put(None)
            writer.join(timeout=2.0)
            if master is not None:
                _close_quietly(master)
        code = process.wait()
        return {"signal": -code} if code < 0 else {"exit_code": code}

    def _spawn(
        self, cwd: str, env: dict[str, str], slave: int | None
    ) -> subprocess.Popen[bytes]:
        """Start the command, falling back to a PATH lookup for agent-local tools.

        Agents bundle helpers (ripgrep, for instance) under their own install
        directory.  That exact path exists on the client's machine but not here, so if the
        literal path is missing we retry with the bare program name and let
        this machine's ``PATH`` resolve it.
        """
        stdio = slave if slave is not None else subprocess.PIPE
        candidates: list[str | None] = [self._program] if self._program else [None]
        if self._program and os.path.dirname(self._program):
            candidates.append(os.path.basename(self._program))
        last: OSError | None = None
        for executable in candidates:
            try:
                return subprocess.Popen(
                    self._argv,
                    executable=executable,
                    cwd=cwd,
                    env=env,
                    stdin=stdio,
                    stdout=stdio,
                    stderr=stdio,
                    start_new_session=True,
                    # A controlling tty can only be claimed between the fork and the exec, and
                    # the call that claims it is a single ioctl.
                    preexec_fn=_attach_controlling_tty if self._tty else None,  # noqa: PLW1509
                    close_fds=True,
                )
            except (FileNotFoundError, NotADirectoryError) as exc:
                last = exc
        raise (
            last
            if last is not None
            else FileNotFoundError(errno.ENOENT, "no program to run")
        )

    def _resolve_cwd(self) -> str:
        try:
            return self._table.resolve(self._cwd_virtual)
        except PermissionError:
            # A command launched from outside the workspace must still run;
            # fall back to this machine's home directory.
            return os.path.expanduser("~")

    def _pump_stdin(self, master: int | None, pipe: IO[bytes] | None) -> None:
        """Forward queued stdin until the peer signals end of input."""
        fd = master if master is not None else (pipe.fileno() if pipe else -1)
        try:
            while (data := self._stdin.get()) is not None:
                if fd < 0:
                    continue
                try:
                    os.write(fd, data)
                except OSError:
                    break
        finally:
            # Closing the pipe delivers EOF to the child.  The pty master is
            # shared with the output pump, so its owner closes it instead.
            if master is None and pipe is not None:
                _close_quietly(pipe)

    def _pump_output(
        self, process: subprocess.Popen[bytes], master: int | None
    ) -> None:
        selector = selectors.DefaultSelector()
        if master is not None:
            selector.register(master, selectors.EVENT_READ, Stream.STDOUT)
        else:
            assert process.stdout is not None  # noqa: S101
            assert process.stderr is not None  # noqa: S101
            selector.register(process.stdout, selectors.EVENT_READ, Stream.STDOUT)
            selector.register(process.stderr, selectors.EVENT_READ, Stream.STDERR)
        try:
            while selector.get_map():
                for key, _ in selector.select():
                    try:
                        data = os.read(key.fd, CHUNK_SIZE)
                    except OSError:
                        data = b""  # a pty master reports EIO once the child is gone
                    if not data:
                        selector.unregister(key.fileobj)
                        continue
                    self._emit(key.data, data)
        finally:
            selector.close()
            for stream in (process.stdout, process.stderr):
                if stream is not None:
                    _close_quietly(stream)


class TunnelSession(Session):
    """Opens an outbound TCP connection from this machine and relays it."""

    def __init__(self, msg_id: int, channel: Channel, request: dict[str, Any]) -> None:
        super().__init__(msg_id, channel)
        self._host: str = request["host"]
        self._port: int = int(request["port"])
        self._socket: socket.socket | None = None
        self._ready = threading.Event()

    def feed(self, stream: Stream, data: bytes) -> None:  # noqa: ARG002
        if not self._ready.wait(timeout=30.0) or self._socket is None:
            return
        try:
            self._socket.sendall(data)
        except OSError:
            self.shutdown()

    def end_input(self, stream: Stream) -> None:  # noqa: ARG002
        if self._socket is not None:
            with suppress(OSError):
                self._socket.shutdown(socket.SHUT_WR)

    def shutdown(self) -> None:
        if self._socket is not None:
            with suppress(OSError):
                self._socket.shutdown(socket.SHUT_RDWR)

    def _run(self) -> dict[str, Any]:
        sock = socket.create_connection((self._host, self._port), timeout=30.0)
        sock.settimeout(None)
        self._socket = sock
        self._ready.set()
        try:
            while True:
                try:
                    data = sock.recv(CHUNK_SIZE)
                except OSError:
                    break
                if not data:
                    break
                self._emit(Stream.DATA, data)
        finally:
            self._ready.set()
            _close_quietly(sock)
        return {}


def _attach_controlling_tty() -> None:  # pragma: no cover - runs in the forked child
    os.setsid()
    with suppress(OSError):
        fcntl.ioctl(0, termios.TIOCSCTTY, 0)


def _close_quietly(handle: Any) -> None:
    with suppress(OSError):
        os.close(handle) if isinstance(handle, int) else handle.close()
