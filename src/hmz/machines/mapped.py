"""The workspace on the machine a run is landing on, as the flow's own code reaches it.

An agent whose turns land elsewhere is answered for by coganchor: it reads and writes and runs
commands, and every one of those happens on the target without the agent being told. The flow
driving that agent is not under a supervisor -- it is this process, running Python -- so its
own reads, writes and commands happen here.

Most of the time that is exactly right and nothing has to be said about it: a container of the
flow's own is given the project directory itself rather than a copy, mounted at the path it
already has, so a file the flow opens is the same file the agent's turn opened. What is not
the same is everything that is not a file: a command the flow runs is run by this machine's
shell, against this machine's tools, which is the one thing a container was reached for to
avoid.

So this is the other half, said rather than intercepted. A flow that is running in a container
can ask for the workspace as the container has it -- read it, write it, run something in it --
and what comes back is the container's answer. It is the same road the agent's turns take,
which is why a file written here is a file the next turn reads.
"""

from __future__ import annotations

import errno
import io
import os
import shlex
import threading
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Self, cast

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping, Sequence

    from hmz.coganchor import AnchorConfig
    from hmz.coganchor.remote import RemoteClient

__all__ = ["Mapped", "Ran"]


@dataclass(frozen=True, slots=True)
class Ran:
    """What one command run on the machine came to.

    Attributes:
      argv: What was run.
      status: The exit status it stopped on.
      output: Everything it wrote, both streams together in the order they arrived -- which
        is what a person reading a command's output has, and what a flow deciding whether it
        worked reads.
    """

    argv: tuple[str, ...]
    status: int
    output: str

    @property
    def ok(self) -> bool:
        """Whether it succeeded, which is the one thing most callers ask."""
        return self.status == 0

    def __str__(self) -> str:
        """What it wrote, so that a flow may print one or put it in a prompt."""
        return self.output


