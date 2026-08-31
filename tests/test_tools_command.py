"""`hmz tools`: the pipe a coding agent speaks the tool protocol over, relayed to a flow.

A callback of a flow's is a Python function in the flow's own process, and a CLI takes a tool
by starting a program and talking to it over that program's stdin and stdout. This is that
program, and it is spawned rather than typed -- which is why it is checked here rather than
found by driving a real agent, where it is one moving part of many and only runs at all when
somebody has a backend installed.

What it owes its two ends: every line goes both ways, a line goes as soon as it is written
rather than when a buffer fills, closing either end closes the other, and a socket that is not
there is a flow that has ended rather than a turn that failed.

The socket is bound by a bare name from inside its own directory. A Unix socket address holds
about a hundred bytes whole -- 104 on macOS -- and the directory pytest hands out is longer
than that, which is the same thing `hmz.daemon.where` does and for the same reason.
"""

from __future__ import annotations

import io
import socket
import threading
from typing import TYPE_CHECKING

import pytest

from hmz.cli.tools import _moves, tools

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

#: What the socket is called inside the directory the test stands in.
SOCKET = "tools.sock"


class _Stdin:
    """Stands in for `sys.stdin`, which the relay reaches through `.buffer`."""

    def __init__(self, said: bytes) -> None:
        self.buffer = io.BytesIO(said)


class _Stdout:
    """The same for `sys.stdout`, holding what the relay wrote back."""

    def __init__(self) -> None:
        self.buffer = io.BytesIO()

    def said(self) -> bytes:
        return self.buffer.getvalue()


@pytest.fixture
def flow(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[socket.socket]:
    """A flow serving its callbacks on a socket, stood beside so the name alone reaches it."""
    monkeypatch.chdir(tmp_path)
    listening = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    listening.bind(SOCKET)
    listening.listen(1)
    try:
        yield listening
    finally:
        listening.close()


def _cli(said: bytes, monkeypatch: pytest.MonkeyPatch) -> _Stdout:
    """Stands the CLI's two streams in front of the relay, and hands back what it hears.

    Called from the test body rather than out of a fixture: pytest puts its own capture back
    over `sys.stdout` when it resumes capturing for the call, so a stand-in installed during
    setup is one the relay never sees.

    Args:
      said: What the CLI writes to the flow.
      monkeypatch: The test's own, so both streams go back however the test ends.

    Returns:
      What the relay wrote back to the CLI.
    """
    out = _Stdout()
    monkeypatch.setattr("sys.stdin", _Stdin(said))
    monkeypatch.setattr("sys.stdout", out)
    return out


def _answers(listening: socket.socket, replies: list[bytes]) -> threading.Thread:
    """A flow that reads a line, says each of these back, and lets go.

    Returns:
      The thread it is running on, already started.
    """

    def serve() -> None:
        held, _ = listening.accept()
        with held, held.makefile("rb") as reading, held.makefile("wb") as writing:
            reading.readline()
            for said in replies:
                writing.write(said)
                writing.flush()

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    return thread


@pytest.mark.timeout(30)
def test_a_line_the_cli_writes_reaches_the_flow_and_the_answer_comes_back(
    flow: socket.socket, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Which is the whole errand: the function runs where the flow is, not in a process here."""
    heard: list[bytes] = []

    def serve() -> None:
        held, _ = flow.accept()
        with held, held.makefile("rb") as reading, held.makefile("wb") as writing:
            heard.append(reading.readline())
            writing.write(b'{"result": "done"}\n')
            writing.flush()

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    ends = _cli(b'{"call": "one"}\n', monkeypatch)

    assert tools(["--at", SOCKET]) == 0

    thread.join(timeout=10)
    assert heard == [b'{"call": "one"}\n']
    assert ends.said() == b'{"result": "done"}\n'


@pytest.mark.timeout(30)
def test_a_flow_may_say_something_before_it_is_asked(
    flow: socket.socket, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Both ways at once, so neither end waits on the other."""
    thread = _answers(flow, [b'{"note": "first"}\n', b'{"note": "second"}\n'])
    ends = _cli(b'{"call": "one"}\n', monkeypatch)

    assert tools(["--at", SOCKET]) == 0

    thread.join(timeout=10)
    assert ends.said() == b'{"note": "first"}\n{"note": "second"}\n'


@pytest.mark.timeout(30)
def test_the_cli_closing_its_end_closes_the_one_the_flow_is_reading(
    flow: socket.socket, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Without saying so the flow sits reading a socket nobody is going to write to."""
    ended = threading.Event()

    def serve() -> None:
        held, _ = flow.accept()
        with held, held.makefile("rb") as reading:
            while reading.readline():
                pass
            # Read to the end rather than blocked partway, which is what is being checked.
            ended.set()

    threading.Thread(target=serve, daemon=True).start()
    _cli(b'{"call": "one"}\n', monkeypatch)

    assert tools(["--at", SOCKET]) == 0

    assert ended.wait(timeout=10)


@pytest.mark.timeout(30)
def test_a_socket_that_is_not_there_is_a_flow_that_has_ended(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """One rather than a crash: the CLI reads it as tools unavailable, not a failed turn."""
    monkeypatch.chdir(tmp_path)

    assert tools(["--at", "nobody-is-serving-this.sock"]) == 1

    said = capsys.readouterr().err
    assert "hmz tools" in said
    assert "nobody-is-serving-this.sock" in said


def test_the_socket_to_relay_to_has_to_be_said() -> None:
    """It is spawned rather than typed, so there is no sensible default to fall back on."""
    with pytest.raises(SystemExit) as stopped:
        tools([])

    assert stopped.value.code == 2


def test_a_line_goes_as_soon_as_it_is_written_rather_than_when_a_buffer_fills() -> None:
    """The protocol is one JSON object per line, and a held line is a request held."""
    written: list[bytes] = []

    class Watching(io.BytesIO):
        def flush(self) -> None:
            written.append(self.getvalue())

    source = io.BytesIO(b'{"one": 1}\n{"two": 2}\n')
    sink = Watching()

    _moves(source, sink)

    assert written == [b'{"one": 1}\n', b'{"one": 1}\n{"two": 2}\n']


def test_carrying_stops_where_the_stream_does_rather_than_raising() -> None:
    """Either end going is the ordinary way this ends, and is not something to report."""
    source = io.BytesIO(b"")
    sink = io.BytesIO()

    _moves(source, sink)

    assert sink.getvalue() == b""


def test_a_stream_that_is_already_closed_is_the_same_as_one_that_ended() -> None:
    source = io.BytesIO(b'{"one": 1}\n')
    source.close()
    sink = io.BytesIO()

    _moves(source, sink)

    assert sink.getvalue() == b""
