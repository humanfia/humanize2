"""`hmz fallback`: where a turn goes when the agent taking it cannot take it at all.

Its own command rather than a flag of the accounts, because it is its own thing. An account
that goes down is answered by the next account of the same backend, inside the conversation
that was running -- that is `hmz providers falls-back`, and it stays there because it is a
thing about an account. This is what is left when there is no next account: another agent
entirely, at another CLI, another model, another effort.
"""

from __future__ import annotations

import argparse
import sys

__all__ = ["fallback"]


def fallback(argv: list[str]) -> int:
    """Lists, writes down and takes away the steps a turn walks between agents.

    Args:
      argv: The arguments after `hmz fallback`.

    Returns:
      Zero, or one for a line to correct.
    """
    parser = argparse.ArgumentParser(
        prog="hmz fallback",
        description="where a turn goes when the agent taking it cannot take it at all",
    )
    doing = parser.add_subparsers(dest="doing")

    listing = doing.add_parser("list", help="every step written down")
    listing.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        help="one agent a line, and nothing else",
    )

    showing = doing.add_parser("show", help="the agents one turn would walk, in order")
    showing.add_argument(
        "agent",
        metavar="CLI[@ACCOUNT]/MODEL:EFFORT",
        help="the agent the turn starts at",
    )

    adding = doing.add_parser(
        "add", help="say where one agent's turns go when it cannot run"
    )
    adding.add_argument(
        "agent",
        metavar="CLI[@ACCOUNT]/MODEL:EFFORT",
        help="the agent that cannot run",
    )
    adding.add_argument(
        "at",
        metavar="CLI[@ACCOUNT]/MODEL:EFFORT",
        help="the agent that takes the turn instead",
    )

    dropping = doing.add_parser("remove", help="take one step away")
    dropping.add_argument(
        "agent",
        metavar="CLI[@ACCOUNT]/MODEL:EFFORT",
        help="the agent it was written down against",
    )

    args = parser.parse_args(argv)
    if args.doing in (None, "list"):
        return _list(quiet=getattr(args, "quiet", False))
    if args.doing == "show":
        return _show(args.agent)
    if args.doing == "add":
        return _add(args.agent, args.at)
    return _remove(args.agent)


def _list(*, quiet: bool) -> int:
    """Prints every step, one a line, in the order they were written down."""
    from hmz import fallbacks

    found = fallbacks.falls()
    if not found:
        if quiet:
            return 0
        print(
            "no fallbacks yet; try "
            "`hmz fallback add claude/claude-opus-5:high codex/gpt-5.6-sol:high`"
        )
        return 0
    for one in found:
        print(one.spec if quiet else f"{one.spec}  ->  {one.to}")
    return 0


def _show(agent: str) -> int:
    """Prints the agents one turn walks, the one it starts at first."""
    from hmz import fallbacks

    walked = fallbacks.chain(agent)
    if not fallbacks.reads(agent):
        print(f"hmz: {agent}: expected CLI[@ACCOUNT]/MODEL:EFFORT", file=sys.stderr)
        return 1
    for at, one in enumerate(walked):
        print(f"{at + 1}. {one}")
    if len(walked) == 1:
        print("falls back nowhere: a failed turn is a failed turn")
    return 0


def _add(agent: str, at: str) -> int:
    """Says where one agent's turns go when it has nowhere left to run."""
    from hmz import fallbacks

    try:
        step = fallbacks.points(agent, at)
    except ValueError as why:
        print(f"hmz: {why}", file=sys.stderr)
        return 1
    print(f"{step.spec} falls back to {step.to}")
    return 0


def _remove(agent: str) -> int:
    """Takes one step away, which is an agent that falls back nowhere again."""
    from hmz import fallbacks

    if not fallbacks.clear(agent):
        print(f"hmz: nothing written down for {agent}", file=sys.stderr)
        return 1
    print(f"{fallbacks.reads(agent)} falls back to nowhere")
    return 0
