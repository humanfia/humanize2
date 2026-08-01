"""``hmz collect`` -- the trajectories the agents left behind, as one trace file."""

from __future__ import annotations

__all__ = ["collect"]


def collect(argv: list[str]) -> int:
    """Writes the trajectories the agents left behind as one trace file.

    Args:
      argv: What followed the command name.

    Returns:
      Zero, once the trace has been written.
    """
    import argparse

    parser = argparse.ArgumentParser(
        prog="hmz collect",
        description="Aggregate agent trajectories into a Chrome trace.",
    )
    parser.add_argument(
        "workspace",
        nargs="?",
        help="Workspace directory, defaults to the current one unless sessions are named.",
    )
    parser.add_argument(
        "--session",
        action="append",
        dest="sessions",
        metavar="SESSION[,SESSION...]",
        help="Sessions to include, comma separated and repeatable, defaults to every session.",
    )
    parser.add_argument(
        "--output",
        help="Trace file to write, defaults to .humanize/<datetime>.trace.json.",
    )
    parser.add_argument(
        "--start", help="Earliest session time to include, e.g. '2 days ago'."
    )
    parser.add_argument(
        "--end", help="Latest session time to include, e.g. 'yesterday 18:00'."
    )
    args = parser.parse_args(argv)

    import datetime

    from hmz.cycle import cycles, opened
    from hmz.tracing.collector import collect as gather

    # One trace per run, named after the moment it was taken, so collecting twice keeps both
    # rather than writing over the first.
    stamp = datetime.datetime.now(datetime.UTC).strftime("%Y%m%dT%H%M%SZ")
    output = args.output or f".humanize/{stamp}.trace.json"
    # Who ran what, taken from the last flow run here: the backends log a session under an id
    # and never say whose it was, so two agents at one configuration are one agent to a trace
    # unless the run itself says otherwise -- and the run wrote down that it did.
    agents: dict[str, list[str]] = {}
    for cycle in cycles(args.workspace):
        agents = opened(cycle) or agents

    try:
        document = gather(
            args.workspace,
            sessions=args.sessions,
            agents=agents or None,
            output=output,
            start=args.start,
            end=args.end,
        )
    except ValueError as error:
        parser.error(str(error))
    summary = document["otherData"]
    print(
        f"{output}: {summary.get('sessions', '0')} sessions, "
        f"{summary.get('slices', '0')} slices"
    )
    return 0
