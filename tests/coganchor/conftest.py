"""Shared fixtures.

Every end-to-end test runs three directories apart:

``target``
    Stands in for the target's copy of the project. Only the serving half
    touches it.
``mirror``
    The local mirror. Starts empty.
``workspace``
    The virtual path both sides use to name the project.  It exists on neither
    machine, so any correct read proves the data came through the target.

That separation is what makes the assertions meaningful: if interception ever
silently fell back to local execution, the tests would read an empty directory.
"""

from __future__ import annotations

import os
import socket
import subprocess
import threading
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from amflows.coganchor import AnchorConfig
from amflows.coganchor.proto import Channel
from amflows.coganchor.remote import RemoteClient
from amflows.coganchor.serve.exports import ExportTable
from amflows.coganchor.serve.server import Server

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

#: The virtual workspace path.  Deliberately not creatable without root, so it
#: cannot accidentally resolve on either side.
VIRTUAL_WORKSPACE = "/coganchor-project"

DEFAULT_TIMEOUT = 90


@dataclass(frozen=True)
class Anchorage:
    """A configured coganchor session under test."""

    target: Path
    mirror: Path
    workspace: str = VIRTUAL_WORKSPACE

    def seed(self, files: dict[str, str]) -> None:
        """Create files on the target before the agent starts."""
        for name, content in files.items():
            path = self.target / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)

    def run(
        self,
        *command: str,
        stdin: bytes = b"",
        timeout: int = DEFAULT_TIMEOUT,
        **settings: Any,
    ) -> subprocess.CompletedProcess[str]:
        """Run ``command`` as the agent under full interception.

        Spawned the way a flow spawns it, through :meth:`AnchorConfig.command`, so the
        settings this suite drives coganchor with are the ones janus renders.
        """
        config = AnchorConfig(
            target=f"local:{self.target}",
            workspace=self.workspace,
            shadow=str(self.mirror),
            **settings,
        )
        completed = subprocess.run(
            config.command(command),
            input=stdin,
            capture_output=True,
            timeout=timeout,
            cwd=str(REPO_ROOT),
            env={**os.environ, "PYTHONPATH": str(REPO_ROOT / "src")},
            check=False,
        )
        return _decode(completed)

    def shell(
        self, script: str, *, stdin: bytes = b"", timeout: int = DEFAULT_TIMEOUT
    ) -> subprocess.CompletedProcess[str]:
        """Run a bash script as the agent."""
        return self.run("bash", "-c", script, stdin=stdin, timeout=timeout)

    def target_text(self, name: str) -> str:
        return (self.target / name).read_text()


def _decode(
    result: subprocess.CompletedProcess[bytes],
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(
        result.args,
        result.returncode,
        result.stdout.decode("utf-8", "replace"),
        result.stderr.decode("utf-8", "replace"),
    )


@pytest.fixture
def anchorage(tmp_path: Path) -> Anchorage:
    """A fresh target/mirror pair for one test."""
    target = tmp_path / "target"
    mirror = tmp_path / "mirror"
    target.mkdir()
    mirror.mkdir()
    return Anchorage(target=target, mirror=mirror)


#: Virtual root the unit tests export, as opposed to the end-to-end workspace.
VIRTUAL_EXPORT = "/project"


@dataclass(frozen=True)
class Link:
    """A client talking to an in-process server over a socketpair."""

    client: RemoteClient
    target: Path


@pytest.fixture
def link(tmp_path: Path) -> Iterator[Link]:
    """Both halves wired together in one process, without a subprocess or a port."""
    target = tmp_path / "target"
    target.mkdir()
    left, right = socket.socketpair()
    server = Server(
        Channel.from_socket(right), ExportTable.parse([f"{VIRTUAL_EXPORT}:{target}"])
    )
    thread = threading.Thread(target=server.serve, daemon=True)
    thread.start()

    client = RemoteClient(Channel.from_socket(left))
    client.start()
    yield Link(client, target)
    client.close()
    thread.join(timeout=5)
