"""A minimal, typed ``ptrace(2)`` binding built on :mod:`ctypes`.

The supervisor needs four capabilities from ptrace:

* stop a tracee when the seccomp filter fires,
* read and rewrite its registers,
* cancel a syscall and substitute a return value,
* replace a syscall outright (``execve`` becomes ``exit_group``).

Everything goes through ``PTRACE_GETREGSET``/``PTRACE_SETREGSET``, which is the only form
aarch64 has -- ``PTRACE_GETREGS`` does not exist there at all -- and which x86-64 supports
just as well.  Changing *which* syscall a tracee makes is the one thing the register set
cannot always do: see :attr:`~hmz.coganchor.linux.syscalls.Arch.number_regset`.

Everything here is synchronous and must be called from the thread that
attached to the tracee -- the kernel enforces that.
"""

from __future__ import annotations

import ctypes
import errno
import os
from typing import Final

from hmz.coganchor.linux.syscalls import ARCH

__all__ = [
    "EVENT_CLONE",
    "EVENT_EXEC",
    "EVENT_FORK",
    "EVENT_SECCOMP",
    "EVENT_VFORK",
    "OPTIONS",
    "SYSCALL_STOP_ENTRY",
    "SYSCALL_STOP_EXIT",
    "SYSCALL_STOP_SECCOMP",
    "SYSCALL_STOP_SIG",
    "WALL",
    "Registers",
    "blank",
    "cont",
    "get_event_message",
    "getregs",
    "setoptions",
    "setregs",
    "syscall",
    "syscall_stop_kind",
    "traceme",
]

_libc = ctypes.CDLL("libc.so.6", use_errno=True)
_libc.ptrace.restype = ctypes.c_long
_libc.ptrace.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p]

# Requests.
_TRACEME: Final = 0
_CONT: Final = 7
_SYSCALL: Final = 24
_SETOPTIONS: Final = 0x4200
_GETEVENTMSG: Final = 0x4201
_GETREGSET: Final = 0x4204
_SETREGSET: Final = 0x4205
_GET_SYSCALL_INFO: Final = 0x420E

_NT_PRSTATUS: Final = 1

#: ``PTRACE_SYSCALL_INFO_*``: which half of a syscall a stop is at, as the kernel itself
#: reports it.  The alternative -- reading the result register and looking for ``-ENOSYS``
#: -- only works where the kernel plants one, which aarch64 does not.
SYSCALL_STOP_ENTRY: Final = 1
SYSCALL_STOP_EXIT: Final = 2
SYSCALL_STOP_SECCOMP: Final = 3

# ``PTRACE_EVENT_*`` codes, delivered in the high bits of a wait status.
# Events the supervisor does not name (exec, exit, vfork-done) are resumed
# generically, so only these are spelled out.
EVENT_FORK: Final = 1
EVENT_VFORK: Final = 2
EVENT_CLONE: Final = 3
EVENT_EXEC: Final = 4
EVENT_SECCOMP: Final = 7

#: Options installed on every tracee: follow the whole process tree, report
#: seccomp traps, distinguish group-stops, and kill everything if we die.
OPTIONS: Final = (
    0x00000001  # TRACESYSGOOD
    | 0x00000002  # TRACEFORK
    | 0x00000004  # TRACEVFORK
    | 0x00000008  # TRACECLONE
    | 0x00000010  # TRACEEXEC
    | 0x00000080  # TRACESECCOMP
    | 0x00100000  # EXITKILL
)

#: Bit set in ``WSTOPSIG`` for syscall stops when ``TRACESYSGOOD`` is enabled.
SYSCALL_STOP_SIG: Final = 0x80

#: ``__WALL``: wait for clone children whose exit signal is not SIGCHLD.
WALL: Final = 0x40000000


class _Iovec(ctypes.Structure):
    _fields_ = [("base", ctypes.c_void_p), ("len", ctypes.c_size_t)]


def _ptrace(request: int, pid: int, addr: int, data: int) -> int:
    ctypes.set_errno(0)
    # The addresses as the numbers they are: ctypes converts an integer to a `void *`
    # argument itself, and a supervisor stopping tens of thousands of times a session would
    # otherwise build two pointer objects at every one of them and drop both.
    result = _libc.ptrace(request, pid, addr, data)
    if result == -1:
        code = ctypes.get_errno()
        if code:
            raise OSError(
                code, os.strerror(code), f"ptrace request {request} on pid {pid}"
            )
    return int(result)


