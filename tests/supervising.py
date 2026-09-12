"""Whether the machine running the suite can supervise a program, and how one is spawned.

Two questions, and they are not the same one.

The first is whether the bindings import at all. :mod:`hmz.coganchor.linux` opens `libc.so.6`
and picks a register map at import time, refusing any architecture it has not got one for, so
a test module that names those bindings cannot be *collected* anywhere else -- a skip written
inside it would never be reached, because the import above it raises first.
:data:`WITHOUT_BINDINGS` is what such a module asks before importing them.

The second is whether this kernel will really hand over a tracee, which only running one
answers: a container without `CAP_SYS_PTRACE` has every module and can supervise nothing.
:data:`WITHOUT` is that answer, and :data:`traced` is the mark that leaves a test out where
it is no.

Here rather than beside the supervisor's own tests because most of what asks is somewhere
else. A turn run as a named account is a supervised turn -- the paths that turn reads are
answered by others, which is what the filter and the tracer are for -- so the accounts, the
catalogues kept per account, an epic naming the account a session ran as and a flow running
one CLI as two of them all ask this before they ask for one. A conftest asks too, and a
conftest is a pytest plugin rather than a module to import from, so it cannot be the one that
holds it.
"""

from __future__ import annotations

import platform
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

#: What the machine itself is signed in as, which a turn under a provider must never see.
MACHINE = '{"token": "the one at this machine"}'

#: What the provider is signed in as, which is what every read below has to come back with.
PROVIDER = '{"token": "the provider"}'

#: How long a supervised program is given before the run is taken to have hung.
PATIENCE = 45


def cred(
    argv: list[str], *, stdin: str = "", timeout: int = PATIENCE
) -> subprocess.CompletedProcess[str]:
    """Runs `hmz cred` as a turn under a provider runs it: its own process, on its own.

    Args:
      argv: What follows the command name -- the swaps, `--`, and the program.
      stdin: What to write to the program's standard input.
      timeout: How long to wait before taking the run to have hung.

    Returns:
      What the run came to, with its output read back.
    """
    return subprocess.run(
        [sys.executable, "-m", "hmz", "cred", *argv],
        input=stdin,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


#: The architectures :mod:`hmz.coganchor.linux.syscalls` has a register map for, spelled out
#: again rather than read off it: reading it off would mean importing the very module this
#: says whether it may be imported, which on a third architecture raises. That the two agree
#: is checked by `tests/coganchor/test_architectures.py`, which runs where the import works.
SUPPORTED_MACHINES = frozenset({"x86_64", "aarch64"})


def _cannot_import() -> str:
    """Why the Linux bindings will not import here, or "" where they will.

    Asked of the platform rather than by importing them, because the caller is a module that
    has not imported them yet and wants to know whether it may.
    """
    if sys.platform != "linux":
        return "a redirected run is a Linux seccomp filter and a ptrace supervisor"
    if platform.machine() not in SUPPORTED_MACHINES:
        return (
            f"there is a register map for {', '.join(sorted(SUPPORTED_MACHINES))}, "
            f"and this host is {platform.machine()}"
        )
    return ""


#: Why a module that names :mod:`hmz.coganchor.linux` cannot be imported here, or "" where it
#: can. A module gated on this skips itself before reaching for the bindings.
WITHOUT_BINDINGS = _cannot_import()


def _cannot_trace() -> str:
    """Why a redirected run cannot be watched on this machine, or "" where one can.

    Answered by running one: the modules import on any Linux there is a register map for,
    and whether the kernel will hand over a tracee is a question only the attempt asks.
    """
    if WITHOUT_BINDINGS:
        return WITHOUT_BINDINGS
    with tempfile.TemporaryDirectory() as folder:
        named, instead = Path(folder) / "named", Path(folder) / "instead"
        named.write_text(MACHINE)
        instead.write_text(PROVIDER)
        try:
            done = cred([f"--map={named}={instead}", "--", "cat", str(named)])
        except (OSError, subprocess.SubprocessError) as why:
            return f"a supervisor could not be started here: {why}"
    if done.stdout != PROVIDER:
        return f"nothing is traced here: {done.stderr.strip() or done.returncode}"
    return ""


#: Why the end-to-end tests cannot run here, and the mark that leaves them out when so.
WITHOUT = _cannot_trace()
traced = pytest.mark.skipif(bool(WITHOUT), reason=WITHOUT or "this machine can trace")
