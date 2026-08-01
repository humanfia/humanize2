"""Thin, dependency-free bindings to the Linux facilities coganchor relies on.

Split by concern: :mod:`syscalls` (numbers and register layout),
:mod:`seccomp` (the trap filter), :mod:`ptrace` (stop, inspect, tamper) and
:mod:`procfs` (tracee memory, working directory, descriptor stealing).
"""

from hmz.coganchor.linux import procfs, ptrace, seccomp, syscalls

__all__ = ["procfs", "ptrace", "seccomp", "syscalls"]
