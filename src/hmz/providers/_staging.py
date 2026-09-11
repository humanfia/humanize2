"""The credential an agent reads a thousand times, held where reading it is free.

pi asks about its `auth.json` six to eight hundred times in one turn -- more than half of
every path syscall that turn makes -- and each of those, answered with a path inside the
provider's directory, is a question put to a disk about a token of a few hundred bytes that
did not change. So the token is copied once into a directory of this run's own on `/dev/shm`,
which is memory, and the reads are answered there: what asks about a credential or opens one
to read it is given the copy.

What writes one is not. A refreshed token has to be durable the moment the CLI writes it --
staging the write and copying it back at teardown loses the refresh of a run that is killed,
and two runs of one account would race over which copy landed -- so every call that could
change what is at a credential path is answered with the provider's own directory, exactly as
before, and takes the copy with it. The next read makes a new one. Writes are rare and reads
are thousands: the rare one goes to the safe place.

A copy is also held against the file it was made from once a second, which is what keeps two
agents of one account honest: the other one's refresh is a write this run never saw, and a
cache that went on serving the token it replaced would be an agent signing in with a secret
that has been rotated away.

It is a cache of a secret, so the directory is this user's alone -- `0700`, holding files at
`0600`, under a name nobody can guess -- and it is unlinked when the run ends. Which is not
every way a run ends: a turn is ended by killing the supervisor, and `SIGKILL` runs no
teardown. So it is swept from both ends as well -- by whoever killed one, the moment it has
been waited on, and by the next run before it makes a directory of its own -- and what is
left over in the meantime is bounded at the directories of runs that are already over.
"""

from __future__ import annotations

import contextlib
import os
import re
import secrets
import shutil
import stat
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

__all__ = ["Staging", "swept"]

#: Where a copy is kept. `/dev/shm` is a tmpfs -- POSIX shared memory is mounted there, so a
#: Linux that has one at all has this one -- which makes a read of what is in it a read of
#: memory. A container has it too, at 64 MiB by default, which is thousands of credentials.
_ROOT = Path("/dev/shm")  # noqa: S108

#: What a run's own directory is called: this program, the supervisor's process id so that a
#: run which was killed can be told from one still going, and bytes nobody can guess. The
#: random half is not what keeps another user out -- the directory is `0700`, and it is made
#: rather than opened, so a name somebody got in first with is refused and another taken --
#: it is what stops them getting in first at all.
_CALLED = "hmz-"

#: The same, read back: whose it is, by the run that made it.
_MINE = re.compile(r"hmz-(\d+)-")

#: How large a credential can be before it is left where it is. A token is hundreds of bytes
#: and the biggest of these files is tens of kilobytes; something of megabytes is a CLI's
#: project history rather than its account, and copying one of those on every write it takes
#: would cost more than the reads it saves.
_MOST = 1 << 20

#: How long a copy is trusted without looking at the file it was made from. What this run's
#: own agent writes drops the copy as it is written, so this is for the writer this run
#: cannot see: another agent of the same account, refreshing the same token.
_FRESH = 1.0

#: What is never copied, whatever else it is. A lock file is a rendezvous between processes
#: rather than bytes to read, and a copy of one is a lock the other process cannot see. pi
#: keeps one beside its `auth.json`, and the table answers it as it answers the credential.
_LOCK = ".lock"

#: What a path that is not there was found to be, which no real file is: a file this run may
#: not even look at is still an answer to hold, and holding it is what stops the run asking
#: again at every read.
_NOTHING = (-1, -1, -1)


@dataclass(slots=True)
class _Held:
    """One credential as this run last found it, and the copy it is being answered with.

    Attributes:
      at: Where the copy is, or "" for a path there is no copy to make of -- a directory, a
        link, a lock, something too large, or nothing at all. Either way it is an answer,
        and holding the second kind is what stops it being worked out at every read.
      was: What the provider's own file was when this was decided, as inode, size and the
        moment it last changed. A file that is none of those any more is one to copy again.
      looked: When that was last held against the file, on the monotonic clock.
    """

    at: str
    was: tuple[int, int, int]
    looked: float


