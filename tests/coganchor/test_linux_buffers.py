"""Synchronous kernel transfers own their buffers only as long as the call needs them."""

from __future__ import annotations

import ctypes
import errno
import gc
import os
import signal
import subprocess
import sys
import weakref
from typing import TYPE_CHECKING

import pytest

from hmz.coganchor.linux import procfs, ptrace
from tests.providers.test_redirect import traced

if TYPE_CHECKING:
    from collections.abc import Iterator


@pytest.fixture
def allocations(
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[list[weakref.ReferenceType[ctypes.Array[ctypes.c_char]]]]:
    """Observe temporary buffers without a GC run hiding accidental ownership cycles."""
    allocated: list[weakref.ReferenceType[ctypes.Array[ctypes.c_char]]] = []
    original = ctypes.create_string_buffer

    def allocate(
        init: bytes | int, size: int | None = None
    ) -> ctypes.Array[ctypes.c_char]:
        buffer = original(init) if isinstance(init, int) else original(init, size)
        allocated.append(weakref.ref(buffer))
        return buffer

    monkeypatch.setattr(ctypes, "create_string_buffer", allocate)
    enabled = gc.isenabled()
    gc.disable()
    try:
        yield allocated
    finally:
        if enabled:
            gc.enable()


@pytest.mark.parametrize("size", [1, 4097])
def test_memory_transfers_are_byte_exact_and_release_temporary_buffers(
    size: int,
    allocations: list[weakref.ReferenceType[ctypes.Array[ctypes.c_char]]],
) -> None:
    # Includes embedded NULs and a transfer larger than one page. The caller's storage
    # remains owned; only the temporary kernel transfer buffers should disappear.
    payload = bytes(index % 256 for index in range(size))
    target = (ctypes.c_char * (size + 2)).from_buffer_copy(b"<" + payload + b">")
    address = ctypes.addressof(target) + 1

    assert procfs.read_bytes(os.getpid(), address, size) == payload
    replacement = payload[::-1]
    assert procfs.write_bytes(os.getpid(), address, replacement) == size
    assert target.raw == b"<" + replacement + b">"
    assert len(allocations) == 2
    assert all(buffer() is None for buffer in allocations)


def test_failed_memory_transfers_release_temporary_buffers(
    allocations: list[weakref.ReferenceType[ctypes.Array[ctypes.c_char]]],
) -> None:
    with pytest.raises(OSError, match="process_vm_readv") as read:
        procfs.read_bytes(os.getpid(), 0, 64)
    assert read.value.errno == errno.EFAULT
    with pytest.raises(OSError, match="process_vm_writev") as write:
        procfs.write_bytes(os.getpid(), 0, b"unmapped")
    assert write.value.errno == errno.EFAULT
    # Exception tracebacks retain their frames until the caller releases them.
    del read, write
    assert len(allocations) == 2
    assert all(buffer() is None for buffer in allocations)


@traced
@pytest.mark.timeout(10)
def test_real_tracee_register_and_memory_rewrites_release_buffers(
    allocations: list[weakref.ReferenceType[ctypes.Array[ctypes.c_char]]],
) -> None:
    program = """
import os
import signal
from hmz.coganchor.linux import ptrace

payload = b"native registers are intact"
ptrace.traceme()
os.kill(os.getpid(), signal.SIGSTOP)
os.write(1, payload)
"""
    child = subprocess.Popen(
        [sys.executable, "-c", program],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        waited, status = os.waitpid(child.pid, os.WUNTRACED)
        assert waited == child.pid
        assert os.WIFSTOPPED(status)
        assert os.WSTOPSIG(status) == signal.SIGSTOP
        ptrace.setoptions(child.pid, 1)  # TRACESYSGOOD, without process-tree events.
        for _ in range(100):
            ptrace.syscall(child.pid)
            waited, status = os.waitpid(child.pid, 0)
            assert waited == child.pid
            assert os.WIFSTOPPED(status)
            assert os.WSTOPSIG(status) == signal.SIGTRAP | ptrace.SYSCALL_STOP_SIG
            registers = ptrace.getregs(child.pid)
            if registers.syscall_number == 1:  # x86-64 write(2).
                break
        else:
            pytest.fail("the tracee never reached its write syscall")

        assert registers.arg(0) == 1
        assert registers.arg(2) == len(b"native registers are intact")
        address = registers.arg(1)
        assert procfs.read_bytes(child.pid, address, 6) == b"native"
        replacement = b"\0edited"
        assert procfs.write_bytes(child.pid, address, replacement) == len(replacement)
        registers.set_arg(2, len(replacement))
        ptrace.setregs(child.pid, registers)
        observed = ptrace.getregs(child.pid)
        assert observed.arg(1) == address
        assert observed.arg(2) == len(replacement)
        register_buffers = [weakref.ref(registers.buffer), weakref.ref(observed.buffer)]
        del registers, observed
        assert all(buffer() is None for buffer in register_buffers)
        assert all(buffer() is None for buffer in allocations)

        ptrace.cont(child.pid)
        stdout, stderr = child.communicate(timeout=5)
        assert child.returncode == 0, stderr.decode()
        assert stdout == replacement
    finally:
        if child.poll() is None:
            child.kill()
        child.communicate(timeout=5)
