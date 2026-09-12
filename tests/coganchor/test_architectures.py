"""The architecture maps, checked against the kernel's own headers and against themselves.

A register map is the one thing in coganchor that cannot be wrong quietly. Every other
mistake shows up as a failed syscall; a wrong index reads somebody else's register and
rewrites the tracee with it, and the first sign of that is a process behaving in a way that
has nothing to do with the code that caused it. So the aarch64 map is not asked to be
believed: the syscall numbers are read out of `<asm-generic/unistd.h>`, which is the table
aarch64 uses and which this machine has a copy of whatever this machine is; the audit
architecture is computed from `<linux/elf-em.h>` the way `<linux/audit.h>` computes it; and
`NT_ARM_SYSTEM_CALL` is read out of `<linux/elf.h>`. The x86-64 map is checked the same way,
field by field, against `<sys/user.h>` and `<asm/unistd_64.h>`.

Two things live in an `asm/` header a machine only has if it is that machine, or has had the
cross headers installed: the shape of `struct user_pt_regs`, and the `O_DIRECTORY` aarch64
takes from AArch32 rather than from the generic header. Both are checked against those
headers where they are here and skipped where they are not, and both are checked for internal
consistency either way -- that the indices are distinct, in range, and name the registers the
map claims -- so a transcription slip fails here rather than in a tracee.

A header may be absent: a container with no `linux-libc-dev` has none of them. Each check
that needs one skips aloud rather than passing on nothing.
"""

from __future__ import annotations

import platform
import re
import struct
from pathlib import Path

import pytest

from tests.supervising import SUPPORTED_MACHINES, WITHOUT_BINDINGS

if (
    WITHOUT_BINDINGS
):  # what is imported below is the binding itself, so it is asked first
    pytest.skip(WITHOUT_BINDINGS, allow_module_level=True)

from hmz.coganchor import handlers, standin
from hmz.coganchor.linux import ptrace, seccomp
from hmz.coganchor.linux.syscalls import (
    AARCH64,
    AARCH64_NUMBERS,
    ARCH,
    NR,
    NT_ARM_SYSTEM_CALL,
    X86_64,
    X86_64_NUMBERS,
    Arch,
    Numbers,
)
from hmz.coganchor.linux.syscalls import SUPPORTED_MACHINES as MAPPED

#: The generic syscall table, which is aarch64's own: a 64-bit architecture added after the
#: `*at` calls existed gets `<asm-generic/unistd.h>` and nothing else.
GENERIC_UNISTD = Path("/usr/include/asm-generic/unistd.h")

#: x86-64's, which is not generic at all -- it is the table every other one was numbered
#: against, and it kept the calls the generic one dropped.
X86_64_UNISTD = Path("/usr/include/x86_64-linux-gnu/asm/unistd_64.h")

#: Where the `user_regs_struct` this machine's map indexes into is declared.
X86_64_USER = Path("/usr/include/x86_64-linux-gnu/sys/user.h")

#: The ELF machine numbers an audit architecture is built out of, and the note types a
#: register set is named by.
ELF_EM = Path("/usr/include/linux/elf-em.h")
ELF = Path("/usr/include/linux/elf.h")

#: aarch64's own headers, where this is an aarch64 machine or one with the cross headers
#: installed. The multiarch spelling is the one that can only ever be aarch64's; the plain
#: one is read as well on an aarch64 machine, where a distribution that does not lay its
#: headers out by architecture has only that.
AARCH64_ASM = [Path("/usr/include/aarch64-linux-gnu/asm")]
if platform.machine() == "aarch64":
    AARCH64_ASM.append(Path("/usr/include/asm"))

#: What `<linux/audit.h>` ors an `EM_*` with for a little-endian 64-bit architecture.
AUDIT_64BIT_LE = 0x80000000 | 0x40000000

#: The two architectures, so that a check written once is made of both.
MAPS = {"x86_64": X86_64, "aarch64": AARCH64}


