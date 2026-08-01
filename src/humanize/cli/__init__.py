"""``hmz`` -- the whole command line, over layers that have none of their own.

    hmz
    hmz -f humanize1 -c setup.yaml -a claude/claude-opus-5:max ...
    hmz exec -f ralph_loop -a claude/claude-opus-4-8:high "$(cat TASK.md)"
    hmz collect
    hmz anchor --target ssh://build-box claude

A command imports what it needs when it is the one asked for, and no earlier. Two things turn
on that: `hmz exec` must not pay for a date parser it will not use, and `hmz anchor serve` is
what the zipapp bootstrapped onto a target runs, where coganchor is the only layer present
and the architecture is whatever the target happens to be.

A command whose line takes a parser of its own has a module of its own here, so that reaching
one of them costs nothing for the others. `exec` has none: the line it takes is read by
:func:`humanize.runner.flow_and_agents`, since the terminal interface starts a flow from that
same line.
"""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from argparse import ArgumentParser

__all__ = ["COMMANDS", "main"]


def _exec(argv: list[str]) -> int:
    """Drives the flow named on the command line, on the agents it names.

    Args:
      argv: What followed the command name.

    Returns:
      Zero, once the flow has returned.
    """
    from humanize.runner import NotAFlow, Runner, flow_and_agents

    path, agents, task, config = flow_and_agents(argv)
    try:
        runner = Runner(path, agents, config)
    except NotAFlow as error:
        # A flow that is not there, or one that takes other agents than these, is a command
        # line that was wrong before anything ran, so it exits as argparse's own rejections
        # do. What the flow raises for itself is the flow's, and is left to say so itself.
        print(f"hmz exec: error: {error}", file=sys.stderr)
        raise SystemExit(2) from error
    runner.run(task)
    return 0


def _collect(argv: list[str]) -> int:
    """Writes the trajectories the agents left behind as one trace file.

    Args:
      argv: What followed the command name.

    Returns:
      Zero, once the trace has been written.
    """
    from .collect import collect

    return collect(argv)


def _anchor(argv: list[str]) -> int:
    """Runs the agent named on the command line, with its work landing on another machine.

    Args:
      argv: What followed the command name.

    Returns:
      The agent's exit status, or one of our own if it never ran.
    """
    from .anchor import anchor

    return anchor(argv)


def _cred(argv: list[str]) -> int:
    """Runs a program whose credentials are kept somewhere other than where it looks.

    Args:
      argv: What followed the command name.

    Returns:
      The program's exit status, or one of our own if it never ran.
    """
    from .cred import cred

    return cred(argv)


def _providers(argv: list[str]) -> int:
    """Lists, makes and takes away the accounts an agent may be run as.

    Args:
      argv: What followed the command name.

    Returns:
      Zero, or two for a line to correct.
    """
    from .providers import providers

    return providers(argv)


def _line() -> ArgumentParser:
    """The line `hmz` itself takes, which is how the interface is opened set up.

    Built here rather than where it is parsed because it is read in two places: the line that
    opens the interface is parsed with it, and the help asks it what `hmz` takes. A second
    copy of these three flags would be one to keep in step, and the one somebody typing
    `hmz --help` was shown would be the one that drifted.

    Returns:
      The parser, without the commands: whoever wants those adds them.
    """
    import argparse

    parser = argparse.ArgumentParser(
        prog="hmz",
        description="Orchestrate, execute, and observe agent flows. Naming no command opens "
        "the terminal interface, set up as the line says.",
        epilog="Run `hmz COMMAND --help` for what a command takes.",
    )
    parser.add_argument(
        "-f",
        "--flow",
        default="",
        metavar="PATH",
        help="the flow to open on: one that came with humanize, by name, or a file of your own",
    )
    parser.add_argument(
        "-a",
        "--agent",
        action="append",
        default=[],
        dest="agents",
        metavar="CLI/MODEL:EFFORT",
        help="what one of that flow's agents runs, repeated once for each it drives, in the "
        "order it takes them; the written-out form may include permission=PERMISSION; needs -f",
    )
    parser.add_argument(
        "-c",
        "--config",
        metavar="PATH",
        help="a YAML file of what to set that flow up with, as `/config` would ask for it; "
        "needs -f",
    )
    return parser


