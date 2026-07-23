"""What to do when the seccomp filter stops a traced process.

Every handler receives the tracee's registers at syscall *entry* and returns an
:class:`Action`:

``ALLOW``
    Let the syscall run natively.  Used for reads and metadata lookups once
    the shadow tree has been made to tell the target's truth, which is the
    common case and costs nothing.
``fails(errno)``
    Cancel the syscall and hand back the target's exact error.
``STALL``
    Leave the process stopped; the supervisor resumes it when the remote work
    it started has finished.  Used only for ``execve``.

Mutating syscalls are replayed on the target *first*, so its errno
wins, and then allowed to run locally, which keeps the shadow in step.
"""

from __future__ import annotations

import errno
import logging
import os
import socket
import struct
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from amflows.coganchor.linux import procfs
from amflows.coganchor.linux.ptrace import Registers
from amflows.coganchor.linux.syscalls import NR, syscall_name

if TYPE_CHECKING:  # pragma: no cover - import cycle only matters for typing
    from amflows.coganchor.supervisor import Supervisor, Tracee

__all__ = ["ALLOW", "STALL", "Action", "SyscallDispatcher", "fails"]

log = logging.getLogger(__name__)

AT_FDCWD = -100
AT_REMOVEDIR = 0x200

O_WRONLY = 0o1
O_RDWR = 0o2
O_CREAT = 0o100
O_TRUNC = 0o1000
O_DIRECTORY = 0o200000
O_ACCMODE = 0o3

_CREAT_FLAGS = O_CREAT | O_WRONLY | O_TRUNC


@dataclass(frozen=True, slots=True)
class Action:
    """What the supervisor should do with a stopped syscall."""

    kind: Literal["allow", "errno", "stall"]
    errno: int = 0


ALLOW = Action("allow")
STALL = Action("stall")


def fails(code: int) -> Action:
    return Action("errno", code or errno.EIO)


