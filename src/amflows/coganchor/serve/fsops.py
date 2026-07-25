"""Filesystem operations executed on this machine.

Each function takes virtual paths, resolves them through the
:class:`~amflows.coganchor.serve.exports.ExportTable`, and lets :class:`OSError`
propagate so the client is handed this machine's exact ``errno``.
"""

from __future__ import annotations

import contextlib
import itertools
import os
import stat as stat_module
from collections.abc import Callable
from typing import Any

from amflows.coganchor.proto import CHUNK_SIZE
from amflows.coganchor.serve.exports import ExportTable

__all__ = [
    "FileWriter",
    "chmod",
    "describe",
    "link",
    "listdir",
    "mkdir",
    "read",
    "readlink",
    "rename",
    "rmdir",
    "stat",
    "symlink",
    "truncate",
    "unlink",
    "utime",
]


#: Distinguishes concurrent writers within one process.  ``--listen`` serves
#: every connection from the same process, so a name built only from the pid
#: would be shared by two sessions writing the same path.
_WRITER_SEQUENCE = itertools.count()


def _kind(mode: int) -> str:
    if stat_module.S_ISDIR(mode):
        return "dir"
    if stat_module.S_ISLNK(mode):
        return "link"
    if stat_module.S_ISREG(mode):
        return "file"
    return "other"


def describe(real: str, *, name: str | None = None) -> dict[str, Any]:
    """Return the wire representation of one directory entry or path."""
    info = os.lstat(real)
    entry: dict[str, Any] = {
        "kind": _kind(info.st_mode),
        "mode": info.st_mode,
        "size": info.st_size,
        "mtime_ns": info.st_mtime_ns,
    }
    if name is not None:
        entry["name"] = name
    if stat_module.S_ISLNK(info.st_mode):
        entry["target"] = os.readlink(real)
    return entry


def stat(table: ExportTable, path: str) -> dict[str, Any]:
    return describe(table.resolve(path))


def listdir(table: ExportTable, path: str) -> dict[str, Any]:
    """List a directory, returning full metadata for every entry.

    One round trip carries a whole directory, which is what lets a client
    mirror it and answer ``stat``/``getdents`` without asking again.
    """
    real = table.resolve(path)
    entries: list[dict[str, Any]] = []
    with os.scandir(real) as scan:
        for item in scan:
            try:
                entries.append(describe(item.path, name=item.name))
            except OSError:
                # The entry vanished between scandir and lstat; skip it.
                continue
    info = os.stat(real)
    return {"entries": entries, "mode": info.st_mode, "mtime_ns": info.st_mtime_ns}


def read(
    table: ExportTable, path: str, emit: Callable[[bytes], None]
) -> dict[str, Any]:
    """Stream a file's contents through ``emit`` in bounded chunks."""
    real = table.resolve(path)
    with open(real, "rb") as handle:
        info = os.fstat(handle.fileno())
        while chunk := handle.read(CHUNK_SIZE):
            emit(chunk)
    return {"size": info.st_size, "mode": info.st_mode, "mtime_ns": info.st_mtime_ns}


class FileWriter:
    """Streaming, atomic replacement of a single file.

    Content lands on a sibling temporary file that is renamed over the target,
    so a torn connection can never leave a half-written source file behind.
    Symlinks are followed, matching the write the client already performed
    against its own copy.
    """

    def __init__(self, table: ExportTable, path: str, mode: int | None) -> None:
        real = table.resolve(path)
        if os.path.islink(real):
            real = os.path.realpath(real)
        os.makedirs(os.path.dirname(real) or "/", exist_ok=True)
        self._real = real
        self._mode = mode
        self._temp = f"{real}.amflows-{os.getpid()}-{next(_WRITER_SEQUENCE)}.tmp"
        self._handle = open(self._temp, "wb")  # noqa: SIM115 - closed by finish/abort

    def feed(self, data: bytes) -> None:
        self._handle.write(data)

    def finish(self) -> dict[str, Any]:
        try:
            self._handle.close()
            mode = self._mode if self._mode is not None else self._existing_mode()
            if mode is not None:
                os.chmod(self._temp, stat_module.S_IMODE(mode))
            os.replace(self._temp, self._real)
        except BaseException:
            self.abort()
            raise
        return describe(self._real)

    def abort(self) -> None:
        with contextlib.suppress(OSError):
            self._handle.close()
        with contextlib.suppress(OSError):
            os.unlink(self._temp)

    def _existing_mode(self) -> int | None:
        try:
            return os.stat(self._real).st_mode
        except OSError:
            return None


def mkdir(table: ExportTable, path: str, mode: int, parents: bool) -> dict[str, Any]:
    real = table.resolve(path)
    if parents:
        os.makedirs(real, mode=mode, exist_ok=True)
    else:
        os.mkdir(real, mode)
    return {}


def rmdir(table: ExportTable, path: str) -> dict[str, Any]:
    os.rmdir(table.resolve(path))
    return {}


def unlink(table: ExportTable, path: str) -> dict[str, Any]:
    os.unlink(table.resolve(path))
    return {}


def rename(table: ExportTable, src: str, dst: str, replace: bool) -> dict[str, Any]:
    real_src, real_dst = table.resolve(src), table.resolve(dst)
    if replace:
        os.replace(real_src, real_dst)
    else:
        os.rename(real_src, real_dst)
    return {}


def symlink(table: ExportTable, target: str, path: str) -> dict[str, Any]:
    os.symlink(target, table.resolve(path))
    return {}


def link(table: ExportTable, src: str, dst: str) -> dict[str, Any]:
    os.link(table.resolve(src), table.resolve(dst))
    return {}


def readlink(table: ExportTable, path: str) -> dict[str, Any]:
    return {"target": os.readlink(table.resolve(path))}


def chmod(table: ExportTable, path: str, mode: int) -> dict[str, Any]:
    os.chmod(table.resolve(path), stat_module.S_IMODE(mode))
    return {}


def truncate(table: ExportTable, path: str, size: int) -> dict[str, Any]:
    os.truncate(table.resolve(path), size)
    return {}


def utime(
    table: ExportTable, path: str, atime_ns: int | None, mtime_ns: int | None
) -> dict[str, Any]:
    """Set timestamps; ``None`` for both means "now", matching ``utimensat``."""
    real = table.resolve(path)
    if atime_ns is None and mtime_ns is None:
        os.utime(real)
        return {}
    info = os.stat(real)
    os.utime(
        real,
        ns=(
            info.st_atime_ns if atime_ns is None else atime_ns,
            info.st_mtime_ns if mtime_ns is None else mtime_ns,
        ),
    )
    return {}
