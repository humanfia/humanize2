"""A turn that has stopped saying anything, noticed and dealt with rather than waited on.

Every read loop in this package blocks on the backend: a line off a pipe, an event off a
queue, a notification off somebody's SDK. Two of the three things that can happen next are
already handled -- a backend that answers ends the turn, and a backend that exits fails it.
The third is the one no read loop can see: a CLI that is still there, still holding its socket,
and never going to say another word. Waited on, that is a flow hung until a person notices,
and on a fleet of sixteen conversations the person notices hours later.

So a turn runs under a clock. It is patted every time the backend says anything at all, and
when it runs out the ladder here is climbed: look at the process before believing it is wedged,
ask the turn to stop, put the transport down, kill what is left. Each rung says so on the
stream the turn is read from, the way a retry and a fallback do -- an intervention nobody can
see reads exactly like the stall it was fixing.

What the clock is set to is a fact about the backend rather than a number chosen here:
:mod:`hmz.coganchor.backends` says how long each of them may go without a word, and how much of a
conversation survives its transport being put down. Generous on purpose. A turn thinks for
minutes and says nothing for most of them, so a window short enough to catch a wedge quickly
is a window that kills healthy turns, and killing a healthy turn is the worse mistake: a
wedge noticed late costs the time it was wedged, and a healthy turn shot costs the work.
"""

# A watchdog and the session it is watching are two halves of one thing: it reads what the
# turn is riding and puts that transport down, which is the session's own inside. The
# underscore keeps those out of the package rather than out of this.
# pyright: reportPrivateUsage=false

from __future__ import annotations

import contextlib
import enum
import os
import threading
import time
from typing import TYPE_CHECKING, Self

import psutil

from hmz.coganchor import backends

from .event import Event, Failed, Stopped

if TYPE_CHECKING:
    import subprocess
    from collections.abc import Callable, Generator
    from types import TracebackType

    from .base import AgentBase, SessionBase

__all__ = ["Watchdog", "held", "silence"]

#: What every backend's own window can be overridden with, in seconds, for a machine where
#: the defaults are wrong -- a container that suspends, a gateway that queues for an hour, a
#: test that cannot wait a quarter of one. Zero or less turns the watchdog off entirely,
#: which is what humanize did before there was one.
WATCHDOG = "HUMANIZE_WATCHDOG"

#: How often the clock is looked at. The windows are quarter-hours, so this is a thread asleep
#: for all but a microsecond of its life; it is a second rather than a minute so that a wedge
#: found is acted on while whoever is watching still has it on the screen.
_TICK = 1.0

#: How long `__exit__` waits for the ticking thread, which is only ever mid-rung. Bounded
#: because the turn has already ended by then: a thread still killing something must not hold
#: up the answer, and it is a daemon, so an interpreter on its way out does not wait either.
_STOPPING = 5.0

#: How many windows of silence a process visibly burning CPU is given before it is treated as
#: wedged anyway. A model thinking and a process spinning look identical from outside, so the
#: benefit of the doubt has to run out somewhere: one that never does is the same hang this
#: file exists to end, wearing patience as a disguise.
_GRANTS = 4

#: How much processor time counts as working, per window. A CLI waiting on a model's HTTP
#: response burns none, so this does not say a quiet turn is dead -- it says a loud one is
#: alive: the tree under a wedged CLI running a twenty-minute test suite is doing real work
#: and must not be shot for saying nothing while it does.
_BUSY = 0.5


class _State(enum.Enum):
    """What the process behind a turn is doing, as far as the machine can say."""

    #: There is no process of this turn's own to look at: the transport is a runtime in this
    #: interpreter, or a server every conversation with the agent shares. Not a state of the
    #: backend at all -- it is this having nothing to go on, and so nothing to say.
    NONE = ""
    #: Burning processor time, itself or under something it started.
    WORKING = "is still working"
    #: Up, and doing nothing at all -- which is what waiting on a model looks like too.
    IDLE = "is idle"
    #: Suspended: signalled to stop and never continued, so it will not say another word.
    STOPPED = "is stopped"
    #: Ended, or defunct, with the turn still open.
    GONE = "is gone"


