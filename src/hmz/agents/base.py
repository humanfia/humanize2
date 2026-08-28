"""The base classes: an agent is structure, a session is the history that structure runs on."""

# A session and the agent holding it are two halves of one object declared in one
# file, which is what the underscore keeps out of the package rather than out of them.
# pyright: reportPrivateUsage=false

from __future__ import annotations

import contextlib
import functools
import json
import os
import queue
import re
import subprocess
import sys
import threading
import time
import uuid
import weakref
from abc import ABC, abstractmethod
from collections import Counter, deque
from concurrent.futures import ThreadPoolExecutor
from typing import IO, TYPE_CHECKING, Any, ClassVar, Literal, Protocol, Self, overload

from .event import Event, Failed, Question, Stopped, Unrecoverable, Usage, say
from .hooks import EVERYWHERE, Hooks, Moment, Occasion, Verdict
from .skills import Loaded, mount, unmount

if TYPE_CHECKING:
    import asyncio
    from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence

    from pydantic import BaseModel

    from hmz.coganchor import AnchorConfig
    from hmz.machines import MachineConfig
    from hmz.providers import Provider

    from .config import AgentConfig


class Journal(Protocol):
    """Where an agent writes down a session it opened, which is the run it is part of.

    Named rather than imported: a run is written out of the agents it drove, so naming the
    run from here would be a circle. This is the whole of what an agent asks of one, and
    :class:`hmz.cycle.Cycle` is what answers to it.
    """

    def opened(self, agent: AgentBase, session: str) -> None:
        """Writes down a session one of the agents has just opened."""
        ...


def _tee(
    source: IO[str],
    sink: IO[str] | None,
    captured: list[str],
    said: queue.Queue[Event | None] | None = None,
    reads: Callable[[str], Iterable[Event]] | None = None,
) -> None:
    """Copies `source` into `sink` line by line, keeping every line and announcing it.

    A sink that has gone away stops the copying but not the reading: a pipe nobody drains
    blocks the agent writing to it, and the turn would then be waiting on an agent that is
    itself waiting. A sink of None is a stream that is not to be copied anywhere at all --
    one carrying a protocol rather than the agent talking -- and is read and kept just the
    same. The None at the end is how a turn reading `said` knows this stream is spent; a
    stream nobody is reading events from is drained and kept all the same.
    """
    with contextlib.suppress(OSError, ValueError):
        # A source closed under us is a process that has ended, which is not a failure here.
        for line in source:
            captured.append(line)
            if said is not None and reads is not None:
                for event in reads(line):
                    said.put(event)
            if sink is not None:
                say(line, sink, end="")
    with contextlib.suppress(OSError, ValueError):
        source.close()  # the reader closes what it read, whoever else has finished with it
    if said is not None:
        said.put(None)


def _reaped(proc: subprocess.Popen[str]) -> None:
    """Ends a process and takes its exit status, so that neither is left behind.

    Killed and then waited on, rather than killed: a process nobody waits on stays in the
    table as a zombie until whoever started it exits, and a flow that opens a session per turn
    would gather one per turn for as long as it runs. A process that has already ended is
    waited on all the same, since that is what takes its status.

    Args:
      proc: The process to end, which may already have ended.
    """
    with contextlib.suppress(OSError):
        proc.kill()
    with contextlib.suppress(OSError):
        proc.wait()


#: What a turn is told when its backend has no way of being held to a shape. The schema is the
#: whole of the instruction: it says the fields, their types and which of them are required,
#: and a sentence restating any of that would be a second place for it to be wrong.
_IN_SHAPE = """

Answer with JSON and nothing else -- no prose around it, no code fence -- matching this JSON \
Schema exactly:

{schema}
"""

#: What a model wraps an answer in when it is talking as well as answering.
_FENCED = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


def _readings(said: str) -> Iterator[str]:
    """Every part of an answer that might be the JSON it was asked for, likeliest first.

    A backend held to a schema answers with the object and nothing else, and that is the first
    of these. The rest are for one that was asked rather than held: a fenced block, and the
    span from the first brace to the last, which is the object with the talking cut off.

    Args:
      said: The whole answer.

    Yields:
      What to try reading, in the order to try it.
    """
    held = said.strip()
    yield held
    for block in _FENCED.findall(held):
        yield str(block).strip()
    first, last = held.find("{"), held.rfind("}")
    if 0 <= first < last:
        yield held[first : last + 1]


def _shaped[T: BaseModel](said: str, schema: type[T]) -> T:
    """Reads what a turn answered as the model it was asked to answer with.

    Args:
      said: The whole answer.
      schema: The shape it was asked for.

    Returns:
      The answer, as that model.

    Raises:
      ValueError: If none of the answer reads as one -- which is a turn that did not do what
        it was asked, and is reported as such rather than passed on half-read.
    """
    from pydantic import ValidationError

    for reading in _readings(said):
        with contextlib.suppress(ValidationError, ValueError):
            return schema.model_validate_json(reading)
    raise ValueError(f"the turn did not answer as a {schema.__name__}: {said[:200]}")


def _lands[T](landed: asyncio.Future[T], answered: T) -> None:
    """Hands a thread's answer to whoever awaited it, unless nobody is waiting any more."""
    if not landed.done():  # a task that was cancelled is not one to answer
        landed.set_result(answered)


def _failed(landed: asyncio.Future[Any], why: BaseException) -> None:
    """Raises a thread's failure where it was awaited, unless nobody is waiting any more."""
    if not landed.done():
        landed.set_exception(why)


def _posted(
    loop: asyncio.AbstractEventLoop, what: Callable[..., None], *said: Any
) -> None:
    """Says something back to a loop from the thread that was working for it.

    A loop that has gone takes nothing more: the flow that was awaiting this went with it,
    and a thread that raised on its way to a closed loop would only put a traceback on the
    terminal a run is watched from.

    Args:
      loop: The loop to say it to.
      what: What to call there.
      said: What to call it with.
    """
    with contextlib.suppress(RuntimeError):
        loop.call_soon_threadsafe(what, *said)


async def _awaited[T](call: Callable[[], T], named: str) -> T:
    """Runs one blocking call on a thread of its own, so the loop is free while it takes.

    A turn is minutes of waiting on a process, and a flow that ran one on its own event loop
    would hold up every other turn it has going for as long as that one took. So a turn takes
    a thread and gives the loop back: ten thousand of them at once are ten thousand coroutines
    over as many threads as are actually running, which is what waiting on a process costs.

    A thread cannot be taken back, so a task cancelled while it waits here stops waiting and
    leaves the turn to finish -- which is what stopping the agent is for.

    Args:
      call: What to run, which is the turn as the flow asked for it.
      named: What to call the thread, so that a wide run says whose turn each of them is.

    Returns:
      Whatever the call answered.
    """
    import asyncio

    loop = asyncio.get_running_loop()
    landed: asyncio.Future[T] = loop.create_future()

    def carry() -> None:
        try:
            answered = call()
        except BaseException as why:  # noqa: BLE001 -- carried across, not handled
            _posted(loop, _failed, landed, why)
        else:
            _posted(loop, _lands, landed, answered)

    threading.Thread(target=carry, name=named, daemon=True).start()
    return await landed


def _at_once(asked: int, of: int) -> int:
    """How many of a batch run at once: what it asked for, or all of them where it said none.

    Args:
      asked: What the caller said, or 0 for as many as there are -- a flow that asks for a
        thousand answers has asked for a thousand turns, and pacing them behind a number
        nobody chose would be this library deciding how wide a fan-out may be.
      of: How many there are.

    Returns:
      A count of at least one, since a pool of no threads runs nothing.
    """
    return max(min(asked, of) if asked > 0 else of, 1)


#: How far back a rate is measured unless something asks for another window. Five minutes is
#: long enough to carry across the gaps a flow leaves -- a turn that thinks, a round it sleeps
#: off, a commit it makes -- and short enough that a run which has gone quiet reads as quiet.
#: The same window the interface's own readout is over, so that a flow reading a rate and a
#: person watching one are reading the same number.
WINDOW = 300.0


class Meter:
    """What has been spent and when, so that a rate can be read off it.

    Written from whichever thread a turn is running on and read from whichever thread is
    asking, so every touch of it is under the lock. What goes in is what one request to the
    model cost, as its backend reports it -- an addition rather than a total, since a total
    read twice would count the first of it twice.
    """

    def __init__(self) -> None:
        """Initializes a meter that has seen nothing spent."""
        self._lock = threading.Lock()
        self._total: Counter[str] = Counter()
        #: Recent spending as (when, what, whether it was a turn of the model), bounded by
        #: the window rather than by the length of the run: a flow going for days keeps five
        #: minutes of it.
        self._recent: deque[tuple[float, Usage, bool]] = deque()
        self._began = time.monotonic()

    def spend(
        self, usage: Usage, now: float | None = None, *, turn: bool = True
    ) -> None:
        """Notes what one request to the model cost.

        Args:
          usage: What it cost, by kind.
          now: When, defaulting to this moment. Given only so a test can say.
          turn: Whether this is a turn of the model rather than a correction to the ones
            already counted. A backend that states a turn's whole cost after having said what
            each request in it came to is settling up, not taking another turn -- and counting
            it as one would put a turn in the average that never happened.
        """
        if not usage.total:
            return
        moment = time.monotonic() if now is None else now
        with self._lock:
            self._total.update(usage)
            self._recent.append((moment, usage, turn))
            # Cut down as it is written rather than only when somebody reads a rate: an
            # agent driving ten thousand sessions is told what every request of every one of
            # them cost, and a run nobody is watching would otherwise keep all of it for as
            # long as it ran. What is kept is the window, which is what this deque is.
            while self._recent and self._recent[0][0] < moment - WINDOW:
                self._recent.popleft()

    def spent(self) -> Usage:
        """Everything spent so far, by kind.

        Returns:
          The whole of it, `input` and `output` always among the kinds even where nothing has
          gone on them: those two are what every backend counts, so a reader of one of these
          need not ask whether they are there.
        """
        with self._lock:
            return Usage({"input": 0.0, "output": 0.0} | dict(self._total))

    def rate(self, over: float = WINDOW, now: float | None = None) -> Usage:
        """How fast it is being spent, by kind, over the last stretch of it.

        Seconds on the clock rather than seconds an agent was talking: a flow sleeps between
        rounds, commits, reads what the last turn wrote, and that time is time the tokens were
        spent over. A window longer than the run itself is the run itself, so a rate read a
        minute in is what that minute came to rather than a fifth of it.

        Args:
          over: How far back to measure, in seconds.
          now: The moment to measure at, defaulting to this one. Given only so a test can say.

        Returns:
          Tokens a second, by kind, with `input` and `output` always among them.
        """
        moment = time.monotonic() if now is None else now
        window = max(over, 0.0)
        with self._lock:
            while self._recent and self._recent[0][0] < moment - window:
                self._recent.popleft()
            lately = Usage({"input": 0.0, "output": 0.0})
            for _, usage, _ in self._recent:
                lately = lately + usage
            return lately / min(window, max(moment - self._began, 0.0))

    def juice(self, over: float = WINDOW, now: float | None = None) -> float:
        """What an average turn of the model came out with, over the last stretch of the run.

        A turn of the model rather than a turn of the flow: one request and the answer to it,
        of which the work a flow asks for is many. How much of an answer that comes to is what
        the effort a model runs at moves -- so it is the number to steer by when what is being
        held is how hard the thing is thinking, rather than how fast a bill is running up.

        Args:
          over: How far back to measure, in seconds.
          now: The moment to measure at, defaulting to this one. Given only so a test can say.

        Returns:
          Output tokens per turn, and nothing at all where no turn has landed in the window --
          which reads as nothing to go on rather than as a turn that said nothing.
        """
        moment = time.monotonic() if now is None else now
        window = max(over, 0.0)
        with self._lock:
            while self._recent and self._recent[0][0] < moment - window:
                self._recent.popleft()
            turns = sum(1 for _, _, taken in self._recent if taken)
            if not turns:
                return 0.0
            return sum(usage.output for _, usage, _ in self._recent) / turns


