"""What one run of one flow was, written down as it runs.

A flow drives several agents through many sessions, and every one of those sessions is written
down by the backend that ran it -- under an id of its own, in a directory of its own, saying
nothing about whose it was or what it was part of. The run itself is written nowhere. This is
that: which flow was run, on what, by which agents, and which sessions each of them opened as
it went. Enough to gather a trace of the run afterwards out of the ids alone, and enough to
find the sessions a run left behind.

Not what the sessions said. A backend's own log is the turn-by-turn record and this is not a
second copy of it: what is kept here is the shape of the run, one line per thing that happened
to it.

One cycle is one run. It opens when the flow starts and closes when the flow stops, however it
stops -- finished, failed, or interrupted. A closed cycle is never reopened: running the flow
again is another run, with sessions of its own, and so another cycle.
"""

from __future__ import annotations

import datetime
import json
import re
import threading
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Any, Self

from humanize import home

if TYPE_CHECKING:
    from collections.abc import Sequence

    from .agents import AgentBase

__all__ = ["Cycle", "cycles", "opened"]

#: What a directory may be called after: everything else in a path is flattened, the way the
#: agents themselves flatten a workspace into the folder they log it under.
_PLAIN = re.compile(r"[^A-Za-z0-9]")


def _now() -> str:
    """This moment, as every file humanize writes spells one."""
    return (
        datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
    )


class Cycle:
    """One run of one flow: the file it is written to, and what has happened to it so far."""

    def __init__(
        self,
        flow: str,
        agents: Sequence[AgentBase],
        task: str,
        workspace: Path | None = None,
    ) -> None:
        """Opens a cycle, and writes down what it is a run of.

        Args:
          flow: The flow being run, as it was named.
          agents: The agents it is being run with, in the order it takes them.
          task: What they were asked to do.
          workspace: Where the run happens, defaulting to this directory. Cycles are kept
            under the workspace they ran in, since that is what anyone looking for one has.
        """
        self._at = (
            home()
            / "cycles"
            / _PLAIN.sub("-", str((workspace or Path.cwd()).resolve()))
            # The moment names it and six hex say which, since two flows may be started in
            # one second and neither is the other's run.
            / f"{datetime.datetime.now(datetime.UTC):%Y%m%dT%H%M%SZ}-{uuid.uuid4().hex[:6]}.jsonl"
        )
        self._writing = (
            threading.Lock()
        )  # sessions open on whichever thread a turn runs on
        self._agents = list(agents)
        self.write(
            "began",
            flow=flow,
            task=task,
            workspace=str((workspace or Path.cwd()).resolve()),
            agents=[
                {
                    "agent": agent.id,
                    "backend": agent.backend,
                    "model": agent.config.model,
                    "effort": agent.config.effort,
                }
                for agent in agents
            ],
        )

    @property
    def path(self) -> Path:
        """The file this cycle is written to."""
        return self._at

    def __enter__(self) -> Self:
        """Hands the cycle to whatever is running the flow inside it."""
        return self

    def __exit__(
        self, kind: type[BaseException] | None, why: object, traceback: object
    ) -> None:
        """Closes the cycle, saying how the run ended: a cycle closes once and for all.

        Args:
          kind: What was raised out of the run, if anything.
          why: The exception itself, unread.
          traceback: Where it was raised, unread.
        """
        from .agents import Stopped

        # An agent that was told to stop is a run that was stopped, whatever the turn under
        # way made of it: the process goes out from under that turn, and from inside one that
        # reads as a turn that could not finish.
        stopped = kind is not None and (
            issubclass(kind, Stopped) or any(agent.stopped for agent in self._agents)
        )
        self.write(
            "ended",
            how="stopped" if stopped else "failed" if kind is not None else "done",
        )
        for agent in self._agents:
            agent.cycle = None

    def opened(self, agent: AgentBase, session: str) -> None:
        """Writes down a session one of the agents has just opened.

        Args:
          agent: Whose session it is.
          session: The backend's id for it, which is what a trace of the run is gathered by.
        """
        self.write("opened", agent=agent.id, backend=agent.backend, session=session)

    def write(self, event: str, **said: Any) -> None:
        """Appends one line to the cycle.

        Appended and flushed apiece rather than held: a flow runs for hours and is watched
        while it does, and a run that died is a run whose cycle has to say what it got to.

        Args:
          event: What happened.
          said: What is worth saying about it.
        """
        with self._writing:
            self._at.parent.mkdir(parents=True, exist_ok=True)
            with self._at.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps({"event": event, "at": _now(), **said}) + "\n")


def cycles(workspace: Path | str | None = None) -> list[Path]:
    """The cycles run in one workspace, oldest first.

    Args:
      workspace: Where they ran, defaulting to this directory.

    Returns:
      One path per cycle, which is empty where nothing has been run.
    """
    under = (
        home()
        / "cycles"
        / _PLAIN.sub("-", str(Path(workspace or Path.cwd()).resolve()))
    )
    return sorted(under.glob("*.jsonl"))


def opened(cycle: Path) -> dict[str, list[str]]:
    """What each agent of one cycle opened, as the ids the backends gave those sessions.

    Which is what a trace is gathered by: the backends log a session under an id and never
    say whose it was, so the run has to say it instead.

    Args:
      cycle: The cycle to read.

    Returns:
      One entry per agent that opened anything, oldest session first.
    """
    held: dict[str, list[str]] = {}
    try:
        lines = cycle.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return held
    for line in lines:
        try:
            said = json.loads(line)
        except ValueError:
            continue  # a run that died mid-line, which is a line and not a cycle
        if said.get("event") == "opened" and said.get("session"):
            held.setdefault(str(said.get("agent")), []).append(str(said["session"]))
    return held
