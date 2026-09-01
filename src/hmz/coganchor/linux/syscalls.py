"""Syscall numbers and register layout for the host architecture.

coganchor only needs to *recognise* a small, cold set of syscalls: the ones
that name a path, spawn a process or open a socket.  Hot syscalls (``read``,
``write``, ``mmap``, ``futex``, ``getdents64``) are deliberately absent from
the seccomp filter and therefore run at native speed.

x86-64 and aarch64 are implemented, and they differ by more than a table of
numbers: aarch64 keeps the syscall number in a register that is not part of the
register set ptrace hands over, has no red zone below the stack pointer, spells
``O_DIRECTORY`` differently, and has no ``open``, ``stat`` or ``readlink`` at
all -- only the ``*at`` forms.  Each of those is written down here, once, as a
fact about an architecture rather than as a branch at the point of use.

Rather than ship an untested register map, any other architecture fails loudly
at start-up, and says what to do instead.
"""

from __future__ import annotations

import itertools
import platform
import sys
from dataclasses import dataclass, fields

__all__ = [
    "ARCH",
    "NR",
    "SUPPORTED_MACHINES",
    "TRAPPED_SYSCALLS",
    "Arch",
    "syscall_name",
]

#: Numbers no syscall can have, handed out one apiece to the calls an architecture does not
#: implement.  Distinct rather than shared, so that the tables :mod:`hmz.coganchor.handlers`
#: keys by syscall number get one dead entry per missing call instead of several calls
#: colliding on a single key and the last one quietly replacing the rest.  Well below -1,
#: which is the number a cancelled syscall is renumbered to: a table keyed by these must not
#: have an entry that a skipped call would be looked up under.
_ABSENT = itertools.count(-1000, -1)


def _absent() -> int:
    """A number for a syscall this architecture does not have.

    Returns:
      A negative number of its own, which no trap can ever carry: a seccomp filter reports
      the number the process asked for, and that is never below zero.
    """
    return next(_ABSENT)


@dataclass(frozen=True, slots=True)
class Numbers:
    """The syscall numbers of one architecture, under the names the supervisor uses.

    A call the architecture does not have is given a number from :func:`_absent` rather than
    left out, so that every table keyed by these is written the same way on both and a
    missing call is unreachable rather than an attribute that is not there.  aarch64 is the
    architecture that makes this necessary: the generic table it uses has no ``open``,
    ``stat``, ``lstat``, ``access``, ``readlink``, ``mkdir``, ``rmdir``, ``unlink``,
    ``rename``, ``symlink``, ``link``, ``chmod``, ``creat`` or ``utimes``, because libc
    reaches every one of them through the ``*at`` form instead.
    """

    # Process execution.
    EXECVE: int
    EXECVEAT: int
    EXIT_GROUP: int

    # Opening files.
    OPEN: int
    OPENAT: int
    OPENAT2: int
    CREAT: int

    # Metadata lookups (trapped so the shadow tree can materialise lazily).
    STAT: int
    LSTAT: int
    NEWFSTATAT: int
    STATX: int
    ACCESS: int
    FACCESSAT: int
    FACCESSAT2: int
    READLINK: int
    READLINKAT: int
    CHDIR: int

    # Mutations, replayed on the target.
    MKDIR: int
    MKDIRAT: int
    RMDIR: int
    UNLINK: int
    UNLINKAT: int
    RENAME: int
    RENAMEAT: int
    RENAMEAT2: int
    SYMLINK: int
    SYMLINKAT: int
    LINK: int
    LINKAT: int
    CHMOD: int
    FCHMODAT: int
    TRUNCATE: int
    UTIMENSAT: int
    UTIMES: int

    # Networking.
    CONNECT: int

    # Helpers invoked by the supervisor itself.
    SECCOMP: int
    PIDFD_OPEN: int
    PIDFD_GETFD: int
    PROCESS_VM_READV: int
    PROCESS_VM_WRITEV: int

    def trapped(self) -> frozenset[int]:
        """The numbers the seccomp filter must trap, less the calls this host has not got."""
        return frozenset(
            number
            for number in (
                self.EXECVE,
                self.EXECVEAT,
                self.OPEN,
                self.OPENAT,
                self.OPENAT2,
                self.CREAT,
                self.STAT,
                self.LSTAT,
                self.NEWFSTATAT,
                self.STATX,
                self.ACCESS,
                self.FACCESSAT,
                self.FACCESSAT2,
                self.READLINK,
                self.READLINKAT,
                self.CHDIR,
                self.MKDIR,
                self.MKDIRAT,
                self.RMDIR,
                self.UNLINK,
                self.UNLINKAT,
                self.RENAME,
                self.RENAMEAT,
                self.RENAMEAT2,
                self.SYMLINK,
                self.SYMLINKAT,
                self.LINK,
                self.LINKAT,
                self.CHMOD,
                self.FCHMODAT,
                self.TRUNCATE,
                self.UTIMENSAT,
                self.UTIMES,
                self.CONNECT,
            )
            if number >= 0
        )


