"""`hmz tools`: the pipe a coding agent speaks the tool protocol over, relayed to a flow.

A callback of a flow's is a Python function in the flow's own process, and a CLI takes a tool
by starting a program and talking to it over that program's stdin and stdout. This is the
program: it does nothing but carry each line between the two, so that the function runs where
the flow is rather than in a process of its own.

Spawned rather than typed, like `hmz cred`: it is a command line because starting a process is
what a backend does with a tool server, and not because it is a thing anybody runs by hand.
"""

from __future__ import annotations

import argparse
import contextlib
import socket
import sys
import threading
from typing import IO

__all__ = ["tools"]


def tools(argv: list[str]) -> int:
    """Relays this process's stdin and stdout to a flow's toolbox.

    Args:
      argv: The arguments after `hmz tools`.

    Returns:
      Zero once either end has gone, and one for a socket that is not there -- which is a
      flow that has ended, and a CLI that reads the tools as unavailable rather than as a
      turn that failed.
    """
    parser = argparse.ArgumentParser(
        prog="hmz tools",
        description="relay the tool protocol to the flow whose callbacks these are",
    )
    parser.add_argument(
        "--at",
        required=True,
        metavar="SOCKET",
        help="the socket the flow is serving its callbacks on",
    )
    args = parser.parse_args(argv)
    held = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        held.connect(args.at)
    except OSError as why:
        print(f"hmz tools: {args.at}: {why}", file=sys.stderr)
        held.close()
        return 1

    def upward() -> None:
        """Carries what the CLI says to the flow, and says when the CLI has stopped."""
        with held.makefile("wb") as writing:
            _moves(sys.stdin.buffer, writing)
        # The CLI has closed its end, so this one has: without saying so the flow would sit
        # reading a socket nobody is going to write to, and this process would sit reading a
        # socket that is therefore never closed -- which is a CLI that never exits.
        with contextlib.suppress(OSError):
            held.shutdown(socket.SHUT_WR)

    with held, held.makefile("rb") as reading:
        # Both ways at once: a client writes a request and waits, and a server may say
        # something before it is asked. One thread apiece is what makes neither wait on the
        # other, and the first of them to end is what ends the relay.
        threading.Thread(target=upward, daemon=True).start()
        _moves(reading, sys.stdout.buffer)
    return 0


def _moves(source: IO[bytes], sink: IO[bytes]) -> None:
    """Carries one stream into the other a line at a time, until the first of them ends.

    A line at a time rather than a block: the protocol is one JSON object per line, and a
    read that waited for a buffer to fill would hold a request until the next one arrived.

    Args:
      source: What to read.
      sink: What to write.
    """
    with contextlib.suppress(OSError, ValueError):
        while line := source.readline():
            sink.write(line)
            sink.flush()
