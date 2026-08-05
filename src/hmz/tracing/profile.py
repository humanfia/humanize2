"""What else was running while the agents were: the programs a run started, sampled.

An agent's turn is mostly other programs. It runs the tests, it builds the thing, it greps the
repository, and the minutes a run takes are mostly minutes those took -- none of which appears
anywhere in the backend's own log, which records the tool call and not the process. So a run
may be profiled as well as traced: while the cycle is open, the processes underneath it are
sampled, and what they were and how long each took is written down beside the sessions.

Which is the whole point of putting them in one trace. An agent's sessions are a process whose
sub-agents are tracks; a program the agent ran is a process whose threads are tracks; both are
drawn on one timeline, at one scale, and the question `what was this run actually doing at
09:41` has one answer instead of two.

Sampled rather than intercepted: nothing here is between the agent and what it runs. A sampler
that missed a process that lived for thirty milliseconds has missed thirty milliseconds, and a
sampler that could not read `/proc` at all has missed everything -- neither of which is a
reason for a run to stop.
"""

from __future__ import annotations

import contextlib
import json
import threading
import time
from typing import TYPE_CHECKING, Any, NamedTuple

import psutil

if TYPE_CHECKING:
    import os
    from collections.abc import Iterator
    from pathlib import Path

__all__ = ["PROFILE", "Process", "Profiler", "Thread", "read"]

#: What a run's profile is written to, inside the cycle it was taken in.
PROFILE = "profile.jsonl"

#: How often the processes under a run are looked at. Fast enough to catch a `grep` and slow
#: enough to cost a run nothing: reading a process tree is a directory listing and a handful
#: of small files, and twenty of those a second is not what makes an agent slow.
EVERY = 0.05


class Thread(NamedTuple):
    """One thread of one program a run ran.

    Attributes:
      tid: What the operating system calls it. The one equal to the process's own id is that
        process's first thread, which is the one that ran `main`.
      began: When it was first seen, in epoch seconds.
      ended: When it was last seen.
      cpu: How many seconds of processor time it had used by then, user and system together.
    """

    tid: int
    began: float
    ended: float
    cpu: float = 0.0


class Process(NamedTuple):
    """One program a run ran, as the sampler saw it.

    Attributes:
      pid: What the operating system called it.
      ppid: What started it, which is how the tree is rebuilt.
      name: What it is, as the process calls itself.
      argv: The line it was started with, as far as it can be read.
      began: When it started, as the operating system says -- corrected, once the whole
        profile has been read, by how far the operating system's idea of when a process
        started is from the clock the rest of a trace is timed by. It is derived from the
        moment the machine booted, which is itself estimated: half a second out is ordinary,
        and half a second is a mile on a trace where a tool call is timed to the millisecond.
      seen: When the sampler first saw it, which is what that correction is worked out from:
        a process is seen within one sample of starting, so the smallest gap between the two
        across a whole profile is as good a measure of the difference as there is.
      ended: When it was last seen running.
      threads: Its threads, oldest first.
    """

    pid: int
    ppid: int
    name: str
    argv: tuple[str, ...]
    began: float
    ended: float
    threads: tuple[Thread, ...] = ()
    seen: float = 0.0

    @property
    def label(self) -> str:
        """What to call it where it is drawn: what it is, and which one it was."""
        return f"{self.name} · {self.pid}"


