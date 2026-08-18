"""Reaching into a stopped tracee: its memory, its ``/proc`` view, its fds.

Memory access goes through ``process_vm_readv``/``process_vm_writev`` (no file
descriptors to manage), and descriptors are duplicated with ``pidfd_getfd``,
which -- unlike opening ``/proc/<pid>/fd/N`` -- also works for the AF_UNIX
socketpairs that Node and Rust use for child stdio.
"""

from __future__ import annotations

import ctypes
import errno
import os
from typing import Final

from hmz.coganchor.linux.syscalls import NR

__all__ = [
    "MAX_ARG_STRLEN",
    "PATH_MAX",
    "TraceeGoneError",
    "fd_target",
    "read_bytes",
    "read_cstring",
    "read_string_array",
    "steal_fd",
    "working_directory",
    "write_bytes",
]

PATH_MAX: Final = 4096
_PAGE_SIZE: Final = os.sysconf("SC_PAGESIZE")
_MAX_ARGV_ENTRIES: Final = 65536

#: The kernel's own ceiling on one ``argv`` or ``envp`` entry, ``MAX_ARG_STRLEN``: thirty-two
#: pages. What a command may be, as opposed to what a path may be.
MAX_ARG_STRLEN: Final = 32 * _PAGE_SIZE

_libc = ctypes.CDLL("libc.so.6", use_errno=True)


class _Iovec(ctypes.Structure):
    _fields_ = [("base", ctypes.c_void_p), ("len", ctypes.c_size_t)]


_libc.process_vm_readv.restype = ctypes.c_ssize_t
_libc.process_vm_readv.argtypes = [
    ctypes.c_int,
    ctypes.POINTER(_Iovec),
    ctypes.c_ulong,
    ctypes.POINTER(_Iovec),
    ctypes.c_ulong,
    ctypes.c_ulong,
]
_libc.process_vm_writev.restype = ctypes.c_ssize_t
_libc.process_vm_writev.argtypes = _libc.process_vm_readv.argtypes
_libc.syscall.restype = ctypes.c_long


class TraceeGoneError(OSError):
    """The traced process disappeared mid-inspection."""


def read_bytes(pid: int, address: int, size: int) -> bytes:
    """Read ``size`` bytes from a tracee's address space."""
    if size <= 0:
        return b""
    buffer = ctypes.create_string_buffer(size)
    local = _Iovec(ctypes.cast(buffer, ctypes.c_void_p), size)
    remote = _Iovec(ctypes.c_void_p(address), size)
    ctypes.set_errno(0)
    count = _libc.process_vm_readv(
        pid, ctypes.byref(local), 1, ctypes.byref(remote), 1, 0
    )
    if count < 0:
        code = ctypes.get_errno()
        error = TraceeGoneError if code == errno.ESRCH else OSError
        raise error(
            code, os.strerror(code), f"process_vm_readv(pid={pid}, addr={address:#x})"
        )
    return buffer.raw[:count]


def write_bytes(pid: int, address: int, data: bytes) -> int:
    """Write ``data`` into a tracee's address space; returns bytes written."""
    if not data:
        return 0
    buffer = ctypes.create_string_buffer(data, len(data))
    local = _Iovec(ctypes.cast(buffer, ctypes.c_void_p), len(data))
    remote = _Iovec(ctypes.c_void_p(address), len(data))
    ctypes.set_errno(0)
    count = _libc.process_vm_writev(
        pid, ctypes.byref(local), 1, ctypes.byref(remote), 1, 0
    )
    if count < 0:
        code = ctypes.get_errno()
        raise OSError(
            code, os.strerror(code), f"process_vm_writev(pid={pid}, addr={address:#x})"
        )
    return int(count)


def read_cstring(pid: int, address: int, limit: int = PATH_MAX) -> str | None:
    """Read a NUL-terminated string, stopping at the first unreadable page.

    Returns ``None`` for a NULL pointer, which several syscalls accept.
    """
    if address == 0:
        return None
    parts: list[bytes] = []
    remaining = limit
    while remaining > 0:
        span = min(remaining, _PAGE_SIZE - (address % _PAGE_SIZE))
        try:
            block = read_bytes(pid, address, span)
        except OSError:
            break
        if not block:
            break
        end = block.find(b"\0")
        if end >= 0:
            parts.append(block[:end])
            return b"".join(parts).decode("utf-8", "surrogateescape")
        parts.append(block)
        address += span
        remaining -= span
    return b"".join(parts).decode("utf-8", "surrogateescape")


def read_string_array(
    pid: int, address: int, limit: int = _MAX_ARGV_ENTRIES
) -> list[str]:
    """Read a NULL-terminated array of string pointers (``argv``/``envp``)."""
    if address == 0:
        return []
    values: list[str] = []
    word = ctypes.sizeof(ctypes.c_void_p)
    while len(values) < limit:
        raw = read_bytes(pid, address, word)
        if len(raw) < word:
            break
        pointer = int.from_bytes(raw, "little")
        if pointer == 0:
            break
        # An argv entry is not a path, so PATH_MAX is the wrong ceiling for it: the kernel
        # lets one be MAX_ARG_STRLEN long, and a shell command is routinely longer than a
        # path. Truncating one is worse than failing to read it -- what reaches the target
        # is then a prefix of the command, which runs and means something else.
        text = read_cstring(pid, pointer, MAX_ARG_STRLEN)
        values.append("" if text is None else text)
        address += word
    return values


def working_directory(pid: int) -> str:
    """Current working directory of a tracee, as the kernel sees it."""
    return _readlink(f"/proc/{pid}/cwd")


def fd_target(pid: int, fd: int) -> str:
    """Path a tracee's descriptor refers to (``/proc/<pid>/fd/<n>``)."""
    return _readlink(f"/proc/{pid}/fd/{fd}")


def _readlink(path: str) -> str:
    try:
        return os.readlink(path)
    except FileNotFoundError as exc:
        raise TraceeGoneError(exc.errno, "tracee vanished", path) from exc


def steal_fd(pid: int, fd: int) -> int:
    """Duplicate a tracee's descriptor into this process.

    Uses ``pidfd_getfd(2)``, so pipes, sockets and ttys all work.
    """
    ctypes.set_errno(0)
    pidfd = _libc.syscall(NR.PIDFD_OPEN, pid, 0)
    if pidfd < 0:
        code = ctypes.get_errno()
        raise OSError(code, os.strerror(code), f"pidfd_open({pid})")
    try:
        ctypes.set_errno(0)
        stolen = _libc.syscall(NR.PIDFD_GETFD, pidfd, fd, 0)
        if stolen < 0:
            code = ctypes.get_errno()
            raise OSError(code, os.strerror(code), f"pidfd_getfd({pid}, {fd})")
        return int(stolen)
    finally:
        os.close(pidfd)
