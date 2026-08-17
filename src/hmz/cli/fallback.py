"""`hmz fallback`: where a turn goes when the place taking it cannot take it at all.

Its own command rather than a flag of the accounts, because it is its own layer. An account
that goes down is answered by the next account of the same backend, inside the conversation
that was running -- that is `hmz providers falls-back`, and it stays there because it is a
thing about an account. This is what is left when there is no next account: another place
entirely, which is a CLI, an account and a model and nothing else.

Trying again is said here too. How many goes a failed turn gets before the step is taken is a
thing about the place rather than about the agent standing in it, so one command says both.

The store is reached through :class:`hmz.sdk.Hmz`, which is what the interface's own
`/fallback` asks as well: one place a thing is kept is one place it is kept.
"""

from __future__ import annotations

import argparse
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from hmz.fallbacks import Falls
    from hmz.sdk import Fallbacks

__all__ = ["fallback"]

#: What a place is called wherever this command asks for one.
_PLACE = "CLI[@ACCOUNT]/MODEL"


def fallback(argv: list[str]) -> int:
    """Lists, writes down and takes away the steps a turn walks between places.

    Args:
      argv: The arguments after `hmz fallback`.

    Returns:
      Zero, or one for a line to correct.
    """
    from hmz.sdk import Hmz

    steps = Hmz().fallbacks
    parser = argparse.ArgumentParser(
        prog="hmz fallback",
        description="where a turn goes when the place taking it cannot take it at all",
    )
    doing = parser.add_subparsers(dest="doing")

    listing = doing.add_parser("list", help="every step written down")
    listing.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        help="one place a line, and nothing else",
    )

    showing = doing.add_parser("show", help="the places one turn would walk, in order")
    showing.add_argument("place", metavar=_PLACE, help="the place the turn starts at")

    adding = doing.add_parser(
        "add", help="say where one place's turns go when it cannot run"
    )
    adding.add_argument("place", metavar=_PLACE, help="the place that cannot run")
    adding.add_argument(
        "at", metavar=_PLACE, help="the place that takes the turn instead"
    )

    trying = doing.add_parser(
        "retry", help="say how a failed turn at one place is taken again"
    )
    trying.add_argument("place", metavar=_PLACE, help="the place it is about")
    trying.add_argument(
        "tries", type=int, help="how many goes beyond the first, or 0 for none"
    )
    trying.add_argument(
        "-p",
        "--policy",
        default=steps.default,
        choices=[one.name for one in steps.policies()],
        help="how long to wait between them",
    )
    trying.add_argument(
        "-t",
        "--timeout",
        type=float,
        default=0.0,
        metavar="SECONDS",
        help="the longest the trying again may go on for, or 0 for no limit",
    )

    dropping = doing.add_parser("remove", help="take one step away")
    dropping.add_argument(
        "place", metavar=_PLACE, help="the place it was written down against"
    )

    args = parser.parse_args(argv)
    if args.doing in (None, "list"):
        return _list(steps, quiet=getattr(args, "quiet", False))
    if args.doing == "show":
        return _show(steps, args.place)
    if args.doing == "add":
        return _add(steps, args.place, args.at)
    if args.doing == "retry":
        return _retry(steps, args.place, args.tries, args.policy, args.timeout)
    return _remove(steps, args.place)


def _said(step: Falls) -> str:
    """One step as a line of a listing: where it goes, and how often it is tried first."""
    goes = f"falls back to {step.to}" if step.to else "falls back nowhere"
    if not step.tries:
        return goes
    over = f", up to {step.timeout:.0f}s" if step.timeout else ""
    return f"{step.tries} more tries, {step.policy}{over}; {goes}"


def _list(steps: Fallbacks, *, quiet: bool) -> int:
    """Prints every step, one a line, in the order they were written down."""
    found = steps.all()
    if not found:
        if quiet:
            return 0
        print(
            "nothing written down yet; try "
            "`hmz fallback add claude/claude-opus-5 codex/gpt-5.6-sol`"
        )
        return 0
    for one in found:
        print(one.spec if quiet else f"{one.spec}  ->  {_said(one)}")
    return 0


def _show(steps: Fallbacks, place: str) -> int:
    """Prints the places one turn walks, the one it starts at first."""
    if not steps.reads(place):
        print(f"hmz: {place}: expected {_PLACE}", file=sys.stderr)
        return 1
    walked = steps.chain(place)
    for at, one in enumerate(walked):
        step = steps.tried(one)
        tries = f"   [{step.tries} more tries, {step.policy}]" if step.tries else ""
        print(f"{at + 1}. {one}{tries}")
    if len(walked) == 1:
        print("falls back nowhere: a failed turn is a failed turn")
    return 0


def _add(steps: Fallbacks, place: str, at: str) -> int:
    """Says where one place's turns go when it has nowhere left to run."""
    try:
        step = steps.points(place, at)
    except ValueError as why:
        print(f"hmz: {why}", file=sys.stderr)
        return 1
    print(f"{step.spec} falls back to {step.to}")
    return 0


def _retry(
    steps: Fallbacks, place: str, tries: int, policy: str, timeout: float
) -> int:
    """Says how many goes a failed turn at one place gets before the step is taken."""
    try:
        step = steps.retrying(place, tries, policy, timeout)
    except ValueError as why:
        print(f"hmz: {why}", file=sys.stderr)
        return 1
    if not step.tries:
        print(f"{step.spec} is tried once: a failed turn is a failed turn")
        return 0
    over = f", up to {step.timeout:.0f}s" if step.timeout else ""
    print(f"{step.spec} is tried {step.tries} more times, {step.policy}{over}")
    return 0


def _remove(steps: Fallbacks, place: str) -> int:
    """Takes one step away, which is a place that falls back nowhere again."""
    if not steps.clear(place):
        print(f"hmz: nothing written down for {place}", file=sys.stderr)
        return 1
    print(f"{steps.reads(place)} falls back to nowhere")
    return 0
