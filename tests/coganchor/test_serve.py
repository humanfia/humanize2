"""Unit tests for the target half: exports, filesystem ops, and the server."""

from __future__ import annotations

import errno
import os
from typing import TYPE_CHECKING

import pytest

from humanize.coganchor.proto import Frame, Kind, Op, RemoteOSError
from humanize.coganchor.serve import fsops
from humanize.coganchor.serve.exports import Export, ExportTable
from humanize.coganchor.serve.sessions import compose_env

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