#: x86-64's own table, from <asm/unistd_64.h>.
X86_64_NUMBERS = Numbers(
    EXECVE=59,
    EXECVEAT=322,
    EXIT_GROUP=231,
    OPEN=2,
    OPENAT=257,
    OPENAT2=437,
    CREAT=85,
    STAT=4,
    LSTAT=6,
    NEWFSTATAT=262,
    STATX=332,
    ACCESS=21,
    FACCESSAT=269,
    FACCESSAT2=439,
    READLINK=89,
    READLINKAT=267,
    CHDIR=80,
    MKDIR=83,
    MKDIRAT=258,
    RMDIR=84,
    UNLINK=87,
    UNLINKAT=263,
    RENAME=82,
    RENAMEAT=264,
    RENAMEAT2=316,
    SYMLINK=88,
    SYMLINKAT=266,
    LINK=86,
    LINKAT=265,
    CHMOD=90,
    FCHMODAT=268,
    TRUNCATE=76,
    UTIMENSAT=280,
    UTIMES=235,
    CONNECT=42,
    SECCOMP=317,
    PIDFD_OPEN=434,
    PIDFD_GETFD=438,
    PROCESS_VM_READV=310,
    PROCESS_VM_WRITEV=311,
)

#: aarch64's table, which is the generic one in <asm-generic/unistd.h> -- the same header
#: this machine has, so `tests/coganchor/test_architectures.py` checks every number below
#: against it rather than against this comment.  The fourteen calls spelled `_absent()` are
#: not in that header at all: a 64-bit architecture added after the ``*at`` calls existed
#: gets only the ``*at`` calls, and libc synthesises the rest.
AARCH64_NUMBERS = Numbers(
    EXECVE=221,
    EXECVEAT=281,
    EXIT_GROUP=94,
    OPEN=_absent(),
    OPENAT=56,
    OPENAT2=437,
    CREAT=_absent(),
    STAT=_absent(),
    LSTAT=_absent(),
    NEWFSTATAT=79,
    STATX=291,
    ACCESS=_absent(),
    FACCESSAT=48,
    FACCESSAT2=439,
    READLINK=_absent(),
    READLINKAT=78,
    CHDIR=49,
    MKDIR=_absent(),
    MKDIRAT=34,
    RMDIR=_absent(),
    UNLINK=_absent(),
    UNLINKAT=35,
    RENAME=_absent(),
    RENAMEAT=38,
    RENAMEAT2=276,
    SYMLINK=_absent(),
    SYMLINKAT=36,
    LINK=_absent(),
    LINKAT=37,
    CHMOD=_absent(),
    FCHMODAT=53,
    TRUNCATE=45,
    UTIMENSAT=88,
    UTIMES=_absent(),
    CONNECT=203,
    SECCOMP=277,
    PIDFD_OPEN=434,
    PIDFD_GETFD=438,
    PROCESS_VM_READV=270,
    PROCESS_VM_WRITEV=271,
)


