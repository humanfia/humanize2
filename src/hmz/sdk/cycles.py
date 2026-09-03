"""The runs of a workspace that have already happened, and the traces gathered of them.

One run is one cycle: a directory holding what happened, what each session was logged to, and
what a flow that says it can be picked up left behind. What is written down as a run happens
is :mod:`hmz.cycle`; reading the backends' own logs back is :mod:`hmz.tracing`. Both are asked
here, so that whatever is listing the runs -- a command line, the interface's own `/cycles` --
asks one object about the one workspace it is about.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import os
    from collections.abc import Iterable, Mapping
    from typing import Any

    from hmz.cycle import Ran, Session

__all__ = ["Cycles"]


class Cycles:
    """Every run of one workspace, newest last, and what can be read back out of one."""

    def __init__(self, workspace: str | os.PathLike[str] | None = None) -> None:
        """Holds the workspace whose runs these are.

        Args:
          workspace: The project directory the runs were run in, or None for wherever
            humanize is being run. None is kept as None rather than filled in: naming
            sessions without a workspace collects them wherever they were recorded, and a
            workspace here would narrow that to whatever directory somebody was standing in.
        """
        self._workspace = Path(workspace) if workspace is not None else None

    def under(self) -> Path:
        """The directory this workspace's runs are kept in."""
        from hmz.cycle import under

        return under(self._workspace)

    def all(self) -> list[Path]:
        """Every run of this workspace, oldest first, which is the order they are named in."""
        from hmz.cycle import cycles

        return cycles(self._workspace)

    def read(self, cycle: Path) -> Ran | None:
        """What one run was: when, which flow, on what, how it went, and what it opened."""
        from hmz.cycle import read

        return read(cycle)

    def sessions(self, cycle: Path) -> list[Session]:
        """Every session one run opened, across each of the records it holds."""
        from hmz.cycle import sessions

        return sessions(cycle)

    def opened(self, cycle: Path) -> dict[str, list[str]]:
        """What each agent of one run opened, by the name the run knew that agent as."""
        from hmz.cycle import opened

        return opened(cycle)

    def resumed(self, flow: str) -> Path | None:
        """The last run of one flow here, which is what running a resumable flow picks up."""
        from hmz.cycle import resumed

        return resumed(flow, self._workspace)

    def state(self, cycle: Path, flow: str = "") -> dict[str, Any]:
        """What a flow that says it can be picked up left behind in one run."""
        from hmz.cycle import state

        return state(cycle, flow)

    def traced(
        self,
        cycle: Path,
        *,
        output: str | os.PathLike[str] | None = None,
        start: str | None = None,
        end: str | None = None,
    ) -> tuple[Path, dict[str, Any]]:
        """Gathers what one run left behind into a trace of that run.

        A trace of a run holds the sessions that run opened and no others, asked for by the
        ids the run wrote down rather than by the directory it ran in: a directory is run in
        over and over, and a flow that worked in a machine's mirror logged its sessions under
        one this has never heard of. And it goes with the run: the sessions it points at and
        the state it left are already there.

        Args:
          cycle: The run, by the directory it is written in.
          output: Where to write it, or None for the run's own `traces/`, named after the
            moment it was collected so that collecting twice keeps both.
          start: The earliest session time to include, in any wording dateparser understands.
          end: The latest.

        Returns:
          Where it was written, and the trace itself.
        """
        import datetime

        from hmz.cycle import TRACES, forks
        from hmz.tracing.profile import PROFILE

        agents = self.opened(cycle)
        where = Path(output) if output is not None else None
        if where is None:
            stamp = datetime.datetime.now(datetime.UTC).strftime("%Y%m%dT%H%M%SZ")
            where = cycle / TRACES / f"{stamp}.trace.json"
        where.parent.mkdir(parents=True, exist_ok=True)
        # No workspace at all: the ids are exactly this run's, wherever they were logged.
        document = Cycles().trace(
            sessions=[ident for ids in agents.values() for ident in ids],
            agents=agents or None,
            output=where,
            start=start,
            end=end,
            profile=cycle / PROFILE,
            parents=forks(cycle),
        )
        return where, document

    def trace(
        self,
        *,
        sessions: str | Iterable[str] | None = None,
        agents: Mapping[str, Iterable[str]] | None = None,
        output: str | os.PathLike[str] | None = None,
        start: str | None = None,
        end: str | None = None,
        profile: str | os.PathLike[str] | None = None,
        parents: Mapping[str, str] | None = None,
    ) -> dict[str, Any]:
        """Gathers what a run left behind into one Chrome trace.

        Args:
          sessions: Which sessions to collect, or None for every session of the workspace.
            An empty iterable is no sessions rather than every session, which is what a trace
            of a run that opened none holds.
          agents: What each agent of a flow opened, so that a loop of one-shot sessions reads
            as one agent rather than a hundred.
          output: Where to write it, or None to gather it without writing.
          start: The earliest session time to include, in any wording dateparser understands.
          end: The latest.
          profile: Where the run's own profile was written, for a run that was profiled.
          parents: What each session branched from, child id to parent id, for the forked
            children a trace draws under their parent.

        Returns:
          The trace, as the object that was written.
        """
        from hmz.tracing.collector import collect

        return collect(
            self._workspace,
            sessions=sessions,
            agents=agents,
            output=output,
            start=start,
            end=end,
            profile=profile,
            parents=parents,
        )
