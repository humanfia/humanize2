"""Official Kimi event notifications accelerate polling without owning turn state."""

from __future__ import annotations

import json
import threading
from contextlib import contextmanager, suppress
from typing import TYPE_CHECKING

import pytest
from websockets.exceptions import ConnectionClosed
from websockets.sync.server import serve

from hmz.agents import kimi

if TYPE_CHECKING:
    from collections.abc import Callable, Generator

    from websockets.sync.server import ServerConnection


@contextmanager
def server(handler: Callable[[ServerConnection], None]) -> Generator[str]:
    with serve(handler, "127.0.0.1", 0) as running:
        reader = threading.Thread(target=running.serve_forever, daemon=True)
        reader.start()
        yield f"http://127.0.0.1:{running.socket.getsockname()[1]}/api/v1"
        running.shutdown()
        reader.join(timeout=2)


def acknowledge(socket: ServerConnection, code: int = 0) -> None:
    assert socket.request is not None
    assert socket.request.headers["Authorization"] == "Bearer test-token"
    assert json.loads(socket.recv())["payload"] == {"session_ids": ["ours"]}
    socket.send(json.dumps({"type": "ack", "id": "hmz", "code": code}))


def test_notifications_are_isolated_and_completion_removes_settle_sleep(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handler(socket: ServerConnection) -> None:
        acknowledge(socket)
        for session, kind in (
            ("theirs", "turn.ended"),
            ("ours", "tool.call.started"),
            ("ours", "turn.ended"),
        ):
            socket.send(json.dumps({"type": kind, "session_id": session}))
        socket.recv()  # keep the stream open until the reader closes it

    with server(handler) as base:
        updates = kimi._Updates(base, "test-token", "ours")
        try:
            updates.wait(settled=False)
            assert not updates.ended
            updates.wait(settled=False)
            assert updates.ended
            slept: list[float] = []
            monkeypatch.setattr(kimi.time, "sleep", slept.append)
            updates.wait(settled=True)
            assert not slept
        finally:
            updates.close()


def test_heartbeats_echo_the_nonce_and_keep_notifications_flowing() -> None:
    replies: list[object] = []

    def handler(socket: ServerConnection) -> None:
        acknowledge(socket)
        for nonce, kind in (("one", "tool.call.started"), ("two", "turn.ended")):
            # Official application heartbeats have no session_id. Progress is withheld
            # until the client answers, so automatic WebSocket control pongs cannot pass.
            socket.send(json.dumps({"type": "ping", "payload": {"nonce": nonce}}))
            replies.append(json.loads(socket.recv(timeout=1)))
            socket.send(json.dumps({"type": kind, "session_id": "ours"}))
        socket.recv()

    with server(handler) as base:
        updates = kimi._Updates(base, "test-token", "ours")
        try:
            updates.wait(settled=False)
            assert not updates.ended
            updates.wait(settled=False)
            assert updates.ended
            assert updates._socket is not None
            assert replies == [
                {"type": "pong", "payload": {"nonce": "one"}},
                {"type": "pong", "payload": {"nonce": "two"}},
            ]
        finally:
            updates.close()


def test_saturated_notification_queue_does_not_delay_cleanup() -> None:
    sent = threading.Event()

    def handler(socket: ServerConnection) -> None:
        acknowledge(socket)
        for _ in range(64):
            socket.send(
                json.dumps(
                    {"type": "assistant.delta", "session_id": "ours", "payload": {}}
                )
            )
        sent.set()
        with suppress(ConnectionClosed):
            socket.recv(timeout=2)

    with server(handler) as base:
        updates = kimi._Updates(base, "test-token", "ours")
        try:
            socket = updates._socket
            assert socket is not None
            assert sent.wait(timeout=2)
            deadline = kimi.time.monotonic() + 2
            while not socket.recv_messages.paused and kimi.time.monotonic() < deadline:
                kimi.time.sleep(0.001)
            # Reproduce the actual failure: flow control prevents the receive thread
            # from reading the peer's close reply until the closing timeout expires.
            assert socket.recv_messages.paused
            assert socket.recv_messages.frames.qsize() > 16
            began = kimi.time.monotonic()
            updates.close()
            assert kimi.time.monotonic() - began < 0.5
            assert updates._socket is None
            assert socket.state.name == "CLOSED"
            assert not socket.recv_events_thread.is_alive()
        finally:
            updates.close()


def test_failed_heartbeat_reply_returns_to_polling(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handler(socket: ServerConnection) -> None:
        acknowledge(socket)
        socket.send(json.dumps({"type": "ping", "payload": {"nonce": "one"}}))
        socket.recv()

    def fail_send(_message: object) -> None:
        raise OSError("connection lost while replying")

    with server(handler) as base:
        updates = kimi._Updates(base, "test-token", "ours")
        assert updates._socket is not None
        monkeypatch.setattr(updates._socket, "send", fail_send)
        updates.wait(settled=False)
        assert updates._socket is None
        slept: list[float] = []
        monkeypatch.setattr(kimi.time, "sleep", slept.append)
        updates.wait(settled=False)
        assert slept == [kimi._POLL_SECONDS]


def test_refused_subscription_returns_to_polling(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handler(socket: ServerConnection) -> None:
        acknowledge(socket, code=40001)

    with server(handler) as base:
        updates = kimi._Updates(base, "test-token", "ours")
        slept: list[float] = []
        monkeypatch.setattr(kimi.time, "sleep", slept.append)
        updates.wait(settled=False)
        assert slept == [kimi._POLL_SECONDS]
        assert updates._socket is None


def test_lost_event_stream_returns_to_polling(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(socket: ServerConnection) -> None:
        acknowledge(socket)

    with server(handler) as base:
        updates = kimi._Updates(base, "test-token", "ours")
        updates.wait(settled=False)
        assert updates._socket is None
        slept: list[float] = []
        monkeypatch.setattr(kimi.time, "sleep", slept.append)
        updates.wait(settled=False)
        assert slept == [kimi._POLL_SECONDS]


def test_quiet_event_stream_still_allows_recovery_polls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handler(socket: ServerConnection) -> None:
        acknowledge(socket)
        socket.recv()

    monkeypatch.setattr(kimi, "_RECOVERY_SECONDS", 0.01)
    with server(handler) as base:
        updates = kimi._Updates(base, "test-token", "ours")
        try:
            updates.wait(settled=False)
            assert updates._socket is not None
            assert not updates.ended
        finally:
            updates.close()


@pytest.mark.parametrize(
    "message",
    [
        "[]",
        json.dumps({"type": "turn.ended", "session_id": "ours", "payload": []}),
        json.dumps({"type": "ping", "payload": {"nonce": 1}}),
    ],
)
def test_malformed_notification_returns_to_polling(message: str) -> None:
    def handler(socket: ServerConnection) -> None:
        acknowledge(socket)
        socket.send(message)
        socket.recv()

    with server(handler) as base:
        updates = kimi._Updates(base, "test-token", "ours")
        updates.wait(settled=False)
        assert updates._socket is None


def test_streaming_text_wakes_a_recovery_wait(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handler(socket: ServerConnection) -> None:
        acknowledge(socket)
        socket.send(json.dumps({"type": "assistant.delta", "session_id": "ours"}))
        socket.recv()

    # Without a text wakeup this would wait the ten-second recovery interval instead.
    monkeypatch.setattr(kimi, "_POLL_SECONDS", 0.01)
    with server(handler) as base:
        updates = kimi._Updates(base, "test-token", "ours")
        try:
            started = kimi.time.monotonic()
            updates.wait(settled=False)
            assert kimi.time.monotonic() - started < 1
        finally:
            updates.close()


def test_subagent_completion_does_not_settle_the_main_turn() -> None:
    def handler(socket: ServerConnection) -> None:
        acknowledge(socket)
        for agent, kind in (
            ("main", "turn.started"),
            ("worker", "turn.ended"),
            ("main", "turn.ended"),
            ("worker", "turn.started"),
            ("worker", "turn.ended"),
            ("main", "turn.started"),
            ("main", "event.approval.requested"),
        ):
            socket.send(
                json.dumps(
                    {"type": kind, "session_id": "ours", "payload": {"agentId": agent}}
                )
            )
        socket.recv()

    with server(handler) as base:
        updates = kimi._Updates(base, "test-token", "ours")
        try:
            updates.wait(settled=False)
            assert not updates.ended
            updates.wait(settled=False)
            assert updates.ended
            updates.wait(settled=False)
            assert updates.ended
            updates.wait(settled=False)
            assert not updates.ended
        finally:
            updates.close()
