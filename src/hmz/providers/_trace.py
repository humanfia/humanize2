"""The supervisor half of a redirected run: the loop, and the paths it rewrites.

Separate from :mod:`hmz.providers.redirect` because this half needs ptrace and an
x86-64 register map, which reading a provider and rendering a command line do not: a machine
that cannot trace can still hold providers, choose one, and hand a turn its variables.

What it does is one thing. Every syscall that names a path is stopped on the way in; the path
is resolved as the kernel would resolve it -- against the process's own directory, or against
the descriptor an `*at` call was given -- and if it is one of the provider's, a path inside
the provider's directory is written into the tracee and the register pointed at it. The
syscall then runs, natively, against the file it was given. One that cannot be rewritten is
failed rather than let through: a turn that read the credentials of whoever is at this machine
would be a turn run as the wrong account, which is worse than a turn that did not run.
"""

from __future__ import annotations

import contextlib
import os
import signal
from typing import TYPE_CHECKING, Any

from hmz.coganchor.linux import procfs, ptrace
from hmz.coganchor.linux.syscalls import NR

from .redirect import UNSWAPPABLE, failed

if TYPE_CHECKING:
    from hmz.coganchor.linux.ptrace import Registers

    from .redirect import Swaps

__all__ = ["Tracing"]

#: `AT_FDCWD`: the descriptor that means "wherever the process is".
_AT_FDCWD = -100

#: Where `struct open_how` keeps the resolution it insists on, and the two settings of it that
#: an absolute path cannot honour: one says the file must be under the descriptor it was given,
#: the other that the descriptor is the root. A call that asked for either is failed rather
#: than answered, since answering it would either break the promise or quietly re-root it.
_OPEN_HOW_RESOLVE = 16
_RESOLVE_CONFINED = 0x08 | 0x10

#: What a rewritten path is kept clear of: the red zone, which a leaf function of the tracee
#: may be using this moment, and which is the only part of the stack below the pointer that is
#: anybody's. Everything below it is stack the process has not reached.
#:
#: Only as many bytes as the paths themselves take, and no more: a thread with a stack of its
#: own -- a Node worker, a Rust pool -- may have only a page or two left below the pointer,
#: and a fixed few kilobytes would be written past the end of it, into whatever the allocator
#: happened to put there.
_RED_ZONE = 128

#: Where each trapped syscall keeps the paths it names, as `(descriptor argument, path
#: argument)` pairs -- the descriptor being None for a call that has none and resolves against
#: the process's own directory. Read off the manual pages, one line per call.
_PATHS: dict[int, tuple[tuple[int | None, int], ...]] = {
    NR.OPEN: ((None, 0),),
    NR.CREAT: ((None, 0),),
    NR.STAT: ((None, 0),),
    NR.LSTAT: ((None, 0),),
    NR.ACCESS: ((None, 0),),
    NR.READLINK: ((None, 0),),
    NR.CHDIR: ((None, 0),),
    NR.MKDIR: ((None, 0),),
    NR.RMDIR: ((None, 0),),
    NR.UNLINK: ((None, 0),),
    NR.CHMOD: ((None, 0),),
    NR.TRUNCATE: ((None, 0),),
    NR.UTIMES: ((None, 0),),
    # The link itself, not what it says: what a symlink points at is text the kernel does not
    # resolve here, and rewriting it would be answering a question nobody asked.
    NR.SYMLINK: ((None, 1),),
    NR.LINK: ((None, 0), (None, 1)),
    NR.RENAME: ((None, 0), (None, 1)),
    NR.OPENAT: ((0, 1),),
    NR.OPENAT2: ((0, 1),),
    NR.NEWFSTATAT: ((0, 1),),
    NR.STATX: ((0, 1),),
    NR.FACCESSAT: ((0, 1),),
    NR.FACCESSAT2: ((0, 1),),
    NR.READLINKAT: ((0, 1),),
    NR.MKDIRAT: ((0, 1),),
    NR.UNLINKAT: ((0, 1),),
    NR.FCHMODAT: ((0, 1),),
    NR.UTIMENSAT: ((0, 1),),
    NR.SYMLINKAT: ((1, 2),),
    NR.RENAMEAT: ((0, 1), (2, 3)),
    NR.RENAMEAT2: ((0, 1), (2, 3)),
    NR.LINKAT: ((0, 1), (2, 3)),
}