@dataclass(frozen=True, slots=True)
class Arch:
    """What a supervisor must know that differs from one architecture to the next.

    The register map first -- which word of the set ptrace hands over holds what -- and then
    the handful of ABI facts that decide where a rewritten path may be written and what the
    flags a syscall carries mean.
    """

    name: str
    #: What ``seccomp_data.arch`` reads as here, which the filter compares against so that a
    #: 32-bit entry point is let through rather than read with the wrong table.
    audit_arch: int
    #: Index into the register set of the syscall number as seen on entry.
    number_index: int
    #: The ptrace regset that *changes* the syscall number, for an architecture where
    #: writing :attr:`number_index` back would not: aarch64 latches the number out of ``x8``
    #: before the tracer ever sees the stop, so cancelling or replacing a syscall there
    #: means ``NT_ARM_SYSTEM_CALL``.  ``None`` where the register itself is the number,
    #: which is x86-64's ``orig_rax``.
    number_regset: int | None
    #: Index of the register holding the syscall return value.
    result_index: int
    #: Indices of the six syscall argument registers, in order.
    arg_indices: tuple[int, int, int, int, int, int]
    #: Index of the stack pointer, below which scratch space is found.
    stack_index: int
    #: Number of ``unsigned long`` words in the register set ``NT_PRSTATUS`` carries.
    register_count: int
    #: Bytes below the stack pointer a leaf function of the tracee may be using this moment,
    #: which a planted path must stay clear of.  x86-64 reserves 128; the aarch64 procedure
    #: call standard has no red zone at all, so there is nothing to skip.
    red_zone: int
    #: Whether the kernel parks ``-ENOSYS`` in the result register at every syscall-entry
    #: stop, which is what identifies one where ``PTRACE_GET_SYSCALL_INFO`` is not available.
    #: x86-64 does; aarch64 does it only for a process that really called ``syscall(-1)``,
    #: and leaves the first argument sitting in ``x0`` otherwise.
    entry_plants_enosys: bool
    #: ``O_DIRECTORY``, which is *not* the same number on both: aarch64 redefines it, along
    #: with ``O_NOFOLLOW``, ``O_DIRECT`` and ``O_LARGEFILE``, to match what AArch32 uses.
    o_directory: int
    #: The syscall numbers of this architecture.
    numbers: Numbers


# Field order of x86-64 ``struct user_regs_struct`` (see <sys/user.h>).
_X86_64_FIELDS = [
    "r15", "r14", "r13", "r12", "rbp", "rbx", "r11", "r10", "r9", "r8",
    "rax", "rcx", "rdx", "rsi", "rdi", "orig_rax", "rip", "cs", "eflags",
    "rsp", "ss", "fs_base", "gs_base", "ds", "es", "fs", "gs",
]  # fmt: skip
_X86_64_INDEX = {name: index for index, name in enumerate(_X86_64_FIELDS)}

# Field order of aarch64 ``struct user_pt_regs`` (see <asm/ptrace.h>): the thirty-one
# general-purpose registers, then the stack pointer, the program counter and the processor
# state.  Thirty-four words, against x86-64's twenty-seven -- which is why the count is a
# fact about the architecture and not a constant anywhere.
_AARCH64_FIELDS = [*(f"x{index}" for index in range(31)), "sp", "pc", "pstate"]
_AARCH64_INDEX = {name: index for index, name in enumerate(_AARCH64_FIELDS)}

#: ``NT_ARM_SYSTEM_CALL`` from <linux/elf.h>: a one-``int`` regset that is the only way to
#: change which syscall an aarch64 tracee is about to make.
NT_ARM_SYSTEM_CALL = 0x404

X86_64 = Arch(
    name="x86_64",
    audit_arch=0xC000003E,  # AUDIT_ARCH_X86_64
    number_index=_X86_64_INDEX["orig_rax"],
    number_regset=None,
    result_index=_X86_64_INDEX["rax"],
    arg_indices=tuple(  # pyright: ignore[reportArgumentType]
        _X86_64_INDEX[name] for name in ("rdi", "rsi", "rdx", "r10", "r8", "r9")
    ),
    stack_index=_X86_64_INDEX["rsp"],
    register_count=len(_X86_64_FIELDS),
    red_zone=128,
    entry_plants_enosys=True,
    o_directory=0o200000,
    numbers=X86_64_NUMBERS,
)

