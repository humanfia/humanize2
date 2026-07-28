"""Syscall numbers and register layout for the host architecture.

coganchor only needs to *recognise* a small, cold set of syscalls: the ones
that name a path, spawn a process or open a socket.  Hot syscalls (``read``,
``write``, ``mmap``, ``futex``, ``getdents64``) are deliberately absent from
the seccomp filter and therefore run at native speed.

Only x86-64 is implemented.  Rather than ship an untested register map, other
architectures fail loudly at start-up.
"""

from __future__ import annotations

import platform
from dataclasses import dataclass

__all__ = ["ARCH", "NR", "TRAPPED_SYSCALLS", "Arch", "syscall_name"]


@dataclass(frozen=True, slots=True)
class Arch:
    """Register layout needed to read and tamper with syscalls."""

    name: str
    audit_arch: int
    #: Index into ``user_regs_struct`` of the syscall number as seen on entry.
    number_index: int
    #: Index of the register holding the syscall return value.
    result_index: int
    #: Indices of the six syscall argument registers, in order.
    arg_indices: tuple[int, int, int, int, int, int]
    #: Index of the stack pointer, whose red zone is used as scratch space.
    stack_index: int
    #: Number of ``unsigned long`` words in ``user_regs_struct``.
    register_count: int


# Field order of x86-64 ``struct user_regs_struct`` (see <sys/user.h>).
_X86_64_FIELDS = [
    "r15", "r14", "r13", "r12", "rbp", "rbx", "r11", "r10", "r9", "r8",
    "rax", "rcx", "rdx", "rsi", "rdi", "orig_rax", "rip", "cs", "eflags",
    "rsp", "ss", "fs_base", "gs_base", "ds", "es", "fs", "gs",
]  # fmt: skip
_X86_64_INDEX = {name: index for index, name in enumerate(_X86_64_FIELDS)}

X86_64 = Arch(
    name="x86_64",
    audit_arch=0xC000003E,
    number_index=_X86_64_INDEX["orig_rax"],
    result_index=_X86_64_INDEX["rax"],
    arg_indices=tuple(  # pyright: ignore[reportArgumentType]
        _X86_64_INDEX[name] for name in ("rdi", "rsi", "rdx", "r10", "r8", "r9")
    ),
    stack_index=_X86_64_INDEX["rsp"],
    register_count=len(_X86_64_FIELDS),
)

_SUPPORTED = {"x86_64": X86_64}


def _detect() -> Arch:
    machine = platform.machine()
    arch = _SUPPORTED.get(machine)
    if arch is None:
        raise RuntimeError(
            f"humanize supports x86_64 only; this host reports {machine!r}. "
            "Interception needs an architecture-specific register map."
        )
    return arch


ARCH = _detect()


class NR:
    """x86-64 syscall numbers used by the supervisor."""

    # Process execution.
    EXECVE = 59
    EXECVEAT = 322
    EXIT_GROUP = 231

    # Opening files.
    OPEN = 2
    OPENAT = 257
    OPENAT2 = 437
    CREAT = 85

    # Metadata lookups (trapped so the shadow tree can materialise lazily).
    STAT = 4
    LSTAT = 6
    NEWFSTATAT = 262
    STATX = 332
    ACCESS = 21
    FACCESSAT = 269
    FACCESSAT2 = 439
    READLINK = 89
    READLINKAT = 267
    CHDIR = 80

    # Mutations, replayed on the target.
    MKDIR = 83
    MKDIRAT = 258
    RMDIR = 84
    UNLINK = 87
    UNLINKAT = 263
    RENAME = 82
    RENAMEAT = 264
    RENAMEAT2 = 316
    SYMLINK = 88
    SYMLINKAT = 266
    LINK = 86
    LINKAT = 265
    CHMOD = 90
    FCHMODAT = 268
    TRUNCATE = 76
    UTIMENSAT = 280
    UTIMES = 235

    # Networking.
    CONNECT = 42

    # Helpers invoked by the supervisor itself.
    SECCOMP = 317
    PIDFD_OPEN = 434
    PIDFD_GETFD = 438
    PROCESS_VM_READV = 310
    PROCESS_VM_WRITEV = 311


#: The complete seccomp trap set.  Everything else runs untouched.
TRAPPED_SYSCALLS: frozenset[int] = frozenset(
    {
        NR.EXECVE,
        NR.EXECVEAT,
        NR.OPEN,
        NR.OPENAT,
        NR.OPENAT2,
        NR.CREAT,
        NR.STAT,
        NR.LSTAT,
        NR.NEWFSTATAT,
        NR.STATX,
        NR.ACCESS,
        NR.FACCESSAT,
        NR.FACCESSAT2,
        NR.READLINK,
        NR.READLINKAT,
        NR.CHDIR,
        NR.MKDIR,
        NR.MKDIRAT,
        NR.RMDIR,
        NR.UNLINK,
        NR.UNLINKAT,
        NR.RENAME,
        NR.RENAMEAT,
        NR.RENAMEAT2,
        NR.SYMLINK,
        NR.SYMLINKAT,
        NR.LINK,
        NR.LINKAT,
        NR.CHMOD,
        NR.FCHMODAT,
        NR.TRUNCATE,
        NR.UTIMENSAT,
        NR.UTIMES,
        NR.CONNECT,
    }
)

_NAMES = {
    value: name.lower()
    for name, value in vars(NR).items()
    if not name.startswith("_") and isinstance(value, int)
}


def syscall_name(number: int) -> str:
    """Human-readable name for a syscall number, for logs and errors."""
    return _NAMES.get(number, f"syscall_{number}")