class Profiler:
    """Samples the programs running under this process, and writes down what it saw.

    Started by the run it is a profile of and stopped when that run ends. What it writes is
    one line per program -- when it started, when it was last seen, what it was and what
    started it -- appended as the program goes rather than held to the end, for the reason a
    cycle's own record is appended: a run that died is a run whose profile has to say what it
    got to.
    """

    def __init__(
        self, at: str | os.PathLike[str], every: float = EVERY, root: int | None = None
    ) -> None:
        """Holds where to write and what to watch.

        Args:
          at: The file to write, which is `profile.jsonl` in the run's own cycle.
          every: How often to look, in seconds.
          root: The process whose descendants are the run's, defaulting to this one -- which
            is the process the agents were started from, so everything they started is under
            it. A pid of somebody else's is what a test hands over.
        """
        import pathlib

        self._at = pathlib.Path(at)
        self._every = every
        self._root = root
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._writing = threading.Lock()
        #: What has been seen so far, by the pid and the moment it started -- a pid alone is
        #: a name the operating system hands out again, and a run of hours will see it twice.
        self._seen: dict[tuple[int, float], Process] = {}
        #: Which of those have been written down as gone.
        self._left: set[tuple[int, float]] = set()

    def start(self) -> None:
        """Begins sampling, on a thread of its own.

        A thread rather than the run's: the run is a flow taking turns, and a sampler that
        only looked between them would be a sampler that saw nothing -- what it is watching
        is exactly what happens while a turn is under way.
        """
        if self._thread is not None:
            return
        self._thread = threading.Thread(
            target=self._sampling, name="humanize-profile", daemon=True
        )
        self._thread.start()

    def stop(self, seconds: float = 2.0) -> None:
        """Stops sampling, and writes down whatever was still running.

        Args:
          seconds: How long to wait for the sampler to notice, after which it is left as the
            daemon thread it is: a run must not hang on its own profile.
        """
        self._stop.set()
        held = self._thread
        if held is not None:
            held.join(seconds)
        self._thread = None
        self._ends()

    def _sampling(self) -> None:
        """Looks at what is running, over and over, until it is told to stop."""
        while not self._stop.is_set():
            with contextlib.suppress(Exception):
                # Anything at all: a process tree read while it is changing raises whatever
                # the platform raises, and a profile is not a thing to fail a run over.
                self._sample()
            self._stop.wait(self._every)
        with contextlib.suppress(Exception):
            self._sample()

    def _sample(self) -> None:
        """Looks once at every program running under the root, and writes down the new ones."""
        now = time.time()
        for one in self._under():
            try:
                held = (one.pid, one.create_time())
                threads = self._threads(one, now)
                if held not in self._seen:
                    self._seen[held] = Process(
                        pid=one.pid,
                        ppid=one.ppid(),
                        name=one.name(),
                        argv=tuple(one.cmdline()),
                        began=held[1],
                        ended=now,
                        threads=threads,
                        seen=now,
                    )
                    self._wrote("ran", self._seen[held])
                else:
                    self._seen[held] = self._seen[held]._replace(
                        ended=now, threads=threads or self._seen[held].threads
                    )
            except (psutil.Error, OSError):
                continue  # a process that went while it was being read is one that went
        self._gone()

    def _under(self) -> list[psutil.Process]:
        """Every program running under the root now, deepest last.

        Returns:
          The descendants of the process the run is happening in, which is every program an
          agent of it started -- and the agents themselves, which are started the same way.
          The root is not among them: it is humanize, which is what the trace is of rather
          than something in it.
        """
        try:
            root = psutil.Process(self._root)
            return root.children(recursive=True)
        except (psutil.Error, OSError):
            return []

    def _threads(self, one: psutil.Process, now: float) -> tuple[Thread, ...]:
        """The threads of one program, as they stand.

        Args:
          one: The program.
          now: This moment, which is when each of them was last seen.

        Returns:
          One apiece, oldest first, and nothing at all where the platform will not say.
        """
        try:
            said = one.threads()
        except (psutil.Error, OSError, NotImplementedError):
            return ()
        held = {thread.id: (thread.user_time + thread.system_time) for thread in said}
        was = {thread.tid: thread for thread in self._known(one)}
        return tuple(
            Thread(
                tid=tid,
                began=was[tid].began if tid in was else now,
                ended=now,
                cpu=cpu,
            )
            for tid, cpu in sorted(held.items())
        )

    def _known(self, one: psutil.Process) -> tuple[Thread, ...]:
        """What was already known about one program's threads, if anything was."""
        with contextlib.suppress(psutil.Error, OSError):
            held = self._seen.get((one.pid, one.create_time()))
            if held is not None:
                return held.threads
        return ()

    def _gone(self) -> None:
        """Writes down every program that has stopped since the last look."""
        running: set[tuple[int, float]] = set()
        for one in self._under():
            with contextlib.suppress(psutil.Error, OSError):
                running.add((one.pid, one.create_time()))
        for held, one in self._seen.items():
            if held not in running and held not in self._left:
                self._left.add(held)
                self._wrote("left", one)

    def _ends(self) -> None:
        """Writes down whatever was still running when the profile stopped."""
        for held, one in self._seen.items():
            if held not in self._left:
                self._left.add(held)
                self._wrote("left", one)

    def _wrote(self, event: str, one: Process) -> None:
        """Appends one line about one program.

        Args:
          event: Whether this is the program being seen or the program having gone.
          one: What was seen.
        """
        said: dict[str, Any] = {
            "event": event,
            "pid": one.pid,
            "ppid": one.ppid,
            "name": one.name,
            "argv": list(one.argv),
            "began": one.began,
            "seen": one.seen,
            "ended": one.ended,
            "threads": [list(thread) for thread in one.threads],
        }
        with self._writing, contextlib.suppress(OSError):
            self._at.parent.mkdir(parents=True, exist_ok=True)
            with self._at.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(said) + "\n")


