"""Making the agent's own outbound TCP connections come from the target.

Commands the agent runs already use the target's network, because they run
there.  This module covers the remaining case: connections opened by the agent
process itself, such as a built-in web fetch.

``connect(2)`` is trapped, the destination is swapped for a loopback listener
allocated here, and whatever the agent sends is relayed through the target and
out of the target.  One listener is bound per destination, so the port a
connection arrives on identifies where it was really headed -- no per-connection
state has to be guessed.

The agent's own control-plane traffic (its model API) must keep using machine
A, so this is opt-in and takes an allow-list.
"""

from __future__ import annotations

import contextlib
import ipaddress
import logging
import selectors
import socket
import threading
from typing import TYPE_CHECKING, Any

from hmz.coganchor.proto import CHUNK_SIZE, Stream

if TYPE_CHECKING:
    from hmz.coganchor.remote import RemoteClient

__all__ = ["NetProxy"]

log = logging.getLogger(__name__)


class NetProxy:
    """Redirects selected outbound TCP through the target machine."""

    def __init__(self, client: RemoteClient, keep_local: tuple[str, ...] = ()) -> None:
        self._client = client
        self._keep_local = _resolve_allow_list(keep_local)
        self._listeners: dict[tuple[str, int], socket.socket] = {}
        self._selector = selectors.DefaultSelector()
        self._lock = threading.Lock()
        self._running = threading.Event()
        self._wake_read, self._wake_write = socket.socketpair()

    def start(self) -> None:
        self._running.set()
        self._selector.register(self._wake_read, selectors.EVENT_READ, None)
        threading.Thread(target=self._accept_loop, name="netproxy", daemon=True).start()

    def close(self) -> None:
        self._running.clear()
        self._wake_write.send(b"\x00")

    def redirect(self, host: str, port: int, family: int) -> tuple[str, int] | None:
        """Return the loopback address to connect to instead, or ``None``.

        ``None`` means "leave this connection alone", which is the answer for
        loopback, link-local and unspecified addresses and anything explicitly
        allow-listed.  The replacement is in the caller's own address family:
        the tracee is about to hand it to a socket that already has one, and a
        socket given an address of the wrong family fails ``EINVAL``.
        """
        if not self._running.is_set() or self._should_stay_local(host, port):
            return None
        with self._lock:
            listener = self._listeners.get((host, port))
            if listener is None:
                listener = self._bind_listener(host, port, family)
        return _loopback(family), listener.getsockname()[1]

    def _should_stay_local(self, host: str, port: int) -> bool:
        if f"{host}:{port}" in self._keep_local or host in self._keep_local:
            return True
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            return False
        return address.is_loopback or address.is_link_local or address.is_unspecified

    def _bind_listener(self, host: str, port: int, family: int) -> socket.socket:
        listener = socket.socket(family, socket.SOCK_STREAM)
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind((_loopback(family), 0))
        listener.listen(64)
        listener.setblocking(False)  # noqa: FBT003  -- the socket module's own signature
        local_port = listener.getsockname()[1]
        self._listeners[(host, port)] = listener
        # The destination rides on the selector key rather than a port lookup:
        # an IPv4 and an IPv6 listener can hold the same port number.
        self._selector.register(listener, selectors.EVENT_READ, (host, port))
        self._wake_write.send(b"\x00")
        log.debug(
            "tunnelling %s:%d -> %s:%d via the target",
            _loopback(family),
            local_port,
            host,
            port,
        )
        return listener

    def _accept_loop(self) -> None:
        while self._running.is_set():
            for key, _ in self._selector.select(timeout=0.5):
                if key.data is None:
                    self._wake_read.recv(4096)
                    continue
                self._accept(key.fileobj, key.data)  # pyright: ignore[reportArgumentType]
        self._shutdown()

    def _accept(self, listener: socket.socket, destination: tuple[str, int]) -> None:
        try:
            client, _ = listener.accept()
        except OSError:
            return
        _Relay(self._client, client, destination).start()

    def _shutdown(self) -> None:
        with self._lock:
            for listener in self._listeners.values():
                with contextlib.suppress(KeyError, ValueError):
                    self._selector.unregister(listener)
                listener.close()
            self._listeners.clear()
        self._selector.close()
        self._wake_read.close()
        self._wake_write.close()


class _Relay:
    """Pumps one accepted loopback connection through a remote TCP tunnel."""

    def __init__(
        self, client: RemoteClient, sock: socket.socket, destination: tuple[str, int]
    ) -> None:
        self._client = client
        self._socket = sock
        self._host, self._port = destination
        self._closed = threading.Event()

    def start(self) -> None:
        threading.Thread(target=self._run, name="net-relay", daemon=True).start()

    def _run(self) -> None:
        handle = self._client.open_tunnel(
            self._host, self._port, self._on_data, self._on_close
        )
        self._socket.settimeout(None)
        try:
            while not self._closed.is_set():
                data = self._socket.recv(CHUNK_SIZE)
                if not data:
                    handle.close_write()
                    break
                handle.send(data)
        except OSError:
            pass
        finally:
            self._closed.wait(timeout=30.0)
            _close(self._socket)

    def _on_data(self, stream: Stream, data: bytes) -> None:  # noqa: ARG002
        try:
            self._socket.sendall(data)
        except OSError:
            self._closed.set()

    def _on_close(self, result: dict[str, Any] | None, error: OSError | None) -> None:  # noqa: ARG002
        if error is not None:
            log.debug("tunnel to %s:%d ended: %s", self._host, self._port, error)
        self._closed.set()
        with contextlib.suppress(OSError):
            self._socket.shutdown(socket.SHUT_RDWR)


def _close(sock: socket.socket) -> None:
    with contextlib.suppress(OSError):
        sock.close()


def _loopback(family: int) -> str:
    return "::1" if family == socket.AF_INET6 else "127.0.0.1"


def _resolve_allow_list(entries: tuple[str, ...]) -> frozenset[str]:
    """Expand ``--net-allow`` entries into the addresses ``connect`` will name.

    ``connect(2)`` is trapped after the agent has already resolved the name, so
    the destination is always numeric by the time it is matched.  An entry
    naming a host therefore only ever matches once resolved here.
    """
    expanded = set(entries)
    for entry in entries:
        host, _, port = entry.rpartition(":")
        if not host or not port.isdigit():
            host, port = entry, ""
        try:
            ipaddress.ip_address(host)
        except ValueError:
            pass
        else:
            continue  # already an address; nothing to resolve
        try:
            infos = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
        except OSError:
            log.warning("could not resolve --net-allow %r; it will never match", entry)
            continue
        for info in infos:
            address = str(info[4][0])
            expanded.add(f"{address}:{port}" if port else address)
    return frozenset(expanded)
