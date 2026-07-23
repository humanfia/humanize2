"""Tests for routing the agent's own TCP connections through the target."""

from __future__ import annotations

import socket
import threading
from collections.abc import Iterator

import pytest

from amflows.coganchor.netproxy import NetProxy
from tests.coganchor.conftest import Anchorage, Link


def _routable_address() -> str:
    """An address on this host that is not loopback, or skip."""
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect(("192.0.2.1", 9))  # TEST-NET-1; no packet is sent
        address = str(probe.getsockname()[0])
    except OSError:
        pytest.skip("no routable address on this host")
    finally:
        probe.close()
    if address.startswith("127."):
        pytest.skip("only loopback is available on this host")
    return address


@pytest.fixture
def echo_server() -> Iterator[tuple[str, int]]:
    """A TCP server on a non-loopback address that echoes what it receives."""
    host = _routable_address()
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind((host, 0))
    listener.listen(8)
    stop = threading.Event()

    def serve() -> None:
        while not stop.is_set():
            try:
                connection, _ = listener.accept()
            except OSError:
                return
            with connection:
                while data := connection.recv(4096):
                    connection.sendall(b"echo:" + data)

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    yield listener.getsockname()
    stop.set()
    listener.close()
    thread.join(timeout=2)


def test_loopback_connections_are_left_alone(link: Link) -> None:
    proxy = NetProxy(link.client)
    proxy.start()
    try:
        assert proxy.redirect("127.0.0.1", 8080, socket.AF_INET) is None
        assert proxy.redirect("::1", 8080, socket.AF_INET6) is None
    finally:
        proxy.close()


def test_allow_listed_hosts_are_left_alone(link: Link) -> None:
    proxy = NetProxy(link.client, keep_local=("203.0.113.7", "198.51.100.9:443"))
    proxy.start()
    try:
        assert proxy.redirect("203.0.113.7", 443, socket.AF_INET) is None
        assert proxy.redirect("198.51.100.9", 443, socket.AF_INET) is None
        assert proxy.redirect("198.51.100.9", 80, socket.AF_INET) is not None
    finally:
        proxy.close()


def test_an_allow_listed_hostname_is_resolved(link: Link) -> None:
    """``connect`` names an address, so a hostname must be resolved to match.

    Without this the entry is compared against a numeric address it can never
    equal, and the connection is tunnelled out of the target regardless.
    """
    proxy = NetProxy(link.client, keep_local=("localhost:443",))
    proxy.start()
    try:
        assert proxy.redirect("127.0.0.1", 443, socket.AF_INET) is None
        # A name that resolves to nothing must not smuggle anything through.
        assert NetProxy(
            link.client, keep_local=("no-such-host.invalid",)
        )._keep_local == frozenset({"no-such-host.invalid"})
    finally:
        proxy.close()


def test_a_destination_always_maps_to_the_same_listener(link: Link) -> None:
    proxy = NetProxy(link.client)
    proxy.start()
    try:
        first = proxy.redirect("203.0.113.7", 443, socket.AF_INET)
        assert first == proxy.redirect("203.0.113.7", 443, socket.AF_INET)
        assert first != proxy.redirect("203.0.113.7", 8443, socket.AF_INET)
    finally:
        proxy.close()


def test_an_ipv6_destination_is_replaced_by_an_ipv6_stand_in(link: Link) -> None:
    """An AF_INET6 socket handed an IPv4 sockaddr fails EINVAL, so keep the family."""
    proxy = NetProxy(link.client)
    proxy.start()
    try:
        stand_in = proxy.redirect("2001:db8::1", 443, socket.AF_INET6)
        assert stand_in is not None
        assert stand_in[0] == "::1", "an IPv6 socket cannot be handed a v4 address"
        listener = proxy._listeners[("2001:db8::1", 443)]
        assert listener.family == socket.AF_INET6, "nor reach a v4 listener"
    finally:
        proxy.close()


def test_traffic_reaches_the_destination_through_the_target(
    link: Link, echo_server: tuple[str, int]
) -> None:
    """Data sent to the loopback stand-in comes back from the real server."""
    proxy = NetProxy(link.client)
    proxy.start()
    try:
        stand_in = proxy.redirect(*echo_server, socket.AF_INET)
        assert stand_in is not None

        with socket.create_connection(stand_in, timeout=10) as connection:
            connection.sendall(b"ping")
            connection.settimeout(10)
            assert connection.recv(100) == b"echo:ping"
    finally:
        proxy.close()


@pytest.mark.timeout(120)
def test_agent_connections_are_tunnelled_end_to_end(
    anchorage: Anchorage, echo_server: tuple[str, int]
) -> None:
    """A ``connect`` from the traced agent itself is redirected and still works."""
    host, port = echo_server
    program = (
        "import socket\n"
        f"s = socket.create_connection(({host!r}, {port}), timeout=20)\n"
        "s.sendall(b'from-the-agent')\n"
        "print(s.recv(100).decode())\n"
    )
    result = anchorage.run("python3", "-c", program, net="remote", timeout=90)
    assert "echo:from-the-agent" in result.stdout, result.stderr


@pytest.mark.timeout(120)
def test_local_net_mode_leaves_connections_alone(
    anchorage: Anchorage, echo_server: tuple[str, int]
) -> None:
    """The default keeps the agent's own traffic on this machine and working."""
    host, port = echo_server
    program = (
        "import socket\n"
        f"s = socket.create_connection(({host!r}, {port}), timeout=20)\n"
        "s.sendall(b'direct')\n"
        "print(s.recv(100).decode())\n"
    )
    result = anchorage.run("python3", "-c", program, timeout=90)
    assert "echo:direct" in result.stdout, result.stderr
