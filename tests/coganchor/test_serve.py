"""Unit tests for the target half: exports, filesystem ops, and the server."""

from __future__ import annotations

import errno
import os
import pty
import signal
import socket
import threading
from typing import TYPE_CHECKING, Any

import pytest

from hmz.coganchor.proto import (
    PROTOCOL_VERSION,
    Channel,
    Frame,
    Kind,
    Op,
    RemoteOSError,
)
from hmz.coganchor.remote import RemoteClient
from hmz.coganchor.serve import fsops
from hmz.coganchor.serve.exports import Export, ExportTable
from hmz.coganchor.serve.server import Server
from hmz.coganchor.serve.sessions import _read_stream, compose_env
from tests.coganchor.conftest import VIRTUAL_EXPORT

if TYPE_CHECKING:
    from collections.abc import Iterable
    from pathlib import Path

    from tests.coganchor.conftest import Link

# --------------------------------------------------------------------- exports


def test_export_parses_identity_and_mapped_forms() -> None:
    assert Export.parse("/project") == Export.parse("/project:/project")
    mapped = Export.parse("/project:/srv/real")
    assert (mapped.virtual, mapped.real) == ("/project", "/srv/real")


def test_export_rejects_relative_virtual_paths() -> None:
    with pytest.raises(ValueError, match="absolute"):
        Export.parse("project:/srv/real")


def test_resolution_maps_into_the_real_directory() -> None:
    table = ExportTable.parse(["/project:/srv/real"])
    assert table.resolve("/project") == "/srv/real"
    assert table.resolve("/project/src/a.py") == "/srv/real/src/a.py"


def test_resolution_refuses_escapes() -> None:
    table = ExportTable.parse(["/project:/srv/real"])
    for escape in ("/project/../etc/passwd", "/etc/passwd", "/projectile/x"):
        with pytest.raises(PermissionError):
            table.resolve(escape)


def test_longest_export_wins() -> None:
    table = ExportTable.parse(["/project:/srv/real", "/project/data:/mnt/data"])
    assert table.resolve("/project/data/set.csv") == "/mnt/data/set.csv"
    assert table.resolve("/project/src/a.py") == "/srv/real/src/a.py"


# --------------------------------------------------------------------- fsops


def _write(
    table: ExportTable, path: str, chunks: Iterable[bytes], mode: int | None = None
) -> None:
    """Drive a FileWriter the way the server does, aborting on a failed stream."""
    writer = fsops.FileWriter(table, path, mode)
    try:
        for chunk in chunks:
            writer.feed(chunk)
    except BaseException:
        writer.abort()
        raise
    writer.finish()


@pytest.fixture
def table(tmp_path: Path) -> ExportTable:
    return ExportTable.parse([f"/project:{tmp_path}"])


def test_listdir_reports_full_metadata(table: ExportTable, tmp_path: Path) -> None:
    (tmp_path / "file.txt").write_text("abc")
    (tmp_path / "sub").mkdir()
    (tmp_path / "link").symlink_to("file.txt")

    entries = {
        entry["name"]: entry for entry in fsops.listdir(table, "/project")["entries"]
    }
    assert entries["file.txt"]["kind"] == "file"
    assert entries["file.txt"]["size"] == 3
    assert entries["sub"]["kind"] == "dir"
    assert entries["link"]["kind"] == "link"
    assert entries["link"]["target"] == "file.txt"


def test_read_streams_in_chunks(table: ExportTable, tmp_path: Path) -> None:
    payload = os.urandom(200_000)
    (tmp_path / "blob.bin").write_bytes(payload)

    collected: list[bytes] = []
    meta = fsops.read(table, "/project/blob.bin", collected.append)
    assert b"".join(collected) == payload
    assert meta["size"] == len(payload)
    assert len(collected) > 1, "a large file should arrive in several chunks"


def test_write_is_atomic_and_leaves_no_debris(
    table: ExportTable, tmp_path: Path
) -> None:
    _write(table, "/project/out.txt", [b"one ", b"two"], mode=0o644)
    assert (tmp_path / "out.txt").read_bytes() == b"one two"
    assert [p.name for p in tmp_path.iterdir()] == ["out.txt"]


def test_concurrent_writers_to_one_path_do_not_share_a_temporary(
    table: ExportTable, tmp_path: Path
) -> None:
    """``--listen`` serves every connection from one process, so two may share a path.

    A per-process temporary name would have them overwrite each other's bytes.
    """
    first = fsops.FileWriter(table, "/project/out.txt", 0o644)
    second = fsops.FileWriter(table, "/project/out.txt", 0o644)
    assert first._temp != second._temp

    first.feed(b"first")
    second.feed(b"second")
    second.finish()
    first.finish()
    assert (tmp_path / "out.txt").read_bytes() == b"first"
    assert [p.name for p in tmp_path.iterdir()] == ["out.txt"]