def _tui(argv: list[str]) -> int:
    """Opens the terminal interface, set up the way the line says if it says anything.

    A line naming no command opens it as it was left; one naming a flow, what to run it on,
    or what to set it up with opens it that way instead -- so a run that is always the same
    run is one line rather than three walks through the sheets. Nothing is started: the
    interface opens ready, and what starts it is still the first thing said.

    Args:
      argv: The whole line, which names no command.

    Returns:
      Zero, once the interface has been closed, or two for a line to correct.
    """
    from humanize.flows import find
    from humanize.runner import configures, read_agent, set_up_from, wanted
    from humanize.tui import Humanize
    from humanize.tui.pick import Runs

    parser = _line()
    args = parser.parse_args(argv)

    flow = args.flow or ""
    if args.agents and not flow:
        parser.error("-a says what runs the flow, so it needs -f")
    if args.config is not None and not flow:
        parser.error("-c says how the flow runs, so it needs -f")
    for spec in args.agents:
        try:
            read_agent(spec)
        except ValueError as bad:
            parser.error(f"bad agent {spec!r}: {bad}")
    setting = None
    if args.config is not None:
        try:
            model = configures(find(flow))
        except Exception as why:  # noqa: BLE001 -- a flow that will not load is a line to fix
            parser.error(str(why))
        if model is None:
            parser.error(
                f"{flow} takes no setting up, so there is nothing for -c to say"
            )
        try:
            setting = model.model_validate(set_up_from(args.config))
        except ValueError as refused:
            parser.error(f"{args.config}: {refused}")
    if args.agents:
        try:
            places = wanted(find(flow))
        except Exception as why:  # noqa: BLE001
            parser.error(str(why))
        if len(places) != len(args.agents):
            parser.error(
                f"{flow} drives {len(places)} agents, {len(args.agents)} given"
            )
    Humanize(
        flow=flow, agents=[Runs(spec) for spec in args.agents], config=setting
    ).run()
    return 0


#: Each command, as what carries it out and the line a listing shows it as. There is no
#: command for the terminal interface: naming nothing at all is how it opens.
COMMANDS = {
    "exec": (_exec, "run an agent flow in this directory"),
    "collect": (
        _collect,
        "aggregate the trajectories agents left behind into a Chrome trace",
    ),
    "anchor": (_anchor, "run an agent here that acts on another machine"),
    "providers": (_providers, "the accounts an agent may be run as"),
    "cred": (_cred, "run an agent whose credentials are kept somewhere else"),
}


def main(argv: list[str] | None = None) -> int:
    """Runs the command named on the command line, or opens the interface if none is.

    Args:
      argv: The arguments to parse, defaulting to this process's own.

    Returns:
      The command's exit status.
    """
    arguments = sys.argv[1:] if argv is None else argv
    if not arguments:
        return _tui([])
    # A line that names no command and starts with a flag is the interface being set up: what
    # flow, what runs it, how it is set up. Two flags on their own are not: `--version` says
    # the version, and `--help` lists the commands, which is what somebody typing it wants.
    if arguments[0].startswith("-") and arguments not in (
        ["--version"],
        ["--help"],
        ["-h"],
    ):
        return _tui(arguments)
    if arguments[0] not in COMMANDS:
        if arguments == ["--version"]:
            # Read from the installed metadata, which costs more to reach than everything
            # else here put together -- so it is reached only when it is what was asked for.
            from importlib.metadata import version

            print(f"hmz {version('hmz')}")
            return 0
        # Anything else naming no command it knows: argparse says which was meant and exits,
        # so nothing below it runs. `--version` is handled above precisely because it is the
        # one flag this parser no longer carries, and would otherwise fall through to a
        # command lookup that has nothing to look up.

        # The same line `hmz` itself takes, with the commands added: one help, saying both
        # what may be opened and what may be run, since both are `hmz` and somebody typing
        # `hmz --help` is asking about the whole of it. It knows the commands by name and not
        # by what they take -- each one answers `hmz COMMAND --help` itself.
        parser = _line()
        commands = parser.add_subparsers(metavar="COMMAND", required=True)
        for name, (_, summary) in COMMANDS.items():
            commands.add_parser(name, help=summary, add_help=False)
        parser.parse_args(arguments)

    return COMMANDS[arguments[0]][0](arguments[1:])