class Tracing:
    """One redirected run: the processes it is watching, and what each of them is told."""

    def __init__(self, swaps: Swaps) -> None:
        """Initializes a run that is watching nothing yet.

        Args:
          swaps: Which paths are answered by which others.
        """
        self._swaps = swaps
        #: Every process being watched, and whether it has been attached to yet: a child
        #: reports itself before its parent's fork event arrives, and the first stop of one
        #: is where its options are set.
        self._watching: dict[int, bool] = {}
        #: What to plant at the exit stop of a syscall that was cancelled, by process.
        self._owed: dict[int, int] = {}
        self._root = 0
        self._status = 1

    def trapped(self) -> list[int]:
        """The syscalls the filter has to stop, which is every one that names a path."""
        return sorted(_PATHS)

    def watch(self, pid: int) -> int:
        """Services one process and everything it starts, until the first of them exits.

        Args:
          pid: The process, stopped at the `SIGSTOP` it raised before it became the program.

        Returns:
          Its exit status, or 128 plus the signal that killed it.
        """
        self._root = pid
        os.waitpid(pid, 0)  # the stop it raised for us, before it exec'd anything
        ptrace.setoptions(pid)
        self._watching[pid] = True

        # A signal aimed at this process is aimed at the program under it: whatever asked for
        # it -- a flow taking a session down, a service manager -- asked for the agent to
        # stop, and this is only the thing holding its paths. So it is passed on rather than
        # acted on: dying here would leave the agent running with nobody answering its
        # credential paths. `SIGINT` is the exception, and is ignored: a ctrl-c at a terminal
        # already reaches the whole group, so passing it on would deliver it twice.
        def passed(said: int, _frame: object) -> None:
            with contextlib.suppress(OSError):
                os.kill(pid, said)

        with contextlib.suppress(OSError, ValueError):
            signal.signal(signal.SIGINT, signal.SIG_IGN)
        for said in (signal.SIGTERM, signal.SIGQUIT, signal.SIGHUP):
            with contextlib.suppress(OSError, ValueError):
                signal.signal(said, passed)
        _try(ptrace.cont, pid)
        while self._watching:
            try:
                got, status = os.waitpid(-1, ptrace.WALL)
            except ChildProcessError:
                break
            except InterruptedError:  # pragma: no cover -- retried by the loop
                continue
            self._stopped(got, status)
        return self._status

    def _stopped(self, pid: int, status: int) -> None:
        """Acts on one thing that happened to one of the processes being watched."""
        if os.WIFEXITED(status) or os.WIFSIGNALED(status):
            self._watching.pop(pid, None)
            self._owed.pop(pid, None)
            if pid == self._root:
                self._status = failed(status)
                # The run is over the moment the program it was for is, rather than when the
                # last thing it started is: waiting for those would be waiting on a daemon.
                # What is still being traced goes with this process, which is what ptrace's
                # own `EXITKILL` is for -- a process left running with nobody answering its
                # credential paths would be one reading the wrong account's.
                self._watching.clear()
            return
        if not self._watching.get(pid, False):
            # Its first stop, whether or not the fork event has arrived: attach here.
            self._watching[pid] = True
            _try(ptrace.setoptions, pid)
            _try(ptrace.cont, pid)
            return
        event = status >> 16
        said = os.WSTOPSIG(status)
        if event == ptrace.EVENT_SECCOMP:
            self._syscall(pid)
        elif event in (ptrace.EVENT_FORK, ptrace.EVENT_VFORK, ptrace.EVENT_CLONE):
            with contextlib.suppress(OSError):
                self._watching.setdefault(int(ptrace.get_event_message(pid)), False)
            _try(ptrace.cont, pid)
        elif event:
            _try(ptrace.cont, pid)
        elif said == (signal.SIGTRAP | ptrace.SYSCALL_STOP_SIG):
            self._answer(pid)
        elif said == signal.SIGTRAP:
            _try(ptrace.cont, pid)
        else:
            _try(ptrace.cont, pid, said)

    def _syscall(self, pid: int) -> None:
        """Rewrites the paths one stopped syscall names, and lets it run."""
        try:
            registers = ptrace.getregs(pid)
        except OSError:
            return
        taken = (
            0  # what the paths already planted have used, so two do not overwrite one
        )
        for descriptor, argument in _PATHS.get(registers.syscall_number, ()):
            try:
                named = self._named(pid, registers, descriptor, argument)
            except (OSError, ValueError):
                continue  # a process that went away mid-read is not one to fail a call for
            if named is None:
                continue
            instead = self._swaps.swap(named)
            if instead is None:
                continue
            if self._confined(pid, registers):
                self._cancel(pid, registers)
                return
            room = self._plant(pid, registers, taken, argument, instead)
            if room is None:
                self._cancel(pid, registers)
                return
            taken += room
        if registers.dirty:
            _try(ptrace.setregs, pid, registers)
        _try(ptrace.cont, pid)

    def _confined(self, pid: int, registers: Registers) -> bool:
        """Whether this call asked for a resolution an answered path cannot be given.

        Args:
          pid: The process.
          registers: Its registers at the stop.

        Returns:
          True for an `openat2` that insisted on staying under the descriptor it was given,
          which an absolute path somewhere else cannot do. Everything else takes an absolute
          path as an absolute path.
        """
        if registers.syscall_number != NR.OPENAT2:
            return False
        try:
            raw = procfs.read_bytes(pid, registers.arg(2), _OPEN_HOW_RESOLVE + 8)[
                _OPEN_HOW_RESOLVE:
            ]
        except OSError:
            return False
        return bool(int.from_bytes(raw, "little") & _RESOLVE_CONFINED)

    def _named(
        self, pid: int, registers: Registers, descriptor: int | None, argument: int
    ) -> str | None:
        """The absolute path one argument names, resolved as the kernel would resolve it.

        Args:
          pid: The process that named it.
          registers: Its registers at the stop.
          descriptor: Which argument holds the directory to resolve against, or None for a
            call that resolves against the process's own directory.
          argument: Which argument holds the path.

        Returns:
          The path, or None where there is nothing to resolve -- an empty path, which names
          the descriptor itself, or a directory that cannot be read back.
        """
        raw = procfs.read_cstring(pid, registers.arg(argument))
        if not raw:
            return None
        if raw.startswith("/"):
            return os.path.normpath(raw)
        at = _AT_FDCWD if descriptor is None else registers.signed_arg(descriptor)
        under = (
            procfs.working_directory(pid)
            if at == _AT_FDCWD
            else procfs.fd_target(pid, at)
        )
        if not under.startswith("/"):
            return None  # a descriptor that is not a directory of this filesystem
        return os.path.normpath(os.path.join(under, raw))

    def _plant(
        self, pid: int, registers: Registers, taken: int, argument: int, path: str
    ) -> int | None:
        """Writes a path into the tracee and points one of its arguments at it.

        Args:
          pid: The process.
          registers: Its registers, which are written back by the caller.
          taken: How many bytes this syscall's earlier paths have already used below the
            pointer, so that the second of them does not land on the first.
          argument: Which argument to point at the new path.
          path: The path itself.

        Returns:
          How many bytes it took, or None where it could not be written -- a stack with no
          room left below it, or a process that went away mid-write. An absolute path ignores
          whatever descriptor the call was also given, so nothing else has to be rewritten for
          it to be the file that is opened.
        """
        # As the tracee named it: a path is bytes, and one that is not valid text came back
        # through the surrogates `read_cstring` escapes it with.
        blob = os.fsencode(path) + b"\0"
        where = registers.stack_pointer - _RED_ZONE - taken - len(blob)
        try:
            procfs.write_bytes(pid, where, blob)
            if procfs.read_bytes(pid, where, len(blob)) != blob:
                return None
        except (OSError, ValueError, UnicodeEncodeError):
            return None
        registers.set_arg(argument, where)
        return len(blob)

    def _cancel(self, pid: int, registers: Registers) -> None:
        """Fails a syscall whose path could not be rewritten, with the target's own errno.

        The kernel overwrites the return register when a syscall is skipped, so the errno can
        only be planted at the exit stop -- which is what :meth:`_answer` is waiting for.
        """
        registers.syscall_number = -1
        self._owed[pid] = UNSWAPPABLE
        try:
            ptrace.setregs(pid, registers)
            ptrace.syscall(pid)
        except OSError:
            self._owed.pop(pid, None)

    def _answer(self, pid: int) -> None:
        """Plants the errno owed to a cancelled syscall, at the stop on its way out."""
        code = self._owed.pop(pid, 0)
        if not code:
            _try(ptrace.cont, pid)
            return
        try:
            registers = ptrace.getregs(pid)
            registers.result = -code
            ptrace.setregs(pid, registers)
            ptrace.cont(pid)
        except OSError:
            pass


def _try(call: Any, *args: Any) -> None:
    """Runs a ptrace call, tolerating a process that has already gone."""
    with contextlib.suppress(OSError):
        call(*args)
