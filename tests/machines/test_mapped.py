"""The workspace as the flow's own code reaches it: what it answers, and what it holds open.

Driven against a target of its own rather than a container -- a `serve` on the other end of a
pipe or a socket, which is the road a container is reached by minus the image -- so a command
really is spawned somewhere else, its input really is a pipe, and a handshake can be made to
fail without a daemon.
"""

from __future__ import annotations

import contextlib
import socket
import threading
from typing import TYPE_CHECKING

import pytest

from hmz.coganchor import AnchorConfig
from hmz.coganchor.proto import Channel
from hmz.coganchor.serve.exports import ExportTable
from hmz.coganchor.serve.server import Server
from hmz.machines import Mapped

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

    from hmz.machines import Ran

#: The workspace both sides name. It is on neither of them, so anything read or run under it
#: came back through the target rather than out of this directory.
WORKSPACE = "/machines-project"


@pytest.fixture
def anchor(tmp_path: Path) -> AnchorConfig:
    """A target that is a child of this process, standing in for a machine of its own."""
    target = tmp_path / "target"
    target.mkdir()
    return AnchorConfig(target=f"local:{target}", workspace=WORKSPACE)


def test_a_command_that_reads_its_input_is_told_there_is_none(
    anchor: AnchorConfig,
) -> None:
    """`run` has no way of sending any, so a command waiting for input waits for the run.

    Held in a thread of its own only so that the wait has an end here: the thing being asked
    is whether it ends at all, and a `cat` that never hears the end of its input takes the
    flow, the connection and the container with it.
    """
    said: list[Ran] = []
    went: list[BaseException] = []
    held = Mapped(anchor)

    def ask() -> None:
        try:
            said.append(held.run(["cat"]))
        except Exception as why:  # noqa: BLE001 -- said below, where the test can read it
            went.append(why)

    asking = threading.Thread(target=ask, name="reads-its-input", daemon=True)
    asking.start()
    try:
        asking.join(timeout=15)
        assert not asking.is_alive(), (
            "`run` never came back: the command is still waiting for input to end"
        )
    finally:
        # However that went: closing wakes a `run` still in its wait, so the thread ends with
        # the test rather than outliving it.
        held.close()
        asking.join(timeout=10)

    assert not went
    # It read to the end of its input and found none, which is the whole of the answer.
    assert said[0].ok
    assert said[0].output == ""


def test_a_command_that_wants_no_input_runs_and_says_what_it_came_to(
    anchor: AnchorConfig,
) -> None:
    """The ordinary case, which ending its input at once must leave exactly as it was."""
    with Mapped(anchor) as held:
        said = held.run("echo it ran")

        assert said.ok
        assert said.output == "it ran\n"
        # And one that failed says so, having had its input ended like any other.
        assert not held.run(["sh", "-c", "exit 3"]).ok


@pytest.fixture
def door(tmp_path: Path) -> Iterator[str]:
    """A target that turns the first caller away and serves the next, reached over tcp.

    Asking for a secret the caller was not given is one way a handshake fails with the
    connection itself up, which is the shape that matters: a container still coming up, or a
    target that lost the connection between the socket and the reply, fails the same way.
    """
    target = tmp_path / "target"
    target.mkdir()
    (target / "one.txt").write_text("on the target\n")
    exports = ExportTable.parse([f"{WORKSPACE}:{target}"])
    listening = socket.create_server(("127.0.0.1", 0))
    answered: list[Server] = []

    def answer() -> None:
        while True:
            try:
                taken, _ = listening.accept()
            except OSError:
                return  # the listener closed, which is the fixture going away
            server = Server(
                Channel.from_socket(taken),
                exports,
                token=None if answered else "not-the-one",
            )
            answered.append(server)
            threading.Thread(target=server.serve, name="door", daemon=True).start()

    threading.Thread(target=answer, name="door-accept", daemon=True).start()
    yield f"tcp://127.0.0.1:{listening.getsockname()[1]}"
    # Shut down before closing: closing alone leaves the thread parked in `accept` for as
    # long as the test session lasts, holding the port it was listening on.
    with contextlib.suppress(OSError):
        listening.shutdown(socket.SHUT_RDWR)
    listening.close()


def test_a_mapping_whose_handshake_failed_holds_nothing_and_opens_again(
    door: str,
) -> None:
    """Because half a connection is worse than none: it is what says a mapping is open.

    A failure left in place would answer for the machine for the rest of the run -- an empty
    workspace, paths that are all relative and all there -- and never connect again.
    """
    held = Mapped(AnchorConfig(target=door, workspace=WORKSPACE))

    with pytest.raises(OSError, match="token"):
        _ = held.workspace

    with held:
        # Nothing of that was kept, so this opens a connection rather than reading one.
        assert held.workspace == WORKSPACE
        assert held.read_text("one.txt") == "on the target\n"
        assert held.listdir() == ["one.txt"]