def test_write_follows_symlinks(table: ExportTable, tmp_path: Path) -> None:
    (tmp_path / "real.txt").write_text("old")
    (tmp_path / "alias.txt").symlink_to("real.txt")

    _write(table, "/project/alias.txt", [b"new"])
    assert (tmp_path / "real.txt").read_text() == "new"
    assert (tmp_path / "alias.txt").is_symlink()


def test_failed_write_removes_its_temporary_file(
    table: ExportTable, tmp_path: Path
) -> None:
    def explode() -> bytes:
        raise RuntimeError("stream died")

    with pytest.raises(RuntimeError):
        _write(table, "/project/out.txt", (chunk for chunk in [b"x", explode()]))
    assert list(tmp_path.iterdir()) == []


def test_utime_with_no_arguments_means_now(table: ExportTable, tmp_path: Path) -> None:
    target = tmp_path / "stamp.txt"
    target.write_text("x")
    os.utime(target, ns=(0, 0))

    fsops.utime(table, "/project/stamp.txt", None, None)
    assert target.stat().st_mtime_ns > 0


# ------------------------------------------------------------------ environment


def test_environment_starts_from_this_machine() -> None:
    env = compose_env({"PATH": "/machine-a/bin", "MY_TOKEN": "abc"}, "/work", tty=False)
    assert env["PATH"] == os.environ["PATH"], "PATH must describe the target"
    assert env["MY_TOKEN"] == "abc", "the agent's own variables must carry over"
    assert env["PWD"] == "/work"


def test_host_specific_variables_do_not_leak() -> None:
    env = compose_env(
        {"HOME": "/machine-a/home", "LD_PRELOAD": "/evil.so"}, "/work", tty=False
    )
    assert env["HOME"] == os.environ["HOME"]
    assert "LD_PRELOAD" not in env


def test_what_a_mac_says_about_itself_does_not_leak_either() -> None:
    """What a macOS client's own login session put in its environment stays on that machine.

    ``DYLD_INSERT_LIBRARIES`` is that machine's ``LD_PRELOAD`` and would name a library of
    the client's; the rest name the launchd session it logged in on. Asserted against this
    machine's own environment rather than against absence, because a macOS target has its own
    copies of these and is entitled to keep them.
    """
    clients = {
        "DYLD_INSERT_LIBRARIES": "/machine-a/evil.dylib",
        "DYLD_LIBRARY_PATH": "/machine-a/lib",
        "SECURITYSESSIONID": "186a6",
        "__CF_USER_TEXT_ENCODING": "0x1F5:0x0:0x0",
        "Apple_PubSub_Socket_Render": "/private/tmp/com.apple.launchd.0/Render",
        "XPC_SERVICE_NAME": "0",
    }
    env = compose_env(clients | {"MY_TOKEN": "abc"}, "/work", tty=False)

    for name in clients:
        assert env.get(name) == os.environ.get(name), f"{name} came from the client"
    assert env["MY_TOKEN"] == "abc", "and everything else still crosses"


# ---------------------------------------------------------------------- server


def test_handshake_reports_the_exports(link: Link) -> None:
    assert link.client.info["exports"][0]["virtual"] == "/project"


def test_missing_file_raises_the_targets_errno(link: Link) -> None:
    with pytest.raises(RemoteOSError) as caught:
        link.client.call(Op.STAT, path="/project/absent.txt")
    assert caught.value.errno == errno.ENOENT


def test_paths_outside_exports_are_refused(link: Link) -> None:
    with pytest.raises(RemoteOSError) as caught:
        link.client.call(Op.STAT, path="/etc/passwd")
    assert caught.value.errno == errno.EACCES


def test_file_round_trip_over_the_channel(link: Link) -> None:
    payload = os.urandom(300_000)
    source = link.target / "source.bin"
    source.write_bytes(payload)

    with source.open("rb") as handle:
        link.client.write_file("/project/copy.bin", handle, 0o644)
    assert (link.target / "copy.bin").read_bytes() == payload

    sink = link.target / "back.bin"
    with sink.open("wb") as handle:
        meta = link.client.read_file("/project/copy.bin", handle)
    assert sink.read_bytes() == payload
    assert meta["size"] == len(payload)


def test_mutations_are_applied(link: Link) -> None:
    link.client.mkdir("/project/box")
    assert (link.target / "box").is_dir()

    link.client.symlink("box", "/project/alias")
    assert link.client.call(Op.READLINK, path="/project/alias")["target"] == "box"

    link.client.rename("/project/box", "/project/crate")
    assert (link.target / "crate").is_dir()

    link.client.rmdir("/project/crate")
    assert not (link.target / "crate").exists()


