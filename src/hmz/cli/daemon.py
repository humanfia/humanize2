"""``hmz daemon`` -- the runs being held apart from a terminal, from a command line.

A run of a flow outlives the terminal it was started from: the interface goes on running
where nothing is reading it, and `hmz` in that directory opens it again. This is the rest of
what there is to say about one from outside it -- which there are, what one of them is doing,
and the two ways one ends.

Starting one is here too, for the machine that is being set up rather than sat at: a run put
where a terminal closing cannot reach it, ready for the first `hmz` to read.
"""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from argparse import ArgumentParser

    from hmz.daemon import Daemon

__all__ = ["daemon"]


def daemon(argv: list[str]) -> int:
    """Carries out one `hmz daemon` line.

    Args:
      argv: What followed the command name.

    Returns:
      Zero, or two for a line to correct, or one for something that could not be done.
    """
    import argparse

    parser = argparse.ArgumentParser(
        prog="hmz daemon",
        description="The runs being held apart from a terminal: one per directory, holding "
        "the interface and whatever flow is running in it.",
    )
    doing = parser.add_subparsers(dest="doing", metavar="COMMAND")

    listing = doing.add_parser("list", help="what runs are being held")
    listing.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        help="just the directories, one a line, for a script to read",
    )

    showing = doing.add_parser("status", help="what one of them is doing")
    showing.add_argument("workspace", nargs="?", default=None, help="which directory")

    starting = doing.add_parser("start", help="hold a run here, without reading it")
    starting.add_argument(
        "-f", "--flow", default="", metavar="FLOW", help="the flow to open on"
    )
    starting.add_argument(
        "-a",
        "--agent",
        action="append",
        default=[],
        dest="agents",
        metavar="CLI/MODEL:EFFORT",
        help="what one of that flow's agents runs; needs -f",
    )

    reading = doing.add_parser("attach", help="read one of them from this terminal")
    reading.add_argument("workspace", nargs="?", default=None, help="which directory")

    ending = doing.add_parser("stop", help="stop the flow and close the interface")
    ending.add_argument("workspace", nargs="?", default=None, help="which directory")
    ending.add_argument(
        "--kill",
        action="store_true",
        help="end the process holding it instead of asking it to close, for one that will "
        "not go",
    )

    args = parser.parse_args(argv)
    if args.doing in (None, "list"):
        return _list(quiet=getattr(args, "quiet", False))
    if args.doing == "start":
        return _start(args.flow, args.agents, parser)
    if args.doing == "status":
        return _status(args.workspace)
    if args.doing == "attach":
        return _attach(args.workspace)
    return _stop(args.workspace, kill=args.kill)


def _list(*, quiet: bool) -> int:
    """Prints every run being held on this machine, oldest first."""
    from hmz.cli import many
    from hmz.daemon import daemons

    found = daemons()
    if not found:
        if quiet:
            return 0
        print("no runs are being held; `hmz` in a directory starts one")
        return 0
    for one in found:
        if quiet:
            print(one.workspace)
            continue
        said = one.status()
        reading = said.get("attached") or 0
        print(
            f"{one.workspace}  pid {one.pid}  since {one.started}  "
            f"{many(reading, 'terminal')} reading"
        )
    return 0


def _status(workspace: str | None) -> int:
    """Prints what one held run is doing."""
    from hmz.cli import many

    one = _found(workspace)
    if one is None:
        return 1
    said = one.status()
    flows = said.get("flows")
    print(f"workspace   {one.workspace}")
    print(f"pid         {one.pid}")
    print(f"started     {one.started}")
    print(f"socket      {one.at}")
    # What the run is drawing for, which is the terminal it was started from: a run holds
    # one pseudoterminal for its whole life, and a terminal of another kind that reads it
    # later is read at that one's size and told in that one's language.
    print(f"drawing for {said.get('term') or 'an unnamed terminal'}")
    print(f"reading     {many(said.get('attached') or 0, 'terminal')}")
    print(f"running     {', '.join(flows) if flows else 'nothing'}")
    return 0


def _attach(workspace: str | None) -> int:
    """Reads one held run from this terminal, which is what `hmz` alone does."""
    one = _found(workspace)
    if one is None:
        return 1
    return one.attach()


def _start(flow: str, agents: list[str], parser: ArgumentParser) -> int:
    """Holds a run here without reading it, for a machine being set up rather than sat at."""
    import functools

    from hmz import daemon as held
    from hmz.cli import apart, runs_of

    already = held.running()
    if already is not None:
        print(
            f"hmz: a run is already being held in {already.workspace}", file=sys.stderr
        )
        return 1
    opening = functools.partial(apart, flow, tuple(runs_of(parser, flow, agents)), None)
    try:
        one = held.start(opening)
    except OSError as why:
        print(f"hmz: {why}", file=sys.stderr)
        return 1
    print(f"holding a run in {one.workspace} as pid {one.pid}; `hmz` reads it")
    return 0


def _stop(workspace: str | None, *, kill: bool) -> int:
    """Stops the flow and closes the interface, or ends the process holding both."""
    one = _found(workspace)
    if one is None:
        return 1
    gone = one.kill() if kill else one.stop()
    if not gone:
        print(
            f"hmz: the run in {one.workspace} has not gone; `--kill` ends it",
            file=sys.stderr,
        )
        return 1
    print(f"the run in {one.workspace} is over")
    return 0


def _found(workspace: str | None) -> Daemon | None:
    """The run being held in one directory, saying so where none is."""
    from hmz.daemon import running

    one = running(workspace)
    if one is None:
        where = workspace or "this directory"
        print(f"hmz: no run is being held in {where}", file=sys.stderr)
    return one