class SyscallDispatcher:
    """Routes each trapped syscall to its handler."""

    def __init__(self, supervisor: Supervisor) -> None:
        self._sup = supervisor
        self._table = {
            NR.EXECVE: self._execve,
            NR.EXECVEAT: self._execveat,
            NR.OPEN: self._open,
            NR.OPENAT: self._openat,
            NR.OPENAT2: self._openat2,
            NR.CREAT: self._creat,
            NR.STAT: self._peek_path0,
            NR.LSTAT: self._peek_path0,
            NR.ACCESS: self._peek_path0,
            NR.READLINK: self._peek_path0,
            NR.NEWFSTATAT: self._peek_path1,
            NR.STATX: self._peek_path1,
            NR.FACCESSAT: self._peek_path1,
            NR.FACCESSAT2: self._peek_path1,
            NR.READLINKAT: self._peek_path1,
            NR.CHDIR: self._chdir,
            NR.MKDIR: self._mkdir,
            NR.MKDIRAT: self._mkdirat,
            NR.RMDIR: self._rmdir,
            NR.UNLINK: self._unlink,
            NR.UNLINKAT: self._unlinkat,
            NR.RENAME: self._rename,
            NR.RENAMEAT: self._renameat,
            NR.RENAMEAT2: self._renameat,
            NR.SYMLINK: self._symlink,
            NR.SYMLINKAT: self._symlinkat,
            NR.LINK: self._link,
            NR.LINKAT: self._linkat,
            NR.CHMOD: self._chmod,
            NR.FCHMODAT: self._fchmodat,
            NR.TRUNCATE: self._truncate,
            NR.UTIMENSAT: self._utimensat,
            NR.UTIMES: self._utimes,
            NR.CONNECT: self._connect,
        }

    def dispatch(self, tracee: Tracee, registers: Registers) -> Action:
        handler = self._table.get(registers.syscall_number)
        if handler is None:
            return ALLOW
        try:
            return handler(tracee, registers)
        except procfs.TraceeGoneError:
            return ALLOW
        except OSError as exc:
            log.debug(
                "%s failed for pid %d: %s",
                syscall_name(registers.syscall_number),
                tracee.pid,
                exc,
            )
            return fails(exc.errno or errno.EIO)

    # ------------------------------------------------------------------ opening

    def _open(self, tracee: Tracee, registers: Registers) -> Action:
        path = self._path(tracee.pid, AT_FDCWD, registers.arg(0))
        return self._prepare_open(path, registers.arg(1))

    def _openat(self, tracee: Tracee, registers: Registers) -> Action:
        path = self._path(tracee.pid, registers.signed_arg(0), registers.arg(1))
        return self._prepare_open(path, registers.arg(2))

    def _openat2(self, tracee: Tracee, registers: Registers) -> Action:
        path = self._path(tracee.pid, registers.signed_arg(0), registers.arg(1))
        raw = procfs.read_bytes(tracee.pid, registers.arg(2), 8)
        flags = int.from_bytes(raw, "little") if len(raw) == 8 else 0
        return self._prepare_open(path, flags)

    def _creat(self, tracee: Tracee, registers: Registers) -> Action:
        path = self._path(tracee.pid, AT_FDCWD, registers.arg(0))
        return self._prepare_open(path, _CREAT_FLAGS)

    def _prepare_open(self, path: str | None, flags: int) -> Action:
        """Make a local ``open`` on a remote path behave like one on the target."""
        if path is None or not self._sup.router.is_remote_path(path):
            return ALLOW
        shadow = self._sup.shadow
        shadow.ensure_path(path)
        if flags & O_DIRECTORY:
            shadow.ensure_directory(path)
            return ALLOW
        writable = bool(flags & (O_WRONLY | O_RDWR | O_CREAT))
        # A truncating write never needs the old bytes; everything else does,
        # including O_APPEND and read-modify-write editing.
        if not (flags & O_TRUNC and (flags & O_ACCMODE) == O_WRONLY):
            shadow.ensure_content(path)
        if writable:
            shadow.note_write(path)
        return ALLOW

    # ----------------------------------------------------- metadata and lookups

    def _peek_path0(self, tracee: Tracee, registers: Registers) -> Action:
        """Materialise the directory holding ``arg0`` and let the syscall run."""
        return self._peek(self._path(tracee.pid, AT_FDCWD, registers.arg(0)))

    def _peek_path1(self, tracee: Tracee, registers: Registers) -> Action:
        return self._peek(
            self._path(tracee.pid, registers.signed_arg(0), registers.arg(1))
        )

    def _peek(self, path: str | None) -> Action:
        if path is not None and self._sup.router.is_remote_path(path):
            self._sup.shadow.ensure_path(path)
        return ALLOW

    def _chdir(self, tracee: Tracee, registers: Registers) -> Action:
        path = self._path(tracee.pid, AT_FDCWD, registers.arg(0))
        if path is not None and self._sup.router.is_remote_path(path):
            self._sup.shadow.ensure_directory(path)
        return ALLOW

    # -------------------------------------------------------------- mutations

    def _mkdir(self, tracee: Tracee, registers: Registers) -> Action:
        return self._make_dir(
            self._path(tracee.pid, AT_FDCWD, registers.arg(0)), registers.arg(1)
        )

    def _mkdirat(self, tracee: Tracee, registers: Registers) -> Action:
        return self._make_dir(
            self._path(tracee.pid, registers.signed_arg(0), registers.arg(1)),
            registers.arg(2),
        )

    def _make_dir(self, path: str | None, mode: int) -> Action:
        if path is None or not self._sup.router.is_remote_path(path):
            return ALLOW
        self._sup.shadow.ensure_path(path)
        return self._replay(
            lambda: self._sup.client.mkdir(self._virtual(path), mode & 0o7777)
        )

    def _rmdir(self, tracee: Tracee, registers: Registers) -> Action:
        return self._remove(
            self._path(tracee.pid, AT_FDCWD, registers.arg(0)), is_dir=True
        )

    def _unlink(self, tracee: Tracee, registers: Registers) -> Action:
        return self._remove(
            self._path(tracee.pid, AT_FDCWD, registers.arg(0)), is_dir=False
        )

    def _unlinkat(self, tracee: Tracee, registers: Registers) -> Action:
        path = self._path(tracee.pid, registers.signed_arg(0), registers.arg(1))
        return self._remove(path, is_dir=bool(registers.arg(2) & AT_REMOVEDIR))

    def _remove(self, path: str | None, *, is_dir: bool) -> Action:
        if path is None or not self._sup.router.is_remote_path(path):
            return ALLOW
        self._sup.shadow.ensure_path(path)
        virtual = self._virtual(path)
        remove = self._sup.client.rmdir if is_dir else self._sup.client.unlink
        action = self._replay(lambda: remove(virtual))
        if action is ALLOW:
            self._sup.shadow.forget(path)
        return action

    def _rename(self, tracee: Tracee, registers: Registers) -> Action:
        source = self._path(tracee.pid, AT_FDCWD, registers.arg(0))
        target = self._path(tracee.pid, AT_FDCWD, registers.arg(1))
        return self._relate(
            source, target, self._sup.client.rename, self._sup.shadow.rename
        )

    def _renameat(self, tracee: Tracee, registers: Registers) -> Action:
        source = self._path(tracee.pid, registers.signed_arg(0), registers.arg(1))
        target = self._path(tracee.pid, registers.signed_arg(2), registers.arg(3))
        return self._relate(
            source, target, self._sup.client.rename, self._sup.shadow.rename
        )

    def _relate(
        self,
        source: str | None,
        target: str | None,
        replay: Callable[[str, str], object],
        record: Callable[[str, str], None],
    ) -> Action:
        """Replay a two-path mutation on the target, then mirror it locally.

        Shared by ``rename`` and ``link``, which differ only in the pair of
        calls they make.
        """
        router = self._sup.router
        if source is None or target is None:
            return ALLOW
        if not router.is_remote_path(source) and not router.is_remote_path(target):
            return ALLOW
        if router.is_remote_path(source) != router.is_remote_path(target):
            # Crossing the boundary would need a copy; refuse the way the
            # kernel refuses a cross-device rename, so callers fall back.
            return fails(errno.EXDEV)
        self._sup.shadow.ensure_path(source)
        self._sup.shadow.ensure_path(target)
        action = self._replay(
            lambda: replay(self._virtual(source), self._virtual(target))
        )
        if action is ALLOW:
            record(source, target)
        return action

    def _symlink(self, tracee: Tracee, registers: Registers) -> Action:
        target = procfs.read_cstring(tracee.pid, registers.arg(0))
        path = self._path(tracee.pid, AT_FDCWD, registers.arg(1))
        return self._make_symlink(target, path)

    def _symlinkat(self, tracee: Tracee, registers: Registers) -> Action:
        target = procfs.read_cstring(tracee.pid, registers.arg(0))
        path = self._path(tracee.pid, registers.signed_arg(1), registers.arg(2))
        return self._make_symlink(target, path)

    def _make_symlink(self, target: str | None, path: str | None) -> Action:
        if path is None or target is None or not self._sup.router.is_remote_path(path):
            return ALLOW
        self._sup.shadow.ensure_path(path)
        return self._replay(
            lambda: self._sup.client.symlink(target, self._virtual(path))
        )

    def _link(self, tracee: Tracee, registers: Registers) -> Action:
        source = self._path(tracee.pid, AT_FDCWD, registers.arg(0))
        target = self._path(tracee.pid, AT_FDCWD, registers.arg(1))
        return self._relate(
            source, target, self._sup.client.link, self._sup.shadow.duplicate
        )

    def _linkat(self, tracee: Tracee, registers: Registers) -> Action:
        source = self._path(tracee.pid, registers.signed_arg(0), registers.arg(1))
        target = self._path(tracee.pid, registers.signed_arg(2), registers.arg(3))
        return self._relate(
            source, target, self._sup.client.link, self._sup.shadow.duplicate
        )

    def _chmod(self, tracee: Tracee, registers: Registers) -> Action:
        return self._change_mode(
            self._path(tracee.pid, AT_FDCWD, registers.arg(0)), registers.arg(1)
        )

    def _fchmodat(self, tracee: Tracee, registers: Registers) -> Action:
        return self._change_mode(
            self._path(tracee.pid, registers.signed_arg(0), registers.arg(1)),
            registers.arg(2),
        )

    def _change_mode(self, path: str | None, mode: int) -> Action:
        if path is None or not self._sup.router.is_remote_path(path):
            return ALLOW
        self._sup.shadow.ensure_path(path)
        return self._replay(
            lambda: self._sup.client.chmod(self._virtual(path), mode & 0o7777)
        )

    def _truncate(self, tracee: Tracee, registers: Registers) -> Action:
        path = self._path(tracee.pid, AT_FDCWD, registers.arg(0))
        if path is None or not self._sup.router.is_remote_path(path):
            return ALLOW
        # Truncation reshapes local content, which the next flush pushes; no
        # separate remote call is needed.
        self._sup.shadow.ensure_content(path)
        self._sup.shadow.note_write(path)
        return ALLOW

    def _utimensat(self, tracee: Tracee, registers: Registers) -> Action:
        path = self._path(tracee.pid, registers.signed_arg(0), registers.arg(1))
        times = self._read_times(tracee.pid, registers.arg(2), micro=False)
        return self._set_times(path, times)

    def _utimes(self, tracee: Tracee, registers: Registers) -> Action:
        path = self._path(tracee.pid, AT_FDCWD, registers.arg(0))
        times = self._read_times(tracee.pid, registers.arg(1), micro=True)
        return self._set_times(path, times)

    def _set_times(
        self, path: str | None, times: tuple[int | None, int | None]
    ) -> Action:
        if path is None or not self._sup.router.is_remote_path(path):
            return ALLOW
        if times == (None, None):
            return ALLOW  # both omitted: the syscall asks for no change at all
        self._sup.shadow.ensure_path(path)
        return self._replay(
            lambda: self._sup.client.utime(self._virtual(path), times[0], times[1])
        )

    # ------------------------------------------------------------------ execve

    def _execve(self, tracee: Tracee, registers: Registers) -> Action:
        program = procfs.read_cstring(tracee.pid, registers.arg(0))
        return self._exec(
            tracee, registers, program, registers.arg(1), registers.arg(2)
        )

    def _execveat(self, tracee: Tracee, registers: Registers) -> Action:
        program = self._path(tracee.pid, registers.signed_arg(0), registers.arg(1))
        return self._exec(
            tracee, registers, program, registers.arg(2), registers.arg(3)
        )

    def _exec(
        self,
        tracee: Tracee,
        registers: Registers,
        program: str | None,
        argv_addr: int,
        envp_addr: int,
    ) -> Action:
        tracee.exec_count += 1
        if program is None:
            return ALLOW
        resolved = self._absolute(tracee.pid, program)
        if self._sup.is_agent_launch(tracee, resolved):
            log.debug("pid %d: running %s on this machine", tracee.pid, resolved)
            return ALLOW
        argv = procfs.read_string_array(tracee.pid, argv_addr)
        env = _as_mapping(procfs.read_string_array(tracee.pid, envp_addr))
        return self._sup.begin_remote_exec(
            tracee, registers, resolved, argv or [resolved], env
        )

    # ----------------------------------------------------------------- network

    def _connect(self, tracee: Tracee, registers: Registers) -> Action:
        proxy = self._sup.netproxy
        if proxy is None:
            return ALLOW
        endpoint = _read_sockaddr(tracee.pid, registers.arg(1), registers.arg(2))
        if endpoint is None:
            return ALLOW
        family, host, port = endpoint
        replacement = proxy.redirect(host, port, family)
        if replacement is None:
            return ALLOW
        blob = _encode_sockaddr(family, *replacement)
        if procfs.write_bytes(tracee.pid, registers.arg(1), blob) != len(blob):
            return ALLOW
        registers.set_arg(2, len(blob))
        return ALLOW

    # --------------------------------------------------------------- utilities

    def _replay(self, operation: Callable[[], object]) -> Action:
        """Perform a mutation on the target, mapping its errno onto the syscall."""
        try:
            self._sup.shadow.flush()
            operation()
        except OSError as exc:
            return fails(exc.errno or errno.EIO)
        return ALLOW

    def _virtual(self, local_path: str) -> str:
        return self._sup.router.to_virtual(local_path)

    def _path(self, pid: int, dirfd: int, address: int) -> str | None:
        raw = procfs.read_cstring(pid, address)
        if raw is None:
            return None
        if raw == "":
            # AT_EMPTY_PATH: the descriptor itself names the target.
            return None if dirfd == AT_FDCWD else _fd_path(pid, dirfd)
        if raw.startswith("/"):
            return os.path.normpath(raw)
        base = (
            procfs.working_directory(pid) if dirfd == AT_FDCWD else _fd_path(pid, dirfd)
        )
        if base is None:
            return None
        return os.path.normpath(os.path.join(base, raw))

    @staticmethod
    def _absolute(pid: int, program: str) -> str:
        if program.startswith("/"):
            return os.path.normpath(program)
        return os.path.normpath(os.path.join(procfs.working_directory(pid), program))

    @staticmethod
    def _read_times(
        pid: int, address: int, *, micro: bool
    ) -> tuple[int | None, int | None]:
        """Read the atime/mtime pair ``utimensat`` and ``utimes`` both point at.

        The two structs are laid out identically; only the fraction's scale
        differs, and only ``timespec`` carries the OMIT/NOW sentinels.  A null
        pointer means "set both to now", which is spelled out here so that a
        ``None`` in the result can mean only "leave this one alone".
        """
        if address == 0:
            now = time.time_ns()
            return (now, now)
        raw = procfs.read_bytes(pid, address, 32)
        if len(raw) < 32:
            return (None, None)
        atime_s, atime_frac, mtime_s, mtime_frac = struct.unpack("<qqqq", raw)
        if micro:
            return (
                atime_s * 1_000_000_000 + atime_frac * 1000,
                mtime_s * 1_000_000_000 + mtime_frac * 1000,
            )
        return (_timespec_ns(atime_s, atime_frac), _timespec_ns(mtime_s, mtime_frac))


