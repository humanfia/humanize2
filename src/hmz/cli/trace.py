"""``hmz trace`` -- what a run left behind, gathered into something that can be read.

One command with what there is to do to a trace under it, rather than a verb at the top
level: collecting one is what there is today, and a top-level `collect` says what happens to
the thing without ever saying what the thing is.

Where it goes is the run it is a trace of. A cycle is a directory -- what happened, what each
session was logged to, what the flow left behind -- and a trace of that run belongs beside
those rather than in a `.humanize/` in whatever directory somebody happened to be standing in.
An output named outright still wins: a trace is also a thing to attach to an issue.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from argparse import ArgumentParser, Namespace
    from pathlib import Path

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
        "--cycle",
        help="Which run the trace is filed with and named by, by the name of its directory "
        "or a leading part of it, defaults to the last run of the workspace.",
    )
    collecting.add_argument(
        "--session",
        action="append",
        dest="sessions",
        metavar="SESSION[,SESSION...]",
        help="Sessions to include, comma separated and repeatable, defaults to every session.",
    )
    collecting.add_argument(
        "--output",
        help="Trace file to write, defaults to traces/<datetime>.trace.json in the cycle.",
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

    Args:
      said: What the line said.
      parser: The line itself, for reporting one to correct.

    Returns:
      Zero, once the trace has been written.
    """
    import datetime

    from hmz.cycle import cycles, opened, read
    from hmz.tracing.collector import collect as gather
    from hmz.tracing.profile import PROFILE

    found = cycles(said.workspace)
    if said.cycle:
        found = [one for one in found if one.name.startswith(said.cycle)]
        if not found:
            parser.error(f"no run of this workspace is called {said.cycle!r}")
    cycle = found[-1] if found else None
    # Who ran what, taken from the run being traced: the backends log a session under an id
    # and never say whose it was, so two agents at one configuration are one agent to a trace
    # unless the run itself says otherwise -- and the run wrote down that it did.
    agents = opened(cycle) if cycle is not None else {}
    profile = cycle / PROFILE if cycle is not None else None
    stamp = datetime.datetime.now(datetime.UTC).strftime("%Y%m%dT%H%M%SZ")
    output = said.output or str(_beside(cycle, said.workspace) / f"{stamp}.trace.json")

    try:
        document = gather(
            said.workspace,
            sessions=said.sessions,
            agents=agents or None,
            output=output,
            start=said.start,
            end=said.end,
            profile=profile,
        )
    except ValueError as why:
        parser.error(str(why))
    summary = document["otherData"]
    ran = read(cycle) if cycle is not None else None
    where = f" of {ran.name}" if ran is not None else ""
    programs = f", {summary['programs']} programs" if summary.get("programs") else ""
    print(
        f"{output}{where}: {summary.get('sessions', '0')} sessions, "
        f"{summary.get('slices', '0')} slices{programs}"
    )
    return 0


def _beside(cycle: Path | None, workspace: str | None) -> Path:
    """Where a trace goes when the line did not say, and makes the directory.

    Args:
      cycle: The run being traced, or None where this workspace has run nothing.
      workspace: What the line named, if anything.

    Returns:
      The directory to write into: the run's own `traces/`, or -- for a workspace nothing has
      been run in -- the directory its runs would be kept in, so that a trace is still with
      the rest of what humanize keeps about this project rather than in whatever directory
      somebody happened to be standing in.
    """
    from hmz.cycle import TRACES, under

    at = cycle / TRACES if cycle is not None else under(workspace)
    at.mkdir(parents=True, exist_ok=True)
    return at