class Registers:
    """Mutable view over the general-purpose registers ``NT_PRSTATUS`` carries."""

    __slots__ = (
        "_buffer",
        "_dirty",
        "_number",
        "_number_box",
        "_number_vector",
        "_vector",
    )

    def __init__(self, buffer: ctypes.Array[ctypes.c_ulonglong]) -> None:
        self._buffer = buffer
        self._dirty = False
        # The iovec the kernel is handed to fill this in and to read it back out, made once
        # and held beside what it points at: it holds the address as a number rather than a
        # reference, so a vector that outlived its buffer would name freed memory. Held here
        # so a tracer reading a register set per stop is not building one per stop too.
        self._vector = _Iovec(ctypes.addressof(buffer), ctypes.sizeof(buffer))
        # And the one-`int` regset that renumbers a syscall where the register it was read
        # out of cannot, with its own vector for the same reason. Built whatever the
        # architecture, since it is one word per tracer rather than one per stop, and left
        # untouched where `Arch.number_regset` is None.
        self._number: int | None = None
        self._number_box = ctypes.c_int()
        self._number_vector = _Iovec(
            ctypes.addressof(self._number_box), ctypes.sizeof(self._number_box)
        )

    @property
    def dirty(self) -> bool:
        return self._dirty

    @property
    def buffer(self) -> ctypes.Array[ctypes.c_ulonglong]:
        return self._buffer

    @property
    def vector(self) -> int:
        """Where the iovec naming this register set is, for a ptrace call to be given."""
        return ctypes.addressof(self._vector)

    @property
    def renumbered(self) -> bool:
        """Whether this stop asked for a syscall other than the one the tracee made.

        Only ever true where the number lives outside the register set: elsewhere the number
        *is* a register, and writing the set writes it.
        """
        return self._number is not None

    @property
    def number_vector(self) -> int:
        """Where the iovec naming the replacement syscall number is."""
        return ctypes.addressof(self._number_vector)

    def settled(self) -> None:
        """Says these are the tracee's own registers again, with nothing written over them.

        Called by whatever has just read a stop's registers into a set that has been used
        before: what `dirty` answers is whether this stop wrote anything, and a set carried
        from the last stop would answer for that one.
        """
        self._dirty = False
        self._number = None

    @property
    def syscall_number(self) -> int:
        if self._number is not None:
            return self._number
        return self._buffer[ARCH.number_index]

    @syscall_number.setter
    def syscall_number(self, value: int) -> None:
        self._dirty = True
        if ARCH.number_regset is None:
            self._buffer[ARCH.number_index] = _as_unsigned(value)
            return
        # The register this was read out of is not the one the kernel will act on -- aarch64
        # has already taken the number out of `x8` by the time the stop is reported -- so
        # writing it back would change nothing and lie to whoever read it again. The value
        # is held here instead, and `setregs` writes it through the regset that does act.
        # Held as the register would have held it, so that reading a number back answers the
        # same on both architectures rather than -1 here and its unsigned self there.
        self._number = _as_unsigned(value)
        self._number_box.value = _as_signed_int(value)

    @property
    def result(self) -> int:
        return _as_signed(self._buffer[ARCH.result_index])

    @result.setter
    def result(self, value: int) -> None:
        self._buffer[ARCH.result_index] = _as_unsigned(value)
        self._dirty = True

    @property
    def stack_pointer(self) -> int:
        """Where the tracee's stack is, below which scratch space is found."""
        return self._buffer[ARCH.stack_index]

    def scratch(self, size: int) -> int:
        """Where `size` bytes may be written in the tracee, for a path it is to be given.

        Below the stack pointer, clear of whatever red zone the architecture reserves for a
        leaf function that may be using it this moment -- 128 bytes on x86-64, and none at
        all under the aarch64 procedure call standard, which is why the offset is a fact
        about the architecture rather than a constant at the point of use. Only as many
        bytes as are being written are skipped: a thread with a stack of its own may have
        very little left, and a fixed few kilobytes would be written past the end of it.

        Neither architecture promises the bytes survive a signal arriving in the meantime --
        the kernel builds its signal frame below the stack pointer too -- but the tracee runs
        no instruction between the write and the kernel's read of it, so the window is one
        syscall wide.

        Args:
          size: How many bytes are to be written, including the terminator.

        Returns:
          The address the lowest of those bytes goes at.
        """
        return self._buffer[ARCH.stack_index] - ARCH.red_zone - size

    def arg(self, index: int) -> int:
        """Return syscall argument ``index`` (0-based) as an unsigned word."""
        return self._buffer[ARCH.arg_indices[index]]

    def signed_arg(self, index: int) -> int:
        """Return syscall argument ``index`` interpreted as a signed int."""
        return _as_signed_int(self._buffer[ARCH.arg_indices[index]])

    def set_arg(self, index: int, value: int) -> None:
        self._buffer[ARCH.arg_indices[index]] = _as_unsigned(value)
        self._dirty = True