def _read(header: Path) -> str:
    """The text of a kernel header, or a skip saying which one is not installed."""
    try:
        return header.read_text(encoding="utf-8")
    except OSError:
        pytest.skip(f"{header} is not installed here")


def _read_aarch64(name: str) -> str:
    """The text of one of aarch64's own headers, or a skip saying it is not here.

    Args:
      name: The file inside `asm/`, such as "ptrace.h".

    Returns:
      Its text, from whichever spelling of the directory this machine has.
    """
    for folder in AARCH64_ASM:
        try:
            return (folder / name).read_text(encoding="utf-8")
        except OSError:
            continue
    pytest.skip(f"aarch64's own asm/{name} is not installed here")


def _defines(text: str, pattern: str) -> dict[str, int]:
    """Every `#define NAME <number>` in a header, as the numbers they are."""
    return {
        name: int(value, 0)
        for name, value in re.findall(pattern, text, flags=re.MULTILINE)
    }


def generic_syscalls() -> dict[str, int]:
    """The syscall numbers `<asm-generic/unistd.h>` gives a 64-bit architecture.

    The header names some calls twice -- `__NR_truncate` is whichever of a 32-bit and a
    64-bit `__NR3264_truncate` applies -- so the aliases are followed. An alias whose target
    was never defined is a call the architecture has not got: `__NR3264_stat` is defined by
    nobody, which is why there is no `stat` on aarch64.

    Two of the calls below sit behind `__ARCH_WANT_RENAMEAT` and `__ARCH_WANT_NEW_STAT`, and
    are taken here because arm64's own `asm/unistd.h` defines both before including this one
    -- a table frozen before `renameat2` existed keeps the `renameat` it shipped with. That
    is read off arm64's header rather than assumed, and
    `test_the_aarch64_register_set_is_what_its_own_ptrace_header_declares` is where that
    header is checked directly on a machine that has it.

    Returns:
      Every call in the table, by the name without its `__NR_` prefix.
    """
    text = _read(GENERIC_UNISTD)
    direct = _defines(text, r"^#define (__NR(?:3264)?_\w+)\s+(\d+)\s*$")
    aliases = dict(
        re.findall(r"^#define (__NR_\w+)\s+(__NR3264_\w+)\s*$", text, re.MULTILINE)
    )
    numbers = {
        name: value for name, value in direct.items() if name.startswith("__NR_")
    }
    for name, target in aliases.items():
        if target in direct:
            numbers[name] = direct[target]
    return {name.removeprefix("__NR_"): value for name, value in numbers.items()}


def x86_64_syscalls() -> dict[str, int]:
    """The syscall numbers `<asm/unistd_64.h>` gives this machine."""
    text = _read(X86_64_UNISTD)
    return {
        name.removeprefix("__NR_"): value
        for name, value in _defines(text, r"^#define (__NR_\w+)\s+(\d+)\s*$").items()
    }


def audit_arch(machine: str) -> int:
    """`AUDIT_ARCH_*` for a little-endian 64-bit architecture, built as `<linux/audit.h>` does."""
    text = _read(ELF_EM)
    elf_machines = _defines(text, r"^#define (EM_\w+)\s+(\d+)\b")
    name = {"x86_64": "EM_X86_64", "aarch64": "EM_AARCH64"}[machine]
    return elf_machines[name] | AUDIT_64BIT_LE


def test_every_aarch64_syscall_number_is_the_one_the_generic_table_gives_it() -> None:
    """The table aarch64 uses is a header this machine has, whatever this machine is."""
    table = generic_syscalls()
    named = {
        field.name: getattr(AARCH64_NUMBERS, field.name)
        for field in AARCH64_NUMBERS.__dataclass_fields__.values()
    }
    assert {name: number for name, number in named.items() if number >= 0} == {
        name: table[name.lower()] for name in named if name.lower() in table
    }