AARCH64 = Arch(
    name="aarch64",
    audit_arch=0xC00000B7,  # AUDIT_ARCH_AARCH64
    # The number is in ``x8``, which the register set carries but the kernel has already
    # read by the time the stop is reported -- so this index reads it and cannot write it.
    number_index=_AARCH64_INDEX["x8"],
    number_regset=NT_ARM_SYSTEM_CALL,
    result_index=_AARCH64_INDEX["x0"],
    arg_indices=tuple(  # pyright: ignore[reportArgumentType]
        _AARCH64_INDEX[f"x{index}"] for index in range(6)
    ),
    stack_index=_AARCH64_INDEX["sp"],
    register_count=len(_AARCH64_FIELDS),
    red_zone=0,
    entry_plants_enosys=False,
    o_directory=0o40000,
    numbers=AARCH64_NUMBERS,
)

#: Every architecture there is a register map for, by the name :func:`platform.machine`
#: gives it.  Big-endian aarch64 reports ``aarch64_be`` and is deliberately not here: every
#: structure read out of a tracee below is decoded little-endian.
SUPPORTED_MACHINES: dict[str, Arch] = {"x86_64": X86_64, "aarch64": AARCH64}

#: Said by both refusals below: a diagnostic that only names what is missing leaves the
#: reader to guess, and the first thing worth knowing is that not every way of anchoring
#: needs any of this.
_UNAFFECTED = (
    "An anchor mode that does not intercept syscalls needs no register map and is "
    "unaffected, and so is serving a target from here."
)

#: What to do about a host that is not Linux, which is in practice a Mac.  Deliberately not
#: Firecracker: it is a Linux hypervisor, so naming it here would be sending somebody whose
#: whole problem is that they are not on Linux to fetch something that only runs on it.
_GET_A_LINUX = (
    "To intercept them, run the agent inside a Linux virtual machine -- Docker Desktop, "
    "colima and lima each give you one, on Intel Macs and on Apple silicon alike."
)

#: And what to do about a Linux host of an architecture there is no map for, which is not
#: the same advice at all: a virtual machine on a riscv64 host is a riscv64 machine, and
#: would be refused by this same line.  What is worth saying instead is that only *this*
#: end is restricted.
_ANCHOR_FROM_ELSEWHERE = (
    "Only the machine the agent runs on is restricted; the target may be any architecture, "
    "so this machine can still be anchored to from one of those."
)


def _detect() -> Arch:
    """The architecture this host is, or a refusal that says where else to run.

    Returns:
      The register map and ABI facts for this machine.

    Raises:
      RuntimeError: If the supervisor cannot run here at all -- because the platform is not
        Linux, or because the architecture has no register map written for it.
    """
    if sys.platform != "linux":
        raise RuntimeError(
            "humanize intercepts syscalls with a Linux seccomp filter and a ptrace "
            f"supervisor, and this host is {sys.platform!r}. {_UNAFFECTED} {_GET_A_LINUX}"
        )
    machine = platform.machine()
    arch = SUPPORTED_MACHINES.get(machine)
    if arch is None:
        supported = ", ".join(sorted(SUPPORTED_MACHINES))
        raise RuntimeError(
            f"humanize has a register map for {supported}; this host reports {machine!r}, "
            f"and interception needs an architecture-specific one. {_UNAFFECTED} "
            f"{_ANCHOR_FROM_ELSEWHERE}"
        )
    return arch


ARCH = _detect()

#: This architecture's syscall numbers, which is what everything above here names them by.
NR = ARCH.numbers

#: The complete seccomp trap set.  Everything else runs untouched.
TRAPPED_SYSCALLS: frozenset[int] = NR.trapped()

_NAMES = {
    number: field.name.lower()
    for field in fields(NR)
    if (number := getattr(NR, field.name)) >= 0
}


def syscall_name(number: int) -> str:
    """Human-readable name for a syscall number, for logs and errors."""
    return _NAMES.get(number, f"syscall_{number}")
