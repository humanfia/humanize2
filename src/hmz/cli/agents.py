"""``hmz agents`` -- the agents written down under a name, from a command line.

The same store the interface's `/agents` walks through, said as arguments instead: what there
is, what one of them is, and the two things that can happen to one -- written down, taken
away. That is the way in for a machine being set up, a CI job, or anywhere the interface is
not open, and what it wrote down is there to be imported the next time a flow's agent is set
up.

It is the agents kept under a name and not the agents of any flow: what an agent is -- a CLI,
an account, a model at an effort, what it may do -- is not a thing about the flow that happens
to be driving it. Which flow drives what is `/flow`, and is a thing about a workspace.

Nothing here reaches the store itself. What an agent written down is, and what refusing a name
already taken means, is :class:`hmz.sdk.Hmz`'s -- the same answers the interface gets when it
saves one from a menu. This reads the line and prints what came of it.
"""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from hmz.kept import Runs

__all__ = ["agents"]


def agents(argv: list[str]) -> int:
    """Carries out one `hmz agents` line.

    Args:
      argv: What followed the command name.

    Returns:
      Zero, or two for a line to correct, or one for something that could not be done.
    """
    import argparse

    parser = argparse.ArgumentParser(
        prog="hmz agents",
        description="The agents written down under a name, to be reached for from any flow.",
    )
    doing = parser.add_subparsers(dest="doing", metavar="COMMAND")

    listing = doing.add_parser("list", help="what agents there are")
    listing.add_argument(
        "-q", "--quiet", action="store_true", help="just the names, one a line"
    )

    showing = doing.add_parser("show", help="what one of them is")
    showing.add_argument("name", help="what it is written down under")

    writing = doing.add_parser("add", help="write one down under a name")
    writing.add_argument("name", help="what to call it")
    writing.add_argument(
        "agent",
        metavar="CLI[@PROVIDER]/MODEL:EFFORT",
        help="what it runs, as `-a` takes it; the written-out form may include "
        "permission=PERMISSION and web_search=on|off",
    )
    writing.add_argument(
        "--anchor",
        default="",
        metavar="TARGET",
        help="the machine its work lands on, as `hmz anchor --target` takes it",
    )
    writing.add_argument(
        "--goals",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="whether its backend's own goals are available to it",
    )
    writing.add_argument(
        "--web-search",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="whether it may search the web, defaulting to what the agent line said and to "
        "on where it said nothing",
    )
    writing.add_argument(
        "--force",
        action="store_true",
        help="write over the one of that name, if there is one",
    )

    dropping = doing.add_parser("remove", help="take one away")
    dropping.add_argument("name")

    args = parser.parse_args(argv)
    if args.doing in (None, "list"):
        return _list(quiet=getattr(args, "quiet", False))
    if args.doing == "show":
        return _show(args.name)
    if args.doing == "remove":
        return _remove(args.name)
    return _add(
        args.name,
        args.agent,
        anchor=args.anchor,
        goals=args.goals,
        web_search=args.web_search,
        force=args.force,
    )


def _list(*, quiet: bool) -> int:
    """Prints every agent written down, by name and by what it runs."""
    from hmz.sdk import Hmz

    found = Hmz().agents.all()
    if not found:
        if quiet:
            return 0
        print("no agents written down yet; try `hmz agents add mine claude/MODEL:high`")
        return 0
    for one in found:
        if quiet:
            print(one.name)
            continue
        print(f"{one.name:16} {_reads(one.runs)}")
    return 0


def _show(name: str) -> int:
    """Prints what one agent is, a field a line, saying nothing where it says nothing."""
    from hmz.sdk import Hmz

    kept = Hmz().agents.find(name)
    if kept is None:
        print(f"hmz: no agent {name}", file=sys.stderr)
        return 1
    runs = kept.runs
    cli, _, rest = runs.spec.partition("/")
    model, _, effort = rest.rpartition(":")
    print(f"agent       {kept.name}")
    print(f"cli         {cli}")
    print(f"model       {model}")
    print(f"effort      {effort}")
    print(f"account     {runs.provider or 'as this machine is signed in'}")
    print(f"may         {runs.permission or 'whatever it is asked to'}")
    print(f"works       {runs.anchor or 'here'}")
    print(f"goals       {'on' if runs.goals else 'off'}")
    print(f"web search  {'on' if runs.web_search else 'off'}")
    # The skills are the CLI's own: every one it finds here, installed and switched off the
    # way that CLI does it, plus whatever the flow it is driving mounts onto its sessions.
    print("skills      as its CLI finds them")
    return 0


def _add(
    name: str,
    spec: str,
    *,
    anchor: str,
    goals: bool,
    web_search: bool | None,
    force: bool,
) -> int:
    """Writes one agent down under a name, refusing a name already taken."""
    from hmz.sdk import Hmz, Taken

    try:
        kept = Hmz().agents.add(
            name,
            spec,
            anchor=anchor,
            goals=goals,
            web_search=web_search,
            force=force,
        )
    except Taken as why:
        # Which flag means it, said here rather than where it was refused: a menu that has
        # already asked which name to save over has nothing to add to the same refusal.
        print(f"hmz: {why}; --force writes over it", file=sys.stderr)
        return 1
    except ValueError as why:
        print(f"hmz: {why}", file=sys.stderr)
        return 1
    print(f"{kept.name}  {_reads(kept.runs)}")
    return 0


def _remove(name: str) -> int:
    """Takes one agent away."""
    from hmz.sdk import Hmz

    if not Hmz().agents.remove(name):
        print(f"hmz: no agent {name}", file=sys.stderr)
        return 1
    print(f"{name} is no longer written down")
    return 0


def _reads(runs: Runs) -> str:
    """One agent on one line: what it runs, and whatever else it says about itself."""
    said = [runs.spec]
    if runs.provider:
        said.append(f"as {runs.provider}")
    if runs.anchor:
        said.append(f"on {runs.anchor}")
    if runs.permission:
        said.append(runs.permission)
    # Only where it is a narrowing: on is what an agent nobody has been asked about does,
    # and a line that said so of every agent would be a line saying nothing.
    if not runs.web_search:
        said.append("no web search")
    return "  ".join(said)
