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


def test_notifications_say_which_authoritative_read_is_due() -> None:
    def handler(socket: ServerConnection) -> None:
        acknowledge(socket)
        for kind in (
            "tool.call.started",
            "turn.step.completed",
            "event.approval.requested",
            "event.question.requested",
            "error",
        ):
            socket.send(json.dumps({"type": kind, "session_id": "ours"}))
        socket.recv()

    with server(handler) as base:
        updates = kimi._Updates(base, "test-token", "ours")
        try:
            # A listener that has been told nothing yet asks the daemon everything.
            assert (updates.questioned, updates.stepped) == (True, True)
            for expected in (
                (False, False),  # a tool starting moves neither spending nor questions
                (False, True),  # a step that landed is spending that moved
                (True, False),  # an approval is a question by another name
                (True, False),
                (True, True),  # and one the daemon could not name is both
            ):
                updates.questioned = updates.stepped = False
                updates.wait(settled=False)
                assert (updates.questioned, updates.stepped) == expected
        finally:
            updates.close()


def test_a_frame_under_an_unknown_name_still_wakes_the_reader(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handler(socket: ServerConnection) -> None:
        acknowledge(socket)
        socket.send(json.dumps({"type": "event.consent.wanted", "session_id": "ours"}))
        socket.recv()

    # Without this the reader would wait out the whole recovery interval for a question
    # the daemon had named something this table has never heard of.
    monkeypatch.setattr(kimi, "_RECOVERY_SECONDS", 30)
    monkeypatch.setattr(kimi, "_POLL_SECONDS", 0.05)
    with server(handler) as base:
        updates = kimi._Updates(base, "test-token", "ours")
        try:
            updates.questioned = updates.stepped = False
            started = kimi.time.monotonic()
            updates.wait(settled=False)
            assert kimi.time.monotonic() - started < 5
            assert (updates.questioned, updates.stepped) == (True, True)
        finally:
            updates.close()


def test_streamed_chunks_are_coalesced_rather_than_woken_for_one_by_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent = threading.Event()

    def handler(socket: ServerConnection) -> None:
        acknowledge(socket)
        for kind in ("shell.output", "tool.call.delta", "tool.progress"):
            for _ in range(8):
                socket.send(json.dumps({"type": kind, "session_id": "ours"}))
        sent.set()
        socket.recv()

    # The daemon streams a running command's output a chunk at a time. One wake per chunk
    # would be four calls per chunk on the daemon every session of the agent shares.
    monkeypatch.setattr(kimi, "_RECOVERY_SECONDS", 30)
    monkeypatch.setattr(kimi, "_POLL_SECONDS", 0.2)
    with server(handler) as base:
        updates = kimi._Updates(base, "test-token", "ours")
        try:
            assert sent.wait(timeout=2)
            wakes = 0
            deadline = kimi.time.monotonic() + 1.5
            while kimi.time.monotonic() < deadline:
                updates.wait(settled=False)
                wakes += 1
            assert wakes <= 12  # twenty-four chunks, at most one wake per poll interval
            assert (updates.questioned, updates.stepped) == (True, True)
        finally:
            updates.close()


def test_streaming_text_alone_does_not_re_arm_the_authoritative_reads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handler(socket: ServerConnection) -> None:
        acknowledge(socket)
        for _ in range(4):
            socket.send(json.dumps({"type": "assistant.delta", "session_id": "ours"}))
        socket.recv()

    # A deadline reached with text still arriving is the coalescing above, not silence:
    # nothing about it says a question is waiting or that spending has moved. Silence is
    # covered separately, and does ask the daemon everything.
    monkeypatch.setattr(kimi, "_RECOVERY_SECONDS", 30)
    monkeypatch.setattr(kimi, "_POLL_SECONDS", 0.05)
    with server(handler) as base:
        updates = kimi._Updates(base, "test-token", "ours")
        try:
            updates.questioned = updates.stepped = False
            updates.wait(settled=False)
            assert (updates.questioned, updates.stepped) == (False, False)
        finally:
            updates.close()


def test_a_listener_that_stops_carrying_events_asks_for_everything(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handler(socket: ServerConnection) -> None:
        acknowledge(socket)
        socket.send(json.dumps({"type": "turn.step.completed", "session_id": "ours"}))
        socket.recv()

    monkeypatch.setattr(kimi, "_RECOVERY_SECONDS", 0.01)
    with server(handler) as base:
        updates = kimi._Updates(base, "test-token", "ours")
        try:
            updates.wait(settled=False)
            updates.questioned = updates.stepped = False
            # Silence for a whole recovery interval is a listener that may have missed
            # something, so the reader goes back to asking the daemon everything.
            updates.wait(settled=False)
            assert (updates.questioned, updates.stepped) == (True, True)
            updates.questioned = updates.stepped = False
            updates.close()
            assert (updates.questioned, updates.stepped) == (True, True)
            updates.questioned = updates.stepped = False
            slept: list[float] = []
            monkeypatch.setattr(kimi.time, "sleep", slept.append)
            updates.wait(settled=False)
            assert slept == [kimi._POLL_SECONDS]
            assert (updates.questioned, updates.stepped) == (True, True)
        finally:
            updates.close()
