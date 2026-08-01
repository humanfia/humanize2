"""Turning a traced process into a stand-in for a command running elsewhere.

When coganchor decides an ``execve`` belongs on the target, the process that
issued it still has a job to do here: it must look, to its parent, exactly like
the child that was asked for -- and then report the remote command's status.

The subtle part is releasing the parent.  A parent that spawns with
``posix_spawn`` or ``vfork`` is suspended by the kernel until its child execs
or exits; a parent that spawns with ``fork`` blocks reading a close-on-exec
handshake pipe.  Both are released by exactly one event: a successful
``execve``.  Simply leaving the process stopped therefore serialises every
command behind the previous one, and hangs any agent that starts a long-lived
shell and then writes to it.

So an exec is made to happen -- just not the one that was asked for.  The path
argument is redirected at a stub, the exec is allowed through, and the process
is caught at ``PTRACE_EVENT_EXEC`` before the stub runs a single instruction.
The parent is free, close-on-exec descriptors are gone, and the stand-in waits
at its first syscall, where the supervisor can later turn it into an
``exit_group`` carrying the remote status.
"""

from __future__ import annotations

import contextlib
import errno
import logging
import os
import signal
from typing import TYPE_CHECKING

from hmz.coganchor.linux import procfs, ptrace
from hmz.coganchor.linux.syscalls import NR

if TYPE_CHECKING:
    from hmz.coganchor.linux.ptrace import Registers

__all__ = ["STUB_PROGRAM", "park"]

log = logging.getLogger(__name__)

#: ``AT_FDCWD`` as an unsigned word, for redirecting ``execveat``.
_AT_FDCWD = 0xFFFFFFFFFFFFFF9C

#: Scratch space in the tracee's stack red zone, which the exec discards anyway.
_RED_ZONE_OFFSET = 512

#: Syscall stops to walk through before giving up on finding an entry stop.
_MAX_STEPS_TO_ENTRY = 4


def _choose_stub() -> str:
    """Pick a program the tracee can exec that is guaranteed never to run.

    It is caught at ``PTRACE_EVENT_EXEC``, before its first instruction, so
    only the kernel's image load ever happens.  ``/proc/self/exe`` is the
    fallback because it always exists and is always executable.
    """
    for candidate in ("/bin/true", "/usr/bin/true"):
        if os.access(candidate, os.X_OK):
            return candidate
    return "/proc/self/exe"


STUB_PROGRAM = _choose_stub()


def park(pid: int, registers: Registers) -> bool:
    """Redirect a stopped ``execve`` at the stub and catch the process after it.

    ``registers`` must be the tracee's state at the ``execve`` stop.  On success
    the process is left at a syscall entry stop, ready to be turned into an
    ``exit_group``.

    Returns ``False`` when the stand-in could not be established.  If that
    happens before the exec is released the process simply stays where it was,
    and spawning stays synchronous; if it happens after, the process is killed,
    because a stub allowed to run would exit zero and the agent would read that
    as a command that succeeded.
    """
    address = _plant_stub_path(pid, registers)
    if address is None:
        log.debug("pid %d: no scratch space for the stub path", pid)
        return False
    try:
        if registers.syscall_number == NR.EXECVE:
            registers.set_arg(0, address)
        else:  # execveat(dirfd, path, ...)
            registers.set_arg(0, _AT_FDCWD)
            registers.set_arg(1, address)
        ptrace.setregs(pid, registers)
        ptrace.cont(pid)
        if _await_exec_event(pid) and _step_to_syscall_entry(pid):
            return True
    except OSError as exc:
        log.debug("pid %d: could not be parked: %s", pid, exc)
    log.warning("pid %d: lost control of the stand-in; failing the command", pid)
    with contextlib.suppress(OSError):
        os.kill(pid, signal.SIGKILL)
    return False


def _plant_stub_path(pid: int, registers: Registers) -> int | None:
    """Write the stub's path into the tracee's stack red zone, and verify it."""
    blob = STUB_PROGRAM.encode() + b"\0"
    address = registers.stack_pointer - _RED_ZONE_OFFSET
    try:
        procfs.write_bytes(pid, address, blob)
        if procfs.read_bytes(pid, address, len(blob)) != blob:
            return None
    except OSError:
        return None
    return address


def _await_exec_event(pid: int) -> bool:
    _, status = os.waitpid(pid, ptrace.WALL)
    return os.WIFSTOPPED(status) and (status >> 16) == ptrace.EVENT_EXEC


def _step_to_syscall_entry(pid: int) -> bool:
    """Leave the tracee where a syscall number can still be rewritten.

    Syscall stops come in entry/exit pairs, and an exec event can leave the
    completing ``execve``'s exit stop still pending, so stepping once is not
    enough.  On entry the kernel parks ``-ENOSYS`` in the result register,
    which identifies the stop exactly.
    """
    for _ in range(_MAX_STEPS_TO_ENTRY):
        if not _step(pid):
            return False
        if ptrace.getregs(pid).result == -errno.ENOSYS:
            return True
    return False


def _step(pid: int) -> bool:
    """Resume to the tracee's next syscall stop and confirm it got there."""
    ptrace.syscall(pid)
    _, status = os.waitpid(pid, ptrace.WALL)
    if not os.WIFSTOPPED(status):
        return False
    stop_signal, event = os.WSTOPSIG(status), status >> 16
    if stop_signal == (signal.SIGTRAP | ptrace.SYSCALL_STOP_SIG):
        return True
    return stop_signal == signal.SIGTRAP and event == ptrace.EVENT_SECCOMP
