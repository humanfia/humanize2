"""Request dispatch for one coganchor connection.

The reader loop owns the channel: it decodes frames, runs short filesystem
operations inline, and hands long-lived work (process execution, TCP tunnels)
to :mod:`hmz.coganchor.serve.sessions` threads so the loop never stalls.
"""

from __future__ import annotations

import contextlib
import errno
import logging
import os
import platform
import sys
import threading
from typing import TYPE_CHECKING, Any

from hmz.coganchor.proto import (
    PROTOCOL_VERSION,
    Channel,
    Frame,
    Kind,
    Op,
    ProtocolError,
    Stream,
)
from hmz.coganchor.serve import fsops
from hmz.coganchor.serve.sessions import ExecSession, Session, TunnelSession

if TYPE_CHECKING:
    from collections.abc import Callable

    from hmz.coganchor.serve.exports import ExportTable

__all__ = ["Server"]

log = logging.getLogger(__name__)

#: Filesystem operations that complete in one round trip.
_SIMPLE_OPS: dict[Op, Callable[[ExportTable, dict[str, Any]], dict[str, Any]]] = {
    Op.STAT: lambda t, m: fsops.stat(t, m["path"]),
    Op.LISTDIR: lambda t, m: fsops.listdir(t, m["path"]),
    Op.MKDIR: lambda t, m: fsops.mkdir(
        t, m["path"], m.get("mode", 0o777), parents=m.get("parents", False)
    ),
    Op.RMDIR: lambda t, m: fsops.rmdir(t, m["path"]),
    Op.UNLINK: lambda t, m: fsops.unlink(t, m["path"]),
    Op.RENAME: lambda t, m: fsops.rename(
        t, m["src"], m["dst"], replace=m.get("replace", True)
    ),
    Op.SYMLINK: lambda t, m: fsops.symlink(t, m["target"], m["path"]),
    Op.LINK: lambda t, m: fsops.link(t, m["src"], m["dst"]),
    Op.READLINK: lambda t, m: fsops.readlink(t, m["path"]),
    Op.CHMOD: lambda t, m: fsops.chmod(t, m["path"], m["mode"]),
    Op.TRUNCATE: lambda t, m: fsops.truncate(t, m["path"], m["size"]),
    Op.UTIME: lambda t, m: fsops.utime(
        t, m["path"], m.get("atime_ns"), m.get("mtime_ns")
    ),
}


class _WriteSink:
    """Streams an inbound file write to disk, replying once END arrives."""

    def __init__(self, msg_id: int, channel: Channel, writer: fsops.FileWriter) -> None:
        self._msg_id = msg_id
        self._channel = channel
        self._writer = writer

    def feed(self, stream: Stream, data: bytes) -> None:  # noqa: ARG002
        self._writer.feed(data)

    def end_input(self, stream: Stream) -> None:  # noqa: ARG002
        try:
            result = self._writer.finish()
        except OSError as exc:
            self._channel.send(Frame.error(self._msg_id, exc))
        else:
            self._channel.send(Frame.reply(self._msg_id, **result))

    def shutdown(self) -> None:
        self._writer.abort()


#: Receives the CHUNK/END frames that follow a streaming request.
_Sink = _WriteSink | Session


