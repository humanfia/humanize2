"""``hmz trace`` -- what a run left behind, gathered into something that can be read.

One command with what there is to do to a trace under it, rather than a verb at the top
level: collecting one is what there is today, and a top-level `collect` says what happens to
the thing without ever saying what the thing is.

What one is of is a run, and what it holds is that run's own sessions. An epic is a directory
-- what happened, what each session was logged to, what the flow left behind -- and a trace of
that run belongs beside those rather than in a `.humanize/` in whatever directory somebody
happened to be standing in. An output named outright still wins: a trace is also a thing to
attach to an issue.

A directory holds sessions no run of a flow ever opened -- somebody's own afternoon at a
coding agent -- and `--session` and `--all` are how those are read back. They are not a run's
trace and are not filed as one; they are here and nowhere else, since the interface's own
`/epics` is a list of runs and has nothing to hang them on.

The runs and the gathering are both reached through :class:`hmz.sdk.Hmz`, which is what the
sheet the runs are read on asks for the same trace.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from argparse import ArgumentParser, Namespace
    from typing import Any

    from hmz.sdk import Epics

__all__ = ["trace"]


def trace(argv: list[str]) -> int:
    """Carries out one `hmz trace` line.

    Args:
      argv: What followed the command name.

    Returns:
      Zero, or two for a line to correct.
    """
    import argparse

    parser = argparse.ArgumentParser(
        prog="hmz trace",
        description="What a run left behind: the agents' own trajectories, and the programs "
        "they ran, gathered into one Chrome trace.",
    )
    doing = parser.add_subparsers(dest="doing", metavar="COMMAND")

    collecting = doing.add_parser(
        "collect", help="aggregate what a run left behind into a Chrome trace"
    )
    collecting.add_argument(
        "workspace",
        nargs="?",
        help="Workspace directory, defaults to the current one unless sessions are named.",
    )
    collecting.add_argument(
        "--epic",
        help="Which run to trace, by the name of its directory or a leading part of it, "
        "defaults to the last run of the workspace.",
    )
    collecting.add_argument(
        "--session",
        action="append",
        dest="sessions",
        metavar="SESSION[,SESSION...]",
        help="Trace these sessions instead of a run, comma separated and repeatable.",
    )
    collecting.add_argument(
        "--all",
        dest="everything",
        action="store_true",
        help="Trace every session of the workspace instead of a run, whichever run "
        "opened them and whether any did.",
    )
    collecting.add_argument(
        "--output",
        help="Trace file to write, defaults to traces/<datetime>.trace.json in the epic.",
    )
    collecting.add_argument(
        "--start", help="Earliest session time to include, e.g. '2 days ago'."
    )
    collecting.add_argument(
        "--end", help="Latest session time to include, e.g. 'yesterday 18:00'."
    )
    args = parser.parse_args(argv)
    if args.doing is None:
        parser.print_help()
        return 2
    return _collect(args, parser)


def _collect(said: Namespace, parser: ArgumentParser) -> int:
    """Writes what one run left behind as one trace file.

    A trace is of a run: the sessions that run opened and no others, named by the agents it
    said opened them, beside the programs it profiled. `--session` and `--all` are the other
    thing -- what a directory holds whoever opened it, which is how a session nothing drove
    is read back -- and neither is a run's trace, so neither goes in a run's directory.

    Args:
      said: What the line said.
      parser: The line itself, for reporting one to correct.

    Returns:
      Zero, once the trace has been written.
    """
    from hmz.cli import many
    from hmz.sdk import Hmz

    runs = Hmz(said.workspace).epics
    wider = bool(said.sessions or said.everything)
    if wider and said.epic:
        parser.error(
            "a trace of a run holds that run's own sessions: --epic takes neither "
            "--session nor --all"
        )
    found = runs.all()
    if said.epic:
        found = [one for one in found if one.name.startswith(said.epic)]
        if not found:
            parser.error(f"no run of this workspace is called {said.epic!r}")
    # A run to trace, unless the line asked for what a run is not: the last of the workspace
    # where none was named, and none at all in a directory nothing has been run in.
    epic = None if wider else found[-1] if found else None
    try:
        if epic is not None:
            # A trace of a run is the run's own to gather: which sessions it opened, which
            # agent opened each, the profile beside them, and where it goes.
            output, document = runs.traced(
                epic, output=said.output, start=said.start, end=said.end
            )
        else:
            output, document = _elsewhere(runs, said)
    except ValueError as why:
        parser.error(str(why))
    summary = document["otherData"]
    ran = runs.read(epic) if epic is not None else None
    where = f" of {ran.name}" if ran is not None else ""
    programs = (
        f", {many(summary['programs'], 'program')}" if summary.get("programs") else ""
    )
    print(
        f"{output}{where}: {many(summary.get('sessions', '0'), 'session')}, "
        f"{many(summary.get('slices', '0'), 'slice')}{programs}"
    )
    return 0


def _elsewhere(runs: Epics, said: Namespace) -> tuple[Path, dict[str, Any]]:
    """Gathers what a directory holds whoever opened it, which is a trace of no run.

    A session no flow ever drove is still a session to read back. It is not a run's trace and
    is not filed as one: it goes beside the runs rather than inside one, so that it is still
    with the rest of what humanize keeps about this project rather than in whatever directory
    somebody happened to be standing in.

    Args:
      runs: The runs of the workspace the line named.
      said: What the line said.

    Returns:
      Where it was written, and the trace itself.
    """
    import datetime

    where = Path(said.output) if said.output else None
    if where is None:
        at = runs.under()
        at.mkdir(parents=True, exist_ok=True)
        stamp = datetime.datetime.now(datetime.UTC).strftime("%Y%m%dT%H%M%SZ")
        where = at / f"{stamp}.trace.json"
    where.parent.mkdir(parents=True, exist_ok=True)
    return where, runs.trace(
        sessions=said.sessions, output=where, start=said.start, end=said.end
    )
