"""``amflows`` -- the one command, over the four things a flow asks for.

    amflows run -f examples/ralph_loop.py -a claude/claude-opus-4-8/high "$(cat TASK.md)"
    amflows collect
    amflows moor --target ssh://build-box claude
    amflows anchor --listen 7777 --export /srv/project

A command parses the rest of the line itself, and is imported only once it is the one asked
for, so reaching any of them costs nothing of the other three.
"""

from __future__ import annotations

import argparse
import importlib
import sys
from importlib.metadata import version

__all__ = ["main"]

#: Each command, as the module its command line lives in and the line a listing shows it as.
_COMMANDS = {
    "run": ("amflows.janus.cli", "run an agent flow in this directory"),
    "collect": (
        "amflows.exomyth.cli",
        "aggregate the trajectories agents left behind into a Chrome trace",
    ),
    "moor": ("amflows.coganchor.cli", "run an agent here that acts on another machine"),
    "anchor": (
        "amflows.coganchor.serve.cli",
        "be the machine an `amflows moor` elsewhere acts on",
    ),
}


def main(argv: list[str] | None = None) -> int:
    """Runs the command named on the command line, on the rest of it.

    Args:
      argv: The arguments to parse, defaulting to this process's own.

    Returns:
      The command's exit status.
    """
    arguments = sys.argv[1:] if argv is None else argv
    if not arguments or arguments[0] not in _COMMANDS:
        # There is nothing to route to, so this parser only has to say so. It knows the
        # commands by name and not by what they take -- each one answers
        # `amflows COMMAND --help` itself -- and whether it lists them or names the one that
        # was meant, it exits rather than returning here.
        parser = argparse.ArgumentParser(
            prog="amflows",
            description="Orchestrate, execute, and observe agent flows.",
            epilog="Run `amflows COMMAND --help` for what a command takes.",
        )
        parser.add_argument(
            "--version", action="version", version=f"amflows {version('amflows')}"
        )
        commands = parser.add_subparsers(metavar="COMMAND", required=True)
        for name, (_, summary) in _COMMANDS.items():
            commands.add_parser(name, help=summary, add_help=False)
        parser.parse_args(arguments)

    module, _ = _COMMANDS[arguments[0]]
    status: int | None = importlib.import_module(module).main(arguments[1:])
    return status or 0