class Mapped:
    """The workspace on the machine a run lands on, reached the way a turn reaches it.

    Opened when a flow first asks for it and held for the rest of the run: the connection is
    the same one an anchored turn opens, and opening one per read would be a handshake per
    line of a file.

    Every path may be given as the machine names it or relative to the workspace, since those
    are the same path for a container that was handed the project directory at the path it
    already had -- which is every container a flow runs in.
    """

    def __init__(self, anchor: AnchorConfig) -> None:
        """Initializes a mapping that has not connected to anything yet.

        Args:
          anchor: Where the run's work lands, which is what a turn of it is run under.
        """
        self._anchor = anchor
        self._client: RemoteClient | None = None
        self._link: Any = None
        self._lock = threading.RLock()
        self._workspace = ""

    @property
    def workspace(self) -> str:
        """The project directory, as the machine names it."""
        self._open()
        return self._workspace

    def read_text(self, path: str, encoding: str = "utf-8") -> str:
        """Reads a file on the machine.

        Args:
          path: The file, as the machine names it or relative to the workspace.
          encoding: How to read the bytes.

        Returns:
          What it holds.

        Raises:
          OSError: If it is not there, or cannot be read.
        """
        return self.read_bytes(path).decode(encoding)

    def read_bytes(self, path: str) -> bytes:
        """The same, as the bytes themselves."""
        held = io.BytesIO()
        self._client_of().read_file(self._at(path), held)
        return held.getvalue()

    def write_text(
        self, path: str, said: str, encoding: str = "utf-8", mode: int | None = None
    ) -> None:
        """Writes a file on the machine, replacing whatever was there.

        Args:
          path: The file, as the machine names it or relative to the workspace.
          said: What to write.
          encoding: How to write the bytes.
          mode: The permissions to give it, or None for the ones it has.

        Raises:
          OSError: If it cannot be written.
        """
        self.write_bytes(path, said.encode(encoding), mode=mode)

    def write_bytes(self, path: str, said: bytes, mode: int | None = None) -> None:
        """The same, from the bytes themselves."""
        self._client_of().write_file(self._at(path), io.BytesIO(said), mode)

    def listdir(self, path: str = "") -> list[str]:
        """What is in a directory on the machine.

        Args:
          path: The directory, or "" for the workspace itself.

        Returns:
          The names in it, in whatever order the machine gave them.

        Raises:
          OSError: If it is not there, or cannot be read.
        """
        said = self._client_of().listdir(self._at(path) if path else self.workspace)
        entries = cast("list[Any]", said.get("entries") or [])
        return [
            str(cast("dict[str, Any]", one).get("name", one))
            if isinstance(one, dict)
            else str(one)
            for one in entries
        ]

    def exists(self, path: str) -> bool:
        """Whether something is at that path on the machine.

        Args:
          path: The path, as the machine names it or relative to the workspace.

        Returns:
          True where something is there. Asked as a listing, since that is the one thing the
          target answers about a path without reading it: not there at all is the one answer
          that means no, and anything else -- a file where a directory was asked about, a
          permission -- is something being there.
        """
        try:
            self._client_of().listdir(self._at(path))
        except OSError as why:
            return why.errno != errno.ENOENT
        return True

    def mkdir(self, path: str, *, parents: bool = True) -> None:
        """Makes a directory on the machine."""
        self._client_of().mkdir(self._at(path), parents=parents)

    def remove(self, path: str) -> None:
        """Takes a file away on the machine."""
        self._client_of().unlink(self._at(path))

    def run(
        self,
        argv: Sequence[str] | str,
        *,
        cwd: str = "",
        env: Mapping[str, str] | None = None,
    ) -> Ran:
        """Runs a command on the machine, and waits for it.

        Which is the half a mounted workspace does not answer for: the files are the same
        files either way, and the tools are the machine's.

        Args:
          argv: The command, as a list or as one line to be split the way a shell splits it.
          cwd: Where to run it, as the machine names it or relative to the workspace, or ""
            for the workspace itself.
          env: What to run it with on top of nothing -- a command on another machine inherits
            that machine's environment rather than this process's.

        Returns:
          What it came to.

        Raises:
          OSError: If it could not be started.
        """
        held = list(shlex.split(argv) if isinstance(argv, str) else argv)
        if not held:
            raise ValueError("a command to run is at least a program")
        said: list[bytes] = []
        done = threading.Event()
        status: list[int] = []
        went: list[OSError] = []

        def wrote(_stream: Any, data: bytes) -> None:
            said.append(data)

        def ended(payload: dict[str, Any] | None, why: OSError | None) -> None:
            if why is not None:
                went.append(why)
            elif payload is not None:
                held = payload.get("exit_code")
                # A command killed by a signal has no status of its own, and the shell's
                # convention is what everything that reads one expects.
                status.append(
                    int(held)
                    if held is not None
                    else 128 + int(payload.get("signal") or 0)
                )
            done.set()

        client = self._client_of()
        client.start_exec(
            held,
            self._at(cwd) if cwd else self.workspace,
            dict(env or {}),
            wrote,
            ended,
        )
        done.wait()
        if went:
            raise went[0]
        return Ran(
            argv=tuple(held),
            # One that ended without saying how did not succeed: a status made up as zero
            # would be a command a flow read as having worked.
            status=status[0] if status else 1,
            output=b"".join(said).decode("utf-8", "replace"),
        )

    def close(self) -> None:
        """Lets go of the connection, for a run that is over. Doing it twice does it once."""
        with self._lock:
            client, self._client = self._client, None
            link, self._link = self._link, None
        if client is not None:
            client.close()
        if link is not None:
            link.close()

    def _open(self) -> None:
        """Connects, once, the first time a flow asks for anything."""
        with self._lock:
            if self._client is not None:
                return
            from hmz.coganchor import transport
            from hmz.coganchor.remote import RemoteClient

            target, workspace, export = self._anchor.mount()
            self._link = transport.connect(target, [export], self._anchor.token)
            self._client = RemoteClient(self._link.channel)
            self._client.start(self._anchor.token)
            self._workspace = workspace

    def _client_of(self) -> RemoteClient:
        """The connection, opening it where nothing has yet."""
        self._open()
        assert self._client is not None  # noqa: S101 -- `_open` set it or raised
        return self._client

    def _at(self, path: str) -> str:
        """One path as the machine names it.

        Args:
          path: What was asked for, absolute or relative to the workspace.

        Returns:
          The absolute path on the machine.
        """
        if path.startswith("/"):
            return path
        return os.path.normpath(os.path.join(self.workspace, path))  # noqa: PTH118

    def __enter__(self) -> Self:
        """Answers with itself, so a flow may hold one for a block."""
        return self

    def __exit__(self, *_why: object) -> None:
        """Lets go of the connection, however the block ended."""
        self.close()

    def __iter__(self) -> Iterator[str]:
        """What is in the workspace, so that `for one in inside()` reads as it looks."""
        return iter(self.listdir())