def _as_unsigned(value: int) -> int:
    return value & 0xFFFFFFFFFFFFFFFF


def _as_signed(value: int) -> int:
    value &= 0xFFFFFFFFFFFFFFFF
    return value - (1 << 64) if value >= (1 << 63) else value


def _as_signed_int(value: int) -> int:
    """Interpret the low 32 bits as a C ``int`` (used for ``dirfd`` arguments)."""
    value &= 0xFFFFFFFF
    return value - (1 << 32) if value >= (1 << 31) else value


def traceme() -> None:
    """Called in the forked child to request tracing by its parent."""
    _ptrace(_TRACEME, 0, 0, 0)


def setoptions(pid: int, options: int = OPTIONS) -> None:
    """Set what the tracer is told about, which holds until it is set again."""
    _ptrace(_SETOPTIONS, pid, 0, options)


def blank() -> Registers:
    """An empty register set of this architecture's shape, to be read into.

    For a tracer that stops tens of thousands of times a session: one set, read over at each
    stop, rather than one allocated and collected per stop. Between two stops the tracee
    runs, so what an allocation there costs is not the allocation but the cache it displaces.
    """
    return Registers((ctypes.c_ulonglong * ARCH.register_count)())


def getregs(pid: int, into: Registers | None = None) -> Registers:
    """Read the registers of a tracee that is stopped.

    Args:
      pid: The stopped tracee.
      into: A register set to read over, or None for one of its own.

    Returns:
      The registers, which are `into` itself where one was given.
    """
    registers = blank() if into is None else into
    _ptrace(_GETREGSET, pid, _NT_PRSTATUS, registers.vector)
    registers.settled()
    return registers


def setregs(pid: int, registers: Registers) -> None:
    """Write registers back, which is how a syscall is answered or redirected.

    Where the syscall number is not one of those registers, a second write carries it: on
    aarch64 that is ``NT_ARM_SYSTEM_CALL``, and without it a cancelled syscall would run
    anyway and a stand-in would never become an ``exit_group``.
    """
    _ptrace(_SETREGSET, pid, _NT_PRSTATUS, registers.vector)
    regset = ARCH.number_regset
    if regset is not None and registers.renumbered:
        _ptrace(_SETREGSET, pid, regset, registers.number_vector)


def cont(pid: int, signal: int = 0) -> None:
    """Resume until the next stop, delivering a signal on the way if one is given."""
    _ptrace(_CONT, pid, 0, signal)


def syscall(pid: int, signal: int = 0) -> None:
    """Resume until the next syscall entry or exit stop."""
    _ptrace(_SYSCALL, pid, 0, signal)


def syscall_stop_kind(pid: int) -> int | None:
    """Which half of a syscall a stopped tracee is at, as the kernel itself says.

    The alternative is to read the result register and look for the ``-ENOSYS`` the kernel
    parks there on entry, which x86-64 does and aarch64 does not -- so asking is the only
    answer that holds on both.

    Args:
      pid: The stopped tracee.

    Returns:
      One of `SYSCALL_STOP_ENTRY`, `SYSCALL_STOP_EXIT` or `SYSCALL_STOP_SECCOMP`; zero where
      this stop is not a syscall stop at all; or None where the kernel will not say, the
      request having arrived in Linux 5.3.
    """
    # Only the first word is read: it holds the op and the architecture, and the kernel
    # truncates what it copies to the size it is given.
    box = ctypes.c_uint64()
    try:
        _ptrace(_GET_SYSCALL_INFO, pid, ctypes.sizeof(box), ctypes.addressof(box))
    except OSError as why:
        if why.errno in (errno.EIO, errno.EINVAL):
            return None
        raise
    return box.value & 0xFF


def get_event_message(pid: int) -> int:
    """Return the ``PTRACE_EVENT_*`` payload, e.g. a new child's pid."""
    box = ctypes.c_ulong()
    _ptrace(_GETEVENTMSG, pid, 0, ctypes.addressof(box))
    return box.value
