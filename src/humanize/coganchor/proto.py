"""Wire protocol between the two halves of a session.

A connection carries length-prefixed frames.  Each frame pairs a small JSON
metadata object with an optional opaque binary body, so file content and
process output never pay base64 overhead::

    +---------+----------+---------+------------------+--------------+
    | u32     | u32      | u64     | meta_len bytes   | remaining    |
    | payload | meta_len | msg id  | JSON metadata    | binary body  |
    +---------+----------+---------+------------------+--------------+

``payload`` counts the bytes following the 16-byte header.

Every exchange shares one ``msg id`` and follows the same lifecycle:

* :attr:`Kind.REQ` opens the exchange.
* Either peer may then stream :attr:`Kind.CHUNK` frames on that id, tagged
  with a :class:`Stream`, and mark a direction finished with :attr:`Kind.END`.
* :attr:`Kind.RSP` (success) or :attr:`Kind.ERR` (failure) closes it.

That single shape covers file reads, file writes, process I/O and tunnelled
sockets, so memory use stays bounded regardless of payload size.

The protocol is deliberately errno-faithful: every failure crosses the wire as
an :attr:`Kind.ERR` frame carrying the remote ``errno``, which is what lets the
traced process be handed the target's exact error.

Both halves import this module and nothing else in common, so it must stay
free of anything platform-specific.
"""

from __future__ import annotations

import enum
import functools
import json
import re
import socket
import struct
import threading
from contextlib import suppress
from dataclasses import dataclass, field
from typing import IO, Any, cast

__all__ = [
    "CHUNK_SIZE",
    "PROTOCOL_VERSION",
    "Channel",
    "Frame",
    "Kind",
    "Op",
    "ProtocolError",
    "RemoteOSError",
    "Stream",
    "rewrite_path_prefix",
]

PROTOCOL_VERSION = 1

#: Body size used when splitting large payloads into stream chunks.
CHUNK_SIZE = 1 << 16

#: Hard ceiling on a single frame, to bound memory use on malformed input.
MAX_FRAME_BYTES = 1 << 30

_HEADER = struct.Struct("<IIQ")


class Kind(enum.Enum):
    """Frame kind."""

    REQ = "q"
    RSP = "r"
    ERR = "e"
    CHUNK = "c"
    END = "z"


class Op(enum.Enum):
    """Remote operations understood by :mod:`humanize.coganchor.serve`."""

    # Handshake.
    HELLO = "hello"

    # Filesystem.
    LISTDIR = "listdir"
    STAT = "stat"
    READ = "read"
    WRITE = "write"
    MKDIR = "mkdir"
    RMDIR = "rmdir"
    UNLINK = "unlink"
    RENAME = "rename"
    SYMLINK = "symlink"
    LINK = "link"
    READLINK = "readlink"
    CHMOD = "chmod"
    TRUNCATE = "truncate"
    UTIME = "utime"

    # Process execution.  EXEC opens a stream that CHUNK/END frames feed;
    # SIGNAL is a separate request naming that stream.
    EXEC = "exec"
    SIGNAL = "signal"

    # TCP tunnelling.  CONNECT opens a stream carried by CHUNK/END frames.
    CONNECT = "connect"


class Stream(enum.IntEnum):
    """Identifies which byte stream a :attr:`Kind.CHUNK` frame belongs to.

    :attr:`DATA` carries file content and tunnelled socket bytes; the standard
    descriptors carry process I/O.
    """

    STDIN = 0
    STDOUT = 1
    STDERR = 2
    DATA = 3


class ProtocolError(Exception):
    """Raised on malformed frames or an unexpected end of stream."""


class RemoteOSError(OSError):
    """An :class:`OSError` that happened on the other machine.

    Carries that machine's ``errno`` verbatim, which is what lets a failure be
    reported here exactly as it occurred there.
    """

    @classmethod
    def from_meta(cls, meta: dict[str, Any]) -> RemoteOSError:
        return cls(
            int(meta.get("errno", 0)),
            str(meta.get("strerror", "remote error")),
            meta.get("filename"),
        )


@dataclass(slots=True)
class Frame:
    """A single protocol frame."""

    kind: Kind
    msg_id: int
    meta: dict[str, Any] = field(default_factory=dict[str, Any])
    body: bytes = b""

    @property
    def op(self) -> Op | None:
        """The requested operation, or ``None`` if absent or unrecognised.

        A peer speaking a newer protocol must get a clean error rather than
        take the connection down, so an unknown name is not an exception.
        """
        raw = self.meta.get("op")
        try:
            return Op(raw) if raw is not None else None
        except ValueError:
            return None

    def encode(self) -> bytes:
        meta = dict(self.meta)
        meta["k"] = self.kind.value
        blob = json.dumps(meta, separators=(",", ":")).encode()
        header = _HEADER.pack(len(blob) + len(self.body), len(blob), self.msg_id)
        return header + blob + self.body

    @classmethod
    def request(cls, msg_id: int, op: Op, body: bytes = b"", **meta: Any) -> Frame:
        return cls(Kind.REQ, msg_id, {"op": op.value, **meta}, body)

    @classmethod
    def reply(cls, msg_id: int, body: bytes = b"", **meta: Any) -> Frame:
        return cls(Kind.RSP, msg_id, dict(meta), body)

    @classmethod
    def error(cls, msg_id: int, exc: OSError) -> Frame:
        strerror = exc.strerror or str(exc) or "remote error"
        meta = {
            "errno": exc.errno or 0,
            "strerror": strerror,
            "filename": exc.filename if isinstance(exc.filename, str) else None,
        }
        return cls(Kind.ERR, msg_id, meta)

    @classmethod
    def chunk(cls, msg_id: int, stream: Stream, body: bytes) -> Frame:
        return cls(Kind.CHUNK, msg_id, {"s": int(stream)}, body)

    @classmethod
    def end(cls, msg_id: int, stream: Stream = Stream.DATA) -> Frame:
        return cls(Kind.END, msg_id, {"s": int(stream)})

    @property
    def stream(self) -> Stream:
        return Stream(self.meta.get("s", int(Stream.DATA)))


