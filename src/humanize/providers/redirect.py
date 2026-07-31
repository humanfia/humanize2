"""Running a coding agent whose credentials are somewhere other than where it looks.

Every one of these CLIs keeps its account in one place under a home directory of its own,
found by a path it decides for itself. Moving that home moves the sessions, the settings and
the skills with it; asking the CLI nicely is not a thing any of them offers. So the paths are
answered rather than moved: the agent is run under a seccomp-filtered ptrace supervisor -- the
same technique :mod:`humanize.coganchor` runs a whole session under -- and the handful of
syscalls that name one of its credential files are handed a path inside the provider's
directory instead.

Only those paths. Everything else the agent does is untouched and runs at native speed, and
the agent is told none of it: what it reads back is a credentials file at the name it wrote,
and what it writes when a token is refreshed lands where it read from.

Two supervisors cannot be nested -- a process has one tracer -- so a turn that is also
anchored is not wrapped in this: the anchor is told the same swaps and its own supervisor
makes them. This is the case where the agent runs on this machine, which is most of them.
"""

from __future__ import annotations

import errno
import os
import signal
import sys
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

__all__ = ["Swaps", "command", "read", "run"]

#: `AT_FDCWD`, the directory descriptor that means "wherever the process is".
_AT_FDCWD = -100

#: Where a rewritten path is written in the tracee: below the red zone, in stack the process
#: has not reached yet, one whole path per slot so that a syscall naming two of them can be
#: given both. The exec that would use this space discards it, and every other syscall here
#: reads its arguments out before returning, so nothing outlives the call it was planted for.
_SCRATCH = 4096


@dataclass(frozen=True, slots=True)
class Swaps:
    """Which paths a traced process is given instead of the ones it named.

    A prefix apiece: a credential kept in a directory -- kimi keeps one file per endpoint it
    has signed into -- is a directory that moves whole, and one kept in a file is that file.
    Longest first, so a path under two of them takes the one that says most about it.
    """

    pairs: tuple[tuple[str, str], ...] = ()

    @classmethod
    def of(cls, pairs: Iterable[tuple[str, str]]) -> Swaps:
        """Builds a table from `(what the agent names, what it gets)` pairs."""
        held = tuple(
            (os.path.normpath(one), os.path.normpath(other))
            for one, other in pairs
            if one and other
        )
        return cls(tuple(sorted(held, key=lambda pair: -len(pair[0]))))

    def __bool__(self) -> bool:
        """Whether anything is pointed anywhere else at all."""
        return bool(self.pairs)

    def swap(self, path: str) -> str | None:
        """What one path is answered with.

        Three shapes, and the third is not a nicety: the file itself, anything inside it where
        it is a directory, and anything beside it under the same name and another suffix. That
        last is how these CLIs rotate a token -- write `.credentials.json.tmp`, rename it over
        `.credentials.json` -- and a temp file left unanswered would put the new token in the
        real store and then rename it across two filesystems.

        Args:
          path: The absolute, normalised path the process named.

        Returns:
          The path to give it instead, or None for a path that is its own -- which is nearly
          all of them.
        """
        for named, instead in self.pairs:
            if path == named:
                return instead
            if path.startswith((named + "/", named + ".")):
                return instead + path[len(named) :]
        return None


def read(said: Iterable[str]) -> Swaps:
    """Reads the swaps off a command line that named them.

    Args:
      said: One `FROM=TO` per swap, as `--map` took them.

    Returns:
      The table.

    Raises:
      ValueError: If one of them is not two absolute paths with an `=` between.
    """
    pairs: list[tuple[str, str]] = []
    for one in said:
        named, sep, instead = one.partition("=")
        if not sep or not named.startswith("/") or not instead.startswith("/"):
            raise ValueError(f"{one!r} is not FROM=TO, of two absolute paths")
        pairs.append((named, instead))
    return Swaps.of(pairs)


def command(
    swaps: Iterable[tuple[str, str]], argv: Sequence[str] | list[str]
) -> list[str]:
    """Renders the invocation that runs `argv` with those paths pointed elsewhere.

    A method of its own rather than the loop it starts, for the reason
    :meth:`humanize.coganchor.AnchorConfig.command` is one: a turn is pumped from threads of
    its own, and a supervisor that forks the agent and takes the process's signal handling
    cannot be given those.

    Args:
      swaps: What to point where.
      argv: The backend to run and its own arguments.

    Returns:
      The command to spawn, which exits with the backend's own status -- or `argv` itself
      when there is nothing to point anywhere, so that a provider which is only variables
      costs no supervisor and no ptrace at all.
    """
    held = Swaps.of(swaps)
    if not held:
        return list(argv)
    mapped = [f"--map={named}={instead}" for named, instead in held.pairs]
    return [sys.executable, "-m", "humanize", "cred", *mapped, "--", *argv]


def run(swaps: Swaps, argv: Sequence[str]) -> int:
    """Runs a program with those paths answered by others, and waits for it.

    Args:
      swaps: What to point where.
      argv: The program and its arguments.

    Returns:
      Its exit status, or 128 plus the signal that killed it.

    Raises:
      OSError: If the supervisor cannot be started, which is a turn that must not run: an
        agent whose credentials were not pointed anywhere would sign in as somebody else.
    """
    # Imported here rather than above: this half needs ptrace and an x86-64 register map,
    # which reading a provider and rendering a command line do not.
    from humanize.coganchor.linux import ptrace, seccomp

    from ._trace import Tracing

    if not argv:
        raise ValueError("no program to run")
    tracing = Tracing(swaps)
    pid = os.fork()
    if not pid:
        try:
            ptrace.traceme()
            seccomp.install(tracing.trapped())
            os.kill(os.getpid(), signal.SIGSTOP)
            # Becoming the program is the whole errand of this fork, and it is an argv
            # rather than a command line, so there is no shell for one to go through.
            os.execvp(argv[0], list(argv))  # noqa: S606
        # Everything, deliberately: this is the forked child, and anything that escapes here
        # would run the parent's code a second time rather than report a failed launch.
        except BaseException as why:  # noqa: BLE001
            os.write(2, f"hmz: cannot run {argv[0]}: {why}\n".encode())
        os._exit(127)
    return tracing.watch(pid)


def failed(status: int) -> int:
    """What a program's wait status comes to as an exit status."""
    if os.WIFEXITED(status):
        return os.WEXITSTATUS(status)
    return 128 + os.WTERMSIG(status) if os.WIFSIGNALED(status) else 1


#: What a syscall that could not be given its new path is answered with. A visible failure,
#: because the alternative is the agent quietly reading the credentials of whoever is at this
#: machine -- a turn that ran as the wrong account is worse than a turn that did not run.
UNSWAPPABLE = errno.EIO
