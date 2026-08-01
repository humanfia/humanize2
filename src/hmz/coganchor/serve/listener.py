"""Serving many sessions at once, for a target left listening on a port.

The other way in is a pipe carrying one session, which needs nothing of this: the far end has
already been started for that session alone, and :class:`~hmz.coganchor.serve.server.Server`
is the whole of it.
"""

from __future__ import annotations

import contextlib
import logging
import socket
import socketserver
import sys
import threading
from typing import TYPE_CHECKING

from hmz.coganchor.proto import Channel
from hmz.coganchor.serve.server import Server

if TYPE_CHECKING:
    from hmz.coganchor.serve.exports import ExportTable

__all__ = ["serve_forever"]

log = logging.getLogger(__name__)


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


def serve_forever(host: str, port: int, table: ExportTable, token: str | None) -> None:
    """Serves every connection to this address, until interrupted.

    The address actually bound is announced on stderr, so that a port of 0 is usable from a
    script that has to know which one it got.

    Args:
      host: The address to listen on.
      port: The port to listen on, or 0 to be given one.
      table: The directories a session may name, and where they really are.
      token: The shared secret a client must present, or None to require none.

    Raises:
      OSError: If the address cannot be listened on, which is the caller's to report.
    """
    live: set[Server] = set()
    lock = threading.Lock()
    server_type = type(
        "HumanizeServer",
        (_ThreadedServer,),
        {"address_family": socket.AF_INET6 if ":" in host else socket.AF_INET},
    )
    handler = type(
        "Handler",
        (_ConnectionHandler,),
        {"table": table, "token": token, "live": live, "lock": lock},
    )
    with server_type((host, port), handler) as server:
        bound = server.server_address
        # Not a message but a handshake: whoever started this reads the port it landed on
        # off this line, a port of 0 having been the way to ask for any free one.
        print(  # noqa: T201
            f"hmz anchor serve listening {bound[0]} {bound[1]}",
            file=sys.stderr,
            flush=True,
        )
        with contextlib.suppress(KeyboardInterrupt):
            server.serve_forever(poll_interval=0.2)
        with lock:
            stragglers = list(live)
        for connection in stragglers:
            connection.close()
