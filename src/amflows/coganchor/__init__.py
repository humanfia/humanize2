"""coganchor -- run a coding agent on one machine, have it act on another.

The agent process stays local, keeping its credentials, its state directory
and its link to its model provider.  A seccomp-filtered ptrace supervisor
intercepts the cold syscalls that name a path, spawn a process or open a
socket, and ``coganchor serve`` replays them on the target machine.
"""

from __future__ import annotations

import sys

__version__ = "0.1.0"

__all__ = ["__version__", "main"]


def main(argv: list[str] | None = None) -> int:
    """Console-script entry point, routing ``serve`` before anything else.

    Both halves of a session are this one program, but only the agent side
    needs ptrace and an x86-64 register map.  Dispatching ``serve`` here, ahead
    of importing :mod:`amflows.coganchor.cli`, is what lets the same program serve a
    target of any architecture.
    """
    arguments = sys.argv[1:] if argv is None else argv
    if arguments and arguments[0] == "serve":
        from .serve.cli import main as serve

        return serve(arguments[1:])
    from .cli import main as anchor

    return anchor(arguments)
