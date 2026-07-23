"""Command line interface of exomyth."""

from __future__ import annotations

import argparse

from .collector import collect


def main() -> None:
    """Parses the command line and writes the aggregated trace file."""
    parser = argparse.ArgumentParser(
        prog="exomyth", description="Inspect agent flow trajectories."
    )
    commands = parser.add_subparsers(dest="command", required=True)
    command = commands.add_parser(
        "collect", help="Aggregate agent trajectories into a Chrome trace."
    )
    command.add_argument(
        "workspace",
        nargs="?",
        help="Workspace directory, defaults to the current one unless sessions are named.",
    )
    command.add_argument(
        "--session",
        action="append",
        dest="sessions",
        metavar="SESSION[,SESSION...]",
        help="Sessions to include, comma separated and repeatable, defaults to every session.",
    )
    command.add_argument(
        "--output",
        default="exomyth.trace.json",
        help="Trace file to write, defaults to exomyth.trace.json.",
    )
    command.add_argument(
        "--start", help="Earliest session time to include, e.g. '2 days ago'."
    )
    command.add_argument(
        "--end", help="Latest session time to include, e.g. 'yesterday 18:00'."
    )
    args = parser.parse_args()

    try:
        document = collect(
            args.workspace,
            sessions=args.sessions,
            output=args.output,
            start=args.start,
            end=args.end,
        )
    except ValueError as error:
        parser.error(str(error))
    summary = document["otherData"]
    print(
        f"{args.output}: {summary.get('sessions', '0')} sessions, "
        f"{summary.get('slices', '0')} slices"
    )
