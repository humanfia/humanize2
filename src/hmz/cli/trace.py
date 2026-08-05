"""``hmz trace`` -- what a run left behind, gathered into something that can be read.

One command with what there is to do to a trace under it, rather than a verb at the top
level: collecting one is what there is today, and a top-level `collect` says what happens to
the thing without ever saying what the thing is.

What one is of is a run, and what it holds is that run's own sessions. A cycle is a directory
-- what happened, what each session was logged to, what the flow left behind -- and a trace of
that run belongs beside those rather than in a `.humanize/` in whatever directory somebody
happened to be standing in. An output named outright still wins: a trace is also a thing to
attach to an issue.

A directory holds sessions no run of a flow ever opened -- somebody's own afternoon at a
coding agent -- and `--session` and `--all` are how those are read back. They are not a run's
trace and are not filed as one; they are here and nowhere else, since the interface's own
`/cycles` is a list of runs and has nothing to hang them on.
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
    import datetime

    from hmz.cycle import cycles, opened, read
    from hmz.tracing.collector import collect as gather
    from hmz.tracing.profile import PROFILE

    wider = bool(said.sessions or said.everything)
    if wider and said.cycle:
        parser.error(
            "a trace of a run holds that run's own sessions: --cycle takes neither "
            "--session nor --all"
        )
    found = cycles(said.workspace)
    if said.cycle:
        found = [one for one in found if one.name.startswith(said.cycle)]
        if not found:
            parser.error(f"no run of this workspace is called {said.cycle!r}")
    # A run to trace, unless the line asked for what a run is not: the last of the workspace
    # where none was named, and none at all in a directory nothing has been run in.
    cycle = None if wider else found[-1] if found else None
    # Who ran what, taken from the run being traced: the backends log a session under an id
    # and never say whose it was, so two agents at one configuration are one agent to a trace
    # unless the run itself says otherwise -- and the run wrote down that it did.
    agents = opened(cycle) if cycle is not None else {}
    profile = cycle / PROFILE if cycle is not None else None
    # The run's own sessions, which are the trace. Asked for by id and not by workspace: the
    # ids are exactly this run's, and a flow that worked in a machine's mirror logged them
    # under a directory this one has never heard of.
    held = (
        [ident for ids in agents.values() for ident in ids]
        if cycle is not None
        else said.sessions
    )
    stamp = datetime.datetime.now(datetime.UTC).strftime("%Y%m%dT%H%M%SZ")
    output = said.output or str(_beside(cycle, said.workspace) / f"{stamp}.trace.json")

    try:
        document = gather(
            None if cycle is not None else said.workspace,
            sessions=held,
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
    programs = (
        f", {_many(summary['programs'], 'program')}" if summary.get("programs") else ""
    )
    print(
        f"{output}{where}: {_many(summary.get('sessions', '0'), 'session')}, "
        f"{_many(summary.get('slices', '0'), 'slice')}{programs}"
    )
    return 0


def _many(count: str, thing: str) -> str:
    """How many of something the trace holds, said as English says it.

    Args:
      count: How many, as the trace counted them.
      thing: What they are, in the singular.

    Returns:
      The two words -- `1 session`, `3 sessions` -- since a line somebody reads is prose, and
      `1 sessions` is a line that reads as a template nobody finished.
    """
    return f"{count} {thing}" if count == "1" else f"{count} {thing}s"


def _beside(cycle: Path | None, workspace: str | None) -> Path:
    """Where a trace goes when the line did not say, and makes the directory.

    Args:
      cycle: The run being traced, or None for a trace that is not of one -- a workspace
        nothing has been run in, or a line that asked for sessions rather than a run.
      workspace: What the line named, if anything.

    Returns:
      The directory to write into: the run's own `traces/`, or -- for a trace of no one run --
      the directory that workspace's runs are kept in, so that it is still with the rest of
      what humanize keeps about this project rather than in whatever directory somebody
      happened to be standing in, and is still not inside a run it is not a trace of.
    """
    from hmz.cycle import TRACES, under

    at = cycle / TRACES if cycle is not None else under(workspace)
    at.mkdir(parents=True, exist_ok=True)
    return at