class _Rung(enum.IntEnum):
    """The steps taken against a turn that has gone quiet, in the order they are taken."""

    LOOK = 0
    INTERRUPT = 1
    DROP = 2
    KILL = 3
    SPENT = 4


def silence(backend: str) -> float:
    """How long a turn of one backend may say nothing before it is looked at.

    Args:
      backend: What the CLI is called.

    Returns:
      The window, in seconds: what the environment says if it says anything, and otherwise
      what is written down about that backend. Zero or less for a watchdog turned off.
    """
    return _window(_profiled(backend))


def _window(profile: backends.Profile) -> float:
    """The same, off a profile already in hand.

    Read this way by the watchdog itself, which holds the profile anyway: asking for a
    backend by name reads every added CLI back off the disk, and a turn that did it twice
    would pay for that reading twice for one answer.

    Args:
      profile: What is written down about the backend.

    Returns:
      The window, in seconds. Zero or less for a watchdog turned off.
    """
    if said := os.environ.get(WATCHDOG, "").strip():
        with contextlib.suppress(ValueError):
            return float(said)
    return profile.silence


@contextlib.contextmanager
def held(agent: AgentBase) -> Generator[None]:
    """Stops the clock on every turn of an agent that is waiting on something else.

    An agent that has stopped to ask a person something has stopped working, and what it is
    waiting on is not its backend: the CLI is sitting there with nothing being asked of it.
    Counted as silence, a person taking a quarter of an hour over a permission prompt would
    have the healthy CLI behind it killed for the delay they caused.

    Every conversation of the agent rather than the one that asked, because the one that asked
    cannot always be named: a backend driven through an app server asks its client from a
    reader of its own, on behalf of whichever of its threads is running.

    Args:
      agent: The agent that has stopped.

    Yields:
      Nothing; every clock starts again, where it was, at the end of the block.
    """
    with contextlib.ExitStack() as holding:
        for session in agent.sessions:
            watch = session._watching
            if watch is not None:
                holding.enter_context(watch.held())
        yield


def _profiled(backend: str) -> backends.Profile:
    """What is written down about a backend, or what is assumed about an unwritten one.

    Args:
      backend: What the CLI is called.

    Returns:
      Its profile, or the one standing for a backend nobody has written down -- which is
      every CLI added through the agent client protocol, since that is a command and a
      promise and nothing else.
    """
    return backends.named(backend) or backends.UNKNOWN


def _under(proc: subprocess.Popen[str]) -> list[psutil.Process]:
    """Everything a process has started, taken down by name before it is signalled.

    By name and in advance because a child outlives the parent it is reparented away from:
    once the CLI has gone, nothing can ask what was under it, and what was under it is what
    still holds the pipe the turn is blocked on.

    Args:
      proc: The process whose children to take down.

    Returns:
      Them, and nothing at all where the system will not say.
    """
    with contextlib.suppress(psutil.Error, OSError):
        return psutil.Process(proc.pid).children(recursive=True)
    return []


def _living(kin: list[psutil.Process]) -> list[psutil.Process]:
    """Which of them are still running, a defunct one being neither alive nor in the way.

    Args:
      kin: What was under the process.

    Returns:
      The ones still there, which are the ones there is anything left to do about.
    """
    held: list[psutil.Process] = []
    for one in kin:
        with contextlib.suppress(psutil.Error, OSError):
            if one.is_running() and one.status() != psutil.STATUS_ZOMBIE:
                held.append(one)
    return held