#: ``UTIME_NOW``/``UTIME_OMIT`` sentinels from <sys/stat.h>.
_UTIME_NOW = (1 << 30) - 1
_UTIME_OMIT = (1 << 30) - 2


def _timespec_ns(seconds: int, nanoseconds: int) -> int | None:
    """Nanoseconds for one ``timespec``, or ``None`` where it says to omit.

    ``UTIME_NOW`` is resolved against this machine's clock rather than left to
    the target: the protocol can say "leave this one alone", but it has no way
    to say "set this one to now and leave the other".  Collapsing both
    sentinels to ``None``, as an earlier version did, made an omitted timestamp
    on the target be rewritten instead of preserved.
    """
    if nanoseconds == _UTIME_OMIT:
        return None
    if nanoseconds == _UTIME_NOW:
        return time.time_ns()
    return seconds * 1_000_000_000 + nanoseconds


def _fd_path(pid: int, dirfd: int) -> str | None:
    try:
        target = procfs.fd_target(pid, dirfd)
    except OSError:
        return None
    return target if target.startswith("/") else None


def _as_mapping(entries: list[str]) -> dict[str, str]:
    env: dict[str, str] = {}
    for entry in entries:
        name, sep, value = entry.partition("=")
        if sep:
            env[name] = value
    return env