class Server:
    """Serves one coganchor connection until the peer disconnects."""

    def __init__(
        self, channel: Channel, table: ExportTable, token: str | None = None
    ) -> None:
        self._channel = channel
        self._table = table
        self._token = token
        self._sinks: dict[int, _Sink] = {}
        self._lock = threading.Lock()
        self._authenticated = token is None

    def serve(self) -> None:
        try:
            while (frame := self._channel.recv()) is not None:
                self._dispatch(frame)
        except ProtocolError as exc:
            log.warning("connection dropped: %s", exc)
        finally:
            self.close()

    def _dispatch(self, frame: Frame) -> None:
        if frame.kind is Kind.REQ:
            self._handle_request(frame)
        elif frame.kind in (Kind.CHUNK, Kind.END):
            self._route_stream(frame)
        else:
            log.debug("ignoring unexpected %s frame", frame.kind)

    def _route_stream(self, frame: Frame) -> None:
        with self._lock:
            sink = self._sinks.get(frame.msg_id)
        if sink is None:
            return
        try:
            if frame.kind is Kind.CHUNK:
                sink.feed(frame.stream, frame.body)
            else:
                sink.end_input(frame.stream)
                if isinstance(sink, _WriteSink):
                    self._release(frame.msg_id)
        except OSError as exc:
            # Tear the sink down before dropping it: a half-written file would
            # otherwise keep its temporary sibling for good.
            sink.shutdown()
            self._channel.send(Frame.error(frame.msg_id, exc))
            self._release(frame.msg_id)

    def _handle_request(self, frame: Frame) -> None:
        op = frame.op
        if op is None:
            self._fail(frame, OSError(errno.ENOSYS, "unknown or missing operation"))
            return
        if op is Op.HELLO:
            self._handle_hello(frame)
            return
        if not self._authenticated:
            self._fail(frame, PermissionError(errno.EACCES, "not authenticated"))
            return
        try:
            if op in _SIMPLE_OPS:
                result = _SIMPLE_OPS[op](self._table, frame.meta)
                self._channel.send(Frame.reply(frame.msg_id, **result))
            elif op is Op.READ:
                self._handle_read(frame)
            elif op is Op.WRITE:
                self._handle_write(frame)
            elif op is Op.EXEC:
                session = ExecSession(
                    frame.msg_id, self._channel, self._table, frame.meta
                )
                self._start(frame, session)
            elif op is Op.CONNECT:
                self._start(
                    frame, TunnelSession(frame.msg_id, self._channel, frame.meta)
                )
            elif op is Op.SIGNAL:
                self._handle_signal(frame)
            else:
                self._fail(frame, OSError(errno.ENOSYS, f"unsupported op {op.value}"))
        except OSError as exc:
            self._fail(frame, exc)
        except (KeyError, TypeError, ValueError) as exc:
            self._fail(
                frame, OSError(errno.EINVAL, f"malformed {op.value} request: {exc}")
            )
        except Exception as exc:
            log.exception("unhandled error serving %s", op.value)
            self._fail(frame, OSError(errno.EIO, str(exc)))

    def _handle_hello(self, frame: Frame) -> None:
        if self._token is not None and frame.meta.get("token") != self._token:
            self._fail(frame, PermissionError(errno.EACCES, "invalid token"))
            return
        version = frame.meta.get("version")
        if version != PROTOCOL_VERSION:
            # Both ends check, because either may be the older build: a client
            # that never hears our version would otherwise proceed regardless.
            # The connection goes with it -- an untokened session starts out
            # authenticated, so merely failing the handshake would leave every
            # following request working.
            self._fail(
                frame,
                OSError(
                    errno.EPROTO,
                    f"client speaks protocol {version}, this humanize speaks {PROTOCOL_VERSION}",
                ),
            )
            self._channel.close()
            return
        self._authenticated = True
        self._channel.send(
            Frame.reply(
                frame.msg_id,
                version=PROTOCOL_VERSION,
                hostname=platform.node(),
                platform=sys.platform,
                python=platform.python_version(),
                pid=os.getpid(),
                exports=[
                    {"virtual": e.virtual, "real": e.real} for e in self._table.exports
                ],
            )
        )

    def _handle_read(self, frame: Frame) -> None:
        def emit(data: bytes) -> None:
            self._channel.send(Frame.chunk(frame.msg_id, Stream.DATA, data))

        result = fsops.read(self._table, frame.meta["path"], emit)
        self._channel.send(Frame.reply(frame.msg_id, **result))

    def _handle_write(self, frame: Frame) -> None:
        writer = fsops.FileWriter(
            self._table, frame.meta["path"], frame.meta.get("mode")
        )
        if frame.body:
            writer.feed(frame.body)
        with self._lock:
            self._sinks[frame.msg_id] = _WriteSink(frame.msg_id, self._channel, writer)

    def _handle_signal(self, frame: Frame) -> None:
        with self._lock:
            sink = self._sinks.get(int(frame.meta["target"]))
        if isinstance(sink, ExecSession):
            sink.signal(int(frame.meta["sig"]))
        self._channel.send(Frame.reply(frame.msg_id))

    def _start(self, frame: Frame, session: Session) -> None:
        with self._lock:
            self._sinks[frame.msg_id] = session
        session.start()
        threading.Thread(
            target=self._reap, args=(frame.msg_id, session), name="reap", daemon=True
        ).start()

    def _reap(self, msg_id: int, session: Session) -> None:
        session.join()
        self._release(msg_id)

    def _release(self, msg_id: int) -> None:
        with self._lock:
            self._sinks.pop(msg_id, None)

    def _fail(self, frame: Frame, exc: OSError) -> None:
        with contextlib.suppress(ProtocolError):
            self._channel.send(Frame.error(frame.msg_id, exc))

    def close(self) -> None:
        """Tear down every session this connection owns.

        Called when the peer goes away, and by the listener on its way out so
        that a target being shut down does not leave commands running here.
        """
        with self._lock:
            sinks = list(self._sinks.values())
            self._sinks.clear()
        for sink in sinks:
            try:
                sink.shutdown()
            except Exception:
                log.debug("sink shutdown failed", exc_info=True)