class SessionBase(ABC):
    """One conversation with one agent, kept alive across turns.

    The first turn opens the backend session; every later one resumes it, so the agent
    still has the earlier turns in context. Discarding the session is how a flow forgets:
    a new instance starts from nothing.
    """

    #: Whether this backend can be held to a shape, rather than asked to keep to one. A
    #: session that can is handed the schema itself, and answers with the object or not at
    #: all; one that cannot is told about it in the prompt, which is the same question put
    #: where the model is still free to answer around it.
    shapes: ClassVar[bool] = False

    def __init__(
        self, agent: AgentBase, cwd: str | os.PathLike[str] | None = None
    ) -> None:
        """Initializes an unopened session and registers it with its agent.

        Args:
          agent: The agent whose config every turn of this session runs at.
          cwd: The directory this conversation works in, or None for the one the flow is
            running in. A directory rather than a turn's argument because that is what it is
            to these backends: a session is opened at a directory and every turn of it is
            there, which is what lets a flow drive one conversation per worktree at once. For
            an agent whose turns land on another machine it is that machine's path, and must
            be inside the workspace the anchor names.
        """
        self._agent = agent
        #: Which of the flow's skills this conversation carries, by name, or None for every
        #: one of them -- which is what a session nobody has said anything about carries. It
        #: is the session's rather than the agent's because it is the one thing about what an
        #: agent works by that changes while it is working: a conversation that has got as
        #: far as writing the tests wants the skill about writing them and no longer wants
        #: the eight about reading the codebase, and it is the same conversation either way.
        self._skills: tuple[str, ...] | None = None
        #: And which of them are actually down in the workspace now, or None while none are.
        #: The two differ for exactly as long as it takes the next turn to start, which is
        #: where what was asked for is put where the backend reads it.
        self._mounted: tuple[str, ...] | None = None
        #: The conversation on the agent this one falls back to, once a turn of this one has
        #: had to be taken there. Held for as long as this session is rather than opened per
        #: turn: what this conversation was is lost at the move, and losing a second one
        #: every turn after it would be a stateful loop started over every round.
        self._moved_to: SessionBase | None = None
        #: Where this conversation works, as it was given, or None for wherever the flow is.
        self._cwd = os.fspath(cwd) if cwd is not None else None
        self._id: str | None = None
        #: What this conversation is to think at from its next turn on, where it has been
        #: told something other than what its agent runs at, and None where it has not.
        self._effort: str | None = None
        #: What this conversation has cost and how fast, written as the backend says what
        #: each request came to rather than once the turn is over: a turn is minutes long,
        #: and a rate that stood still for all of them would be a rate of nothing.
        self._meter = Meter()
        #: A conversation is a sequence: one turn at a time, whoever asked for them. Held
        #: for the whole of a turn -- the moments it fires and the events it says as well as
        #: what the backend is told -- so that two threads on one session are two turns one
        #: after the other rather than two halves of a turn each. Re-entrant because a
        #: backend takes it again where it drives its own process, which is the same turn.
        self._lock = threading.RLock()
        #: Whether a turn has been started in this session, and whether it has been closed:
        #: the two moments that bracket a conversation are each said once.
        self._started = False
        self._ended = False
        #: Every word put into a turn that the agent has not yet said it has, under whatever
        #: the backend will name it by when it does. Written by whoever is talking to the
        #: agent and read by whoever is reading it back, which are two threads, so it is held
        #: under a lock of its own rather than under the one that serializes turns.
        self._steered: dict[str, str] = {}
        self._steering = threading.Lock()
        #: Which account whatever this session is holding open was started under, or None
        #: while it is holding nothing. A process, a link or a runtime carries an account's
        #: environment and its credential paths, and neither changes under one that is
        #: already up -- so a session that has moved account starts another rather than
        #: speaking to the one it has. Read and written on the thread taking the turn.
        self._as: str | None = None
        #: The shape the turn now running was asked to answer in, or None for one asked for
        #: nothing in particular. Written under the lock that serializes the turns and read
        #: by whatever builds the call, since a command line and a process's own arguments
        #: are both built from a session that is already holding the turn.
        self._shaping: type[BaseModel] | None = None
        #: What takes away what this session mounted, once it has mounted anything. However
        #: the session ends -- closed, or let go of by a flow that opens one a turn -- what it
        #: put in the workspace goes with it, so it is a finalizer rather than a line in
        #: `close`: a Ralph loop drops a session a turn and closes none of them.
        self._unmounting: Callable[[], None] | None = None
        #: Whether a turn of this session is running now. Read by `close`, which is what a stop
        #: reaches and so is called from another thread while a turn is under way: what the
        #: turn is working by is not taken away underneath it.
        self._working = False
        # A session drops itself from its agent when it is collected, so the agent neither holds
        # a flow's discarded sessions nor has to prune them while someone is reading them.
        agent._hold(self)

    @property
    def skills(self) -> tuple[str, ...]:
        """The flow's skills this conversation carries, by name, in the flow's own order.

        Every one the flow brought unless this session has been told otherwise, which is what
        a session nobody has said anything about carries. A name this session was told to
        carry that the flow does not bring is not among them: what a session may carry is the
        flow's to say, and a name nothing answers to is a name to correct rather than a skill
        to invent.
        """
        brought = self._agent.loaded
        if self._skills is None:
            return tuple(one.name for one in brought)
        wanted = set(self._skills)
        return tuple(one.name for one in brought if one.name in wanted)

    def loads(self, skills: Iterable[str] | None) -> None:
        """Says which of the flow's skills this conversation is to carry from its next turn.

        The one thing about what an agent works by that a flow may change while it is
        working, and it is a session's rather than an agent's: an agent is what it was set up
        as, and a conversation is a thing that gets somewhere. A loop that has finished
        reading and started writing says so here, and the turn after it is the turn that
        carries the writing skill.

        What is put where the backend reads it is settled at the start of the next turn
        rather than now: a session is opened at a directory and may not have one yet, and a
        turn already running must not have what it is working by moved underneath it.

        Args:
          skills: The names to carry, which are the names the flow brought them under, or
            None for every one of them. Names the flow does not bring are ignored, so a
            session that asked for one a fork of the flow no longer has is a session carrying
            the rest rather than a turn that will not run.
        """
        self._skills = None if skills is None else tuple(dict.fromkeys(skills))

    @property
    def id(self) -> str:
        """The backend's id for this conversation, which every turn after the first resumes.

        Raises:
          RuntimeError: If no turn has landed yet, so the backend has not named the session.
        """
        if self._id is None:
            raise RuntimeError("session has not run a turn yet")
        return self._id

    @property
    def named(self) -> str | None:
        """What the backend calls this conversation, as soon as it has called it anything.

        Which is earlier than :attr:`id`: a session is opened by a turn that lands in it, and
        the backend names it when the turn starts. Between those two is the whole of the first
        turn -- the minutes of it, and the log the backend is writing all the while.

        Returns:
          The backend's id, or None before the backend has said one.
        """
        return self._id

    def spent(self) -> Usage:
        """What this conversation has cost so far, by the kind of token it went on.

        Returns:
          Every kind its backend counts, `input` and `output` among them whatever it counts
          besides. What it comes to is the whole of what has crossed the wire for this
          session, which is what the backend has said each request cost added up.
        """
        return self._meter.spent()

    def rate(self, over: float = WINDOW) -> Usage:
        """How fast this conversation is spending, by kind, over the last stretch of it.

        `session.rate().output` is output tokens a second, over seconds on the clock rather
        than seconds the agent was talking -- the same reckoning the interface's own readout
        is, so that a flow and a person watching it are reading the same thing.

        Args:
          over: How far back to measure, in seconds. The whole run where it is younger than
            that, so a rate read a minute in is what that minute came to.

        Returns:
          Tokens a second, by kind.
        """
        return self._meter.rate(over)

    def juice(self, over: float = WINDOW) -> float:
        """What an average turn of the model came out with, over the last stretch of it.

        A turn of the model, not a turn of the flow: one request and the answer to it, of
        which a turn a flow asks for is many. It is what an effort moves -- a model asked to
        think harder writes more per answer, and takes longer over it -- so this is the number
        to steer by when what is being held is how hard it is thinking.

        Args:
          over: How far back to measure, in seconds.

        Returns:
          Output tokens per turn, and 0.0 where no turn has landed in the window.
        """
        return self._meter.juice(over)

    def _spends(self, usage: Usage, *, turn: bool = True) -> None:
        """Notes what one request of the turn now running cost, as its backend says.

        Told as the turn goes rather than once it is over: a turn is minutes long, and what a
        flow steering by a rate needs is the rate while the turn is still running. Both meters
        are told, so that an agent whose sessions a loop drops one a turn still has the run.

        Args:
          usage: What that request cost, by kind.
          turn: Whether it is a turn of the model rather than a settling up of the ones
            already counted, as for :meth:`Meter.spend`.
        """
        self._meter.spend(usage, turn=turn)
        self._agent._meter.spend(usage, turn=turn)

    @property
    def effort(self) -> str:
        """How hard the next turn of this conversation is to think.

        What the agent runs at, unless this conversation has been told otherwise. A flow may
        say so while the session is running -- an hour into a Ralph loop, watching what it is
        costing -- and the backend is asked for it from the next turn on. The turn already
        under way keeps the effort it started at: a model does not think harder halfway
        through an answer, and a flow that changed it mid-turn would be describing a turn that
        never happened.
        """
        return self._effort or self._agent.effort

    @effort.setter
    def effort(self, effort: str) -> None:
        """Has this conversation think at something other than what its agent runs at.

        Args:
          effort: The backend's own word for it, or "" to go back to the agent's.
        """
        self._effort = effort or None

    @overload
    def __call__(self, prompt: str, *, suppress: bool = False) -> str: ...

    @overload
    def __call__[T: BaseModel](
        self, prompt: str, *, suppress: bool = False, schema: type[T]
    ) -> T | None: ...

    def __call__[T: BaseModel](
        self, prompt: str, *, suppress: bool = False, schema: type[T] | None = None
    ) -> str | T | None:
        """Sends one turn, opening the session on the first call and resuming it after.

        Args:
          prompt: The input prompt for this turn.
          suppress: Whether a turn that fails answers with nothing instead of raising. A flow
            is a loop, and a loop that catches its own turns is `try` around every line of
            it; this is the `|| true` that flowbench writes beside each one.
          schema: The shape to answer in, as the pydantic model a flow reads the answer as, or
            None to take what the agent says as it says it. A turn asked for one answers with
            that model rather than with text, so a flow that needs a decision reads a field
            instead of a marker at the end of a paragraph.

        Returns:
          The response generated by the agent, stripped -- or the model it was asked for,
          where it was asked for one. Nothing at all for a turn that failed, or one whose
          answer is not the shape it was asked for, while `suppress` was set: "" without a
          schema, and None with one.

        Raises:
          subprocess.CalledProcessError: If the turn fails and `suppress` is not set, with
            whatever the backend said about it attached as a diagnostic.
          ValueError: If a turn asked for a shape did not answer in it, and `suppress` is not
            set. An answer that is not what was asked for is a turn that did not do what it
            was told, which is a failed turn however cleanly the backend exited.
          Stopped: If the agent has been told to take no further turn -- which `suppress`
            does not cover, since a loop that carried on past it would never end.
          Unrecoverable: If the turn failed for a reason no other try could come out
            differently on, which `suppress` does not cover either and for the same reason: a
            loop that went round again would meet the same failure every time.
        """
        said = ""
        try:
            for event in self.stream(prompt, schema=schema):
                if event.kind == "result":
                    said = event.text
        except Unrecoverable:
            # Not covered by `suppress`, for the reason `Stopped` is not: a loop that carried
            # on past a turn no other try could come out differently on would go round on the
            # same failure until somebody stopped it. A conversation longer than the model
            # takes is that long on the next round too.
            raise
        except subprocess.CalledProcessError:
            if not suppress:
                raise
            return None if schema is not None else ""
        if schema is None:
            return said.strip()
        try:
            return _shaped(said, schema)
        except ValueError:
            if not suppress:
                raise
            return None

    @overload
    async def aturn(self, prompt: str, *, suppress: bool = False) -> str: ...

    @overload
    async def aturn[T: BaseModel](
        self, prompt: str, *, suppress: bool = False, schema: type[T]
    ) -> T | None: ...

    async def aturn[T: BaseModel](
        self, prompt: str, *, suppress: bool = False, schema: type[T] | None = None
    ) -> str | T | None:
        """The same turn as :meth:`__call__`, awaited: `await session.aturn(prompt)`.

        For a flow written as `async def run`, which is how one drives many conversations at
        once: the turn runs on a thread of its own and the loop is handed back, so the other
        conversations keep going while this one thinks. The session is still a sequence -- two
        turns awaited on one session are one after the other, as two called on it are.

        Args:
          prompt: The input prompt for this turn.
          suppress: Whether a turn that fails answers with nothing, as for :meth:`__call__`.
          schema: The shape to answer in, as for :meth:`__call__`.

        Returns:
          What :meth:`__call__` would have answered with.
        """
        if schema is None:
            return await _awaited(
                lambda: self(prompt, suppress=suppress), f"{self._agent.id}-turn"
            )
        return await _awaited(
            lambda: self(prompt, suppress=suppress, schema=schema),
            f"{self._agent.id}-turn",
        )

    async def apursue(
        self,
        objective: str,
        *,
        suppress: bool = False,
        context: str | None = None,
    ) -> str:
        """The same goal as :meth:`pursue`, awaited: `await session.apursue(objective)`.

        Args:
          objective: What the agent is to have achieved before it stops.
          suppress: Whether a goal that fails answers with nothing, as for :meth:`pursue`.
          context: An ordinary turn to add to this conversation before the goal starts, as
            for :meth:`pursue`.

        Returns:
          What :meth:`pursue` would have answered with.
        """
        return await _awaited(
            lambda: self.pursue(objective, suppress=suppress, context=context),
            f"{self._agent.id}-goal",
        )

    def stream(
        self, prompt: str, *, schema: type[BaseModel] | None = None
    ) -> Iterator[Event]:
        """Sends one turn, saying what the agent says as it says it.

        The turn is over when the iterator is, and its last `result` event is what
        :meth:`__call__` answers with. A caller that only wants the answer calls the session.

        Everything said here reaches whoever is watching the agent, bracketed by the `begins`
        and `ends` that say whose turn it was: a flow drives the sessions and answers to
        nobody, so the turns going past are the only place a run can be watched from.

        It is also where the moments of a turn are: the prompt going in, each tool the agent
        reaches for, and the turn stopping. A hook hung on `Stop` that refuses is what sends
        the agent on again, so one call here is as many turns of the model as the hooks allow
        -- and still one `result` at the end of it, which is the last of them.

        Args:
          prompt: The input prompt for this turn.
          schema: The shape to answer in, or None to take what the agent says. A backend that
            can be held to one is handed it; one that cannot is asked for it in the prompt,
            since a turn that has to be read as an object has to be asked somehow -- under
            the flow's own words rather than in place of them, and not in what the hooks and
            the transcript are shown, which is what the flow said.

        Yields:
          What the agent said, in the order it said it.

        Raises:
          subprocess.CalledProcessError: If the turn fails, as for :meth:`__call__`.
        """
        # The whole turn under the session's own lock, rather than only the part where the
        # backend is spoken to: the moments a turn fires and the events it says are the turn
        # as much as the process is, and two threads calling one session are two turns one
        # after the other. A conversation is a sequence, however many are driving it.
        with self._lock:
            self._working = True
            try:
                yield from self._turning(prompt, schema=schema)
            finally:
                self._working = False
                if self._ended:
                    # Closed while this turn was running -- a stop does not wait for a turn,
                    # and the turn's own process is still reading the skills it was given.
                    # So what the session mounted goes now, which is the first moment nothing
                    # is working by it.
                    self._unmounted()

    def _turning(
        self, prompt: str, *, schema: type[BaseModel] | None = None
    ) -> Iterator[Event]:
        """One turn, from the moments it opens on to the answer it ends with.

        Args:
          prompt: The input prompt for this turn.
          schema: The shape to answer in, or None to take what the agent says.

        Yields:
          What the agent said, in the order it said it.
        """
        if self._agent._stopped:
            raise Stopped(f"{self._agent.id} was stopped")
        # Anything said while nobody was working goes into this turn. A flow's own prompt is
        # the only way into a turn that has not started, so it is asked for here rather than
        # written to the session: a session between turns would answer it on its own.
        held = self._agent.waiting() if self._agent.waiting is not None else []
        if held:
            prompt = "\n\n".join([prompt, *held])
        # Before the moments rather than only on the first turn: a session closed and then
        # spoken to again -- which is what a stopped flow that carries on does -- had what it
        # was working by taken away when it closed, and a turn without the flow's skills is a
        # turn asked to do what it no longer has the means to do. A no-op for a session that
        # is holding them already, which is every turn but the first.
        self._mounts()
        if not self._started:
            self._started = True
            self._fire(Moment.SESSION_START, prompt=prompt)
        submitted = self._fire(Moment.USER_PROMPT_SUBMIT, prompt=prompt)
        if submitted.adds:
            prompt = f"{prompt}\n\n{submitted.adds}"
        self._heard(Event(kind="begins", text=prompt))
        try:
            if submitted.refused:
                # The turn does not run, and what the hook said instead is what it answers
                # with: a turn that was refused still has to end on one `result`, or a flow
                # reading it would be waiting for an answer nobody is going to give.
                yield self._heard(Event(kind="result", text=submitted.because))
                return
            again = 0
            while True:
                answered = Event(kind="result", text="")
                # Asked for afresh each time round, because each time round is a turn: a
                # hook that sends the agent on says what to say next, and a shape that was
                # only on the first prompt would be a shape the last turn was never asked
                # for. On the prompt as it is sent rather than on the one the hooks and the
                # transcript see, which is the flow's own words: a schema in the transcript
                # is the plumbing showing through.
                for event in self._falling_back(prompt, schema=schema):
                    if event.kind == "result":
                        # Held back: a hook may yet send the agent on, and a turn that was
                        # sent on has not answered.
                        answered = event
                        continue
                    self._heard(event)
                    if event.kind == "tool":
                        named, _, about = event.text.partition(" ")
                        self._fire(Moment.PRE_TOOL_USE, tool=named, about=about)
                    yield event
                # Heard whether or not it is passed on, because what a turn cost is on it.
                self._heard(answered)
                stopping = self._fire(
                    Moment.STOP, said=answered.text, prompt=prompt, again=again
                )
                if not (stopping.refused and stopping.because):
                    yield answered
                    return
                prompt, again = stopping.because, again + 1
        finally:
            self._heard(Event(kind="ends", text=""))

    def _falling_back(
        self, prompt: str, *, schema: type[BaseModel] | None = None
    ) -> Iterator[Event]:
        """One turn, tried again and then run under the next account, until one lands.

        A turn fails for two kinds of reason and only one of them is worth another try: a
        gateway that answered 503, a subscription that said "too many requests", a socket
        that closed mid-stream are the same call away from working. So an account says how
        many times a turn under it is tried again and how long to wait between tries, and
        what to carry on under once those are spent -- and each account names the next, so
        what a turn walks is a chain rather than a single second place.

        Which kind it was is the backend's to say, since only the backend knows what its own
        failure means, and it says the second kind by raising `Unrecoverable`. Nothing here
        reads a message to guess at it, and nothing here tries one of those again: a failure
        that cannot come out differently, retried on a schedule, is a flow that makes no
        progress and never stops.

        All of it inside the session that was running: the conversation is the backend's own
        and is named by an id, so the same session carries on under the next account. What a
        failed try already put on the transcript stays there -- it is how somebody reading it
        finds out that the account went down and where the turn went next.

        Args:
          prompt: The input prompt for this turn, as the backend is to be given it.
          schema: The shape to answer in, or None.

        Yields:
          What the agent said, in the order it said it.

        Raises:
            subprocess.CalledProcessError: If every try under every account of the chain
              failed, which is the last of them raised as the turn's own failure -- or at
              once, without another try or another account, for an `Unrecoverable`: a turn
              that failed for a reason no other try could come out differently on is a turn
              that has failed, and trying it again is a loop rather than a recovery.
        """
        from hmz import providers
        from hmz.providers import retry

        last: subprocess.CalledProcessError | None = None
        # Which accounts this turn has been under, so that a chain read again between two of
        # them -- another session of this agent moved it, somebody rewrote a fallback -- is
        # walked forwards rather than back onto one that has already failed here.
        tried: set[str] = set()
        while True:
            account = self._agent.node()
            if account.name in tried:
                break
            tried.add(account.name)
            since = time.monotonic()
            for attempt in range(1, account.retries + 2):
                if self._agent._stopped:
                    raise Stopped(f"{self._agent.id} was stopped")
                waiting = retry.waits(account.policy, attempt)
                if attempt > 1:
                    # Checked before the wait rather than after it, so that a turn is never
                    # started knowing the time it was given is already spent.
                    if (
                        account.timeout
                        and time.monotonic() - since + waiting > account.timeout
                    ):
                        break
                    self._heard(
                        Event(
                            kind="tool",
                            text=f"{self._agent.backend} failed; trying again in "
                            f"{waiting:.0f}s ({attempt - 1} of {account.retries})",
                        )
                    )
                    time.sleep(waiting)
                try:
                    yield from self._stream(
                        self._shaped_ask(prompt, schema), schema=schema
                    )
                except Unrecoverable:
                    # A turn that would fail the same way however often it is taken, and
                    # under whichever account takes it: a prompt longer than the model's
                    # context window is that long again on the next try, and a conversation
                    # its backend can no longer be reached under is not reachable a second
                    # later. Tried again, those are a loop that runs until somebody stops
                    # it -- so this one is the turn's own failure, said once.
                    raise
                except subprocess.CalledProcessError as failed:
                    last = failed
                else:
                    return
            if self._agent._stopped:
                # Stopped while this turn was waiting to try again, or between accounts.
                # A run ended by hand is ended, not carried on somewhere else.
                raise Stopped(f"{self._agent.id} was stopped")
            if self._agent.node().name != account.name:
                # Another session of this agent moved it while this turn was running, and it
                # moved it forwards. Taking the next step from where this turn thought it was
                # would drag the agent back onto an account somebody has already left.
                continue
            instead = next(
                (one for one in providers.chain(account)[1:] if one.name not in tried),
                None,
            )
            if instead is None:
                break
            self._agent.fall_back(instead)
            self._heard(
                Event(
                    kind="tool",
                    text=f"{self._agent.backend} failed; carrying on as "
                    f"{instead.name or 'this machine is signed in'}",
                )
            )
        # Every account of this backend is spent. What is left is another agent -- another
        # CLI, another model, another effort -- which is a step written down between the two
        # rather than on either, and is the second thing tried because it is the one that
        # cannot carry the conversation: no backend takes another backend's session id.
        stood_in = self._agent.stands_in()
        if stood_in is not None:
            self._heard(
                Event(
                    kind="tool",
                    text=f"{self._agent.backend} has nowhere left to run; carrying on as "
                    f"{stood_in.spec}",
                )
            )
            yield from self._instead(stood_in, prompt, schema=schema)
            return
        if last is None:  # nothing ran at all, which is nothing this can raise about
            raise RuntimeError("no account to take the turn under")
        raise last

    def _instead(
        self,
        stood_in: AgentBase,
        prompt: str,
        *,
        schema: type[BaseModel] | None = None,
    ) -> Iterator[Event]:
        """This turn, taken in a session of the agent this one falls back to.

        A new session rather than this one carried on: the conversation is the backend's own
        and is named by an id nothing else answers to, so a turn that leaves its backend
        leaves the conversation. What the flow sees is one turn either way -- the events come
        back through the session it asked, bracketed by the moments and the `begins` and
        `ends` this session was already going to say.

        The stand-in walks its own accounts and then its own next step, so a chain of three
        agents is this called once and then once again inside it. It cannot come round: the
        agent that stood in was built holding only the steps after its own.

        Opened once and held, for as long as this session is: what this conversation was is
        lost at the move, and a second one lost every turn after it would be a stateful loop
        started over every round. It works where this one works, and goes when this one goes.

        Args:
          stood_in: The agent taking the turn.
          prompt: What the flow is asking, in its own words: shaped again for the backend that
            is about to be asked, since one that can be held to a shape is told separately and
            one that cannot is asked in the prompt.
          schema: The shape to answer in, or None.

        Yields:
          What the stand-in said, in the order it said it.
        """
        if self._moved_to is None:
            self._moved_to = stood_in.new(self._cwd)
        session = self._moved_to
        session._shaping = schema
        # The flow's skills go with the turn: the stand-in was made carrying them, and a
        # session of it puts them where its own backend reads them, which is not where this
        # one's does. Whichever of them this session carries, since it is this session's turn.
        session.loads(self._skills)
        session._mounts()
        yield from session._falling_back(prompt, schema=schema)

    def _shaped_ask(self, prompt: str, schema: type[BaseModel] | None) -> str:
        """The prompt as the backend is to be given it, shape and all.

        Args:
          prompt: What the flow is asking.
          schema: The shape it wants back, or None.

        Returns:
          The prompt itself for a backend that can be held to the shape -- it is told
          separately, and telling it twice would be asking for the same thing two ways -- and
          the prompt with the schema under it for one that can only be asked.
        """
        if schema is None or type(self).shapes:
            return prompt
        return prompt + _IN_SHAPE.format(
            schema=json.dumps(schema.model_json_schema(), indent=2)
        )

    def _heard(self, event: Event) -> Event:
        """Tells whoever is watching the agent what was said, and answers with it.

        Said as this conversation's rather than as the agent's: an agent may be holding ten
        at once, and whoever is watching has to be able to tell which of them said a thing --
        to show one conversation rather than ten interleaved, and to say the next thing back
        to the one it is reading.

        Args:
          event: What was said.

        Returns:
          The same event, so that saying it and passing it on is one line.
        """
        self._agent._heard(event, self)
        return event

    def _fire(
        self,
        moment: Moment,
        *,
        prompt: str = "",
        tool: str = "",
        about: str = "",
        called: Mapping[str, Any] | None = None,
        said: str = "",
        again: int = 0,
    ) -> Verdict:
        """Tells whatever is hung on one of this agent's moments that it has arrived.

        Args:
          moment: Which moment it is.
          prompt: What the agent is about to be told, where that is what the moment is about.
          tool: What it reached for, where the moment is about a tool.
          about: What it reached for it with.
          called: What the tool was called with, where the backend says.
          said: What the agent said last.
          again: How many times this turn has already been sent on rather than let stop.

        Returns:
          What the hooks said, which is nothing at all where none is hung.
        """
        return self._agent.hooks.fire(
            Occasion(
                moment=moment,
                agent=self._agent.id,
                session=self._id or "",
                prompt=prompt,
                tool=tool,
                about=about,
                input=called or {},
                said=said,
                again=again,
            )
        )

    @abstractmethod
    def _stream(
        self, prompt: str, *, schema: type[BaseModel] | None = None
    ) -> Iterator[Event]:
        """Sends one turn, saying what the agent says as it says it.

        Args:
          prompt: The input prompt for this turn.
          schema: The shape the turn is to answer in, for a backend that can be held to one,
            and already asked for in the prompt for one that cannot.

        Yields:
          What the agent said, in the order it said it.
        """

    def interject(self, text: str) -> None:
        """Puts a word in while a turn is running, as typing at the agent would.

        The agent reads it when it next looks, so a turn already under way takes it into
        account rather than being restarted with it. Landing it is not the agent having it:
        every backend here answers a word put in twice over -- once to say it has been taken
        from us, and again, later, to say it is in front of the model -- and only the second
        is the agent having heard. That second one is a `took` event.

        Args:
          text: What to say to the agent.

        Raises:
            NotImplementedError: If this backend takes a turn's whole prompt up front and has
            nowhere to put a later word.
        """
        raise NotImplementedError(f"{type(self).__name__} cannot be talked to mid-turn")

    def steering(self, text: str, ticket: str = "") -> str:
        """Writes down a word being put into a turn, against the name it will come back under.

        Args:
          text: The word itself.
          ticket: What the backend will name it by when it says it has it, or "" for a name
            of our own -- which is what a backend takes when it will carry one back.

        Returns:
          The ticket, to be sent with the word.
        """
        said = ticket or uuid.uuid4().hex
        with self._steering:
            self._steered[said] = text
        return said

    def took(self, ticket: str) -> str | None:
        """Takes a word off the book, the agent having said it has it.

        Args:
          ticket: What the backend named it by.

        Returns:
          The word, or None for one this session never put in -- a turn's own prompt comes
          back the same way, and is not a word put into anything.
        """
        with self._steering:
            return self._steered.pop(ticket, None)

    def unsteered(self, text: str) -> None:
        """Takes a word off the book because it never landed at all.

        Args:
          text: The word, which is what a backend that mints its own name knows it by.
        """
        with self._steering:
            for ticket, said in list(self._steered.items()):
                if said == text:
                    del self._steered[ticket]
                    return

    def close(self) -> None:
        """Ends the conversation, so that a turn under way stops waiting.

        `SessionEnd` is said once here, and only for a session that ever started: a session
        opened and dropped without a turn in it never began, and one closed twice did not end
        twice. What holds the conversation open is let go of in :meth:`_shut`, which a
        backend that has to end its process between turns reaches for instead -- ending the
        process is not ending the conversation.
        """
        if self._started and not self._ended:
            self._ended = True
            self._fire(Moment.SESSION_END)
        self._shut()
        if self._moved_to is not None:
            # And the conversation this one moved to, which is this conversation carried on
            # somewhere else: it ends when this one does.
            self._moved_to.close()
        if not self._working:
            # What the session mounted goes when the conversation does. Not while a turn is
            # still running by it, though: this is called to stop an agent, and stopping one
            # does not wait for the turn it is taking -- so a turn that is still reading those
            # files would have them taken away underneath it. The turn itself lets go of them
            # as it ends, which is the first moment nothing is using them.
            self._unmounted()

    def _unmounted(self) -> None:
        """Takes away what this session mounted, once and whenever the last holder is done.

        Calling the finalizer is what runs it, once, whichever gets there first: the close,
        the end of a turn that outlived one, or collection for a session nobody closed.
        """
        if self._unmounting is not None:
            self._unmounting()
            self._unmounting = None
        # And nothing is down, so the next turn puts down whatever this session carries then
        # -- which is what a session closed and spoken to again is owed.
        self._mounted = None

    def _shut(self) -> None:  # noqa: B027  -- empty on purpose, and so not abstract
        """Lets go of whatever is holding this conversation open.

        Does nothing by default: a session that is one command per turn holds nothing
        between them.
        """

    def elsewhere(self) -> bool:
        """Whether what this session is holding open was started under another account.

        Asked on the thread taking the turn, which is the only one that may let go of what
        this session holds: an agent that has fallen back is an agent whose next turn has to
        be spoken to a process started as whoever it now is.

        Returns:
          Whether to let go of it before this turn. False for a session holding nothing yet,
          and for one whose agent has not moved.
        """
        return self._as is not None and self._as != self._agent.node().name

    @property
    def cwd(self) -> str:
        """The directory this conversation works in, as whoever is watching would name it.

        Which is the path on the machine the work lands on: the one the session was opened
        with, or the workspace the flow is running in where it was opened with none.
        """
        anchor = self._agent.anchor
        if self._cwd is not None:
            return os.path.abspath(self._cwd)  # noqa: PTH100
        if anchor is not None:
            return os.path.abspath(anchor.workspace or os.getcwd())  # noqa: PTH100, PTH109
        return os.path.abspath(os.getcwd())  # noqa: PTH100, PTH109

    def _workspace(self) -> str:
        """The project directory a turn of this session works in, as the backend will find it.

        A backend run as a command works in it directly, and coganchor puts an anchored one in
        its mirror of the workspace instead -- which is the workspace's own path unless the
        mirror was put somewhere else. A backend told where to work has to be told that same
        directory, since it is the one whose files reach the target.

        Returns:
          The absolute path to open the session at.

        Raises:
          ValueError: If the session was opened at a directory that is not there, or -- for an
            agent whose turns land elsewhere -- at one outside the workspace the anchor names.
            Said before the first turn rather than as a backend failing to start in it.
        """
        anchor = self._agent.anchor
        if anchor is None:
            where = self.cwd
            if not os.path.isdir(where):  # noqa: PTH112
                raise ValueError(f"{where}: no directory to open a session in")
            return where
        # The mirror's own path for the same place: what the agent reads and writes is the
        # mirror, and coganchor is what makes that the target's copy.
        workspace = os.path.abspath(anchor.workspace or os.getcwd())  # noqa: PTH100, PTH109
        mirror = os.path.abspath(anchor.shadow or workspace)  # noqa: PTH100
        where = self.cwd
        if where != workspace and not where.startswith(workspace + os.sep):
            raise ValueError(
                f"{where} is not inside {workspace}, which is the workspace this agent's "
                "turns land in"
            )
        return os.path.join(  # noqa: PTH118 -- text, as every path on this line is
            mirror, os.path.relpath(where, workspace)
        )

    def _mounts(self) -> None:
        """Puts the skills this session carries where the backend reads them, as a turn opens.

        Where that backend reads a project's own skills, for as long as this session carries
        them: a flow works by the skills it carries, and a session of it that had none would
        be a turn asked to do something the flow never gave it the means to do. As a turn
        opens rather than when the session was made, since the directory it works in is
        settled by then -- and per session, so a skill rewritten between turns is the one the
        next turn carries.

        Asked each turn rather than once, because which of them this session carries is a
        thing a flow may change while the conversation is going: a session told to put one
        down and take another up has the one it was told about from its next turn, which is
        this one. A session carrying what it was already carrying does nothing at all here,
        which is every turn but the first and every turn after a change.

        Nothing at all for a flow that brings none, which is most of them, and for a backend
        that reads no such directory: those carry what their CLI installed and no more.

        Note:
          Into the directory on this machine, never an anchored agent's mirror of the target.
          A mirror is the target's copy -- coganchor makes it hold what the target holds, and
          sweeps away what only it has -- so a skill written into one is a skill deleted, and
          a mirror created here before coganchor has taken it over is a mirror coganchor
          refuses to take over at all, which would be every turn of the run failing. A
          container given this workspace reads this directory and gets them; a machine across
          a network keeps its own, and a flow that brings skills is a flow to run here.
        """
        carrying = self._carrying()
        if tuple(one.name for one in carrying) == self._mounted:
            return  # already carrying exactly these, which is every turn but the first
        # What it was carrying goes before what it is to carry arrives: two sets of skills in
        # the one directory is the session carrying what it was told to put down.
        self._unmounted()
        if not carrying:
            self._mounted = ()
            return
        workspace = self.cwd
        if not os.path.isdir(workspace):  # noqa: PTH112
            return  # a session that cannot say where it works is one that will not run
        mounted = mount(self._agent.backend, workspace, carrying)
        if mounted.at:
            # A finalizer rather than a line in `close`, and callable so that whichever of
            # the two gets there first is the one that runs -- once, whatever happens after.
            self._unmounting = weakref.finalize(self, unmount, mounted)
        self._mounted = tuple(one.name for one in carrying)

    def _carrying(self) -> tuple[Loaded, ...]:
        """The skills this session is to have down, as the flow brought them.

        Returns:
          The flow's own, in the flow's order, less any this session was told not to carry.
        """
        brought = self._agent.loaded
        if self._skills is None:
            return tuple(brought)
        wanted = set(self._skills)
        return tuple(one for one in brought if one.name in wanted)

    def _environment(self) -> Mapping[str, str]:
        """What to set in the command's environment on top of this process's own.

        Whatever the agent's provider says, which is how a key, an endpoint or an account on
        somebody's cloud reaches the CLI, and nothing besides for an agent that has none: a
        turn then inherits the environment the flow is running in, which is what lets the
        agent log in the way it already logs in. A backend that takes a setting of its own
        there adds it to these.

        Returns:
          The variables to add, which are set for the turn and for nothing else.
        """
        return self._agent.environment()

    def _environ(self) -> dict[str, str] | None:
        """The whole environment this session's processes are started with.

        Returns:
          This process's own, less what a provider hushes and plus what this session and that
          provider set, or None where there is nothing to change.
        """
        added, hushed = self._environment(), self._agent.hushed()
        if not added and not hushed:
            return None
        return {
            name: value for name, value in os.environ.items() if name not in hushed
        } | dict(added)

    def _adopt(self, session_id: str) -> None:
        """Takes the name the backend gave this session, the first time a turn lands in it.

        The backend logs the session from here on but never says whose it is, so the moment
        its id becomes known is the moment the agent takes note of it. A turn that failed
        never gets here, which is what leaves the session unopened for the next one to retry.

        Args:
          session_id: The backend's id for this session.
        """
        if self._id is None:  # an id is fixed for the life of the session it names
            self._id = session_id
            self._agent._opens(session_id)
            if self._agent.cycle is not None:
                # The run is the only thing that knows this session was one of its own: the
                # backend logs it under this id and never says whose it was.
                self._agent.cycle.opened(self._agent, session_id)

    def pursue(
        self,
        objective: str,
        *,
        suppress: bool = False,
        context: str | None = None,
    ) -> str:
        """Runs the session under a goal, which the agent then keeps itself going toward.

        This is the backend's own goal feature rather than a prompt that asks for one: the
        agent decides for itself that the objective has been met, and until it does, a turn
        that would have ended starts another. A flow that loops over this is running the
        objective again rather than nudging an agent that stopped early.

        Args:
          objective: What the agent is to have achieved before it stops.
          suppress: Whether a goal that fails answers with nothing instead of raising, as
            for :meth:`__call__`.
          context: An ordinary turn to add to this conversation before the goal starts, or
            None. Its answer is not returned. Use it for task material that the goal needs
            in context but that is not itself the completion condition.

        Returns:
          The agent's response once it stops, stripped, or "" for a goal that failed while
          `suppress` was set.

        Raises:
          NotImplementedError: If this backend has no goal feature to reach for, whether or
            not `suppress` is set: a flow asking for one it has not got is a flow to correct.
          RuntimeError: If goals were disabled for this agent, whether or not `suppress` is
            set: a flow that disabled them retains control of every continuation.
          subprocess.CalledProcessError: If the turn fails and `suppress` is not set.
        """
        if not self._agent.goals_enabled:
            raise RuntimeError(f"{self._agent.id}: goals are disabled")
        if context is not None and not self._agent.pursues:
            raise NotImplementedError(f"{type(self).__name__} has no goal feature")
        try:
            if context is not None:
                self(context)
            return self._pursue(objective)
        except Unrecoverable:
            raise  # not covered by `suppress`, for the reason it is not in a turn
        except subprocess.CalledProcessError:
            if not suppress:
                raise
            return ""

    def _pursue(self, objective: str) -> str:
        """Runs the session under a goal, which each backend reaches for its own way.

        Args:
          objective: What the agent is to have achieved before it stops.

        Returns:
          The agent's response once it stops, stripped.
        """
        raise NotImplementedError(f"{type(self).__name__} has no goal feature")