def test_the_calls_aarch64_is_said_not_to_have_are_absent_from_that_table() -> None:
    """Fourteen calls, and each one missing because libc reaches it through the `*at` form."""
    table = generic_syscalls()
    missing = {
        field.name.lower()
        for field in AARCH64_NUMBERS.__dataclass_fields__.values()
        if getattr(AARCH64_NUMBERS, field.name) < 0
    }

    assert missing == {
        "open", "creat", "stat", "lstat", "access", "readlink", "mkdir", "rmdir",
        "unlink", "rename", "symlink", "link", "chmod", "utimes",
    }  # fmt: skip
    assert not missing & set(table)


def test_every_x86_64_syscall_number_is_the_one_this_machine_s_own_header_gives_it() -> (
    None
):
    """The architecture the suite runs on, checked the same way and not merely preserved."""
    table = x86_64_syscalls()
    for field in X86_64_NUMBERS.__dataclass_fields__.values():
        number = getattr(X86_64_NUMBERS, field.name)
        assert number == table[field.name.lower()], field.name


def test_x86_64_has_every_call_the_supervisor_knows_a_name_for() -> None:
    """Which is why it is the architecture where a missing call was never a question."""
    assert all(
        getattr(X86_64_NUMBERS, field.name) >= 0
        for field in X86_64_NUMBERS.__dataclass_fields__.values()
    )


def test_a_call_an_architecture_has_not_got_is_given_a_number_nothing_can_trap_into() -> (
    None
):
    """Distinct and negative: a seccomp trap carries the number asked for, never below zero."""
    absent = [
        getattr(AARCH64_NUMBERS, field.name)
        for field in AARCH64_NUMBERS.__dataclass_fields__.values()
        if getattr(AARCH64_NUMBERS, field.name) < 0
    ]

    assert len(set(absent)) == len(absent)
    assert AARCH64_NUMBERS.trapped().isdisjoint(absent)
    assert AARCH64_NUMBERS.trapped() == {
        number for number in AARCH64_NUMBERS.trapped() if number >= 0
    }


@pytest.mark.parametrize(
    "numbers", [X86_64_NUMBERS, AARCH64_NUMBERS], ids=["x86_64", "aarch64"]
)
def test_no_two_calls_of_one_architecture_share_a_number(numbers: Numbers) -> None:
    """Two names on one number would make a table keyed by number lose one of them."""
    found = [
        getattr(numbers, field.name) for field in numbers.__dataclass_fields__.values()
    ]

    assert len(set(found)) == len(found)


@pytest.mark.parametrize("machine", sorted(MAPS), ids=sorted(MAPS))
def test_the_audit_architecture_is_what_the_elf_machine_number_makes_it(
    machine: str,
) -> None:
    """The filter compares against this, and a wrong one lets every syscall through."""
    assert MAPS[machine].audit_arch == audit_arch(machine)


def test_the_regset_that_renumbers_an_aarch64_syscall_is_the_one_elf_h_names() -> None:
    """`PTRACE_SETREGS` does not exist on aarch64, and the number is not in `NT_PRSTATUS`."""
    notes = _defines(_read(ELF), r"^#define (NT_\w+)\s+(0x[0-9a-fA-F]+|\d+)\b")

    assert notes["NT_ARM_SYSTEM_CALL"] == NT_ARM_SYSTEM_CALL
    assert AARCH64.number_regset == notes["NT_ARM_SYSTEM_CALL"]
    assert (
        X86_64.number_regset is None
    )  # `orig_rax` is a register, and writing it is enough


def test_the_x86_64_register_indices_are_the_fields_sys_user_h_declares() -> None:
    """The map is derived from a field list, and this is that list read off the header."""
    declared = re.search(
        r"struct user_regs_struct\s*\{(.*?)\}", _read(X86_64_USER), re.DOTALL
    )
    assert declared is not None
    fields = re.findall(r"\bint\s+(\w+);", declared.group(1))

    assert len(fields) == X86_64.register_count
    assert fields.index("orig_rax") == X86_64.number_index
    assert fields.index("rax") == X86_64.result_index
    assert fields.index("rsp") == X86_64.stack_index
    assert tuple(
        fields.index(name) for name in ("rdi", "rsi", "rdx", "r10", "r8", "r9")
    ) == (X86_64.arg_indices)


