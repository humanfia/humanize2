"""Client for a connection to ``amflows anchor`` on the target.

One reader thread demultiplexes replies by message id.  Filesystem calls are
synchronous -- the traced process is stopped anyway, so blocking the caller
costs nothing -- while :meth:`RemoteClient.start_exec` and
:meth:`RemoteClient.open_tunnel` are asynchronous, because a remote command may
run for minutes and must never stall the supervisor.
"""

from __future__ import annotations

import errno
import itertools
import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, BinaryIO

from amflows.coganchor.proto import (
    CHUNK_SIZE,
    PROTOCOL_VERSION,
    Channel,
    Frame,
    Kind,
    Op,
    ProtocolError,
    RemoteOSError,
    Stream,
)

__all__ = ["ExecHandle", "RemoteClient", "TunnelHandle"]

log = logging.getLogger(__name__)

#: How long a filesystem call may take before the target is presumed dead.
DEFAULT_TIMEOUT = 120.0

ChunkHandler = Callable[[Stream, bytes], None]
DoneHandler = Callable[[dict[str, Any] | None, OSError | None], None]


@dataclass(slots=True)
class _Pending:
    """Bookkeeping for one in-flight exchange."""

    on_chunk: ChunkHandler | None
    on_done: DoneHandler | None
    done: threading.Event = field(default_factory=threading.Event)
    result: dict[str, Any] | None = None
    error: OSError | None = None


