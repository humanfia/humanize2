"""A target left listening on a port, serving every session that reaches it.

The other way in is a pipe carrying one session, which `test_serve.py` drives: the far end has
already been started for that session alone, and the server is the whole of it. This is the
other one -- the address is bound here, the port it landed on is announced here, a session per
connection is served at once here, and the shared secret is checked here.

All of it is the serving half, which runs on the target and is portable on purpose: no seccomp
filter, no ptrace supervisor, and nothing that asks what architecture this is. The address is
`127.0.0.1` and the port is whichever one the kernel hands out.
"""

from __future__ import annotations

import socket
import threading
from typing import TYPE_CHECKING, Any

import pytest

from hmz.coganchor.proto import Channel
from hmz.coganchor.remote import RemoteClient
from hmz.coganchor.serve import listener
from hmz.coganchor.serve.exports import ExportTable
from tests.coganchor.conftest import VIRTUAL_EXPORT

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator
    from pathlib import Path

#: The secret a client has to present where the listener was given one.
TOKEN = "not-a-real-shared-secret"


def _caught(monkeypatch: pytest.MonkeyPatch) -> list[listener._ThreadedServer]:
    """Catches the server on its way past, so a test has something to stop.

    `serve_forever` runs until it is interrupted, and a thread is not somewhere a
    `KeyboardInterrupt` can be put -- so what a test stops it by is the server object, which
    the function builds for itself and does not hand back.

    Args:
      monkeypatch: The test's own, so the listener is itself again however the test ends.

    Returns:
      The servers built from now on, in the order they were built.
    """
    made: list[listener._ThreadedServer] = []
    watched = listener._ThreadedServer

    class Caught(watched):
        def __init__(self, *args: Any, **rest: Any) -> None:
            super().__init__(*args, **rest)
            made.append(self)

    monkeypatch.setattr(listener, "_ThreadedServer", Caught)
    return made


class _Listening:
    """A listener running on a port of its own, and the handles a test needs of it."""

    def __init__(
        self,
        port: int,
        target: Path,
        shutdown: Callable[[], None],
        thread: threading.Thread,
    ) -> None:
        self.port = port
        self.target = target
        self._shutdown = shutdown
        self._thread = thread

    def stop(self) -> None:
        """Takes the listener down and waits for it to have finished going.

        `shutdown` only ends the accept loop; closing the sessions still open happens after
        it returns, inside `serve_forever` -- so a test that asked for one and looked at the
        next moment would be looking during the teardown rather than after it.
        """
        self._shutdown()
        self._thread.join(timeout=10)
        assert not self._thread.is_alive(), "the listener did not finish going"

    def client(self, token: str | None = None) -> RemoteClient:
        """One session, connected and handshaken, which the caller closes."""
        held = socket.create_connection(("127.0.0.1", self.port), timeout=10)
        client = RemoteClient(Channel.from_socket(held))
        client.start(token)
        return client