class CommandSessionBase(SessionBase):
    """A session whose turns are one run of a coding agent's command line each."""

    #: Whether what the command writes on stdout is a protocol rather than the agent talking.
    #: A backend that answers in JSON is read into events and watched as those, so its lines
    #: are not put on the terminal as they arrive and its answer is put there at the end --
    #: which is what every backend driven over a protocol does.
    protocol: ClassVar[bool] = False

    def _reads(self, line: str, *, error: bool) -> Iterable[Event]:
        """Reads one line the command wrote into what it says the agent did.

        The whole line, either way round, for a backend that writes what it is doing where a
        person would read it: the agent talks on stdout and puts its progress on stderr. One
        that answers in a protocol reads its own lines instead.

        Args:
          line: The line, as written.
          error: Whether it came from stderr rather than stdout.

        Returns:
          Everything it said, which is nothing at all for a line saying nothing worth showing.
        """
        yield Event(kind="tool" if error else "text", text=line.rstrip("\n"))

    def _result(self, transcript: str) -> Event:
        """The answer the turn ends on, out of everything the command wrote on stdout.

        Args:
          transcript: The whole of stdout.

        Returns:
          The `result` event, carrying what the agent answered and what the turn cost.

        Raises:
          subprocess.CalledProcessError: If what the command wrote says the turn failed. A
            backend that leaves nonzero for the times it could not start says so here instead,
            and a turn that failed must not answer as if it had landed.
        """
        return Event(kind="result", text=transcript.strip())

    def _stream(
        self, prompt: str, *, schema: type[BaseModel] | None = None
    ) -> Iterator[Event]:
        """Sends one turn, saying each line the agent writes as it is written.

        Turns of one session are serialized, so a session shared by two threads holds one
        conversation rather than interleaving two. Both of the agent's streams are teed to ours
        as they arrive, so a long turn stays watchable. A failed turn leaves the session
        unopened, so the next call retries the turn the same way rather than resuming a session
        that may not exist. An anchored agent is run through coganchor, which is what puts the
        turn's files and commands on another machine while the conversation stays here, and an
        isolated one is the same thing against a machine the agent started for itself.

        Args:
          prompt: The input prompt for this turn.
          schema: The shape to answer in, which the command :meth:`_turn` builds reads off
            the session -- it is set here, under the lock the turn is taken under, so that
            what builds the command is looking at this turn's own.

        Yields:
          A line at a time as the agent writes it, and the whole of what it said last.

        Raises:
          subprocess.CalledProcessError: If the agent CLI exits nonzero. Both streams are
            attached to it as diagnostics.
        """
        with self._lock:
            self._shaping = schema
            argv, stdin = self._turn(prompt)
            # Where the turn runs, and where it is spawned from: an anchored turn is put in
            # the mirror by the anchor itself, so only an unanchored one is started here.
            where = self._workspace()
            # Spawned rather than called: a supervisor forks the agent and takes the process's
            # signal handling with it, which a flow pumping turns from threads of its own has
            # no way to lend it. Whether there is one to spawn -- an anchor, a provider's own
            # paths, both -- is the agent's to say.
            argv = self._agent.spawned(argv, self.cwd)
            out: list[str] = []
            err: list[str] = []
            said: queue.Queue[Event | None] = queue.Queue()
            with subprocess.Popen(
                argv,
                # No prompt on stdin means no stdin at all: inheriting ours would let the agent
                # read the terminal a flow is being watched from.
                stdin=subprocess.PIPE if stdin is not None else subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                encoding="utf-8",
                # The agents draw progress bars and check marks: their bytes must never fail a
                # turn, whatever encoding the machine running the flow happens to be set to.
                errors="replace",
                # This process's own, less what the agent's provider hushes and plus what it
                # and the backend set. None rather than a copy where there is nothing to say,
                # so that a turn inherits the environment as it always did.
                env=self._environ(),
                # The directory the session was opened at, which is this one unless it was
                # opened at another; an anchored turn is put there by the anchor instead.
                cwd=None if self._agent.anchor is not None else where,
            ) as proc:
                assert proc.stdout is not None  # noqa: S101
                assert proc.stderr is not None  # noqa: S101
                # Every pipe drains from the moment the agent starts: it puts its progress on
                # stderr and only the final message on stdout, and a prompt larger than the pipe
                # buffer would deadlock against an agent that prints before reading all of it.
                pumps = [
                    threading.Thread(
                        target=_tee,
                        args=(
                            proc.stdout,
                            None if type(self).protocol else sys.stdout,
                            out,
                            said,
                            functools.partial(self._reads, error=False),
                        ),
                    ),
                    threading.Thread(
                        target=_tee,
                        args=(
                            proc.stderr,
                            sys.stderr,
                            err,
                            said,
                            functools.partial(self._reads, error=True),
                        ),
                    ),
                ]
                for pump in pumps:
                    pump.start()
                if stdin is not None:
                    assert proc.stdin is not None  # noqa: S101
                    # An agent that exits before reading the prompt is a failed turn, reported
                    # by its exit status rather than as a broken pipe here.
                    with contextlib.suppress(BrokenPipeError):
                        try:
                            proc.stdin.write(stdin)
                        finally:
                            proc.stdin.close()
                # Said as it arrives, from whichever stream got there first, until both have
                # ended -- one None apiece, which is the only thing that ends this turn.
                for _ in pumps:
                    while (event := said.get()) is not None:
                        if type(self).protocol and not self._agent._watchers:
                            # On stderr, where a backend that writes for a person puts its
                            # progress: its own stdout is the protocol here, and a turn nobody
                            # can watch is a flow that reads as hung for as long as it takes.
                            say(event.text, sys.stderr)
                        yield event
                for pump in pumps:
                    pump.join()
                status = proc.wait()

            stdout = "".join(out)
            if status != 0:
                raise Failed(status, argv, stdout, "".join(err))
            answered = self._result(stdout)
            if self._id is None:
                # Separated, so that a stdout without a trailing newline cannot glue the first
                # line of stderr onto the last of stdout and hide a line the id is read from.
                self._adopt(self._read_session_id(stdout + "\n" + "".join(err)))
            if type(self).protocol and not self._agent._watchers:
                # Where a backend writing for a person would have put its answer. Something
                # watching the agent has had it already, as the turn said it.
                say(answered.text, sys.stdout)
            yield answered

    @abstractmethod
    def _turn(self, prompt: str) -> tuple[list[str], str | None]:
        """Builds the CLI call for one turn.

        Args:
          prompt: The input prompt for this turn.

        Returns:
          The command to run and the text to write to its stdin, or None when the prompt is
          already inside the command. The command opens a new session while the session is
          unopened, and resumes that session once it has an id.
        """

    @abstractmethod
    def _read_session_id(self, transcript: str) -> str:
        """Reads back the id the backend gave this session, once the opening turn has landed.

        Args:
          transcript: Everything the turn printed, on stdout and stderr alike.

        Returns:
          The backend's session id, which every later turn resumes.
        """