class RemoteClient:
    """Speaks the wire protocol to one target."""

    def __init__(self, channel: Channel, timeout: float = DEFAULT_TIMEOUT) -> None:
        self._channel = channel
        self._timeout = timeout
        self._ids = itertools.count(1)
        self._pending: dict[int, _Pending] = {}
        self._lock = threading.Lock()
        self._closed = False
        self._reader = threading.Thread(
            target=self._read_loop, name="remote-reader", daemon=True
        )
        self.info: dict[str, Any] = {}

    # ---------------------------------------------------------------- lifecycle

    def start(self, token: str | None = None) -> dict[str, Any]:
        """Start the reader thread and complete the handshake."""
        self._reader.start()
        self.info = self.call(Op.HELLO, version=PROTOCOL_VERSION, token=token)
        remote_version = self.info.get("version")
        if remote_version != PROTOCOL_VERSION:
            raise ProtocolError(
                f"the target speaks protocol {remote_version}, "
                f"this amflows speaks {PROTOCOL_VERSION}"
            )
        return self.info

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
        self._channel.close()
        self._reader.join(timeout=2.0)
        self._fail_pending(ConnectionResetError(errno.EPIPE, "connection closed"))

    # ----------------------------------------------------------------- requests

    def call(self, op: Op, body: bytes = b"", **meta: Any) -> dict[str, Any]:
        """Issue a request and block until the target replies."""
        msg_id, pending = self._register(None, None)
        self._send(Frame.request(msg_id, op, body, **meta))
        return self._await(msg_id, pending)

    def read_file(self, path: str, sink: BinaryIO) -> dict[str, Any]:
        """Stream a remote file into ``sink``; returns its metadata."""

        def on_chunk(stream: Stream, data: bytes) -> None:
            sink.write(data)

        msg_id, pending = self._register(on_chunk, None)
        self._send(Frame.request(msg_id, Op.READ, path=path))
        return self._await(msg_id, pending)

    def write_file(
        self, path: str, source: BinaryIO, mode: int | None = None
    ) -> dict[str, Any]:
        """Stream a local file to the target, replacing the remote file."""
        msg_id, pending = self._register(None, None)
        self._send(Frame.request(msg_id, Op.WRITE, path=path, mode=mode))
        try:
            while chunk := source.read(CHUNK_SIZE):
                self._send(Frame.chunk(msg_id, Stream.DATA, chunk))
            self._send(Frame.end(msg_id, Stream.DATA))
        except OSError:
            self._discard(msg_id)
            raise
        return self._await(msg_id, pending)

    # --------------------------------------------------------- streaming
    # sessions

    def start_exec(
        self,
        argv: list[str],
        cwd: str,
        env: dict[str, str],
        on_output: ChunkHandler,
        on_exit: DoneHandler,
        *,
        program: str | None = None,
        tty: bool = False,
        winsize: tuple[int, int] | None = None,
    ) -> ExecHandle:
        """Launch a command on the target; callbacks fire on the reader thread.

        ``program`` is the path the tracee passed to ``execve``, which may
        differ from ``argv[0]``; the target falls back to a ``PATH`` lookup if
        that exact path does not exist on the target.
        """
        msg_id, _ = self._register(on_output, on_exit)
        self._send(
            Frame.request(
                msg_id,
                Op.EXEC,
                argv=argv,
                program=program,
                cwd=cwd,
                env=env,
                tty=tty,
                winsize=list(winsize) if winsize else None,
            )
        )
        return ExecHandle(self, msg_id)

    def open_tunnel(
        self, host: str, port: int, on_data: ChunkHandler, on_close: DoneHandler
    ) -> TunnelHandle:
        """Open a TCP connection *from* the target and relay it."""
        msg_id, _ = self._register(on_data, on_close)
        self._send(Frame.request(msg_id, Op.CONNECT, host=host, port=port))
        return TunnelHandle(self, msg_id)

    # ------------------------------------------------------- filesystem helpers

    def listdir(self, path: str) -> dict[str, Any]:
        return self.call(Op.LISTDIR, path=path)

    def mkdir(self, path: str, mode: int = 0o777, parents: bool = False) -> None:
        self.call(Op.MKDIR, path=path, mode=mode, parents=parents)

    def rmdir(self, path: str) -> None:
        self.call(Op.RMDIR, path=path)

    def unlink(self, path: str) -> None:
        self.call(Op.UNLINK, path=path)

    def rename(self, src: str, dst: str, replace: bool = True) -> None:
        self.call(Op.RENAME, src=src, dst=dst, replace=replace)

    def symlink(self, target: str, path: str) -> None:
        self.call(Op.SYMLINK, target=target, path=path)

    def link(self, src: str, dst: str) -> None:
        self.call(Op.LINK, src=src, dst=dst)

    def chmod(self, path: str, mode: int) -> None:
        self.call(Op.CHMOD, path=path, mode=mode)

    def utime(self, path: str, atime_ns: int | None, mtime_ns: int | None) -> None:
        self.call(Op.UTIME, path=path, atime_ns=atime_ns, mtime_ns=mtime_ns)

    # ---------------------------------------------------------------- internals

    def _register(
        self, on_chunk: ChunkHandler | None, on_done: DoneHandler | None
    ) -> tuple[int, _Pending]:
        pending = _Pending(on_chunk, on_done)
        msg_id = next(self._ids)
        with self._lock:
            if self._closed:
                raise ConnectionResetError(
                    errno.EPIPE, "the connection to the target is closed"
                )
            self._pending[msg_id] = pending
        return msg_id, pending

    def _discard(self, msg_id: int) -> None:
        with self._lock:
            self._pending.pop(msg_id, None)

    def _send(self, frame: Frame) -> None:
        try:
            self._channel.send(frame)
        except ProtocolError as exc:
            raise ConnectionResetError(errno.EPIPE, str(exc)) from exc

    def _await(self, msg_id: int, pending: _Pending) -> dict[str, Any]:
        if not pending.done.wait(self._timeout):
            self._discard(msg_id)
            raise TimeoutError(
                errno.ETIMEDOUT, f"the target did not reply within {self._timeout}s"
            )
        if pending.error is not None:
            raise pending.error
        return pending.result or {}

    def _read_loop(self) -> None:
        failure: OSError = ConnectionResetError(errno.EPIPE, "the target disconnected")
        try:
            while (frame := self._channel.recv()) is not None:
                self._deliver(frame)
        except ProtocolError as exc:
            log.warning("connection to the target lost: %s", exc)
            failure = ConnectionResetError(errno.EPIPE, str(exc))
        finally:
            self._fail_pending(failure)

    def _deliver(self, frame: Frame) -> None:
        with self._lock:
            pending = self._pending.get(frame.msg_id)
        if pending is None:
            return
        if frame.kind is Kind.CHUNK:
            if pending.on_chunk is not None:
                pending.on_chunk(frame.stream, frame.body)
            return
        if frame.kind is Kind.END:
            return
        self._discard(frame.msg_id)
        if frame.kind is Kind.ERR:
            pending.error = RemoteOSError.from_meta(frame.meta)
        else:
            pending.result = frame.meta
        pending.done.set()
        if pending.on_done is not None:
            pending.on_done(pending.result, pending.error)

    def _fail_pending(self, error: OSError) -> None:
        with self._lock:
            pending = list(self._pending.items())
            self._pending.clear()
        for _, item in pending:
            item.error = error
            item.done.set()
            if item.on_done is not None:
                item.on_done(None, error)


class ExecHandle:
    """Handle on a running remote command."""

    def __init__(self, client: RemoteClient, msg_id: int) -> None:
        self._client = client
        self.msg_id = msg_id

    def send_stdin(self, data: bytes) -> None:
        self._client._send(Frame.chunk(self.msg_id, Stream.STDIN, data))

    def close_stdin(self) -> None:
        self._client._send(Frame.end(self.msg_id, Stream.STDIN))

    def signal(self, signum: int) -> None:
        try:
            self._client.call(Op.SIGNAL, target=self.msg_id, sig=signum)
        except OSError:
            log.debug("could not forward signal %d to remote command", signum)


class TunnelHandle:
    """Handle on a TCP connection opened from the target."""

    def __init__(self, client: RemoteClient, msg_id: int) -> None:
        self._client = client
        self.msg_id = msg_id

    def send(self, data: bytes) -> None:
        self._client._send(Frame.chunk(self.msg_id, Stream.DATA, data))

    def close_write(self) -> None:
        self._client._send(Frame.end(self.msg_id, Stream.DATA))