@pytest.fixture
def serving(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[Callable[[str | None], _Listening]]:
    """Starts a listener with or without a secret, and takes it down however the test ends.

    The server object is caught on its way past so the test can stop it: `serve_forever` runs
    until it is interrupted, and a thread is not somewhere a `KeyboardInterrupt` can be put.
    """
    target = tmp_path / "target"
    target.mkdir()
    threads: list[threading.Thread] = []
    made = _caught(monkeypatch)

    def start(token: str | None = None) -> _Listening:
        table = ExportTable.parse([f"{VIRTUAL_EXPORT}:{target}"])
        thread = threading.Thread(
            target=listener.serve_forever,
            args=("127.0.0.1", 0, table, token),
            daemon=True,
        )
        thread.start()
        threads.append(thread)
        for _ in range(500):
            if made:
                break
            thread.join(timeout=0.02)
        assert made, "the listener never bound an address"
        return _Listening(made[-1].server_address[1], target, made[-1].shutdown, thread)

    try:
        yield start
    finally:
        for one in made:
            one.shutdown()
        for thread in threads:
            thread.join(timeout=10)


@pytest.mark.timeout(60)
def test_the_port_it_landed_on_is_announced_to_whoever_started_it(
    serving: Callable[[str | None], _Listening], capsys: pytest.CaptureFixture[str]
) -> None:
    """Not a message but a handshake: a port of 0 is how a script asks for any free one."""
    held = serving(None)

    said = capsys.readouterr().err

    assert f"hmz anchor serve listening 127.0.0.1 {held.port}" in said
    assert held.port != 0


@pytest.mark.timeout(60)
def test_a_session_that_connects_is_served_off_the_target_s_own_directory(
    serving: Callable[[str | None], _Listening],
) -> None:
    held = serving(None)
    (held.target / "shipped.txt").write_text("arrived over a port\n")

    client = held.client()
    try:
        listed = client.listdir(VIRTUAL_EXPORT)
    finally:
        client.close()

    assert "shipped.txt" in [one["name"] for one in listed["entries"]]


@pytest.mark.timeout(60)
def test_more_than_one_session_at_once_is_what_a_port_is_for(
    serving: Callable[[str | None], _Listening],
) -> None:
    """A pipe carries one session; this is the way in that carries several."""
    held = serving(None)
    (held.target / "shipped.txt").write_text("arrived over a port\n")

    first, second = held.client(), held.client()
    try:
        # Both open at once, and each one still answers.
        assert first.listdir(VIRTUAL_EXPORT)["entries"]
        assert second.listdir(VIRTUAL_EXPORT)["entries"]
        second.mkdir(f"{VIRTUAL_EXPORT}/made-by-the-second")
        assert "made-by-the-second" in [
            one["name"] for one in first.listdir(VIRTUAL_EXPORT)["entries"]
        ]
    finally:
        first.close()
        second.close()


@pytest.mark.timeout(60)
def test_a_session_presenting_the_secret_is_served(
    serving: Callable[[str | None], _Listening],
) -> None:
    held = serving(TOKEN)
    (held.target / "shipped.txt").write_text("arrived over a port\n")

    client = held.client(TOKEN)
    try:
        assert client.listdir(VIRTUAL_EXPORT)["entries"]
    finally:
        client.close()


@pytest.mark.timeout(60)
def test_a_session_presenting_the_wrong_secret_is_refused(
    serving: Callable[[str | None], _Listening],
) -> None:
    """An `hmz anchor` port is equivalent to a shell on that machine, so this is the door."""
    held = serving(TOKEN)

    with pytest.raises(OSError, match="token"):
        held.client("not-the-secret")


@pytest.mark.timeout(60)
def test_a_session_presenting_no_secret_at_all_is_refused(
    serving: Callable[[str | None], _Listening],
) -> None:
    held = serving(TOKEN)

    with pytest.raises(OSError, match="token"):
        held.client(None)


@pytest.mark.timeout(60)
def test_a_listener_on_its_way_out_does_not_leave_commands_running_on_the_target(
    serving: Callable[[str | None], _Listening],
) -> None:
    """Handler threads are daemons and do not get to finish on their own.

    What the listener takes with it is what each connection owns -- the commands it started
    on the target -- rather than the connection itself: a target being shut down must not
    leave a `sleep` of somebody's behind it.
    """
    held = serving(None)
    client = held.client()
    ended = threading.Event()
    client.start_exec(
        ["sleep", "60"],
        cwd=VIRTUAL_EXPORT,
        env={},
        on_output=lambda stream, data: None,
        on_exit=lambda result, error: ended.set(),
    )
    # Started rather than merely asked for: what is being checked is a command torn down.
    assert not ended.wait(timeout=1)

    held.stop()

    assert ended.wait(timeout=15)
    client.close()


@pytest.mark.timeout(60)
def test_an_address_with_a_colon_in_it_is_listened_on_as_ipv6(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Which is how the one function serves both families without being told which."""
    target = tmp_path / "target"
    target.mkdir()
    made = _caught(monkeypatch)
    table = ExportTable.parse([f"{VIRTUAL_EXPORT}:{target}"])
    thread = threading.Thread(
        target=listener.serve_forever, args=("::1", 0, table, None), daemon=True
    )
    thread.start()
    try:
        for _ in range(500):
            if made:
                break
            thread.join(timeout=0.02)
        assert made, "the listener never bound an address"

        assert made[-1].address_family == socket.AF_INET6
        assert made[-1].socket.family == socket.AF_INET6
    finally:
        for one in made:
            one.shutdown()
        thread.join(timeout=10)
