"""``hmz agents`` -- the agents written down under a name, from a command line.

The same store the interface's `/agents` walks through, said as arguments instead: what there
is, what one of them is, and the two things that can happen to one -- written down, taken
away. That is the way in for a machine being set up, a CI job, or anywhere the interface is
not open, and what it wrote down is there to be imported the next time a flow's agent is set
up.

It is the agents kept under a name and not the agents of any flow: what an agent is -- a CLI,
an account, a model at an effort, what it may do -- is not a thing about the flow that happens
to be driving it. Which flow drives what is `/flow`, and is a thing about a workspace.
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
        "permission=PERMISSION",
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
        force=args.force,
    )


def _list(*, quiet: bool) -> int:
    """Prints every agent written down, by name and by what it runs."""
    from hmz.kept import Templates

    found = Templates().all()
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
    from hmz.kept import Templates

    kept = Templates().find(name)
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
    force: bool,
) -> int:
    """Writes one agent down under a name, refusing a name already taken."""
    from hmz.backends import read
    from hmz.kept import Kept, Runs, Templates

    if not name.strip():
        print("hmz: an agent is written down under a name", file=sys.stderr)
        return 1
    try:
        (
            profile,
            model,
            effort,
            service_tier,
            provider,
            permission,
            overrides,
        ) = read(spec)
        if service_tier != "default":
            print(
                "hmz: service_tier is a per-run setting on the agent line, "
                "not a saved-agent setting",
                file=sys.stderr,
            )
            return 1
        if overrides:
            print(
                "hmz: config.KEY is a setting of the agent on the line that runs it, "
                "not of one written down under a name",
                file=sys.stderr,
            )
            return 1
    except ValueError as why:
        print(f"hmz: {spec}: {why}", file=sys.stderr)
        return 1
    if permission is not None and permission not in _rungs():
        print(
            f"hmz: permission must be one of {', '.join(_rungs())}, not {permission!r}",
            file=sys.stderr,
        )
        return 1
    templates = Templates()
    held = templates.all()
    already = next((one for one in held if one.name == name), None)
    if already is not None and not force:
        print(
            f"hmz: there is already an agent called {name}; --force writes over it",
            file=sys.stderr,
        )
        return 1
    runs = Runs(
        f"{profile.name}/{model}:{effort}",
        anchor.strip(),
        permission or "",
        provider,
        goals,
    )
    # Whole, as the menu writes them: one written over keeps its place in the list, and one
    # that is new goes on the end, which is the order they were written down in.
    kept = [Kept(name, runs) if one.name == name else one for one in held] + (
        [] if already is not None else [Kept(name, runs)]
    )
    templates.keep(kept)
    print(f"{name}  {_reads(runs)}")
    return 0


def _remove(name: str) -> int:
    """Takes one agent away."""
    from hmz.kept import Templates

    templates = Templates()
    held = templates.all()
    if not any(one.name == name for one in held):
        print(f"hmz: no agent {name}", file=sys.stderr)
        return 1
    templates.keep([one for one in held if one.name != name])
    print(f"{name} is no longer written down")
    return 0


def _rungs() -> tuple[str, ...]:
    """What an agent may be allowed to do, hardest last, as `hmz.agents` names them."""
    from hmz.agents import PERMISSIONS

    return PERMISSIONS


def _reads(runs: Runs) -> str:
    """One agent on one line: what it runs, and whatever else it says about itself."""
    said = [runs.spec]
    if runs.provider:
        said.append(f"as {runs.provider}")
    if runs.anchor:
        said.append(f"on {runs.anchor}")
    if runs.permission:
        said.append(runs.permission)
    return "  ".join(said)
