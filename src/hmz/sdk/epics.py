"""The runs of a workspace that have already happened, and what is gathered out of them.

One run is one epic: a directory holding what happened, what each session was logged to, and
what a flow that says it can be picked up left behind. What is written down as a run happens
is :mod:`hmz.epic`; reading the backends' own logs back is :mod:`hmz.tracing`; packaging one
whole run up to send somewhere is :mod:`hmz.exporting`. All three are asked here, so that
whatever is listing the runs -- a command line, the interface's own `/epics` -- asks one
object about the one workspace it is about.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import os
    from collections.abc import Iterable, Mapping
    from typing import Any

    from hmz.epic import Ran, Session

__all__ = ["Epics"]


class Epics:
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
        from hmz.epic import under

        return under(self._workspace)

    def all(self) -> list[Path]:
        """Every run of this workspace, oldest first, which is the order they are named in."""
        from hmz.epic import epics

        return epics(self._workspace)

    def read(self, epic: Path) -> Ran | None:
        """What one run was: when, which flow, on what, how it went, and what it opened."""
        from hmz.epic import read

        return read(epic)

    def sessions(self, epic: Path) -> list[Session]:
        """Every session one run opened, across each of the records it holds."""
        from hmz.epic import sessions

        return sessions(epic)

    def opened(self, epic: Path) -> dict[str, list[str]]:
        """What each agent of one run opened, by the name the run knew that agent as."""
        from hmz.epic import opened

        return opened(epic)

    def resumed(self, flow: str) -> Path | None:
        """The last run of one flow here, which is what running a resumable flow picks up."""
        from hmz.epic import resumed

        return resumed(flow, self._workspace)

    def state(self, epic: Path, flow: str = "") -> dict[str, Any]:
        """What a flow that says it can be picked up left behind in one run."""
        from hmz.epic import state

        return state(epic, flow)

    def traced(
        self,
        epic: Path,
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
          epic: The run, by the directory it is written in.
          output: Where to write it, or None for the run's own `traces/`, named after the
            moment it was collected so that collecting twice keeps both.
          start: The earliest session time to include, in any wording dateparser understands.
          end: The latest.

        Returns:
          Where it was written, and the trace itself.
        """
        import datetime

        from hmz.epic import TRACES
        from hmz.tracing.profile import PROFILE

        agents = self.opened(epic)
        where = Path(output) if output is not None else None
        if where is None:
            stamp = datetime.datetime.now(datetime.UTC).strftime("%Y%m%dT%H%M%SZ")
            where = epic / TRACES / f"{stamp}.trace.json"
        where.parent.mkdir(parents=True, exist_ok=True)
        # No workspace at all: the ids are exactly this run's, wherever they were logged.
        document = Epics().trace(
            sessions=[ident for ids in agents.values() for ident in ids],
            agents=agents or None,
            output=where,
            start=start,
            end=end,
            profile=epic / PROFILE,
        )
        return where, document

    def bundled(
        self,
        epic: Path,
        *,
        output: str | os.PathLike[str] | None = None,
        transcript: str | None = None,
    ) -> tuple[Path, dict[str, Any]]:
        """Packages one whole run up as one archive, to send to somebody who was not there.

        Everything the run wrote and everything its sessions were logged to, with the links
        followed: an epic points at the backends' own logs rather than copying them, and a
        directory of symlinks is a bundle with nothing in it the moment it leaves the machine
        that made it. Credentials are struck out of every byte of it.

        Args:
          epic: The run, by the directory it is written in.
          output: Where to write it -- a file, or a directory to write it into under its own
            name -- or None for `.humanize/` beside wherever this is being run.
          transcript: What was on the screen, for an export from the interface, or None from
            a command line, where nothing was drawn.

        Returns:
          Where it was written, and the manifest as it was written there -- which is what
          says what went in, rather than a second reading of the run afterwards.
        """
        from hmz.exporting import bundle

        return bundle(epic, output, transcript=transcript)

    def trace(
        self,
        *,
        sessions: str | Iterable[str] | None = None,
        agents: Mapping[str, Iterable[str]] | None = None,
        output: str | os.PathLike[str] | None = None,
        start: str | None = None,
        end: str | None = None,
        profile: str | os.PathLike[str] | None = None,
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
        )
