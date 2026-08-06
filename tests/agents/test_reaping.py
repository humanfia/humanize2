"""What a session leaves behind when it is let go of rather than closed.

A flow that opens a session per turn -- a Ralph loop runs for days -- drops each of them the
moment nothing holds it, and the process it was holding open is ended by a finalizer rather
than by a close. Ended is not enough: a process nobody takes the exit status of stays in the
table as a zombie for as long as humanize runs, so a long flow would gather one per turn.
"""

from __future__ import annotations

import gc
import sys
from typing import TYPE_CHECKING

from hmz.agents import AgentBase, AgentConfig, StreamSessionBase

if TYPE_CHECKING:
    import os
    from collections.abc import Iterable

    from hmz.agents import Event

CONFIG = AgentConfig(model="m", effort="high")


class _Session(StreamSessionBase):
    """A session whose process reads its stdin and says nothing, until it is ended."""

    def _command(self) -> list[str]:
        return [sys.executable, "-c", "import sys; sys.stdin.read()"]

    def _write(self, text: str, ticket: str = "") -> str:
        return text + "\n"

    def _read(self, line: str) -> Iterable[Event]:
        return ()


class _Agent(AgentBase):
    def new(self, cwd: str | os.PathLike[str] | None = None) -> _Session:
        return _Session(self, cwd)


def test_a_session_let_go_of_leaves_neither_its_process_nor_its_status() -> None:
    """The finalizer takes the status too, which is what keeps a zombie from being left."""
    session = _Agent(CONFIG).new()
    proc = session._start(session._command())
    assert proc.returncode is None

    del session
    gc.collect()

    # Taken rather than merely killed: a returncode is this process having been waited on,
    # and an unwaited one is exactly the row in the table that would be left behind.
    assert proc.returncode is not None