def read(at: str | os.PathLike[str]) -> list[Process]:
    """The programs one profile holds, in the order they started.

    Args:
      at: The profile, or the cycle it is in.

    Returns:
      One apiece, the last thing written about each being what is read -- a program is
      written down when it is first seen and again when it goes, and the second says how
      long it ran -- and each timed against the clock the rest of a trace is timed by rather
      than against the operating system's own idea of when a process started. Nothing at all
      for a run that was not profiled.
    """
    import pathlib

    where = pathlib.Path(at)
    if where.is_dir():
        where = where / PROFILE
    held: dict[tuple[int, float], Process] = {}
    for said in _lines(where):
        one = _read(said)
        if one is not None:
            held[one.pid, one.began] = one
    return _lined_up(sorted(held.values(), key=lambda one: (one.began, one.pid)))


def _lined_up(held: list[Process]) -> list[Process]:
    """The same programs, timed against the clock rather than against the boot time.

    What the operating system reports as a process's start is worked out from the moment the
    machine booted, and that moment is itself an estimate -- half a second out on an ordinary
    machine, which on a trace is a mile. What it is not is inconsistent: every process is out
    by the same amount, so the difference can be measured from the profile itself. A process
    is seen within one sample of starting, so the smallest gap anywhere in the profile
    between what was reported and when it was seen is as close to that difference as this can
    get, and every start is moved by it.

    Args:
      held: What the profile holds.

    Returns:
      The same, with the starts moved. Unmoved where nothing was ever seen being sampled,
      which is a profile with nothing to measure against.
    """
    gaps = [one.seen - one.began for one in held if one.seen]
    if not gaps:
        return held
    by = max(min(gaps), 0.0)
    return [
        one._replace(began=min(one.began + by, one.ended)) if one.seen else one
        for one in held
    ]


def _lines(at: Path) -> Iterator[dict[str, Any]]:
    """Every record one profile holds, skipping whatever is not one."""
    try:
        lines = at.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return
    for line in lines:
        try:
            said = json.loads(line)
        except ValueError:
            continue  # a run that died mid-line, which is a line and not a profile
        if isinstance(said, dict):
            yield said


def _read(said: dict[str, Any]) -> Process | None:
    """One program, read back off the line it was written as."""
    try:
        return Process(
            pid=int(said["pid"]),
            ppid=int(said.get("ppid", 0)),
            name=str(said.get("name") or ""),
            argv=tuple(str(one) for one in said.get("argv") or ()),
            began=float(said["began"]),
            seen=float(said.get("seen") or 0.0),
            ended=float(said.get("ended") or said["began"]),
            threads=tuple(
                Thread(int(one[0]), float(one[1]), float(one[2]), float(one[3]))
                for one in said.get("threads") or ()
                if len(one) == len(Thread._fields)
            ),
        )
    except (KeyError, TypeError, ValueError):
        return None
