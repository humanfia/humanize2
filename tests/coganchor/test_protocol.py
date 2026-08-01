"""Unit tests for the wire protocol."""

from __future__ import annotations

import errno
import io
import threading
from typing import IO, cast

import pytest

from hmz.coganchor.proto import (
    Channel,
    Frame,
    Kind,
    Op,
    ProtocolError,
    RemoteOSError,
    Stream,
    rewrite_path_prefix,
)


def roundtrip(frame: Frame) -> Frame:
    stream = io.BytesIO(frame.encode())
    decoded = Channel(stream, io.BytesIO()).recv()
    assert decoded is not None
    return decoded


def test_request_roundtrip() -> None:
    frame = roundtrip(Frame.request(7, Op.READ, path="/x/y"))
    assert frame.kind is Kind.REQ
    assert frame.msg_id == 7
    assert frame.op is Op.READ
    assert frame.meta["path"] == "/x/y"


def test_binary_body_survives_unchanged() -> None:
    payload = bytes(range(256)) * 300
    frame = roundtrip(Frame.chunk(3, Stream.STDERR, payload))
    assert frame.body == payload
    assert frame.stream is Stream.STDERR


def test_error_frame_carries_errno() -> None:
    original = FileNotFoundError(errno.ENOENT, "No such file or directory", "/gone")
    frame = roundtrip(Frame.error(11, original))
    restored = RemoteOSError.from_meta(frame.meta)
    assert restored.errno == errno.ENOENT
    assert restored.filename == "/gone"


def test_empty_body_and_meta() -> None:
    frame = roundtrip(Frame.reply(1))
    assert frame.kind is Kind.RSP
    assert frame.body == b""


def test_recv_returns_none_at_clean_eof() -> None:
    assert Channel(io.BytesIO(), io.BytesIO()).recv() is None


def test_truncated_frame_is_rejected() -> None:
    blob = Frame.request(1, Op.HELLO).encode()
    with pytest.raises(ProtocolError, match="truncated"):
        Channel(io.BytesIO(blob[:-3]), io.BytesIO()).recv()


def test_malformed_header_is_rejected() -> None:
    with pytest.raises(ProtocolError, match="implausible"):
        Channel(io.BytesIO(b"\xff" * 16 + b"x"), io.BytesIO()).recv()


class _ShortReader(io.RawIOBase):
    """A stream that returns at most eight bytes per call, like a small pipe."""

    def __init__(self, data: bytes) -> None:
        self._data = data
        self._offset = 0

    def read(self, size: int | None = -1) -> bytes:
        chunk = self._data[self._offset : self._offset + min(size or -1, 8)]
        self._offset += len(chunk)
        return chunk


def test_frames_reassemble_across_short_reads() -> None:
    """Pipes hand back partial buffers; frames must still reassemble."""
    payload = b"z" * 5000
    reader = cast(
        "IO[bytes]", _ShortReader(Frame.chunk(2, Stream.DATA, payload).encode())
    )
    channel = Channel(reader, io.BytesIO())
    frame = channel.recv()
    assert frame is not None
    assert frame.body == payload


def test_send_is_thread_safe() -> None:
    sink = io.BytesIO()
    channel = Channel(io.BytesIO(), sink)
    frames = [Frame.chunk(index, Stream.DATA, b"a" * 1000) for index in range(50)]

    threads = [threading.Thread(target=channel.send, args=(frame,)) for frame in frames]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    reader = Channel(io.BytesIO(sink.getvalue()), io.BytesIO())
    seen: list[int] = []
    while (frame := reader.recv()) is not None:
        seen.append(frame.msg_id)
    assert sorted(seen) == list(range(50))


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("/w", "/real"),
        ("cat /w/file.txt", "cat /real/file.txt"),
        ("cd /w && ls", "cd /real && ls"),
        ("grep -r x '/w/src'", "grep -r x '/real/src'"),
        ("--dir=/w", "--dir=/real"),
        # Boundaries: these are not the path being remapped.
        ("echo hello/w", "echo hello/w"),
        ("echo /width", "echo /width"),
        ("echo a/w/b", "echo a/w/b"),
    ],
)
def test_prefix_rewriting_respects_token_boundaries(text: str, expected: str) -> None:
    assert rewrite_path_prefix(text, "/w", "/real") == expected


def test_prefix_rewriting_is_a_noop_for_identity() -> None:
    assert rewrite_path_prefix("cat /w/f", "/w", "/w") == "cat /w/f"