class Watchdog:
    """The clock one turn is kept under, and the ladder climbed when it runs out.

    Used around the read loop of a turn, whichever shape that loop has::

        with Watchdog(session, riding=lambda: proc) as watch:
            for line in proc.stdout:
                watch.saw()
                ...

    `saw` is what says the backend is alive: it is called for anything the backend sends, a
    line that meant nothing included, since a CLI writing heartbeats is a CLI that has not
    wedged. Nothing else has to be done at the read: the failure a wedged turn ends with is
    put in place of whatever the freed read raised, on the way out of the block.
    """

    def __init__(
        self,
        session: SessionBase,
        *,
        riding: Callable[[], subprocess.Popen[str] | None] | None = None,
        window: float | None = None,
    ) -> None:
        """Initializes a watchdog over one turn, not yet ticking.

        Args:
          session: The conversation taking the turn. Its agent says which backend this is,
            which is what the windows and the ladder are read off; its own `interrupt` and
            transport are what the ladder reaches for.
          riding: What answers with the process this turn is riding, or None for a turn whose
            transport is not a process of its own -- an app server every conversation with the
            agent shares, or a runtime inside this interpreter. Asked each time rather than
            given the process, since a turn that restarts one is riding the new one.
          window: How long it may say nothing, overriding what the backend says. For a caller
            that already knows better; everything else takes the backend's own.
        """
        self._session = session
        self._riding = riding
        self._profile = _profiled(session._agent.backend)
        self._silence = window if window is not None else _window(self._profile)
        now = time.monotonic()
        #: When the backend last said anything, which is what a person is told about, and
        #: when the window now running started, which is what the ladder is timed by. Two
        #: clocks because each rung is given a window of its own to work in: a turn ended by
        #: being interrupted must not also be shot for taking a moment over it.
        self._spoke = now
        self._since = now
        self._granted = 0
        self._at = _Rung.LOOK
        #: How much processor time the tree under this turn had burned when it was last
        #: looked at. Seeded as the watchdog starts rather than left at nothing: a first
        #: window compared against a process's whole life would call every backend busy.
        self._busy = 0.0
        #: How many holders have the clock stopped, and since when. A turn waiting on a
        #: person, or on whatever is reading it, is not a turn waiting on its backend -- and
        #: fifteen minutes spent answering a permission prompt is not a wedge.
        self._holds = 0
        self._held = 0.0
        self._holding = threading.Lock()
        #: What was seen when the ladder started, which is the whole of the diagnostic.
        self._why = ""
        #: The process the ladder armed against, pinned rather than asked for again: a turn
        #: that failed is a turn retried, and the process behind the retry is not this one.
        self._doomed: subprocess.Popen[str] | None = None
        #: What was under that process when it was asked to go, taken down then rather than
        #: looked up later: a child outlives the parent it is reparented away from.
        self._kin: list[psutil.Process] = []
        #: What this turn is to fail with, once the watchdog has decided it is wedged. A
        #: `Failed` rather than a `Stopped`: a wedged CLI is worth another go, and a loop
        #: written against a failed turn is what takes it -- a stop is what such a loop is
        #: written to stop on. Not `Unrecoverable` either: the whole point is that the same
        #: prompt to a fresh transport works. The retry ladder inside the turn is not the
        #: one that walks -- a turn ended by hand is not a turn to take again under the next
        #: account -- so what takes it again is the flow, which reads this and knows why.
        self._verdict: Failed | None = None
        self._done = threading.Event()
        self._thread: threading.Thread | None = None

    def __enter__(self) -> Self:
        """Starts ticking, unless the window says there is to be no watchdog at all."""
        if self._silence <= 0:
            return self
        self._busy = self._burnt()
        # Filed on the session, so that whatever knows this turn is waiting on a person
        # rather than on its backend can find the clock and stop it. On the session rather
        # than on the thread: an app server asks its client from a reader of its own, and
        # the turn it is asking for is on a thread that thread has never heard of.
        self._session._watching = self
        self._thread = threading.Thread(
            target=self._watching,
            name=f"hmz-watchdog-{self._session._agent.backend}",
            daemon=True,
        )
        self._thread.start()
        return self

    def __exit__(
        self,
        kind: type[BaseException] | None,
        value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Stops ticking, and says what the watchdog did in place of what the read raised.

        Args:
          kind: The exception's class, unused: what matters is the instance.
          value: What came out of the block, or None for a turn that ended on its own.
          traceback: Where it came from, unused.

        Raises:
          subprocess.CalledProcessError: The watchdog's own verdict, where it intervened and
            the read then failed. The read fails with whatever the wreckage looked like --
            `exit status -9`, `stdout ended` -- and that sentence describes the killing rather
            than the wedge, so it is replaced by the one that says what actually happened.
        """
        del kind, traceback
        self._done.set()
        if self._session._watching is self:
            self._session._watching = None
        thread, self._thread = self._thread, None
        if thread is not None:
            thread.join(timeout=_STOPPING)
        # Whatever came out, unless it is a run ended by hand -- an SDK's own transport error
        # is as much the watchdog's doing as an exit status is, and a `Stopped` that became a
        # `Failed` here would be a stopped flow going round again. Nothing is replaced where
        # the watchdog never acted, and nothing at all where the turn answered anyway.
        if (
            self._verdict is not None
            and isinstance(value, Exception)
            and not isinstance(value, Stopped)
        ):
            raise self._verdict from value

    def saw(self) -> None:
        """The backend said something, so the clock starts again.

        Anything at all: this is liveness rather than progress, and a line that turned into no
        event is still a CLI that is awake. Ignored once the ladder is being climbed -- a
        backend that speaks up while it is being interrupted is a backend being interrupted,
        and un-escalating there would leave the turn half stopped and running again.
        """
        if self._at is _Rung.LOOK:
            now = time.monotonic()
            self._spoke = now
            self._since = now
            self._granted = 0

    @contextlib.contextmanager
    def held(self) -> Generator[None]:
        """Stops the clock while the turn waits on something that is not its backend.

        A turn stopped to ask a person, or handed to whoever is reading it, is not a turn its
        backend owes anything: the CLI is sitting there answering nothing because nothing has
        been asked of it yet. Counted as silence, a person taking a quarter of an hour over a
        permission prompt would have the healthy CLI behind it killed.

        Yields:
          Nothing; the clock starts again, where it was, at the end of the block.
        """
        with self._holding:
            self._holds += 1
            if self._holds == 1:
                self._held = time.monotonic()
        try:
            yield
        finally:
            with self._holding:
                self._holds -= 1
                if self._holds == 0:
                    # Moved forward rather than restarted: what the backend owes is measured
                    # from when it last spoke, less whatever of that was spent on us.
                    over = time.monotonic() - self._held
                    self._spoke += over
                    self._since += over

    def wedged(self) -> Failed | None:
        """What the watchdog decided, for a caller that ends the turn its own way.

        Returns:
          The failure this turn is to end with, or None while nothing has gone wrong.
        """
        return self._verdict

    def _watching(self) -> None:
        """Ticks until the turn is over, taking one step each time the window runs out."""
        while not self._done.wait(_TICK):
            if time.monotonic() - self._since < self._silence:
                continue
            if self._holds:
                continue  # the turn is waiting on us rather than on its backend
            # Each rung gets a window of its own to work in: a turn that ends because it
            # was interrupted must not also be shot for taking a moment over it.
            self._since = time.monotonic()
            if self._done.is_set():
                # The turn ended between the wait and here. Anything done now would be done
                # to the next turn's process, which is the one thing worse than doing nothing.
                return
            self._at = self._stepped()
            if self._at is _Rung.SPENT:
                return

    def _stepped(self) -> _Rung:
        """Takes the next step against a turn that has said nothing for a whole window.

        Returns:
          The rung to be on afterwards.
        """
        if self._at is _Rung.LOOK:
            return self._looked()
        if self._at is _Rung.INTERRUPT:
            return self._interrupted()
        if self._at is _Rung.DROP:
            return self._dropped()
        return self._killed()

    def _looked(self) -> _Rung:
        """Looks at the process before believing the turn is wedged.

        Thinking and spinning both say nothing, and the one thing that tells them apart from
        out here is what the machine is doing: a tree burning processor time is working at
        something, and a process that is stopped, defunct or gone is working at nothing. So
        the first step is to look rather than to intervene -- and to say what was seen, since
        the thing being fixed is a turn nobody could see waiting.

        Returns:
          The rung to be on afterwards: this one again for a turn given more time, and the
          one that frees the read for a process that has already ended -- asking a dead CLI
          to stop would spend a whole window on nothing.
        """
        state = self._state()
        if state is _State.WORKING and self._granted < _GRANTS:
            self._granted += 1
            self._says(f"has said nothing for {self._quiet()} but is still working")
            return _Rung.LOOK
        # What was seen goes in front of the silence, where there was anything to see: a
        # turn on a shared server has no process of its own, and "codex has no process" is a
        # sentence about this file rather than about what went wrong.
        seen = "" if state is _State.NONE else f"{state.value} and "
        self._why = f"{seen}has said nothing for {self._quiet()}"
        # Said now, not once the read finally unblocks: the point of the whole file is that
        # the read may not unblock for another window, and a person watching a stall has to
        # be told it has been seen at the moment it is seen. What the turn *fails* with is
        # decided by the rung that actually does something -- a CLI that crashed with a
        # diagnostic of its own must keep it, this having had no part in that.
        self._says(self._why)
        return _Rung.DROP if state is _State.GONE else _Rung.INTERRUPT

    def _interrupted(self) -> _Rung:
        """Asks the turn to stop, which is the gentlest thing that ends a wedged one.

        Returns:
          The rung to be on afterwards, which is the next one at once for a backend with no
          way of being asked: a window spent waiting for something that was never sent is a
          window a person spends watching nothing happen.
        """
        why = f"no output for {self._quiet()}"
        # Said before the asking rather than after it: asking is what frees the read, so the
        # turn's own thread may be out of it and reading why it stopped before this line
        # would otherwise have run -- and a turn that finds itself cut off by nobody in
        # particular answers with what a cut-off leaves, which here is nothing at all.
        self._session._wedged = True
        try:
            self._session.interrupt(why=why)
        except NotImplementedError:
            self._says("cannot be interrupted, so its transport goes instead")
            return self._dropped()
        except Exception as refused:  # noqa: BLE001  -- a rung that fails is still a rung
            self._says(
                f"would not be interrupted ({refused}); its transport goes instead"
            )
            return self._dropped()
        self._says(f"was asked to stop: {why}")
        self._verdicts()
        return _Rung.DROP

    def _dropped(self) -> _Rung:
        """Puts the transport down, which is what actually frees a read blocked on it.

        Returns:
          The rung to be on afterwards.
        """
        if not self._profile.restarts:
            # Nothing here may put this one down: whatever holds the turn open is somebody
            # else's, and reaching into it from a second thread breaks more than it frees.
            # No verdict either -- a turn nothing was done to keeps whatever it fails with.
            self._says("cannot have its transport restarted here, so the turn is left")
            return _Rung.SPENT
        proc = self._process()
        if proc is None or self._profile.shares:
            # Through the session, either because there is no process of this turn's own or
            # because the one behind it is the server every conversation with the agent is
            # on: signalling that would end this turn by ending its siblings' turns from
            # underneath them, where the session knows how to put its own server down.
            self._says(
                f"is not answering; putting {self._transport()} down{self._carried()}"
            )
            if self._done.is_set():
                return _Rung.SPENT
            self._verdicts()
            # Whatever it raises, it raised on the way out: a transport that will not go
            # down tidily is one the next rung kills, and a watchdog thread that died here
            # is a watchdog that has stopped watching.
            with contextlib.suppress(Exception):
                self._session._lets_go()
            return _Rung.KILL
        # Signalled rather than shut through the session: the turn's own thread is sitting in
        # this process's pipe, and closing a stream out from under a blocked reader is how one
        # hang becomes two. The signal gives it EOF, and the turn tidies up after itself.
        self._says(f"is not answering; ending it{self._carried()}")
        if self._done.is_set():
            # The turn ended while that was being said. The next turn's process is not this
            # turn's to shoot, and the retry ladder has very likely already started one.
            return _Rung.SPENT
        self._verdicts()
        # Pinned, so the rung after this one ends what this one asked to go rather than
        # whatever the session happens to be holding by then.
        self._doomed = proc
        self._kin = _under(proc)
        for one in self._kin:
            # What it started holds the same pipe: a CLI killed over a child still writing
            # into stdout leaves the read exactly as blocked as it was.
            with contextlib.suppress(psutil.Error, OSError):
                one.terminate()
        with contextlib.suppress(OSError):
            proc.terminate()
        return _Rung.KILL

    def _killed(self) -> _Rung:
        """Kills what is left, for a process that took the polite signal and stayed.

        Returns:
          `SPENT`: there is nothing after this. A read still blocked past a killed process
          tree is blocked on something this cannot reach, and a ladder that went round again
          would be the busy loop it was built to stop.
        """
        proc, left = self._doomed, _living(self._kin)
        if not left and (proc is None or proc.poll() is not None):
            return _Rung.SPENT  # it went when it was asked, which is the end of it
        self._says("did not go when it was asked; killing it and everything under it")
        for one in left:
            with contextlib.suppress(psutil.Error, OSError):
                one.kill()
        if proc is not None:
            with contextlib.suppress(OSError):
                proc.kill()
            with contextlib.suppress(OSError):
                proc.wait()  # reaped rather than killed, as everything else here reaps
        return _Rung.SPENT

    def _state(self) -> _State:
        """What the process behind this turn is doing, as far as the machine will say.

        Returns:
          Its state. `NONE` for a turn riding no process of its own, and `GONE` for one whose
          process the system will no longer answer about -- a process that cannot be looked at
          is not one to go on waiting for.
        """
        proc = self._process()
        if proc is None:
            return _State.NONE
        if proc.poll() is not None:
            return _State.GONE
        try:
            one = psutil.Process(proc.pid)
            with one.oneshot():
                status = one.status()
                busy = sum(one.cpu_times()[:2])
            # And everything under it: a CLI that shells out sits doing nothing while the
            # build it started does the work, and that is a turn to leave alone.
            for child in one.children(recursive=True):
                with contextlib.suppress(psutil.Error, OSError):
                    busy += sum(child.cpu_times()[:2])
        except (psutil.Error, OSError):
            return _State.GONE
        if status in (psutil.STATUS_ZOMBIE, psutil.STATUS_DEAD):
            return _State.GONE
        if status == psutil.STATUS_STOPPED:
            return _State.STOPPED
        spent, self._busy = busy - self._busy, busy
        # A shared server is busy on its siblings' turns as well as on this one, so this
        # reads as working while any conversation with the agent is. Patience where the
        # answer is not certain is the mistake to make: a wedge noticed a window late costs
        # a window, and a turn shot for a sibling's silence costs the work.
        return _State.WORKING if spent >= _BUSY else _State.IDLE

    def _process(self) -> subprocess.Popen[str] | None:
        """The process this turn is riding, or None where it is riding none it can see."""
        return self._riding() if self._riding is not None else None

    def _burnt(self) -> float:
        """How much processor time the tree behind this turn has spent in its whole life.

        Returns:
          The seconds, and nothing at all for a turn with no process to ask about.
        """
        proc = self._process()
        if proc is None:
            return 0.0
        burnt = 0.0
        with contextlib.suppress(psutil.Error, OSError):
            one = psutil.Process(proc.pid)
            burnt = sum(one.cpu_times()[:2])
            for child in one.children(recursive=True):
                with contextlib.suppress(psutil.Error, OSError):
                    burnt += sum(child.cpu_times()[:2])
        return burnt

    def _transport(self) -> str:
        """What is about to be put down, in words that say who else it belongs to."""
        if self._profile.shares:
            return "the server every conversation with this agent shares"
        return "what was holding the conversation open"

    def _carried(self) -> str:
        """What becomes of the conversation once its transport has gone."""
        if self._profile.resumes and self._session._id:
            return f"; {self._session._id} is picked back up on the next try"
        return "; the conversation starts again from nothing"

    def _quiet(self) -> str:
        """How long it has been since the backend last said anything, in words."""
        return f"{time.monotonic() - self._spoke:.0f}s"

    def _verdicts(self) -> None:
        """Writes down what this turn is to fail with, having done something about it.

        Called by the rung that acts rather than by the one that looks. A turn nothing was
        done to keeps whatever it fails with -- a CLI that crashed with a diagnostic of its
        own says something a person can act on, and replacing it with "the watchdog stopped
        this turn" would be this file taking the credit for somebody else's failure.
        """
        backend = self._session._agent.backend
        self._verdict = Failed(
            1, [backend], "", f"the watchdog stopped this turn: {backend} {self._why}"
        )
        # And said on the session, where the turn's own reader is: what a turn cut off by a
        # budget or by a person answers with is what the agent had said, and this turn's
        # backend had stopped saying anything. So this one fails rather than answering.
        self._session._wedged = True

    def _says(self, what: str) -> None:
        """Puts one step of the ladder on the stream this turn is being read from.

        As the retries and the fallbacks say themselves, and for the same reason: what a flow
        can see is what it can act on, and an agent quietly restarted under a watcher is a
        watcher reading a lie.

        Args:
          what: The step, said of the backend.
        """
        self._session._heard(
            Event(kind="tool", text=f"{self._session._agent.backend} {what}")
        )