def _read_sockaddr(pid: int, address: int, length: int) -> tuple[int, str, int] | None:
    """Decode an IPv4/IPv6 ``connect`` target, ignoring anything else."""
    if address == 0 or length < 8:
        return None
    try:
        raw = procfs.read_bytes(pid, address, min(length, 28))
    except OSError:
        return None
    if len(raw) < 8:
        return None
    family = struct.unpack_from("<H", raw, 0)[0]
    port = struct.unpack_from("!H", raw, 2)[0]
    if family == socket.AF_INET:
        return family, socket.inet_ntop(socket.AF_INET, raw[4:8]), port
    if family == socket.AF_INET6 and len(raw) >= 24:
        return family, socket.inet_ntop(socket.AF_INET6, raw[8:24]), port
    return None


def _encode_sockaddr(family: int, host: str, port: int) -> bytes:
    """Build a replacement address in the family the tracee's socket already has.

    Handing an ``AF_INET6`` socket a 16-byte ``sockaddr_in`` fails ``EINVAL``,
    so the redirection has to keep the family it found.
    """
    if family == socket.AF_INET6:
        return (
            struct.pack("<H", socket.AF_INET6)
            + struct.pack("!H", port)
            + bytes(4)  # sin6_flowinfo
            + socket.inet_pton(socket.AF_INET6, host)
            + bytes(4)  # sin6_scope_id
        )
    return (
        struct.pack("<H", socket.AF_INET)
        + struct.pack("!H", port)
        + socket.inet_aton(host)
        + bytes(8)  # sin_zero
    )
