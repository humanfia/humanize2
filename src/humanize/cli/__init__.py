"""``hmz`` -- the whole command line, over layers that have none of their own.

    hmz
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

__all__ = ["COMMANDS", "main"]


def _exec(argv: list[str]) -> int:
    """Drives the flow named on the command line, on the agents it names.

    Args:
      argv: What followed the command name.

    Returns:
      Zero, once the flow has returned.
    """
    from humanize.runner import NotAFlow, Runner, flow_and_agents

    path, agents, task = flow_and_agents(argv)
    try:
        runner = Runner(path, agents)
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


def _tui() -> int:
    """Opens the terminal interface, which is what a line naming no command opens.

    Returns:
      Zero, once the interface has been closed.
    """
    from humanize.tui import Humanize

    Humanize().run()
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
        return _tui()
    if arguments[0] not in COMMANDS:
        import argparse

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

        # There is nothing to route to, so this parser only has to say so. It knows the
        # commands by name and not by what they take -- each one answers
        # `hmz COMMAND --help` itself -- and whether it lists them or names the one that
        # was meant, it exits rather than returning here.
        parser = argparse.ArgumentParser(
            prog="hmz",
            description="Orchestrate, execute, and observe agent flows. "
            "Naming no command opens the terminal interface.",
            epilog="Run `hmz COMMAND --help` for what a command takes.",
        )
        commands = parser.add_subparsers(metavar="COMMAND", required=True)
        for name, (_, summary) in COMMANDS.items():
            commands.add_parser(name, help=summary, add_help=False)
        parser.parse_args(arguments)

    return COMMANDS[arguments[0]][0](arguments[1:])