def test_the_aarch64_register_set_is_thirty_one_registers_and_three_more() -> None:
    """`user_pt_regs` is `regs[31]`, `sp`, `pc`, `pstate` -- seven words longer than x86-64's."""
    assert AARCH64.register_count == 34
    assert AARCH64.arg_indices == (0, 1, 2, 3, 4, 5)  # x0-x5
    assert (
        AARCH64.result_index == 0
    )  # x0 again: the first argument is where the answer lands
    assert (
        AARCH64.number_index == 8
    )  # x8, which the kernel has already read by the stop
    assert AARCH64.stack_index == 31  # straight after the last of the thirty-one


@pytest.mark.parametrize("machine", sorted(MAPS), ids=sorted(MAPS))
def test_every_index_of_a_map_names_a_register_that_set_really_has(
    machine: str,
) -> None:
    """A index past the end reads whatever follows the buffer, which is not a register."""
    arch = MAPS[machine]
    indices = [
        arch.number_index,
        arch.result_index,
        arch.stack_index,
        *arch.arg_indices,
    ]

    assert len(arch.arg_indices) == 6
    assert all(0 <= index < arch.register_count for index in indices)


@pytest.mark.parametrize("machine", sorted(MAPS), ids=sorted(MAPS))
def test_the_arguments_the_number_and_the_stack_pointer_are_all_different_registers(
    machine: str,
) -> None:
    """Everything but the result, which shares a register with an argument on aarch64."""
    arch = MAPS[machine]
    distinct = {arch.number_index, arch.stack_index, *arch.arg_indices}

    assert len(distinct) == len(arch.arg_indices) + 2


@pytest.mark.parametrize("machine", sorted(MAPS), ids=sorted(MAPS))
def test_a_result_register_is_one_the_syscall_would_have_clobbered_anyway(
    machine: str,
) -> None:
    """x86-64 answers in `rax` and aarch64 in `x0`, and neither is the stack pointer."""
    arch = MAPS[machine]

    assert arch.result_index != arch.stack_index
    assert arch.result_index != arch.number_index or arch.number_regset is not None


def test_o_directory_is_what_aarch64_s_own_header_makes_it() -> None:
    """Skipped where those headers are not installed, which is most x86-64 machines.

    Where they are -- an aarch64 runner, or a host with the cross headers -- this is the
    whole of the claim: `asm/fcntl.h` redefines four flags before including the generic one,
    and `O_DIRECTORY` is the one read here.
    """
    # Octal the way C spells it, which is a leading zero and not `0o` -- so base eight is
    # said outright rather than left to `int(..., 0)`, which refuses the C form.
    flags = {
        name: int(value, 8)
        for name, value in re.findall(
            r"^#define (O_\w+)\s+(0[0-7]+)\b", _read_aarch64("fcntl.h"), re.MULTILINE
        )
    }

    assert AARCH64.o_directory == flags["O_DIRECTORY"]


def test_the_aarch64_register_set_is_what_its_own_ptrace_header_declares() -> None:
    """`user_pt_regs`, counted field by field, where aarch64's headers are here to count."""
    declared = re.search(
        r"struct user_pt_regs\s*\{(.*?)\}", _read_aarch64("ptrace.h"), re.DOTALL
    )
    assert declared is not None
    words = re.findall(r"\bregs\[(\d+)\]|\b(sp|pc|pstate);", declared.group(1))
    count = sum(int(size) if size else 1 for size, _ in words)

    assert count == AARCH64.register_count
    assert declared.group(1).index("sp") > declared.group(1).index("regs[")