def test_unknown_operation_reports_enosys_without_dropping_the_link(link: Link) -> None:
    """A peer speaking a newer protocol gets an error, not a dead connection."""
    msg_id, pending = link.client._register(None, None)
    link.client._send(Frame(Kind.REQ, msg_id, {"op": "teleport"}))
    with pytest.raises(RemoteOSError) as caught:
        link.client._await(msg_id, pending)
    assert caught.value.errno == errno.ENOSYS

    still_working = link.client.call(Op.STAT, path="/project")
    assert still_working["kind"] == "dir", "the connection must still work"


def test_a_request_missing_what_it_needs_is_a_bad_request_rather_than_a_dead_link(
    link: Link,
) -> None:
    """A peer that sent nonsense gets an error; the session it sent it on goes on."""
    with pytest.raises(RemoteOSError) as raised:
        link.client.call(Op.STAT)

    assert raised.value.errno == errno.EINVAL
    assert link.client.call(Op.STAT, path=VIRTUAL_EXPORT)["kind"] == "dir"


def test_the_end_of_a_stream_reads_the_same_whichever_way_the_kernel_says_it() -> None:
    """A spent descriptor answers with no bytes, whichever way its kernel says so.

    A pty master whose child is gone raises ``EIO`` on Linux and ends the file on macOS,
    whose ``kqueue`` reports it readable and has no other way to say it. Both are the end of
    the output, and the second is stood in for here by a socket, which says it that way on
    either machine -- so a run on Linux covers the answer a Mac would give.
    """
    master, slave = pty.openpty()
    os.close(slave)
    try:
        assert _read_stream(master) == b""
    finally:
        os.close(master)

    left, right = socket.socketpair()
    with left, right:
        right.close()
        assert _read_stream(left.fileno()) == b""


@pytest.mark.timeout(60)
def test_a_command_given_a_tty_runs_and_ends_on_it(link: Link) -> None:
    """Which is how an agent started from a terminal spawns everything it spawns.

    The session ends when the pty says the child is gone, and that is the only thing that
    ever says so: there is no second descriptor to read the exit off.
    """
    ended = threading.Event()
    said: list[bytes] = []

    def over(_result: dict[str, Any] | None, _error: object) -> None:
        ended.set()

    link.client.start_exec(
        ["sh", "-c", "echo from-the-tty"],
        cwd=VIRTUAL_EXPORT,
        env={},
        on_output=lambda _stream, data: said.append(data),
        on_exit=over,
        tty=True,
        winsize=(24, 80),
    )

    assert ended.wait(timeout=30)
    assert b"from-the-tty" in b"".join(said)


@pytest.mark.timeout(60)
def test_a_signal_reaches_the_command_it_names(link: Link) -> None:
    """A turn stopped here is a process stopped there, or the target keeps running it."""
    ended = threading.Event()
    done: list[dict[str, Any]] = []

    def over(result: dict[str, Any] | None, _error: object) -> None:
        done.append(result or {})
        ended.set()

    running = link.client.start_exec(
        ["sleep", "60"],
        cwd=VIRTUAL_EXPORT,
        env={},
        on_output=lambda stream, data: None,
        on_exit=over,
    )
    assert not ended.wait(timeout=1)

    running.signal(signal.SIGTERM)

    assert ended.wait(timeout=30)
    assert done


@pytest.mark.timeout(60)
def test_a_signal_naming_nothing_is_answered_rather_than_ignored(link: Link) -> None:
    """The client waits on the reply, so a target that said nothing would hang it."""
    assert link.client.call(Op.SIGNAL, target=999_999, sig=signal.SIGTERM) is not None


@pytest.mark.timeout(60)
def test_a_client_speaking_another_protocol_is_refused_and_the_link_goes_with_it() -> (
    None
):
    """Both ends check, because either may be the older build.

    And the connection goes with the refusal: an untokened session starts out
    authenticated, so failing the handshake alone would leave every request after it
    working.
    """
    left, right = socket.socketpair()
    table = ExportTable.parse([f"{VIRTUAL_EXPORT}:/"])
    server = Server(Channel.from_socket(right), table)
    thread = threading.Thread(target=server.serve, daemon=True)
    thread.start()
    client = RemoteClient(Channel.from_socket(left))
    client._reader.start()
    try:
        with pytest.raises(RemoteOSError) as raised:
            client.call(Op.HELLO, version=PROTOCOL_VERSION + 1000, token=None)

        assert raised.value.errno == errno.EPROTO
        thread.join(timeout=10)
        assert not thread.is_alive(), "the connection must go with the refusal"
    finally:
        client.close()
        left.close()
        right.close()
