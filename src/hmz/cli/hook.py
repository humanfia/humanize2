"""`hmz internal hook`: the one call a coding agent's own hook table makes, relayed to a flow.

A moment of a flow's is a Python callable in the flow's own process, and a CLI takes a hook by
starting a program, writing what is happening on its stdin and reading what to do about it off
its stdout. This is the program: it does nothing but carry that one call to the socket the
flow is serving and the answer back again, so that the hook runs where the flow is.

Which is what makes `PreToolUse` mean something. The stream a turn is read from says a tool
was reached for and then the tool runs, so a verdict read off that stream arrives too late to
be one; the CLI's own table is the one place it is waiting to be told, and this is what stands
in that place.

Spawned rather than typed, like `hmz internal cred` and `hmz internal tools`: it is a command
line because starting a process is what a backend does with a hook, and not because it is a
thing anybody runs by hand.
"""

from __future__ import annotations

import argparse
import contextlib
import socket
import sys

__all__ = ["hook"]


def hook(argv: list[str]) -> int:
    """Carries one call of a CLI's hook table to the flow whose moment it is.

    Args:
      argv: The arguments after `hmz internal hook`.

    Returns:
      Zero, whatever the flow said and whether or not it was there to say it, and one for a
      line this could not read -- no `--at`, or a flag it does not know. Never two, whatever
      went wrong: these CLIs read a two as the hook itself having refused the tool, so a relay
      that exited two because it could not reach anybody, or because its own line was wrong,
      would be refusing on a flow's behalf without ever having asked it. What a flow that has
      gone says is nothing, which is the tool going ahead exactly as it would have.
    """
    parser = argparse.ArgumentParser(
        prog="hmz internal hook",
        description="relay one hook call to the flow whose moment it is",
    )
    parser.add_argument(
        "--at",
        required=True,
        metavar="SOCKET",
        help="the socket the flow is serving its moments on",
    )
    try:
        args = parser.parse_args(argv)
    except SystemExit as stopped:
        if stopped.code == 0:
            raise  # `--help`, which ends the process here as it does for any other command
        # Argparse exits two for a line it could not read, and two is the one status this
        # must never leave with: these CLIs read it as the hook itself having refused the
        # tool, so a relay given a flag it did not know would be refusing on a flow's behalf
        # without ever having asked it. A line to correct comes back as one instead.
        return 1
    # The whole of it before anything is sent: a hook is told what is happening as one JSON
    # object and then its input is closed, so there is nothing to stream and nothing to be
    # gained by starting before it has all arrived.
    said = _one_line(sys.stdin.buffer.read())
    held = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        held.connect(args.at)
    except OSError as why:
        # A flow that has ended. Said where a person would see it and nowhere the agent will:
        # every one of these CLIs shows a hook's stderr and goes on with the turn, which is
        # what a gate with nobody behind it has to come to.
        print(f"hmz internal hook: {args.at}: {why}", file=sys.stderr)
        held.close()
        return 0
    answer = b""
    # A flow that went between the question and the answer, which is a socket that ends the
    # file or resets it depending on how it went. Both are the same nothing as a flow that was
    # never there, and neither is a traceback to put in front of the agent: what this owes the
    # CLI is a status of zero and a line it reads as the tool going ahead.
    with contextlib.suppress(OSError), held, held.makefile("rwb") as stream:
        stream.write(said + b"\n")
        stream.flush()
        answer = stream.readline()
    with contextlib.suppress(OSError, ValueError):
        sys.stdout.buffer.write(answer)
        sys.stdout.buffer.flush()
    return 0


def _one_line(said: bytes) -> bytes:
    """What the CLI wrote, as the one line the socket carries a message on.

    The two ends agreed on a message per line, and not every CLI writes its hook's input on
    one: a table read by something that pretty-prints its JSON would arrive as a dozen lines,
    of which the first is not a message at all -- so the flow would answer a dozen times with
    nothing and the gate would quietly let the tool through.

    Args:
      said: What arrived on standard input.

    Returns:
      It as one line. Written again from what it means where that can be read, and with its
      whitespace run together where it cannot: a line this end could not parse is still a line
      the other end should get the chance to refuse.
    """
    import json

    try:
        return json.dumps(json.loads(said or b"{}"), separators=(",", ":")).encode()
    except ValueError:
        return b" ".join(said.split())