def test_the_generic_header_lets_an_architecture_redefine_o_directory() -> None:
    """Which aarch64 does, taking AArch32's number for it, and this map follows.

    The mechanism rather than the number: the test above reads the number itself out of
    aarch64's own header, and is skipped on a machine that has not got one. This reads the
    `#ifndef` that makes an override possible at all, out of a header every machine has --
    so a kernel that stopped yielding here would be noticed wherever the suite runs.
    """
    generic = _read(Path("/usr/include/asm-generic/fcntl.h"))

    assert re.search(r"#ifndef O_DIRECTORY\s*\n#define O_DIRECTORY\s+00200000", generic)
    assert X86_64.o_directory == 0o200000
    assert AARCH64.o_directory == 0o40000
    assert ARCH.o_directory == handlers.O_DIRECTORY  # this machine's, whichever it is


def test_the_gate_the_suite_asks_before_importing_names_the_maps_that_exist() -> None:
    """Two lists that must agree, and only one of them may import the module that has both."""
    assert frozenset(MAPPED) == SUPPORTED_MACHINES
    assert {name: arch.name for name, arch in MAPPED.items()} == {
        name: name for name in MAPPED
    }


def test_scratch_space_starts_below_whatever_red_zone_the_architecture_reserves(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """x86-64 has 128 bytes a leaf function may be in; the aarch64 standard has none."""
    assert X86_64.red_zone == 128
    assert AARCH64.red_zone == 0

    registers = _registers_of(monkeypatch, X86_64, {X86_64.stack_index: 0x7FFF0000})
    assert registers.scratch(16) == 0x7FFF0000 - 128 - 16

    registers = _registers_of(monkeypatch, AARCH64, {AARCH64.stack_index: 0x7FFF0000})
    assert registers.scratch(16) == 0x7FFF0000 - 16


def test_an_aarch64_register_set_is_read_the_way_the_aarch64_map_says(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The whole map, exercised over a buffer laid out as the kernel would fill one in."""
    registers = _registers_of(
        monkeypatch,
        AARCH64,
        {0: 0xA0, 1: 0xA1, 2: 0xA2, 3: 0xA3, 4: 0xA4, 5: 0xA5, 8: 221, 31: 0x7FF000},
    )

    assert len(registers.buffer) == 34
    assert [registers.arg(index) for index in range(6)] == [
        0xA0,
        0xA1,
        0xA2,
        0xA3,
        0xA4,
        0xA5,
    ]
    assert registers.syscall_number == AARCH64_NUMBERS.EXECVE
    assert registers.stack_pointer == 0x7FF000
    assert registers.result == 0xA0  # x0 is both the first argument and the answer


def test_renumbering_an_aarch64_syscall_is_held_apart_from_the_registers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`x8` has already been read by the time the stop is reported, so writing it changes nothing.

    What is checked is that the value is held for the second regset write instead of being
    dropped into a register the kernel will not look at again -- and that reading it back
    answers with what was asked for rather than with what the tracee said.
    """
    registers = _registers_of(monkeypatch, AARCH64, {8: 221})

    registers.syscall_number = AARCH64_NUMBERS.EXIT_GROUP

    assert registers.renumbered
    assert registers.dirty
    assert registers.syscall_number == AARCH64_NUMBERS.EXIT_GROUP
    assert registers.buffer[8] == 221  # x8 is the tracee's still
    registers.settled()
    assert not registers.renumbered
    assert registers.syscall_number == 221


def test_renumbering_an_x86_64_syscall_is_the_register_itself(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Where `orig_rax` is the number, one write of the set is the whole of it."""
    registers = _registers_of(monkeypatch, X86_64, {X86_64.number_index: 59})

    registers.syscall_number = -1

    assert not registers.renumbered
    assert registers.dirty
    assert registers.buffer[X86_64.number_index] == 0xFFFFFFFFFFFFFFFF


@pytest.mark.parametrize("machine", sorted(MAPS), ids=sorted(MAPS))
def test_a_cancelled_syscall_reads_back_the_same_number_on_either_architecture(
    machine: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Minus one is what cancels one, and a register is the width it is on both."""
    registers = _registers_of(monkeypatch, MAPS[machine], {})

    registers.syscall_number = -1

    assert registers.syscall_number == 0xFFFFFFFFFFFFFFFF


def test_no_call_an_architecture_has_not_got_is_numbered_the_way_a_cancelled_one_is() -> (
    None
):
    """A table keyed by these must have no entry a skipped syscall would be looked up under."""
    absent = {
        getattr(AARCH64_NUMBERS, field.name)
        for field in AARCH64_NUMBERS.__dataclass_fields__.values()
        if getattr(AARCH64_NUMBERS, field.name) < 0
    }

    assert -1 not in absent
    assert max(absent) < -1


def test_a_syscall_this_architecture_has_not_got_is_never_trapped_for() -> None:
    """The filter is built out of the numbers, and an absent one is not a number it has."""
    assert all(number >= 0 for number in AARCH64_NUMBERS.trapped())
    assert AARCH64_NUMBERS.OPENAT in AARCH64_NUMBERS.trapped()
    assert len(X86_64_NUMBERS.trapped()) == len(AARCH64_NUMBERS.trapped()) + 14


def test_a_filter_asked_to_trap_a_call_this_machine_has_not_got_simply_does_not() -> (
    None
):
    """Every caller builds its trap set by naming calls, and one name is not a number here.

    The provider half keeps a table of its own and sorts its keys into a filter, so a set
    with an absent call in it is not hypothetical -- and a negative would not pack into the
    unsigned field a BPF instruction's constant is, which is a crash rather than a wrong
    filter.
    """
    plain = seccomp.build_program([NR.OPENAT, NR.EXECVE])

    assert seccomp.build_program([NR.OPENAT, -7, NR.EXECVE, -999]) == plain
    assert seccomp.build_program([-7]) == seccomp.build_program([])


@pytest.mark.parametrize("machine", sorted(MAPS), ids=sorted(MAPS))
def test_either_architecture_s_trap_set_assembles_into_a_filter_that_fits(
    machine: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A flat filter jumps over its own tail, and a jump is one byte wide.

    aarch64 traps fourteen calls fewer, so it cannot be the one that overflows -- but the
    filter it does build has to name that architecture, or a tracee's every syscall would
    be compared against x86-64's audit number and let through untouched.
    """
    arch = MAPS[machine]
    monkeypatch.setattr(seccomp, "ARCH", arch)

    program = seccomp.build_program(arch.numbers.trapped())

    assert len(program) % 8 == 0
    assert struct.pack("HBBI", 0x15, 1, 0, arch.audit_arch) in program
    for number in arch.numbers.trapped():
        assert struct.pack("HBBI", 0x15, 0, 1, number) in program


def test_the_stand_in_names_at_fdcwd_the_way_every_architecture_spells_it() -> None:
    """It is `<linux/fcntl.h>`'s, not an `asm/` header's, so there is one number for it."""
    assert standin._AT_FDCWD == handlers.AT_FDCWD == -100


def _registers_of(
    monkeypatch: pytest.MonkeyPatch, arch: Arch, values: dict[int, int]
) -> ptrace.Registers:
    """A register set of one architecture's shape, on a machine that is the other.

    The binding reads the map through the module-level `ARCH` it was given at import, which
    is what makes a map for a machine this is not testable at all: point that name at the
    other one and everything below it indexes the other way.

    Args:
      monkeypatch: What points `ARCH` at the architecture under test.
      arch: The architecture to lay the set out as.
      values: What to put in it, by index.

    Returns:
      The set, filled in.
    """
    monkeypatch.setattr(ptrace, "ARCH", arch)
    registers = ptrace.blank()
    for index, value in values.items():
        registers.buffer[index] = value
    registers.settled()
    return registers