class Staging:
    """The copies one redirected run answers reads from, and the directory they are in."""

    def __init__(self) -> None:
        """Initializes a run that has copied nothing and made no directory to copy into."""
        #: Where this run's copies are, or None before the first one is made: a turn that
        #: never reads a credential never makes a directory, and never sweeps for old ones.
        self._at: Path | None = None
        #: What is known about each credential, by the provider's own path to it.
        self._held: dict[str, _Held] = {}
        #: How many copies have been made, which names the next one. A copy is never written
        #: over: a process holding the old one open goes on reading the token it opened.
        self._made = 0
        #: Whether copying is possible here at all. A machine with no `/dev/shm`, or one
        #: whose `/dev/shm` is full, answers every read with the provider's file instead --
        #: which is slower and entirely correct.
        self._can = True

    def reading(self, path: str) -> str | None:
        """The copy to answer a read of one credential with.

        Args:
          path: The provider's own path to it, which is what the swap table answered.

        Returns:
          The copy, or None for a path to answer with itself -- one there is no copy to make
          of, and one this run cannot copy anything at all.
        """
        held = self._held.get(path)
        now = time.monotonic()
        if held is not None and now - held.looked < _FRESH:
            return held.at or None
        return self._copy(path, held, now) or None

    def wrote(self, path: str) -> None:
        """Drops the copy of a credential something is about to change.

        The half of this that is not an optimisation: the write goes to the provider's own
        file, so a copy kept afterwards would answer the next read with the token the CLI
        has just replaced -- which is the CLI reading back its own stale credential.

        Args:
          path: The provider's own path to it.
        """
        held = self._held.pop(path, None)
        if held is not None and held.at:
            with contextlib.suppress(OSError):
                Path(held.at).unlink()

    def close(self) -> None:
        """Takes this run's directory and every copy in it away."""
        self._held.clear()
        at, self._at = self._at, None
        self._can = False
        if at is not None:
            shutil.rmtree(at, ignore_errors=True)

    def _copy(self, path: str, held: _Held | None, now: float) -> str:
        """Makes the copy of one credential, or decides there is not one to make.

        Args:
          path: The provider's own path to it.
          held: What was decided about it last time, if anything.
          now: The moment this is being decided at.

        Returns:
          The copy, or "" for a path that is answered with itself.
        """
        file = Path(path)
        try:
            status = file.lstat()
        except OSError:
            # Nothing there, or nothing this process may look at: the call goes to the
            # provider's own directory and fails there, which is the answer to give -- an
            # account that was never signed in is not this machine's account. Held as an
            # answer all the same: an account with four credential paths and one file has
            # three of these, and a CLI asks about the ones that are not there too.
            self.wrote(path)
            self._held[path] = _Held("", _NOTHING, now)
            return ""
        was = (status.st_ino, status.st_size, status.st_mtime_ns)
        if held is not None and held.was == was:
            held.looked = now
            return held.at
        self.wrote(path)
        # A directory is listed and written into, a link is asked about rather than read, and
        # a lock is other processes' business: each of those is answered with the real one.
        if (
            not stat.S_ISREG(status.st_mode)
            or status.st_size > _MOST
            or path.endswith(_LOCK)
        ):
            self._held[path] = _Held("", was, now)
            return ""
        try:
            at = self._planted(file.name, file.read_bytes(), status)
        except OSError:
            at = ""  # a credential that could not be copied is one to read where it is
        self._held[path] = _Held(at, was, now)
        return at

    def _planted(self, name: str, blob: bytes, status: os.stat_result) -> str:
        """Writes one credential into this run's own directory, at nobody else's mode.

        Args:
          name: What the provider calls it, which the copy is called too -- what a CLI says
            when it cannot read one is a path somebody has to recognise.
          blob: What is in it.
          status: The provider's file, as it was found.

        Returns:
          The copy, or "" where there is nowhere to put one.

        Raises:
          OSError: If it could not be written -- a full `/dev/shm`, most likely.
        """
        where = self._where()
        if where is None:
            return ""
        self._made += 1
        at = where / f"{self._made}.{name}"
        handle = os.open(at, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            os.write(handle, blob)
        finally:
            os.close(handle)
        # When it last changed, as well as what is in it: a CLI that decides whether to read
        # a credential again by looking at when it changed would read a copy as a rotation.
        os.utime(at, ns=(status.st_atime_ns, status.st_mtime_ns))
        return str(at)

    def _where(self) -> Path | None:
        """This run's own directory, made the first time there is something to put in it."""
        if self._at is not None or not self._can:
            return self._at
        try:
            swept()
            self._at = Path(
                tempfile.mkdtemp(
                    prefix=f"{_CALLED}{os.getpid()}-{secrets.token_hex(8)}-", dir=_ROOT
                )
            )
        except OSError:
            self._can = False
        return self._at


def swept(only: int = 0) -> None:
    """Takes away what a run that was killed outright left behind.

    Teardown belongs to the run that made the directory, and a run can end in a way that runs
    none: a turn is ended by killing the supervisor, and `SIGKILL` runs nothing. So this is
    the other half of it, and is called from both ends -- by whoever killed a supervisor, the
    moment it has been waited on, and by the next run before it makes a directory of its own,
    which is what covers a driver that was killed too.

    The name carries the process id of the run that made it, and one of ours whose run is
    gone is a directory nobody is reading. A pid that has come round to somebody else is left
    alone, which leaks that one directory rather than risk taking the credentials away from a
    run that is reading them this moment.

    Args:
      only: The run to sweep up after, by the process id of its supervisor, or 0 for every
        one of ours whose run is over.
    """
    wanted = f"{_CALLED}{only}-" if only else ""
    with contextlib.suppress(OSError), os.scandir(_ROOT) as entries:
        for entry in entries:
            said = _MINE.match(entry.name)
            if said is None or (wanted and not entry.name.startswith(wanted)):
                continue
            try:
                if not entry.is_dir(follow_symlinks=False):
                    continue
                # A name like ours from somebody else is not ours to take away, and is not
                # one anything here would have read: the copies are in a directory of ours.
                if entry.stat(follow_symlinks=False).st_uid != os.getuid():
                    continue
                os.kill(int(said[1]), 0)
            except ProcessLookupError:
                shutil.rmtree(entry.path, ignore_errors=True)
            except (OSError, OverflowError, ValueError):
                continue
