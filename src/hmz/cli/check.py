"""``hmz check`` -- reads a flow for what will not run, before anything runs it.

Two readings, in their order. The static one is pure `ast` over every file the flow holds:
it executes nothing, so it is safe to point at a flow nobody has read -- generated, fetched,
forked. Then the flow is loaded and its live config model read, in a subprocess held to a
clock, which is what catches what only running the file can show. Both answer with findings,
one a line, so everything wrong is said at once.

It is here because the moment to check a flow is before something runs it: a CI job holding
a flowverse to its own bar, a flow just written by an agent, a fork about to be tried. The
readings themselves are :mod:`hmz.flows.checking` and :mod:`hmz.flows.proving`, reached
through :class:`hmz.sdk.Hmz` -- the same call anything else that checks a flow makes.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from hmz.flows import Finding
    from hmz.sdk.flows import Flows

__all__ = ["check"]


def check(argv: list[str]) -> int:
    """Carries out one `hmz check` line.

    Args:
      argv: What followed the command name.

    Returns:
      Zero for flows with nothing blocking -- warnings print and pass, unless `--strict`
      says otherwise -- one where any finding blocks, and two for a line to correct or a
      name no flow answers to.
    """
    import argparse

    parser = argparse.ArgumentParser(
        prog="hmz check",
        description="Read a flow for what will not run -- before anything runs it: a "
        "static reading that executes nothing, then the flow loaded in a subprocess held "
        "to a clock. Errors are what no run survives; warnings are runs that may be "
        "regretted.",
    )
    parser.add_argument(
        "flow",
        nargs="+",
        metavar="FLOW",
        help="a flow, by the name `-f` takes -- `chat`, `official/rlar` -- or by a path",
    )
    parser.add_argument(
        "--static",
        action="store_true",
        help="only the reading that executes nothing: do not load the flow at all",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="exit non-zero on warnings too",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="as_json",
        help="one JSON object per finding, one a line, for a script to read",
    )
    said = parser.add_mutually_exclusive_group()
    said.add_argument(
        "--prophecy",
        action="store_true",
        help="print what each atlas compiles to instead of what is wrong with it",
    )
    said.add_argument(
        "--ship",
        action="store_true",
        help="write each atlas's prophecy into its own directory, for runs to walk "
        "instead of compiling it again",
    )
    args = parser.parse_args(argv)

    from pathlib import Path

    from hmz.sdk import Hmz

    flows = Hmz().flows
    for named in args.flow:
        # A name nothing answers to is a line to correct, refused the way argparse refuses
        # one -- before anything is read, and for every name on the line at once.
        if not Path(flows.find(named)).is_file():
            parser.error(f"no flow called {named!r}")
    if args.prophecy or args.ship:
        return _foretold(flows, args.flow, ship=args.ship)
    found: list[Finding] = []
    for named in args.flow:
        found.extend(flows.check(named, static=args.static))
    _said(found, as_json=args.as_json, flows=len(args.flow))
    errors = sum(one.severity == "error" for one in found)
    warned = len(found) - errors
    return 1 if errors or (args.strict and warned) else 0


def _foretold(held: Flows, flows: list[str], *, ship: bool) -> int:
    """Prints or writes what each atlas on the line compiles to.

    Args:
      held: The flows, as the one object every way in asks.
      flows: The flows to read, by the names the line gave.
      ship: Whether to write each prophecy into its flow's own directory rather than print
        it.

    Returns:
      Zero where every one of them compiled, and one where any did not: a name that is not
      an atlas, or is one that the reading refused.
    """
    from hmz.flows import NotAFlow, canonical

    worst = 0
    for named in flows:
        if ship:
            try:
                print(f"{named}: {held.foretell(named)}")
            except NotAFlow as why:
                print(f"hmz check: {why}")
                worst = 1
            continue
        prophecy = held.prophecy(named)
        if prophecy is None:
            print(
                f"hmz check: {named} is not an atlas that compiles -- drop --prophecy"
            )
            worst = 1
            continue
        print(canonical(prophecy))
    return worst


def _said(found: list[Finding], *, as_json: bool, flows: int) -> None:
    """Prints what the readings found, for a person or for a script.

    Args:
      found: The findings, in the order they were found.
      as_json: Whether to say each as one JSON object a line, and no count under them.
      flows: How many flows the line named, for the count.
    """
    if as_json:
        import json

        for one in found:
            print(
                json.dumps(
                    {
                        "code": one.code,
                        "severity": one.severity,
                        "where": str(one.where),
                        "line": one.line,
                        "said": one.said,
                    }
                )
            )
        return
    from . import many

    for one in found:
        print(f"{one.where}:{one.line}: {one.severity}: {one.code}: {one.said}")
    errors = sum(one.severity == "error" for one in found)
    if found:
        print(
            f"hmz check: {many(errors, 'error')}, {many(len(found) - errors, 'warning')}"
        )
    else:
        print(f"hmz check: nothing to say about {many(flows, 'flow')}")