class Channel:
    """A framed, bidirectional connection.

    :meth:`send` is safe to call from any thread.  :meth:`recv` must be driven
    by exactly one thread.
    """

    def __init__(self, reader: IO[bytes], writer: IO[bytes], owns: Any = None) -> None:
        self._reader = reader
        self._writer = writer
        self._owns = owns
        self._send_lock = threading.Lock()
        self._closed = False

    @classmethod
    def from_socket(cls, sock: Any) -> Channel:
        """Wrap a connected socket, keeping it alive for the channel's life."""
        return cls(sock.makefile("rb"), sock.makefile("wb"), owns=sock)

    def send(self, frame: Frame) -> None:
        blob = frame.encode()
        with self._send_lock:
            if self._closed:
                raise ProtocolError("channel is closed")
            try:
                self._writer.write(blob)
                self._writer.flush()
            except (BrokenPipeError, ValueError, OSError) as exc:
                self._closed = True
                raise ProtocolError(f"send failed: {exc}") from exc

    def recv(self) -> Frame | None:
        """Read the next frame, or return ``None`` at a clean end of stream."""
        header = self._read_exactly(_HEADER.size, allow_eof=True)
        if header is None:
            return None
        payload_len, meta_len, msg_id = _HEADER.unpack(header)
        if meta_len > payload_len or payload_len > MAX_FRAME_BYTES:
            raise ProtocolError(f"implausible frame header: {payload_len}/{meta_len}")
        payload = self._read_exactly(payload_len)
        assert payload is not None  # noqa: S101
        try:
            meta = json.loads(payload[:meta_len])
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ProtocolError(f"malformed frame metadata: {exc}") from exc
        if not isinstance(meta, dict):
            raise ProtocolError("frame metadata is not an object")
        named = cast("dict[str, Any]", meta)
        try:
            kind = Kind(named.pop("k"))
        except (KeyError, ValueError) as exc:
            raise ProtocolError(f"invalid frame kind: {exc}") from exc
        return Frame(kind, msg_id, named, payload[meta_len:])

    def close(self) -> None:
        """Close the channel, waking any thread parked in :meth:`recv`.

        Order matters.  ``shutdown`` unblocks a socket read; closing the writer
        gives a pipe peer end-of-input so it exits on its own.  The reader
        object is deliberately left alone: closing a buffered reader waits for
        the lock the blocked thread is holding, which would deadlock.  It is
        released when its owner finishes and the object is collected.
        """
        with self._send_lock:
            if self._closed:
                return
            self._closed = True
        if self._owns is not None:
            with suppress(OSError):
                self._owns.shutdown(socket.SHUT_RDWR)
        for handle in (self._writer, self._owns):
            if handle is not None:
                with suppress(OSError, ValueError):
                    handle.close()

    def _read_exactly(self, size: int, *, allow_eof: bool = False) -> bytes | None:
        """Read exactly ``size`` bytes, looping over short reads.

        A pipe hands back at most its buffer's worth per call, so frames larger
        than 64 KiB arrive in pieces even from a blocking descriptor.
        """
        if size == 0:
            return b""
        chunks: list[bytes] = []
        remaining = size
        while remaining:
            try:
                data = self._reader.read(remaining)
            except (OSError, ValueError) as exc:
                raise ProtocolError(f"read failed: {exc}") from exc
            if not data:
                if allow_eof and remaining == size:
                    return None
                raise ProtocolError(
                    f"truncated frame: wanted {size} bytes, got {size - remaining}"
                )
            chunks.append(data)
            remaining -= len(data)
        return chunks[0] if len(chunks) == 1 else b"".join(chunks)


#: Characters that can precede or follow a path inside a command line.
_BOUNDARY = r"\s'\"=:,;()\[\]<>|&"


@functools.lru_cache(maxsize=64)
def _prefix_pattern(prefix: str) -> re.Pattern[str]:
    return re.compile(
        rf"(?:^|(?<=[{_BOUNDARY}])){re.escape(prefix)}(?=[/{_BOUNDARY}]|$)"
    )


def rewrite_path_prefix(text: str, prefix: str, replacement: str) -> str:
    """Replace ``prefix`` with ``replacement`` where it names a path.

    Both machines must agree on this translation, so it lives beside the
    protocol.  Matches are anchored to token boundaries: ``/w`` is rewritten in
    ``cat /w/f`` but not in ``echo hello/world`` or ``--flag=/wide``.
    """
    if prefix == replacement or prefix not in text:
        return text
    return _prefix_pattern(prefix).sub(replacement.replace("\\", "\\\\"), text)