class StreamSessionBase(SessionBase):
    """A session that is one long-lived process, spoken to in JSON a line at a time.

    A turn is a line written in rather than a command run, which is what leaves somewhere for
    a later word to go: the agent is still there, still reading, so :meth:`interject` reaches
    the turn already under way instead of waiting for the next one.
    """

    def __init__(
        self, agent: AgentBase, cwd: str | os.PathLike[str] | None = None
    ) -> None:
        """Initializes a session holding no process yet.

        Args:
          agent: The agent whose config every turn of this session runs at.
          cwd: The directory this conversation works in, as for :class:`SessionBase`.
        """
        super().__init__(agent, cwd)
        self._proc: subprocess.Popen[str] | None = None
        self._writing = threading.Lock()  # a line is written whole or not at all
        #: Answers still owed to us: the agent replies to each thing said with a turn of its
        #: own, so a word put in mid-turn adds one, and the turn is over when none are left.
        self._owed = 0
        #: What the agent has complained about, which is what a failed turn is reported with.
        self._complaints: list[str] = []
        #: What ends the process if the session is dropped while it is still up.
        self._reaper: weakref.finalize[..., Any] | None = None
        #: Who is reading the process's complaints, so a failed turn can wait for the last.
        self._draining: threading.Thread | None = None

    def _stream(
        self, prompt: str, *, schema: type[BaseModel] | None = None
    ) -> Iterator[Event]:
        """Sends one turn as a line of JSON, and reads the agent's own back until it ends.

        A word put in while the turn runs is a thing said too, and the agent answers each
        thing said with a turn of its own. So the turn here is over when the agent has
        answered everything it was told, not when it first stops -- which is both how what
        was put in gets read at all, and how the next turn avoids picking up its answer.

        Args:
          prompt: The input prompt for this turn.
          schema: The shape to answer in, which is an argument of the process rather than of
            the turn: a session already holding one that was started for another shape ends
            it, and the turn starts one that is asked for this one. The conversation is not
            ended by that -- the new process resumes it, as an anchored session's does every
            turn.

        Yields:
          What the agent said, in the order it said it.

        Raises:
          subprocess.CalledProcessError: If the agent exits rather than answering.
        """
        with self._lock:
            if schema is not self._shaping or self._stale() or self.elsewhere():
                self._shut()
            self._shaping = schema
            argv = self._command()
            proc = self._start(argv)
            assert proc.stdout is not None  # noqa: S101
            try:
                self._say(prompt)
            except RuntimeError as gone:
                # The process was up a moment ago and is not now. A turn that could not even
                # be said is a failed turn, and it says so the way every other one does --
                # so that a flow catches turns rather than transports.
                raise Failed(proc.poll() or 1, argv, "", str(gone)) from gone
            said = ""
            spent: Counter[str] = Counter()
            costing = Usage()
            settled = False
            for line in proc.stdout:
                for event in self._read(line):
                    if event.kind == "failed":
                        # The backend answered, and what it answered is that it could not.
                        # A turn that returned this as its text would be a Ralph loop feeding
                        # an error message forward as the work of the turn before it.
                        status = proc.poll() or 1
                        if self._draining is not None:
                            # Waited on: what the agent said on its way out is the diagnostic,
                            # and it may not have been read yet.
                            self._draining.join(timeout=5)
                        complained = "".join(self._complaints)
                        self._shut()
                        raise Failed(status, argv, event.text, complained)
                    if event.kind == "result":
                        said = event.text
                        # Every answer in the turn cost something, the ones to a word put in
                        # mid-turn included, and the turn is what all of it is charged to --
                        # counted by model and by kind, which are the same spending twice.
                        spent.update(event.tokens)
                        costing = costing + event.spent
                        with self._writing:
                            self._owed -= 1
                            settled = self._owed <= 0
                        if settled:
                            break
                        # An answer to something put in mid-turn. It is counted and not
                        # passed on: the agent said these same words as it said them, and
                        # the turn is watched as it goes -- so passing the answer on here
                        # would show it a second time. Two things said mid-turn would then
                        # read as three answers. The turn goes on to whatever it was told
                        # last, and the answer to that is the one it ends on.
                        continue
                    if not self._agent._watchers:
                        # On stderr, where every other backend puts its progress: stdout is
                        # the protocol here, and a turn nobody can watch is the point of all
                        # this. Something watching the agent shows the turn itself, and would
                        # then be showing it twice.
                        say(event.text, sys.stderr)
                    yield event
                if settled:
                    break
            else:
                # stdout ended instead: the agent is gone, and a turn it never answered is a
                # failed turn rather than an empty one.
                status = proc.wait()
                if self._draining is not None:
                    # Waited on, because a process that wrote its one explanation and left
                    # may not have had it read yet -- and that explanation is the diagnostic.
                    self._draining.join(timeout=5)
                complained = "".join(self._complaints)
                self._shut()
                raise Failed(status or 1, argv, said, complained)
            if self._agent.anchor is not None:
                # An anchored turn has to be over when it says it is: coganchor pushes what the
                # agent wrote when the session ends, so a process held open past the turn would
                # leave that turn's work still on this machine. The cost is that an anchored
                # session cannot be talked to between turns -- there is nothing there to hear.
                # The process, not the conversation: the next turn resumes it.
                self._shut()
            if not self._agent._watchers:
                # Where the backend's own command line would have put the answer, as the other
                # backends put it: the turn that settled the answer broke out of the reading
                # above before saying it, and a flow watched by nobody would end with nothing
                # on the terminal it was run from. Something watching the agent has had it
                # already, as the turn said it, and would then be shown it twice.
                say(said, sys.stdout)
            yield Event(kind="result", text=said, tokens=spent, spent=costing)

    def interject(self, text: str) -> None:
        """Says something to the agent now, whether or not a turn is running.

        Named as it goes, so that the agent saying it has it says which one: several words
        put into one turn come back one at a time, and a name apiece is what tells them
        apart. A word that could not be written is taken off the book again -- there is
        nothing coming back for it.

        Args:
          text: What to say to the agent.

        Raises:
          RuntimeError: If no process is up to hear it, which is a session no turn has opened.
        """
        ticket = self.steering(text)
        try:
            self._say(text, ticket)
        except BaseException:
            self.took(ticket)
            raise

    def _shut(self) -> None:
        """Ends the process, which is what was holding the conversation open."""
        with self._writing:
            # Taken together, so that nothing is written to a process on its way out and no
            # answer is left owed by one that is gone.
            proc, self._proc, self._owed = self._proc, None, 0
        if proc is None:
            return
        with contextlib.suppress(OSError, ValueError):
            if proc.stdin is not None:
                proc.stdin.close()  # its stdin ending is how the agent knows to stop
        try:
            # Short: a process whose stdin has ended is already going, so this waits only for
            # one that is not -- and that one is being stopped, which should read as stopped.
            proc.wait(timeout=1)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()  # reaped rather than left a zombie, one per turn of a long flow
        # stdout is ours to close: the turn has finished reading it. stderr is not -- the
        # reader is sitting in it, and closing a stream another thread is blocked on waits on
        # that thread, which waits on whatever the agent left holding the write end. It is
        # closed by the reader itself, when there is nothing left to come.
        with contextlib.suppress(OSError, ValueError):
            if proc.stdout is not None:
                proc.stdout.close()

    def _say(self, text: str, ticket: str = "") -> None:
        """Writes one line of JSON to the agent, whole, whoever else is writing.

        Counted once it has landed: the agent owes an answer for each thing said, and a turn
        is not over until it has given them all -- so counting one that never arrived would
        leave the next turn waiting for an answer nobody is going to give.

        Args:
          text: What to say.
          ticket: What the agent is to name it by when it says it has it, or "" for a turn's
            own prompt, which needs no name: the turn beginning is the whole of that answer.

        Raises:
          RuntimeError: If there is no process listening, or it stopped while being told.
        """
        with self._writing:
            proc = self._proc
            if proc is None or proc.stdin is None:
                raise RuntimeError("no turn is running to be talked to")
            try:
                proc.stdin.write(self._write(text, ticket))
                proc.stdin.flush()
            except (OSError, ValueError) as gone:
                # A stdin closed under us raises ValueError rather than BrokenPipeError.
                raise RuntimeError("the agent is no longer listening") from gone
            self._owed += 1

    def _send(self, line: str) -> None:
        """Writes one line of the protocol itself, which is not a thing said to the agent.

        An answer to something the agent asked us is not a turn, so nothing is owed for it:
        counting one would leave the turn waiting for a reply that is never coming. A
        process on its way out takes nothing more, since a turn cannot be rescued by it.

        Args:
          line: The line, newline included.
        """
        with self._writing:
            proc = self._proc
            if proc is None or proc.stdin is None:
                return
            with contextlib.suppress(OSError, ValueError):
                proc.stdin.write(line)
                proc.stdin.flush()

    def _start(self, argv: list[str]) -> subprocess.Popen[str]:
        """Starts the process if it is not up, and returns the one to speak to.

        Args:
          argv: The command to run, which this turn already asked for.

        Returns:
          The process to speak to, which is the one already up whenever there is one.
        """
        if self._proc is not None and self._proc.poll() is None:
            return self._proc
        where = self._workspace()
        # Which account this is being started as, read before the environment is built out of
        # it rather than after the process is up: a fallback landing in between would name the
        # account this process is *not* running as, and a session that believes it is already
        # somewhere else is one that never starts again -- the wrong credentials for good.
        # Read early, the same fallback makes it start again once for nothing, which is a
        # turn's cost rather than a run's.
        account = self._agent.node().name
        argv = self._agent.spawned(argv, self.cwd)
        started = subprocess.Popen(
            argv,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            encoding="utf-8",
            errors="replace",
            bufsize=1,  # a line at a time, which is what the protocol is made of
            # This process's own, less what the agent's provider hushes and plus what it and
            # the backend set, as for a session that is one command per turn.
            env=self._environ(),
            # And in the directory the session was opened at, as for one of those: a backend
            # held open across its turns is held open where its conversation is rooted.
            cwd=None if self._agent.anchor is not None else where,
        )
        assert started.stderr is not None  # noqa: S101
        # Which account it was started as, so that an agent that falls back is an agent whose
        # next turn starts another process rather than speaking to this one.
        self._as = account
        with self._writing:
            # A new process owes nothing for what was said to the one before it. Left standing,
            # that count is an answer this session would wait for and never be given.
            self._proc, self._owed, self._complaints = started, 0, []
        self._restarted()
        # Drained for as long as the process lives: stderr is not the protocol, but a pipe
        # nobody reads fills and stops the agent writing to it, which would hang the turn.
        self._draining = threading.Thread(
            target=_tee,
            args=(started.stderr, sys.stderr, self._complaints),
            daemon=True,
        )
        self._draining.start()
        # Held by the finalizer alone, so a flow that drops a session leaves no process behind.
        # The one before it is let go, or a long flow keeps every process it ever started.
        if self._reaper is not None:
            self._reaper.detach()
        self._reaper = weakref.finalize(self, _reaped, started)
        return started

    def _restarted(self) -> None:
        """Told that a new process is up, for whatever was measured against the old one.

        Does nothing by default. A backend counting anything per process says so here.
        """

    def _stale(self) -> bool:
        """Whether the process now up was started for something this turn is no longer.

        A setting that is an argument of the process rather than of the turn moves by
        restarting it -- the conversation is not ended by that, since the new process resumes
        it, which is what an anchored session does between every pair of turns anyway.

        Returns:
          Whether to end the process before this turn, which is never by default: a backend
          with nothing on its command line that a flow can move has nothing to go stale.
        """
        return False

    @abstractmethod
    def _command(self) -> list[str]:
        """The command the session's one process is run as.

        Returns:
          The command to run, which must speak the protocol on stdin and stdout.
        """

    @abstractmethod
    def _write(self, text: str, ticket: str = "") -> str:
        """Renders something to say to the agent as the line to write.

        Args:
          text: What to say.
          ticket: What the agent is to name it by when it says it has it, or "" to ask for
            no such name.

        Returns:
          The line, newline included.
        """

    @abstractmethod
    def _read(self, line: str) -> Iterable[Event]:
        """Reads one line the agent wrote.

        Args:
          line: The line, as written.

        Returns:
          Everything it said, which is nothing at all for a line saying nothing worth
          showing, and more than one thing for a line carrying more than one.
        """


