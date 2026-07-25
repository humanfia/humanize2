"""``amflows anchor`` -- the target half.

Replays the filesystem, process and network operations that the agent's
machine intercepts, over either an ssh pipe (``--stdio``) or a TCP socket
(``--listen``).
"""

from __future__ import annotations

import argparse
import contextlib
import logging
import os
import socket
import socketserver
import sys
import threading

from amflows.coganchor.proto import Channel
from amflows.coganchor.serve.exports import ExportTable
from amflows.coganchor.serve.server import Server

__all__ = ["main"]

log = logging.getLogger(__name__)

_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1", "localhost"})


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="amflows anchor",
        description="Replay an `amflows moor` session's operations on this machine.",
    )
    parser.add_argument(
        "--export",
        metavar="VIRTUAL[:REAL]",
        action="append",
        default=[],
        required=True,
        help="expose a directory; VIRTUAL is the path the agent believes it uses",
    )
    transport = parser.add_mutually_exclusive_group(required=True)
    transport.add_argument(
        "--stdio", action="store_true", help="serve one session over stdin/stdout"
    )
    transport.add_argument(
        "--listen", metavar="[HOST:]PORT", help="serve TCP connections on this address"
    )
    parser.add_argument(
        "--token",
        default=os.environ.get("COGANCHOR_TOKEN"),
        help="shared secret required from clients (default: $COGANCHOR_TOKEN)",
    )
    parser.add_argument(
        "--log-level",
        default=os.environ.get("COGANCHOR_LOG", "warning"),
        choices=["debug", "info", "warning", "error"],
        help="logging verbosity (default: warning)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=args.log_level.upper(),
        format="%(asctime)s amflows %(levelname)s %(message)s",
        stream=sys.stderr,
    )
    try:
        table = ExportTable.parse(args.export)
    except ValueError as exc:
        print(f"amflows: {exc}", file=sys.stderr)
        return 2

    if args.stdio:
        # The real stdin/stdout are duplicated away and fds 0 and 1 pointed at
        # /dev/null, so a stray print from this process or any child it spawns
        # cannot corrupt the protocol stream.  fd 2 keeps carrying the log.
        read_fd, write_fd = os.dup(0), os.dup(1)
        devnull = os.open(os.devnull, os.O_RDWR)
        os.dup2(devnull, 0)
        os.dup2(devnull, 1)
        os.close(devnull)
        channel = Channel(os.fdopen(read_fd, "rb"), os.fdopen(write_fd, "wb"))
        with contextlib.suppress(KeyboardInterrupt):
            Server(channel, table, args.token).serve()
        return 0

    try:
        host, port = _parse_listen(args.listen)
    except ValueError as exc:
        print(f"amflows: {exc}", file=sys.stderr)
        return 2
    if host not in _LOOPBACK_HOSTS and not args.token:
        print(
            "amflows: refusing to listen on a non-loopback address without --token",
            file=sys.stderr,
        )
        return 2
    return _serve_tcp(host, port, table, args.token)


def _parse_listen(spec: str) -> tuple[str, int]:
    host, sep, port = spec.rpartition(":")
    if not sep:
        host, port = "127.0.0.1", spec
    host = host.strip("[]") or "127.0.0.1"
    if not port.isdigit() or not 0 <= int(port) <= 65535:
        raise ValueError(f"malformed listen address {spec!r}; expected [HOST:]PORT")
    return host, int(port)


class _ConnectionHandler(socketserver.BaseRequestHandler):
    table: ExportTable
    token: str | None
    #: Servers currently serving a connection, so the listener can tear them
    #: down on its way out.  Handler threads are daemons and do not get to
    #: finish on their own.
    live: set[Server]
    lock: threading.Lock

    def handle(self) -> None:
        peer = self.client_address
        log.info("connection from %s", peer)
        channel = Channel.from_socket(self.request)
        server = Server(channel, self.table, self.token)
        with self.lock:
            self.live.add(server)
        try:
            server.serve()
        finally:
            with self.lock:
                self.live.discard(server)
            channel.close()
            log.info("connection from %s closed", peer)


class _ThreadedServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


def _serve_tcp(host: str, port: int, table: ExportTable, token: str | None) -> int:
    live: set[Server] = set()
    lock = threading.Lock()
    server_type = type(
        "CoganchorServer",
        (_ThreadedServer,),
        {"address_family": socket.AF_INET6 if ":" in host else socket.AF_INET},
    )
    handler = type(
        "Handler",
        (_ConnectionHandler,),
        {"table": table, "token": token, "live": live, "lock": lock},
    )
    try:
        listener = server_type((host, port), handler)
    except OSError as exc:
        print(
            f"amflows: cannot listen on {host}:{port}: {exc.strerror}",
            file=sys.stderr,
        )
        return 1
    with listener as server:
        bound = server.server_address
        # Announce the bound port so `--listen :0` is usable from scripts.
        print(
            f"amflows anchor listening {bound[0]} {bound[1]}",
            file=sys.stderr,
            flush=True,
        )
        with contextlib.suppress(KeyboardInterrupt):
            server.serve_forever(poll_interval=0.2)
        with lock:
            stragglers = list(live)
        for connection in stragglers:
            connection.close()
    return 0
