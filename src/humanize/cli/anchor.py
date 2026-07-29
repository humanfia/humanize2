"""``hmz anchor`` -- both halves of a session, routed apart before either is reached.

`serve` is what the zipapp bootstrapped onto a target runs, and it is answered first: only
the agent half needs ptrace and an x86-64 register map, which is what lets the same program
serve a target of any architecture.
"""

from __future__ import annotations

import sys

__all__ = ["anchor"]

#: Addresses a target may be left listening on without a secret, because nothing off this
#: machine can reach them.
_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1", "localhost"})

#: The top of the port range, above which a number is not a port at all.
_MAX_PORT = 65535


def anchor(argv: list[str]) -> int:
    """Runs the agent named on the command line, with its work landing on another machine.

    Args:
      argv: What followed the command name.

    Returns:
      The agent's exit status, or one of our own if it never ran.
    """
    if argv and argv[0] == "serve":
        return _serve(argv[1:])

    import logging

    from humanize.coganchor import argv as line

    parser = line.parser()
    args = parser.parse_args(argv)

    from humanize.coganchor.anchor import check, connect
    from humanize.coganchor.proto import ProtocolError

    # stderr, the one stream a session never speaks the protocol on.
    logging.basicConfig(
        level=args.log_level.upper(),
        format="%(asctime)s hmz %(levelname)s %(message)s",
        stream=sys.stderr,
    )
    if not args.command and not args.check:
        parser.error("no agent given; try `hmz anchor claude`")
    try:
        config = line.settings(args)
    except ValueError as exc:
        # Settings a session could not be run under are bad arguments, not failed sessions,
        # so they exit 2 the way argparse's own rejections do.
        parser.error(str(exc))

    try:
        if not args.check:
            return connect(args.command, config)
        found = check(config)
        print(f"target      {found['target']}")
        print(f"hostname    {found.get('hostname')}")
        print(f"python      {found.get('python')} (pid {found.get('pid')})")
        for export in found.get("exports", []):
            print(f"export      {export['virtual']} -> {export['real']}")
        print(f"workspace   {found['workspace']} ({found['entries']} entries)")
    except KeyboardInterrupt:
        return 130
    except (ConnectionError, ProtocolError, OSError, ValueError) as exc:
        print(f"hmz: {exc}", file=sys.stderr)
        return 1
    else:
        return 0


def _serve(argv: list[str]) -> int:
    """Replays on this machine what an `hmz anchor` elsewhere asks of it.

    Args:
      argv: What followed the command name.

    Returns:
      Zero once the session or the listener is done, or a status of our own if neither could
      be started.
    """
    import argparse
    import contextlib
    import logging
    import os

    parser = argparse.ArgumentParser(
        prog="hmz anchor serve",
        description="Replay an `hmz anchor` session's operations on this machine.",
    )
    parser.add_argument(
        "--export",
        metavar="VIRTUAL[:REAL]",
        action="append",
        default=[],
        required=True,
        help="expose a directory; VIRTUAL is the path the agent believes it uses",
    )
    where = parser.add_mutually_exclusive_group(required=True)
    where.add_argument(
        "--stdio", action="store_true", help="serve one session over stdin/stdout"
    )
    where.add_argument(
        "--listen", metavar="[HOST:]PORT", help="serve TCP connections on this address"
    )
    parser.add_argument(
        "--token",
        default=os.environ.get("HUMANIZE_TOKEN"),
        help="shared secret required from clients (default: $HUMANIZE_TOKEN)",
    )
    parser.add_argument(
        "--log-level",
        default=os.environ.get("HUMANIZE_LOG", "warning"),
        choices=["debug", "info", "warning", "error"],
        help="logging verbosity (default: warning)",
    )
    args = parser.parse_args(argv)

    from humanize.coganchor.proto import Channel
    from humanize.coganchor.serve.exports import ExportTable
    from humanize.coganchor.serve.server import Server

    logging.basicConfig(
        level=args.log_level.upper(),
        format="%(asctime)s hmz %(levelname)s %(message)s",
        stream=sys.stderr,
    )
    try:
        table = ExportTable.parse(args.export)
    except ValueError as exc:
        print(f"hmz: {exc}", file=sys.stderr)
        return 2

    if args.stdio:
        # The real stdin/stdout are duplicated away and fds 0 and 1 pointed at /dev/null, so
        # a stray print from this process or any child it spawns cannot corrupt the protocol
        # stream. fd 2 keeps carrying the log.
        read_fd, write_fd = os.dup(0), os.dup(1)
        devnull = os.open(os.devnull, os.O_RDWR)
        os.dup2(devnull, 0)
        os.dup2(devnull, 1)
        os.close(devnull)
        channel = Channel(os.fdopen(read_fd, "rb"), os.fdopen(write_fd, "wb"))
        with contextlib.suppress(KeyboardInterrupt):
            Server(channel, table, args.token).serve()
        return 0

    host, sep, port = args.listen.rpartition(":")
    if not sep:
        host, port = "127.0.0.1", args.listen
    host = host.strip("[]") or "127.0.0.1"
    if not port.isdigit() or not 0 <= int(port) <= _MAX_PORT:
        print(
            f"hmz: malformed listen address {args.listen!r}; expected [HOST:]PORT",
            file=sys.stderr,
        )
        return 2
    if host not in _LOOPBACK_HOSTS and not args.token:
        print(
            "hmz: refusing to listen on a non-loopback address without --token",
            file=sys.stderr,
        )
        return 2

    # Imported here rather than above: a session over a pipe is the one the bootstrapped
    # target runs, and it has no use for a listener that serves many.
    from humanize.coganchor.serve.listener import serve_forever

    try:
        serve_forever(host, int(port), table, args.token)
    except OSError as exc:
        print(f"hmz: cannot listen on {host}:{port}: {exc.strerror}", file=sys.stderr)
        return 1
    return 0
