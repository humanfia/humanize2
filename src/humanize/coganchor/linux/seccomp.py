"""Classic-BPF seccomp filter that decides which syscalls reach the supervisor.

The filter is installed once in the forked child, just before ``execve``, and
is inherited by every descendant process and thread.  It returns
``SECCOMP_RET_TRACE`` for the cold, path-bearing syscalls coganchor cares
about and ``SECCOMP_RET_ALLOW`` for everything else, so hot syscalls never pay
a ptrace stop.
"""

from __future__ import annotations

import ctypes
import os
import struct
from collections.abc import Iterable
from typing import Final

from humanize.coganchor.linux.syscalls import ARCH, NR

__all__ = ["build_program", "install"]

_libc = ctypes.CDLL("libc.so.6", use_errno=True)
_libc.syscall.restype = ctypes.c_long

_PR_SET_NO_NEW_PRIVS: Final = 38
_SECCOMP_SET_MODE_FILTER: Final = 1

_RET_ALLOW: Final = 0x7FFF0000
_RET_TRACE: Final = 0x7FF00000

# BPF instruction classes and modes, from <linux/filter.h>.
_LD_W_ABS: Final = 0x20
_JMP_JEQ_K: Final = 0x15
_RET_K: Final = 0x06

# Offsets into ``struct seccomp_data``.
_OFFSET_NR: Final = 0
_OFFSET_ARCH: Final = 4

_MAX_JUMP: Final = 255


class _SockFprog(ctypes.Structure):
    _fields_ = [("length", ctypes.c_ushort), ("filter", ctypes.c_void_p)]


def _insn(code: int, jt: int, jf: int, k: int) -> bytes:
    return struct.pack("HBBI", code, jt, jf, k)


def build_program(numbers: Iterable[int]) -> bytes:
    """Assemble the BPF program that traps ``numbers``.

    Foreign architectures (32-bit syscall entry points) are allowed through
    untouched: coganchor is a redirector, not a sandbox, so failing open keeps
    an unexpected personality working rather than killing the agent.
    """
    ordered = sorted(set(numbers))
    if len(ordered) * 2 + 4 > _MAX_JUMP:
        raise ValueError("trap set too large for a flat filter")
    program = [
        _insn(_LD_W_ABS, 0, 0, _OFFSET_ARCH),
        _insn(_JMP_JEQ_K, 1, 0, ARCH.audit_arch),
        _insn(_RET_K, 0, 0, _RET_ALLOW),
        _insn(_LD_W_ABS, 0, 0, _OFFSET_NR),
    ]
    for number in ordered:
        program.append(_insn(_JMP_JEQ_K, 0, 1, number))
        program.append(_insn(_RET_K, 0, 0, _RET_TRACE))
    program.append(_insn(_RET_K, 0, 0, _RET_ALLOW))
    return b"".join(program)


def install(numbers: Iterable[int]) -> None:
    """Install the filter on the current thread.

    Called in the forked child between ``PTRACE_TRACEME`` and ``execve``.
    ``PR_SET_NO_NEW_PRIVS`` is required to install a filter without
    ``CAP_SYS_ADMIN``; it also means set-uid binaries below the agent will not
    gain privileges, which is the correct posture for a redirected session.
    """
    blob = build_program(numbers)
    ctypes.set_errno(0)
    if _libc.prctl(_PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) != 0:
        code = ctypes.get_errno()
        raise OSError(code, os.strerror(code), "prctl(PR_SET_NO_NEW_PRIVS)")
    buffer = ctypes.create_string_buffer(blob, len(blob))
    program = _SockFprog(len(blob) // 8, ctypes.cast(buffer, ctypes.c_void_p))
    ctypes.set_errno(0)
    if (
        _libc.syscall(NR.SECCOMP, _SECCOMP_SET_MODE_FILTER, 0, ctypes.byref(program))
        != 0
    ):
        code = ctypes.get_errno()
        raise OSError(code, os.strerror(code), "seccomp(SECCOMP_SET_MODE_FILTER)")