def _built(spec: str) -> AgentBase | Literal[False]:
    """One agent, made from the spec a fallback names it by.

    Made here rather than by whatever wrote the step down, because it is made at the moment a
    turn has nowhere left to go: a chain of four agents that were all started when the run was
    would be three CLIs held open for a failure that never came.

    Args:
      spec: The agent, as `CLI[@ACCOUNT]/MODEL:EFFORT`.

    Returns:
      The agent, or False for a spec that no longer names one -- a CLI nobody has installed
      here, a step written down against a backend that has gone. A turn then fails the way it
      failed before anybody wrote a step down, which is the answer that says what went wrong
      rather than the one about the step.
    """
    from hmz import backends

    from . import driver

    try:
        profile, model, effort, _tier, provider, may, searches, held = backends.read(
            spec
        )
        kind, config = driver(profile.name)
    except (ValueError, KeyError):
        return False
    extra: dict[str, Any] = {}
    if may is not None:
        extra["permission"] = may
    if searches is not None:
        extra["web_search"] = searches
    if held and profile.name == "codex":
        extra["overrides"] = held
    elif held:
        extra["allowed_tools"] = tuple(value for _key, value in held)
    try:
        return kind(config(model=model, effort=effort, provider=provider, **extra))
    except (ValueError, TypeError):
        return False


class AgentBase(ABC):
    """A coding agent behind a uniform interface: structure only, and no history.

    An agent says which model to run at which effort, and is one agent apart from that: a flow
    that reviews its own work runs two of them at one configuration, and they are not the same
    agent. The conversation lives in the :class:`SessionBase` it opens, so a flow decides for
    itself whether turns share context -- a fresh session per turn is a Ralph loop, one session
    across turns is a stateful one.
    """

    #: The moments of a turn a hook may be hung on here. Every backend reaches the ones that
    #: are read off the turn itself; one that also lets a turn be answered mid-flight names
    #: more, and a flow that needs one of those says so where it declares the agents it drives.
    moments: ClassVar[frozenset[Moment]] = EVERYWHERE

    #: Whether this backend has a goal feature of its own -- one where the agent decides for
    #: itself that an objective has been met, and a turn that would have ended starts another
    #: instead, which is what `pursue` reaches for. Four of them have; a flow that runs its
    #: agent under a goal says so where it declares them, and is then refused an agent that
    #: has not rather than raising on the first turn.
    pursues: ClassVar[bool] = False

    #: Provider service tiers this backend can express exactly. A backend opts into ``fast``
    #: only when it has a native request setting for it, so unsupported requests fail before
    #: the first provider turn.
    service_tiers: ClassVar[tuple[str, ...]] = ("default",)

    def __init__(self, config: AgentConfig, *, name: str | None = None) -> None:
        """Initializes an agent that has opened nothing yet.

        Args:
          config: The model and effort every session of this agent runs at.
          name: What to call this agent, defaulting to one nothing else answers to. Two agents
            sharing a name are one agent to a trace, which is how the roles of a flow survive
            being restarted; two left unnamed are two, which is how one configuration driven
            twice -- an actor and the reviewer reading its work -- stays two.
        """
        self._serves(config)
        self._config = config
        #: What this agent's turns are to think at, where a flow has said something other
        #: than what it was configured with, and None where it has not.
        self._effort: str | None = None
        #: What every session of this agent has cost and how fast, kept here as well as on
        #: each of them: a Ralph loop drops a session a turn, and what the agent has spent
        #: must outlive the conversations it spent it in.
        self._meter = Meter()
        self._id = name or f"{type(self).__name__}#{uuid.uuid4().hex[:8]}"
        #: Whether that name is the agent's own, rather than one to be told by whatever ends
        #: up driving it: a flow that names the agents it takes names the ones that are not.
        self._named = name is not None
        #: What this agent has opened, is watched by, and still holds. Every one of them is
        #: written from whichever thread a turn is running on and read from whichever thread
        #: is asking, and a flow may have ten thousand of both, so each is touched under this
        #: one lock. Re-entrant because dropping the last reference to a session runs the
        #: bookkeeping that forgets it, and that can happen under any line that lets go of one
        #: -- including a line already holding this.
        self._holding = threading.RLock()
        #: Every session this agent has opened and somebody still holds, oldest first, each
        #: under a number of its own. A mapping rather than a list: an agent that has opened
        #: ten thousand drops them one at a time and in no particular order, and a list would
        #: search itself for each of them.
        self._sessions: dict[int, weakref.ref[SessionBase]] = {}
        self._holds = 0  # what the next session is filed under
        self._opened: list[str] = []
        self._watchers: list[
            Callable[[AgentBase, SessionBase | None, Event], None]
        ] = []
        #: What is hung on this agent's moments, which a flow adds to and takes from while
        #: the agent is running: the hooks are the flow's own callables rather than a table
        #: the backend read out of a settings file before anything started.
        self._hooks = Hooks(type(self).moments, self._id)
        self._stopped = False
        #: Asked as each turn starts for anything said to this agent while no turn was open,
        #: which goes into that turn. Left unset by a flow driven from the command line,
        #: where there is nobody to say anything mid-run.
        self.waiting: Callable[[], list[str]] | None = None
        #: Asked when a turn of this agent stops to ask its user something, and answers with
        #: what was said or None when nobody is there to say it. Left unset by a flow driven
        #: from the command line, where there is nobody at all.
        self.ask: Callable[[Question], str | None] | None = None
        #: Asked by a flow between turns for the next thing to say to this agent, and answers
        #: with it or None once there will be nothing more. Left unset by a flow driven from
        #: the command line, where nobody is at a prompt. It MUST answer within a while of the
        #: agent being stopped: nothing releases a flow waiting inside it but itself.
        self.prompting: Callable[[], str | None] | None = None
        #: The run this agent is part of, set by whatever is driving the flow and told of
        #: every session this agent opens. Left unset by an agent driven by hand, which is
        #: not a run of anything.
        self.cycle: Journal | None = None
        #: The skills the flow driving this agent brings, mounted onto every session it
        #: opens. Set by whatever started the flow, since a skill is the flow's rather than
        #: the agent's: the same agent under another flow carries that flow's instead.
        self._loads: tuple[Loaded, ...] = ()
        # The machine this agent's turns land on, once the first of them has brought it up.
        self._anchor: AnchorConfig | None = None
        #: Which account its turns run as now: the one it was configured with, or the one it
        #: moved to when that failed. Looked up once, when the first turn needs it, and held
        #: from then on -- an account taken away while a flow is running is not a reason for
        #: the next turn of that flow to sign in as somebody else. None until it is asked for.
        self._at: Provider | None = None
        self._starting = threading.Lock()
        #: The agent this one's turns go to once it has nowhere left to run, once it has been
        #: asked for -- False for an agent that falls back nowhere, so that reading the chain
        #: is a thing that happens once rather than once a turn.
        self._stands_in: AgentBase | Literal[False] | None = None
        #: The rest of that chain, for an agent that is itself a stand-in, or None for one
        #: that has not been told and reads it off what is written down.
        self._beyond: tuple[str, ...] | None = None

    @property
    def id(self) -> str:
        """What this agent is called, and what a trace groups its sessions under."""
        return self._id

    def runs_on(self, machine: MachineConfig | None) -> None:
        """Puts this agent's turns on the machine the flow said they land on.

        For a place a flow declared as one of its own to isolate: the flow says the image and
        nobody is asked, so the machine is settled here rather than chosen anywhere. Said
        before the agent has opened anything, because a session resumes under the settings it
        opened with -- which is the reason the config is frozen in the first place.

        Args:
          machine: Where its turns are to land, or None to leave them here.

        Raises:
          RuntimeError: If this agent has already opened a session, which is a conversation
            that would resume somewhere other than it started.
        """
        from dataclasses import replace

        if self._opened:
            raise RuntimeError(f"{self._id} has already opened a session")
        self._config = replace(self._config, machine=machine)

    def reconfigure(self, config: AgentConfig) -> None:
        """Sets this agent up as something else, from its next turn on.

        The config is frozen because a session resumes under the settings it opened with, and
        an agent that quietly changed model halfway through a conversation would be one
        conversation split across two. This is the one thing that is not that: it is asked for
        by hand, by whoever is watching the run, about an agent that is thinking too little or
        is allowed too much -- and what it says is that everything from here on is to be the
        other thing. The turn under way keeps what it started with, a model not thinking
        harder halfway through an answer.

        What an agent is cannot be changed this way: a backend is the class this is, and one
        of those becoming another is another object, which is a thing only building the flow
        again does.

        Args:
          config: What every turn of it is to run at from now on.

        Raises:
          ValueError: If the backend cannot express the service tier asked for. The same
            refusal as at construction, and for the same reason: a tier that cannot be sent
            must be said no to rather than silently served at another one.
        """
        self._serves(config)
        self._config = config

    def _serves(self, config: AgentConfig) -> None:
        """Refuses a config this backend has no way of expressing.

        Two of them: a service tier it cannot send, and web search it cannot switch off.
        Both are refused wherever the config arrives -- where the agent is made, and where one
        already running is set up as something else -- since a setting a backend quietly
        ignored would be a setting that lies about what the agent is doing.

        Args:
          config: What the agent is to run at.

        Raises:
          ValueError: If the tier is not one of :attr:`service_tiers`, or web search was
            switched off for a backend with no way of being told.
        """
        if config.service_tier not in self.service_tiers:
            raise ValueError(
                f"{type(self).__name__} does not support service tier "
                f"{config.service_tier!r}; expected {', '.join(self.service_tiers)}"
            )
        if not config.web_search and not self._tellable():
            raise ValueError(
                f"{type(self).__name__} has no way of being told not to search the web; "
                "web_search must be on for it"
            )

    def _tellable(self) -> bool:
        """Whether this backend can be told whether its agents may search the web.

        Read off the backend rather than written down on the class, so that the one place
        that says what a CLI is is the one place this is said too.

        Returns:
          True where it can be told, and False for a backend nothing here knows -- a
          stand-in written for a test, a CLI somebody added by hand -- which is the answer
          that refuses rather than the one that pretends.
        """
        from hmz.backends import named

        profile = named(self.backend)
        return profile is not None and profile.searches

    def clone(
        self,
        *,
        config: AgentConfig | None = None,
        name: str | None = None,
        skills: Iterable[Loaded] | None = None,
    ) -> Self:
        """Another agent of this one's backend, differing in what this call names and nothing.

        Which is what an agent set up differently is: not this agent changed, but a second one
        beside it. An agent is what it was made as -- a flow is handed one and drives it, and
        a flow that could set it up as something else would be a flow rewriting what the
        person who started the run chose -- so the way to have one that is not quite this one
        is to make one, and this is that written down::

            careful = agent.clone(config=replace(agent.config, effort="max"))

        Everything that is not named is this agent's. Everything that a run puts on an agent
        rather than sets it up with is not: the clone has opened no conversation, has spent
        nothing, is watched by nobody, has no hook hung on it, and is being written down
        nowhere. Two agents, which is what they are.

        And nothing about it can be said afterwards. That is the whole of the point: what an
        agent is, is settled where it is made, and this is where a second one is made.

        Args:
          config: What every session of it runs at, or None for this agent's own.
          name: What to call it, or None for one nothing else answers to -- since two agents
            are two agents, and a trace that read them as one would read a comparison of two
            efforts as one agent that changed its mind. Given a name, it is that agent.
          skills: The flow's skills it carries, or None for the ones this agent carries.

        Returns:
          The new agent.
        """
        made = self._remade(self._config if config is None else config, name)
        made.loads(self._loads if skills is None else skills)
        return made

    def _remade(self, config: AgentConfig, name: str | None) -> Self:
        """Builds one of this class, for a backend whose making is the ordinary one.

        Overridden by an agent that is not made from a config -- the person at the prompt is
        made from nothing at all -- so that :meth:`clone` is one thing wherever it is called.

        Args:
          config: What it runs at.
          name: What to call it, or None for one nothing else answers to.

        Returns:
          The new agent.
        """
        return type(self)(config, name=name)

    def rename(self, name: str) -> None:
        """Calls this agent what the flow driving it calls it, if it has no name of its own.

        A flow that declares its agents as a named tuple has said what each of them is for --
        builder, reviewer -- and that is a better name than a hex tail. One handed an agent
        that was named where it was made says nothing: the name it was given is the name.

        Args:
          name: What the flow calls this one.
        """
        if not self._named:
            self._id = name
            self._hooks.agent = name

    def loads(self, skills: Iterable[Loaded]) -> None:
        """Says which skills every session this agent opens is to be given.

        Told to the agent rather than configured on it, because they are the flow's: the
        agent is what the flow was handed, and the same agent under another flow carries what
        that flow works by instead.

        Args:
          skills: The skills, already fetched to somewhere they can be copied from.
        """
        self._loads = tuple(skills)

    @property
    def loaded(self) -> tuple[Loaded, ...]:
        """The skills mounted onto every session this agent opens, which are the flow's."""
        return self._loads

    @property
    def hooks(self) -> Hooks:
        """What is hung on this agent's moments, to be hung on and taken from as it runs.

        On the agent rather than on a session, so that a hook covers every conversation the
        agent holds -- and so that a flow which has already started can hang one, which is
        the whole reason these are callables rather than a table in a settings file::

            with agents.builder.hooks.on(Moment.STOP, keep_going):
                agents.builder(task)
        """
        return self._hooks

    @property
    def stopped(self) -> bool:
        """Whether this agent has been told to take no further turn.

        Which is not the same as the turn it was taking having failed, though that is how it
        looks from inside one: a process killed under a turn is a turn that could not finish.
        """
        return self._stopped

    @property
    def goals_enabled(self) -> bool:
        """Whether this agent may be run under a backend goal.

        This is a per-agent runtime policy, distinct from :attr:`pursues`, which says whether
        the backend has a goal feature at all.
        """
        return self._config.goals

    def disable_goals(self) -> None:
        """Prevents this agent and its sessions from starting backend goals.

        Ordinary turns are unaffected. Backends that expose goals outside ``pursue`` may
        override this to disable the corresponding runtime feature as well.
        """
        from dataclasses import replace

        self._config = replace(self._config, goals=False)

    @property
    def backend(self) -> str:
        """The coding agent this drives, named as a command line names it.

        Read off the class rather than written down twice: `ClaudeCodeAgent` drives `claude`,
        and an agent whose class says otherwise would be the one thing nobody could check.
        Read back through the backend that answers to it, so that the name is one the rest of
        humanize can look up -- `GrokBuildAgent` drives `grok`, which is what its accounts,
        its skills and its cost are all kept under.
        """
        from hmz.backends import named

        said = (
            type(self)
            .__name__.removesuffix("Agent")
            .removesuffix("CLI")
            .removesuffix("Code")
            .lower()
        )
        profile = named(said)
        return profile.name if profile is not None else said

    @property
    def opened(self) -> list[str]:
        """The backend's id for every session this agent has opened, oldest first.

        What :attr:`sessions` cannot say: a flow that drops a session per turn keeps none of
        them, but the backend logged them all, and a trace of the run has to know whose they
        were. Ids rather than sessions, so remembering a day of turns costs a list of strings.
        """
        with self._holding:
            return list(self._opened)

    @property
    def config(self) -> AgentConfig:
        """The model and effort every session of this agent was configured with.

        What it was configured with rather than what it is running at: the config is frozen,
        because a session resumes under the settings it opened with, and :attr:`effort` is
        the one of them a flow may move while the agent runs.
        """
        return self._config

    def spent(self) -> Usage:
        """What this agent has cost so far, by the kind of token it went on.

        Every session it has opened, the ones nobody holds any more included: a flow that
        drops a session a turn has still spent what those turns spent.

        Returns:
          Every kind its backend counts, `input` and `output` among them.
        """
        return self._meter.spent()

    def rate(self, over: float = WINDOW) -> Usage:
        """How fast this agent is spending, by kind, over the last stretch of it.

        Args:
          over: How far back to measure, in seconds.

        Returns:
          Tokens a second, by kind.
        """
        return self._meter.rate(over)

    def juice(self, over: float = WINDOW) -> float:
        """What an average turn of this agent's model came out with, over the last stretch.

        Every session it has opened, the ones nobody holds any more included, as for
        :meth:`spent`.

        Args:
          over: How far back to measure, in seconds.

        Returns:
          Output tokens per turn, and 0.0 where no turn has landed in the window.
        """
        return self._meter.juice(over)

    @property
    def effort(self) -> str:
        """How hard this agent's turns are to think, from the next one on.

        What it was configured with until a flow says otherwise. Setting it moves every
        session of this agent that has not been told something of its own -- a flow watching
        what a loop is costing turns the whole agent down, and one nursing a single
        conversation through a hard patch turns that session up.
        """
        return self._effort or self._config.effort

    @effort.setter
    def effort(self, effort: str) -> None:
        """Has this agent's turns think at something other than what it was configured with.

        Args:
          effort: The backend's own word for it, or "" to go back to the configured one.
        """
        self._effort = effort or None

    @property
    def anchor(self) -> AnchorConfig | None:
        """Where this agent's turns land, or None while they land here.

        An agent given a machine brings it up the first time this is asked for, which is the
        first turn it is given: constructing an agent pulls no image and starts no container,
        and a flow that configures more agents than it drives pays for the ones it drives. The
        machine then stands for as long as the agent does -- its sessions are turns of one
        conversation each, and they must find the workspace as the last turn left it -- and is
        taken down when the agent is collected, or at exit for one held to the end. One that
        was already running is only reached, and is left running.
        """
        if self._config.machine is None:
            return None
        # Two sessions of one agent share the machine rather than bringing up one each.
        with self._starting:
            if self._anchor is None:
                machine = self._config.machine.create()
                self._anchor = machine.start()
                # Held by the finalizer alone, which is what takes the machine down: when the
                # agent is collected, and at exit for one held to the end.
                weakref.finalize(self, machine.stop)
            return self._anchor

    @property
    def provider(self) -> Provider | None:
        """Which account this agent's turns run as, or None while they run as the CLI does.

        None is the account this machine is already signed into: an agent nobody gave one
        runs the CLI exactly as whoever is at this machine runs it, with nothing added to its
        environment, nothing taken out of it and no path answered by another. Which is why
        this answers None for that rather than the account :meth:`node` holds -- everything
        that asks whether a turn is run under an account is asking whether any of that is to
        happen, and for the machine's own the answer is no.

        Raises:
          ValueError: If this agent was configured with a provider there is no such thing as.
            Said the first time a turn needs one rather than swallowed: an agent that cannot
            find the account it was told to run as must not quietly run as the one whoever
            started it happens to be signed in as.
        """
        held = self.node()
        return held if held.name else None

    def node(self) -> Provider:
        """The account this agent is on now, whether or not it is one anybody made.

        Which is where its chain is walked from: the one it was configured with, or the one
        this machine is signed into for an agent given none, or -- once a turn has moved --
        wherever it moved to. Read once and kept, for the reason :attr:`provider` is.

        Returns:
          The account. Never None: an agent that was given none is on the account this
          machine is already signed into, which is an account of every backend there is.

        Raises:
          ValueError: If this agent was configured with a provider there is no such thing as.
        """
        from hmz import providers

        with self._starting:
            if self._at is None:
                found = providers.find(self.backend, self._config.provider)
                if found is None and not self._config.provider:
                    # A backend `hmz.backends` has never heard of -- a CLI somebody is
                    # writing, a stand-in a test drives -- still takes its turns as whoever
                    # is at this machine. That is an account with nothing written down about
                    # it, since there is nowhere to write it, rather than no account at all.
                    found = providers.Provider(self.backend, providers.LOCAL, way="")
                if found is None:
                    raise ValueError(
                        f"{self._id}: no {self.backend} provider called "
                        f"{self._config.provider!r}"
                    )
                self._at = found
            return self._at

    def walks(self) -> tuple[Provider, ...]:
        """Every account a turn of this agent may be taken under, in the order it tries them.

        The one it is on, and then whatever that account falls back to, and whatever that one
        does: each account names the next, so a subscription that runs out falls to a key and
        a key that is refused falls to a gateway. Said on the accounts rather than on the
        agent because it is the account that goes down, and whichever agent was running under
        one when it did is the agent that needs somewhere else to go.

        A chain may begin at the account this machine is signed into, which is where an agent
        nobody gave an account starts: `hmz providers falls-back claude/ spare` is what says
        so, and until somebody does it is a chain of one, tried once.

        Returns:
          One per account, the one it is on first. From wherever it is now rather than from
          where it started: an agent that has already moved does not walk the part of the
          chain that failed again. Never empty.
        """
        from hmz import providers

        return tuple(providers.chain(self.node()))

    @property
    def spec(self) -> str:
        """This agent as a command line names it: `CLI[@ACCOUNT]/MODEL:EFFORT`.

        The account it was configured with rather than the one it has moved to, since that is
        what somebody wrote down when they said where this agent falls back to: an agent that
        walked its own accounts and ran out is still the agent they meant.
        """
        from hmz import fallbacks

        return fallbacks.spec(
            self.backend, self._config.model, self.effort, self._config.provider
        )

    def stands_in(self) -> AgentBase | None:
        """The agent that takes this one's turns, once this one has nowhere left to run.

        Which is the other half of a chain: an account that goes down is answered by the next
        account of the same backend, inside the conversation that was running, and this is
        what is left when there is no next account -- a model retired, a CLI that will not
        start, a whole account rate-limited rather than one request. Another agent then, and a
        turn taken in a session of its own, because no backend can be handed another
        backend's session id.

        Made at most once and kept, for the reason an account that has moved stays moved: the
        agent that went down is not one to try again each turn, and a stand-in made afresh
        every time would be a new conversation and a new set of skills mounted every turn.
        Held only for as long as this agent is: it is this agent's answer.

        Returns:
          The agent to take the turn, already carrying this agent's skills and holding the
          rest of the chain so that it cannot come round to this one, or None where nothing
          was written down about this agent -- which is the turn failing as it always has.
        """
        from hmz import fallbacks

        with self._starting:
            if self._stands_in is not None:
                return self._stands_in or None
            walked = (
                self._beyond
                if self._beyond is not None
                else tuple(fallbacks.chain(self.spec)[1:])
            )
            # Written down as "nothing", so that an agent with nowhere to go is asked once
            # rather than once a turn: reading the chain is reading a file.
            self._stands_in = made = _built(walked[0]) if walked else False
            if made:
                made.loads(self._loads)
                made.cycle = self.cycle
                # Only the steps after its own: a chain read again from the top by each hop
                # would be a chain that walks the agents before it a second time.
                made._beyond = walked[1:]
            return made or None

    def fall_back(self, provider: Provider) -> None:
        """Runs every turn from here on under another account.

        Args:
          provider: The account to run as.
        """
        with self._starting:
            self._at = provider
        self.moved()

    def moved(self) -> None:  # noqa: B027  -- empty on purpose, and so not abstract
        """Told that this agent is on another account from here on.

        A session is a process, a server or a runtime started with an account's own
        environment and its own credential paths, and none of that changes under a process
        that is already up -- so everything held open under the account just left has to be
        opened again. Nothing is torn down here, though: what holds one is the thread taking
        turns in it, and reaching across to kill a process another thread is reading would end
        a turn that was doing nothing wrong and might block on a pipe that thread is sitting
        in.

        So this says the account has changed and each holder answers for itself, on its own
        thread, the next time it needs what it holds: a session compares the account its
        process was started under with the one the agent is on now, and starts another when
        they differ. A backend holding something of its own per agent does the same where it
        hands that thing out.
        """

    def environment(self) -> Mapping[str, str]:
        """What this agent's turns are run with, on top of the environment they inherit.

        Which is what a provider that is a key, an endpoint or an account on somebody's cloud
        comes to: every one of these CLIs reads such a thing out of a variable of its own.

        Returns:
          The variables to add, which is nothing at all for an agent running as its CLI does.
        """
        from hmz import providers

        return providers.environ(self.provider)

    def hushed(self) -> frozenset[str]:
        """The variables a turn of this agent is run without, whoever left them lying about.

        A provider is which account the agent is, and these CLIs will take an account from an
        environment variable in preference to the credentials they were signed in with: an
        `ANTHROPIC_API_KEY` exported in somebody's shell profile outranks the file a provider
        holds, and the turn would run -- and bill -- as that key with nothing about it looking
        wrong. So a turn under a provider is run without every variable its backend would read
        an account from, except the ones that provider set itself.

        Returns:
          The variables to take away, which is nothing at all for an agent running as its CLI
          already runs: an agent with no provider is left exactly as it was found.
        """
        from hmz.backends import named

        provider = self.provider
        profile = named(self.backend)
        if provider is None or profile is None:
            return frozenset()
        return profile.accounts() - set(provider.env)

    def _environ(self) -> dict[str, str] | None:
        """The whole environment one of this agent's processes is started with.

        Args:
          None.

        Returns:
          This process's own, less what a provider hushes and plus what it sets, or None
          where there is nothing to change -- which is inheritance, as it always was.
        """
        added, hushed = self.environment(), self.hushed()
        if not added and not hushed:
            return None
        return {
            name: value for name, value in os.environ.items() if name not in hushed
        } | dict(added)

    def spawned(self, argv: list[str], cwd: str = "") -> list[str]:
        """One turn of this agent, as the command to actually spawn.

        Every backend renders its own call and then comes here, so that what a turn is wrapped
        in is decided once: the provider's own arguments are added to the CLI's command line,
        and the whole of it is put under whatever has to supervise it.

        A turn that is both anchored and run under a provider is supervised once, not twice: a
        process has one tracer, so the anchor is told which paths to answer rather than being
        wrapped in something that would answer them for it.

        Args:
          argv: The backend's own command for this turn.
          cwd: Where the session it is a turn of works, as the machine it lands on names it,
            or "" for the workspace itself. An anchored turn is told there rather than put
            there: the agent is started in this machine's mirror of that directory, which is
            the anchor's to work out.

        Returns:
          The command to spawn, which is `argv` itself for an agent that is neither anchored
          nor run under a provider -- which is most of them.
        """
        from hmz.backends import elsewhere

        # A command this machine's PATH does not name is run by the path it is installed at
        # instead: a flow started by something with a PATH of its own -- a notebook kernel, a
        # service, the launcher of a runtime platform -- would otherwise fail to start an
        # agent that is installed here. Everything else is spawned exactly as it was written,
        # so a name PATH answers to is still the name that runs, and one nothing answers to
        # still fails saying what could not be found.
        if (found := elsewhere(argv[0])) is not None:
            argv = [found, *argv[1:]]
        provider = self.provider
        if provider is not None and provider.args:
            argv = [*argv, *provider.args]
        swaps = provider.swaps() if provider is not None else ()
        # What the provider hands the agent as variables is the agent's own, and the target
        # is not to be given it: everything the agent exports is inherited by every command
        # it runs there, and a key crossing to another machine is a key on that machine.
        private = tuple(provider.env) if provider is not None else ()
        anchor = self.anchor
        if anchor is not None:
            return anchor.command(argv, swaps=swaps, private=private, chdir=cwd)
        return provider.command(argv) if provider is not None else argv

    @property
    def sessions(self) -> list[SessionBase]:
        """The sessions opened on this agent and still held by someone, oldest first.

        Held weakly, so a flow that opens a session per turn -- a Ralph loop runs for days --
        does not grow an agent by one session a turn for as long as it runs.
        """
        with self._holding:
            held = list(self._sessions.values())
        return [session for ref in held if (session := ref()) is not None]

    def stop(self) -> None:
        """Has this agent take no further turn, and ends the one it is taking.

        A turn is where a flow spends its time -- a model can think for minutes -- so a stop
        that waited for one would not read as a stop. What the turn was doing is left where
        it got to; what ends is the agent's part in it.

        And whatever is standing in for it, since a turn of this agent's may be being taken
        there: an agent stopped whose stand-in went on thinking would be a run ended by hand
        that did not end.
        """
        self._stopped = True
        for session in self.sessions:
            session.close()
        with self._starting:
            stood_in = self._stands_in
        if stood_in:
            stood_in.stop()

    def watch(
        self, listener: Callable[[AgentBase, SessionBase | None, Event], None]
    ) -> None:
        """Has everything this agent's turns say reach `listener` as they say it.

        Args:
          listener: What to tell, as this agent, the conversation that said it, and the thing
            said. The conversation is None for something the agent said rather than one of
            them -- a question put by a server that serves every session of it at once.
        """
        with self._holding:
            self._watchers.append(listener)

    def _hold(self, session: SessionBase) -> None:
        """Files a session as this agent's, weakly, as the session opens.

        Weakly, so that a flow which drops a session per turn does not grow the agent by one
        a turn; filed under a number of its own, so that dropping one of ten thousand costs
        the same as dropping one of two.

        Args:
          session: The session, which has just been made for this agent.
        """
        with self._holding:
            self._holds += 1
            at = self._holds
            self._sessions[at] = weakref.ref(session, lambda _gone: self._forget(at))

    def _forget(self, at: int) -> None:
        """Drops a session that has been collected, whoever else has dropped it already.

        Called from wherever the collector happens to be -- a turn's own thread as a flow
        lets a session go, or the interpreter on its way out, or a line of this class that
        was itself holding the lock, which is why the lock is re-entrant. A place that no
        longer holds it is a place with nothing to do here, and raising out of a finalizer
        only puts an `Exception ignored in:` on the terminal a flow is being watched from.

        Args:
          at: What the session was filed under.
        """
        with self._holding:
            self._sessions.pop(at, None)

    def _opens(self, session: str) -> None:
        """Writes down a session this agent has just opened, from the turn that opened it.

        Args:
          session: The backend's id for it.
        """
        with self._holding:
            self._opened.append(session)

    def _heard(self, event: Event, session: SessionBase | None = None) -> None:
        """Tells everyone watching what a turn of this agent just said.

        A watcher that raises is a watcher's own problem: a flow must not fail because
        something looking at it did. Told from a copy of the list rather than from the list,
        since a turn saying something is a turn on some other thread than the one hanging a
        watcher on the agent.

        Args:
          event: What was said.
          session: Which conversation said it, or None for something the agent said rather
            than one of them.
        """
        if not self._watchers:
            return
        with self._holding:
            watching = tuple(self._watchers)
        for listener in watching:
            with contextlib.suppress(Exception):
                listener(self, session, event)

    def asked(self, question: Question) -> str | None:
        """Puts something a turn stopped to ask to whoever is driving this agent.

        Called from the turn's own thread, which waits here: an agent that has asked has
        stopped working until it is answered.

        Args:
          question: What the agent wants to know.

        Returns:
          The answer, or None when there is nobody to ask -- a flow run from the command
          line, or an interface told its user is away. The backend is then told that nobody
          answered rather than left waiting, since a turn waiting on an answer that is not
          coming is a flow that has stopped.
        """
        self._heard(Event(kind="asks", text=question.text))
        # An agent that has stopped to ask is an agent that wants a person, which is the one
        # thing a flow running unattended has to be able to hear about.
        self._hooks.fire(
            Occasion(moment=Moment.NOTIFICATION, agent=self._id, said=question.text)
        )
        if self.ask is None:
            return None
        try:
            return self.ask(question)
        except Exception:  # noqa: BLE001 -- whatever was asked failed, and the turn goes on
            return None

    def prompted(self) -> str | None:
        """Waits for the next thing to say to this agent, for a flow that is a conversation.

        Called between turns, from the thread the flow runs on -- which waits here, there
        being nothing for a flow to do until it has been told something.

        Returns:
          What was said, or None once there will be nothing more: a flow driven from the
          command line, where nobody is at a prompt, or an interface that has gone. A flow
          that is a conversation then has had its conversation, and returns.

        Raises:
          Stopped: If the agent was told to take no further turn while this was waiting. A
            run ended by hand is written down as ended by hand, and answering with None here
            would write it down as one that finished.
        """
        said = None
        if self.prompting is not None:
            try:
                said = self.prompting()
            except Exception:  # noqa: BLE001 -- whoever was asked failed, and the flow ends
                said = None
        if self._stopped:
            raise Stopped(f"{self._id} was stopped")
        return said

    @overload
    def __call__(
        self,
        prompt: str,
        *,
        suppress: bool = False,
        cwd: str | os.PathLike[str] | None = None,
    ) -> str: ...

    @overload
    def __call__[T: BaseModel](
        self,
        prompt: str,
        *,
        suppress: bool = False,
        schema: type[T],
        cwd: str | os.PathLike[str] | None = None,
    ) -> T | None: ...

    def __call__[T: BaseModel](
        self,
        prompt: str,
        *,
        suppress: bool = False,
        schema: type[T] | None = None,
        cwd: str | os.PathLike[str] | None = None,
    ) -> str | T | None:
        """Runs one turn in a session of its own, and keeps nothing.

        Which is the shape a Ralph loop is made of: the agent starts from the task and the
        repository, every turn, with none of the last one in context. A flow whose turns are
        to remember each other holds the session :meth:`new` gives it instead.

        Args:
          prompt: The input prompt for the turn.
          suppress: Whether a turn that fails answers with nothing, as for
            :meth:`SessionBase.__call__`.
          schema: The shape to answer in, as for :meth:`SessionBase.__call__` -- which is
            what a flow asking one agent a question rather than setting it to work wants:
            `agents.reviewer(asked, schema=Review).done` is the review read as a decision.
          cwd: Where the turn works, or None for wherever the flow is. One agent given a
            directory apiece is one agent working in several places at once, which is what a
            flow with a worktree per task is doing.

        Returns:
          What the agent answered, stripped, or the model it was asked for.
        """
        opened = self._opens_at(cwd)
        if schema is None:
            return opened(prompt, suppress=suppress)
        return opened(prompt, suppress=suppress, schema=schema)

    def pursue(
        self,
        objective: str,
        *,
        suppress: bool = False,
        context: str | None = None,
        cwd: str | os.PathLike[str] | None = None,
    ) -> str:
        """Runs a goal in a session of its own, and keeps nothing.

        Args:
          objective: What the agent is to have achieved before it stops.
          suppress: Whether a goal that fails answers with nothing, as for
            :meth:`SessionBase.pursue`.
          context: An ordinary turn to add to the goal's conversation first, as for
            :meth:`SessionBase.pursue`.
          cwd: Where it works, as for :meth:`__call__`.

        Returns:
          What the agent answered once it stopped, stripped.
        """
        return self._opens_at(cwd).pursue(objective, suppress=suppress, context=context)

    @overload
    async def aturn(
        self,
        prompt: str,
        *,
        suppress: bool = False,
        cwd: str | os.PathLike[str] | None = None,
    ) -> str: ...

    @overload
    async def aturn[T: BaseModel](
        self,
        prompt: str,
        *,
        suppress: bool = False,
        schema: type[T],
        cwd: str | os.PathLike[str] | None = None,
    ) -> T | None: ...

    async def aturn[T: BaseModel](
        self,
        prompt: str,
        *,
        suppress: bool = False,
        schema: type[T] | None = None,
        cwd: str | os.PathLike[str] | None = None,
    ) -> str | T | None:
        """The same turn as :meth:`__call__`, awaited: `await agent.aturn(prompt)`.

        A session of its own and nothing kept, as calling the agent is -- run on a thread of
        its own, so that a flow written as `async def run` can have as many of these going as
        it likes without any one of them holding up the rest.

        Args:
          prompt: The input prompt for the turn.
          suppress: Whether a turn that fails answers with nothing, as for :meth:`__call__`.
          schema: The shape to answer in, as for :meth:`__call__`.
          cwd: Where the turn works, as for :meth:`__call__` -- which is what makes many at
            once many places at once.

        Returns:
          What :meth:`__call__` would have answered with.
        """
        opened = self._opens_at(cwd)
        if schema is None:
            return await opened.aturn(prompt, suppress=suppress)
        return await opened.aturn(prompt, suppress=suppress, schema=schema)

    async def apursue(
        self,
        objective: str,
        *,
        suppress: bool = False,
        context: str | None = None,
        cwd: str | os.PathLike[str] | None = None,
    ) -> str:
        """The same goal as :meth:`pursue`, awaited: `await agent.apursue(objective)`.

        Args:
          objective: What the agent is to have achieved before it stops.
          suppress: Whether a goal that fails answers with nothing, as for :meth:`pursue`.
          context: An ordinary turn to add to the goal's conversation first, as for
            :meth:`pursue`.
          cwd: Where it works, as for :meth:`__call__`.

        Returns:
          What :meth:`pursue` would have answered with.
        """
        return await self._opens_at(cwd).apursue(
            objective, suppress=suppress, context=context
        )

    def batch_new(
        self, count: int, cwd: str | os.PathLike[str] | None = None
    ) -> list[SessionBase]:
        """Opens as many sessions as it is asked for, at once.

        Sessions cost nothing until a turn lands in one -- a session is a conversation that
        has not started, and the backend has not been told it exists -- so this is a list to
        hand to whatever runs the turns, however long a list it is. Which is the shape a
        fan-out has: ten thousand conversations, each of which will remember its own.

        Args:
          count: How many to open. None at all for a count of nothing or less.
          cwd: The directory they all work in, or None for the one the flow is running in. A
            session per directory is `[agent.new(one) for one in directories]` instead.

        Returns:
          The sessions, in the order they were opened, which is the order the agent has them.
        """
        return [self._opens_at(cwd) for _ in range(max(count, 0))]

    @overload
    def batch(
        self,
        prompts: Sequence[str],
        *,
        suppress: bool = False,
        at_once: int = 0,
        cwd: str | os.PathLike[str] | None = None,
    ) -> list[str]: ...

    @overload
    def batch[T: BaseModel](
        self,
        prompts: Sequence[str],
        *,
        suppress: bool = False,
        schema: type[T],
        at_once: int = 0,
        cwd: str | os.PathLike[str] | None = None,
    ) -> list[T | None]: ...

    def batch[T: BaseModel](
        self,
        prompts: Sequence[str],
        *,
        suppress: bool = False,
        schema: type[T] | None = None,
        at_once: int = 0,
        cwd: str | os.PathLike[str] | None = None,
    ) -> list[Any]:
        """Runs many turns at once, each in a session of its own, and keeps none of them.

        :meth:`__call__` as many times over as there are prompts, all of them going at the
        same time: a fan-out where each turn starts from the task and the repository with none
        of the others in context. What comes back is in the order it was asked for, whichever
        turn landed first.

        A turn is a coding agent and everything it starts, so how many to have going at once
        is a question about the machine rather than about this library: `at_once` is where a
        flow says, and a flow that says nothing gets the fan-out it asked for.

        Args:
          prompts: What to ask, one turn apiece.
          suppress: Whether a turn that fails answers with nothing, as for :meth:`__call__`.
            A batch that does not suppress raises the first failure once every turn of it has
            landed: a turn already running cannot be taken back.
          schema: The shape to answer in, as for :meth:`__call__`.
          at_once: How many turns to have running at a time, or 0 for all of them.
          cwd: Where every turn of it works, or None for wherever the flow is. A batch across
            directories is a session apiece -- `agent.new(one)` -- gathered.

        Returns:
          One answer per prompt, in the order the prompts were given.

        Raises:
          subprocess.CalledProcessError: If a turn failed and `suppress` is not set.
          Stopped: If the agent has been told to take no further turn.
        """
        asked = list(prompts)
        if not asked:
            return []

        def one(prompt: str) -> Any:
            if schema is None:
                return self(prompt, suppress=suppress, cwd=cwd)
            return self(prompt, suppress=suppress, schema=schema, cwd=cwd)

        # Sized to the batch rather than kept between them: a fan-out is over when its
        # answers are in, and the threads it took go with it.
        with ThreadPoolExecutor(
            max_workers=_at_once(at_once, len(asked)),
            thread_name_prefix=f"{self.id}-at",
        ) as crowd:
            return list(crowd.map(one, asked))

    @overload
    async def abatch(
        self,
        prompts: Sequence[str],
        *,
        suppress: bool = False,
        at_once: int = 0,
        cwd: str | os.PathLike[str] | None = None,
    ) -> list[str]: ...

    @overload
    async def abatch[T: BaseModel](
        self,
        prompts: Sequence[str],
        *,
        suppress: bool = False,
        schema: type[T],
        at_once: int = 0,
        cwd: str | os.PathLike[str] | None = None,
    ) -> list[T | None]: ...

    async def abatch[T: BaseModel](
        self,
        prompts: Sequence[str],
        *,
        suppress: bool = False,
        schema: type[T] | None = None,
        at_once: int = 0,
        cwd: str | os.PathLike[str] | None = None,
    ) -> list[Any]:
        """The same batch as :meth:`batch`, awaited: `await agent.abatch(prompts)`.

        Args:
          prompts: What to ask, one turn apiece.
          suppress: Whether a turn that fails answers with nothing, as for :meth:`batch`.
          schema: The shape to answer in, as for :meth:`__call__`.
          at_once: How many turns to have running at a time, or 0 for all of them.
          cwd: Where every turn of it works, as for :meth:`batch`.

        Returns:
          One answer per prompt, in the order the prompts were given.

        Raises:
          subprocess.CalledProcessError: If a turn failed and `suppress` is not set, once
            every turn of the batch has landed, as for :meth:`batch`.
        """
        import asyncio

        asked = list(prompts)
        if not asked:
            return []
        gate = asyncio.Semaphore(_at_once(at_once, len(asked)))

        async def one(prompt: str) -> Any:
            async with gate:
                if schema is None:
                    return await self.aturn(prompt, suppress=suppress, cwd=cwd)
                return await self.aturn(
                    prompt, suppress=suppress, schema=schema, cwd=cwd
                )

        # Gathered whatever any of them did, and only then raised: a batch that let the first
        # failure out from under the others would leave those others running with nobody
        # waiting for them, which is a turn nothing will ever read and a thread nothing joins.
        answered = await asyncio.gather(
            *(one(prompt) for prompt in asked), return_exceptions=True
        )
        for said in answered:
            if isinstance(said, BaseException):
                raise said
        return list(answered)

    def _opens_at(self, cwd: str | os.PathLike[str] | None) -> SessionBase:
        """Opens a session at a directory, or wherever the flow is where none was named.

        Asked for without the argument where there is none to give, so that an agent written
        before there was anywhere else to work -- a stand-in in somebody's suite, whose `new`
        takes only itself -- goes on being an agent.

        Args:
          cwd: The directory the conversation works in, or None.

        Returns:
          The session.
        """
        return self.new() if cwd is None else self.new(cwd)

    @abstractmethod
    def new(self, cwd: str | os.PathLike[str] | None = None) -> SessionBase:
        """Opens a new session, which stays unopened with the backend until its first turn.

        Args:
          cwd: The directory the conversation works in, or None for the one the flow is
            running in. It is a session's setting rather than a turn's because that is what
            it is to these backends: a conversation is rooted at a directory. Which is what
            makes a session per directory the way to work in several at once::

                held = [agent.new(worktree) for worktree in worktrees]
                await asyncio.gather(*(one.aturn(task) for one in held))

        Returns:
          A session with no history yet.
        """
