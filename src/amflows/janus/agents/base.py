"""The base classes: an agent is structure, a session is the history that structure runs on."""

from __future__ import annotations

import contextlib
import os
import queue
import subprocess
import sys
import threading
import uuid
import weakref
from abc import ABC, abstractmethod
from collections import Counter
from collections.abc import Callable, Iterable, Iterator, Mapping
from dataclasses import dataclass, field
from typing import IO, TYPE_CHECKING

from .config import AgentConfig

if TYPE_CHECKING:
    from amflows.coganchor import AnchorConfig

    from ..cycle import Cycle


class Stopped(Exception):
    """Raised in place of a turn, once the agent has been told to stop.

    A flow is a loop, and a loop that catches a failed turn goes round again -- so stopping
    one cannot be a failed turn. This is not a `CalledProcessError`, so the loops that carry
    on past a turn that failed do not carry on past this.
    """


@dataclass(frozen=True, slots=True)
class Event:
    """One thing an agent said while a turn was still running.

    What a turn returns is its last word; this is the rest of them, in the order they were
    said, so that a turn can be watched and talked to rather than only waited on.

    Attributes:
      kind: What was said. `text` is the agent talking, `reasoning` is it thinking aloud,
        `tool` is it using one, and `result` is the answer the turn ends on -- exactly one
        of which closes a turn. `failed` closes it the other way, carrying what went wrong
        in place of an answer. A watcher sees two more: `begins` and `ends`, which bracket
        the turn itself and are not part of what the agent said.
      text: The words themselves, ready to be shown.
      tokens: What the turn cost, as tokens spent per model. Only a `result` carries it, and
        only from a backend that says.
    """

    kind: str
    text: str
    tokens: Mapping[str, int] = field(default_factory=dict)


def say(text: str, sink: IO[str], *, end: str = "\n") -> None:
    """Puts something an agent said where the flow driving it can be watched.

    A sink that has gone away -- a flow piped into something that has exited -- takes nothing
    more rather than taking the turn down with it, whichever backend the turn was run through.

    Args:
      text: What the agent said.
      sink: The stream to put it on.
      end: What to follow it with, which is nothing for words arriving a fragment at a time.
    """
    with contextlib.suppress(OSError):
        sink.write(text + end)
        sink.flush()


def _tee(
    source: IO[str],
    sink: IO[str],
    captured: list[str],
    said: queue.Queue[Event | None] | None = None,
    kind: str = "text",
) -> None:
    """Copies `source` into `sink` line by line, keeping every line and announcing it.

    A sink that has gone away stops the copying but not the reading: a pipe nobody drains
    blocks the agent writing to it, and the turn would then be waiting on an agent that is
    itself waiting. The None at the end is how a turn reading `said` knows this stream is
    spent; a stream nobody is reading events from is drained and kept all the same.
    """
    with contextlib.suppress(OSError, ValueError):
        # A source closed under us is a process that has ended, which is not a failure here.
        for line in source:
            captured.append(line)
            if said is not None:
                said.put(Event(kind=kind, text=line.rstrip("\n")))
            say(line, sink, end="")
    with contextlib.suppress(OSError, ValueError):
        source.close()  # the reader closes what it read, whoever else has finished with it
    if said is not None:
        said.put(None)


class SessionBase(ABC):
    """One conversation with one agent, kept alive across turns.

    The first :meth:`run` opens the backend session; every later one resumes it, so the agent
    still has the earlier turns in context. Discarding the session is how a flow forgets:
    a new instance starts from nothing.
    """

    def __init__(self, agent: AgentBase):
        """Initializes an unopened session and registers it with its agent.

        Args:
          agent: The agent whose config every turn of this session runs at.
        """
        self._agent = agent
        self._id: str | None = None
        self._lock = (
            threading.Lock()
        )  # a conversation is a sequence: one turn at a time
        # A session drops itself from its agent when it is collected, so the agent neither holds
        # a flow's discarded sessions nor has to prune them while someone is reading them.
        agent._sessions.append(weakref.ref(self, agent._sessions.remove))

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

    def run(self, prompt: str) -> str:
        """Sends one turn, opening the session on the first call and resuming it after.

        Args:
          prompt: The input prompt for this turn.

        Returns:
          The response generated by the agent, stripped.

        Raises:
          subprocess.CalledProcessError: If the turn fails, with whatever the backend said
            about it attached as a diagnostic.
        """
        said = ""
        for event in self.stream(prompt):
            if event.kind == "result":
                said = event.text
        return said.strip()

    def stream(self, prompt: str) -> Iterator[Event]:
        """Sends one turn, saying what the agent says as it says it.

        The turn is over when the iterator is, and its last `result` event is what
        :meth:`run` answers with. A caller that only wants the answer wants :meth:`run`.

        Everything said here reaches whoever is watching the agent, bracketed by the `begins`
        and `ends` that say whose turn it was: a flow drives the sessions and answers to
        nobody, so the turns going past are the only place a run can be watched from.

        Args:
          prompt: The input prompt for this turn.

        Yields:
          What the agent said, in the order it said it.

        Raises:
          subprocess.CalledProcessError: If the turn fails, as for :meth:`run`.
        """
        if self._agent._stopped:
            raise Stopped(f"{self._agent.id} was stopped")
        # Anything said while nobody was working goes into this turn. A flow's own prompt is
        # the only way into a turn that has not started, so it is asked for here rather than
        # written to the session: a session between turns would answer it on its own.
        held = self._agent.waiting() if self._agent.waiting is not None else []
        if held:
            prompt = "\n\n".join([prompt, *held])
        self._agent._heard(Event(kind="begins", text=prompt))
        try:
            for event in self._stream(prompt):
                self._agent._heard(event)
                yield event
        finally:
            self._agent._heard(Event(kind="ends", text=""))

    @abstractmethod
    def _stream(self, prompt: str) -> Iterator[Event]:
        """Sends one turn, saying what the agent says as it says it.

        Args:
          prompt: The input prompt for this turn.

        Yields:
          What the agent said, in the order it said it.
        """

    def interject(self, text: str) -> None:
        """Puts a word in while a turn is running, as typing at the agent would.

        The agent reads it when it next looks, so a turn already under way takes it into
        account rather than being restarted with it.

        Args:
          text: What to say to the agent.

        Raises:
          NotImplementedError: If this backend takes a turn's whole prompt up front and has
            nowhere to put a later word.
        """
        raise NotImplementedError(f"{type(self).__name__} cannot be talked to mid-turn")

    def close(self) -> None:
        """Ends whatever this session is holding, so that a turn under way stops waiting.

        Does nothing by default: a session that is one command per turn holds nothing
        between them.
        """

    def _workspace(self) -> str:
        """The project directory a turn of this session works in, as the backend will find it.

        A backend run as a command inherits this from the flow, and coganchor puts an anchored
        one in its mirror of the workspace instead -- which is the workspace's own path unless
        the mirror was put somewhere else. A backend told where to work has to be told that
        same directory, since it is the one whose files reach the target.

        Returns:
          The absolute path to open the session at.
        """
        anchor = self._agent.anchor
        mirror = (anchor.shadow or anchor.workspace) if anchor else None
        return os.path.abspath(mirror or os.getcwd())

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
            self._agent._opened.append(session_id)
            if self._agent.cycle is not None:
                # The run is the only thing that knows this session was one of its own: the
                # backend logs it under this id and never says whose it was.
                self._agent.cycle.opened(self._agent, session_id)

    def pursue(self, objective: str) -> str:
        """Runs the session under a goal, which the agent then keeps itself going toward.

        This is the backend's own goal feature rather than a prompt that asks for one: the
        agent decides for itself that the objective has been met, and until it does, a turn
        that would have ended starts another. A flow that loops over this is running the
        objective again rather than nudging an agent that stopped early.

        Args:
          objective: What the agent is to have achieved before it stops.

        Returns:
          The agent's response once it stops, stripped.

        Raises:
          NotImplementedError: If this backend has no goal feature to reach for.
          subprocess.CalledProcessError: If the turn fails, as for :meth:`run`.
        """
        raise NotImplementedError(f"{type(self).__name__} has no goal feature")


class CommandSessionBase(SessionBase):
    """A session whose turns are one run of a coding agent's command line each."""

    def _stream(self, prompt: str) -> Iterator[Event]:
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

        Yields:
          A line at a time as the agent writes it, and the whole of what it said last.

        Raises:
          subprocess.CalledProcessError: If the agent CLI exits nonzero. Both streams are
            attached to it as diagnostics.
        """
        with self._lock:
            argv, stdin = self._turn(prompt)
            if (anchor := self._agent.anchor) is not None:
                # Spawned rather than called: coganchor's supervisor forks the agent and takes
                # the process's signal handling with it, which a flow pumping turns from
                # threads of its own has no way to lend it.
                argv = anchor.command(argv)
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
            ) as proc:
                assert proc.stdout is not None and proc.stderr is not None
                # Every pipe drains from the moment the agent starts: it puts its progress on
                # stderr and only the final message on stdout, and a prompt larger than the pipe
                # buffer would deadlock against an agent that prints before reading all of it.
                pumps = [
                    threading.Thread(
                        target=_tee, args=(proc.stdout, sys.stdout, out, said, "text")
                    ),
                    threading.Thread(
                        target=_tee, args=(proc.stderr, sys.stderr, err, said, "tool")
                    ),
                ]
                for pump in pumps:
                    pump.start()
                if stdin is not None:
                    assert proc.stdin is not None
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
                        yield event
                for pump in pumps:
                    pump.join()
                status = proc.wait()

            stdout = "".join(out)
            if status != 0:
                raise subprocess.CalledProcessError(status, argv, stdout, "".join(err))
            if self._id is None:
                # Separated, so that a stdout without a trailing newline cannot glue the first
                # line of stderr onto the last of stdout and hide a line the id is read from.
                self._adopt(self._read_session_id(stdout + "\n" + "".join(err)))
            yield Event(kind="result", text=stdout.strip())

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

    def __init__(self, agent: AgentBase):
        """Initializes a session holding no process yet.

        Args:
          agent: The agent whose config every turn of this session runs at.
        """
        super().__init__(agent)
        self._proc: subprocess.Popen[str] | None = None
        self._writing = threading.Lock()  # a line is written whole or not at all
        #: Answers still owed to us: the agent replies to each thing said with a turn of its
        #: own, so a word put in mid-turn adds one, and the turn is over when none are left.
        self._owed = 0
        #: What the agent has complained about, which is what a failed turn is reported with.
        self._complaints: list[str] = []
        #: What ends the process if the session is dropped while it is still up.
        self._reaper: weakref.finalize | None = None
        #: Who is reading the process's complaints, so a failed turn can wait for the last.
        self._draining: threading.Thread | None = None

    def _stream(self, prompt: str) -> Iterator[Event]:
        """Sends one turn as a line of JSON, and reads the agent's own back until it ends.

        A word put in while the turn runs is a thing said too, and the agent answers each
        thing said with a turn of its own. So the turn here is over when the agent has
        answered everything it was told, not when it first stops -- which is both how what
        was put in gets read at all, and how the next turn avoids picking up its answer.

        Args:
          prompt: The input prompt for this turn.

        Yields:
          What the agent said, in the order it said it.

        Raises:
          subprocess.CalledProcessError: If the agent exits rather than answering.
        """
        with self._lock:
            argv = self._command()
            proc = self._start(argv)
            assert proc.stdout is not None
            self._say(prompt)
            said = ""
            spent: Counter[str] = Counter()
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
                        self.close()
                        raise subprocess.CalledProcessError(
                            status, argv, event.text, complained
                        )
                    if event.kind == "result":
                        said = event.text
                        # Every answer in the turn cost something, the ones to a word put in
                        # mid-turn included, and the turn is what all of it is charged to.
                        spent.update(event.tokens)
                        with self._writing:
                            self._owed -= 1
                            settled = self._owed <= 0
                        if settled:
                            break
                        # An answer to something put in mid-turn: shown like anything else
                        # the agent says, and the turn goes on to whatever it was told last.
                        event = Event(kind="text", text=said)
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
                self.close()
                raise subprocess.CalledProcessError(status or 1, argv, said, complained)
            if self._agent.anchor is not None:
                # An anchored turn has to be over when it says it is: coganchor pushes what the
                # agent wrote when the session ends, so a process held open past the turn would
                # leave that turn's work still on this machine. The cost is that an anchored
                # session cannot be talked to between turns -- there is nothing there to hear.
                self.close()
            yield Event(kind="result", text=said, tokens=spent)

    def interject(self, text: str) -> None:
        """Says something to the agent now, whether or not a turn is running.

        Args:
          text: What to say to the agent.

        Raises:
          RuntimeError: If no process is up to hear it, which is a session no turn has opened.
        """
        self._say(text)

    def close(self) -> None:
        """Ends the process, and with it the conversation it was holding."""
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

    def _say(self, text: str) -> None:
        """Writes one line of JSON to the agent, whole, whoever else is writing.

        Counted once it has landed: the agent owes an answer for each thing said, and a turn
        is not over until it has given them all -- so counting one that never arrived would
        leave the next turn waiting for an answer nobody is going to give.

        Args:
          text: What to say.

        Raises:
          RuntimeError: If there is no process listening, or it stopped while being told.
        """
        with self._writing:
            proc = self._proc
            if proc is None or proc.stdin is None:
                raise RuntimeError("no turn is running to be talked to")
            try:
                proc.stdin.write(self._write(text))
                proc.stdin.flush()
            except (OSError, ValueError) as gone:
                # A stdin closed under us raises ValueError rather than BrokenPipeError.
                raise RuntimeError("the agent is no longer listening") from gone
            self._owed += 1

    def _start(self, argv: list[str]) -> subprocess.Popen[str]:
        """Starts the process if it is not up, and returns the one to speak to.

        Args:
          argv: The command to run, which this turn already asked for.

        Returns:
          The process to speak to, which is the one already up whenever there is one.
        """
        if self._proc is not None and self._proc.poll() is None:
            return self._proc
        if (anchor := self._agent.anchor) is not None:
            argv = anchor.command(argv)
        started = subprocess.Popen(
            argv,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            encoding="utf-8",
            errors="replace",
            bufsize=1,  # a line at a time, which is what the protocol is made of
        )
        assert started.stderr is not None
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
        self._reaper = weakref.finalize(self, started.kill)
        return started

    def _restarted(self) -> None:
        """Told that a new process is up, for whatever the old one's numbers were measured
        against.

        Does nothing by default. A backend counting anything per process says so here.
        """

    @abstractmethod
    def _command(self) -> list[str]:
        """The command the session's one process is run as.

        Returns:
          The command to run, which must speak the protocol on stdin and stdout.
        """

    @abstractmethod
    def _write(self, text: str) -> str:
        """Renders something to say to the agent as the line to write.

        Args:
          text: What to say.

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


class AgentBase(ABC):
    """A coding agent behind a uniform interface: structure only, and no history.

    An agent says which model to run at which effort, and is one agent apart from that: a flow
    that reviews its own work runs two of them at one configuration, and they are not the same
    agent. The conversation lives in the :class:`SessionBase` it launches, so a flow decides for
    itself whether turns share context -- a fresh session per turn is a Ralph loop, one session
    across turns is a stateful one.
    """

    def __init__(self, config: AgentConfig, *, name: str | None = None):
        """Initializes an agent that has launched nothing yet.

        Args:
          config: The model and effort every session of this agent runs at.
          name: What to call this agent, defaulting to one nothing else answers to. Two agents
            sharing a name are one agent to a trace, which is how the roles of a flow survive
            being restarted; two left unnamed are two, which is how one configuration driven
            twice -- an actor and the reviewer reading its work -- stays two.
        """
        self._config = config
        self._id = name or f"{type(self).__name__}#{uuid.uuid4().hex[:8]}"
        self._sessions: list[weakref.ref[SessionBase]] = []
        self._opened: list[str] = []
        self._watchers: list[Callable[[AgentBase, Event], None]] = []
        self._stopped = False
        #: Asked as each turn starts for anything said to this agent while no turn was open,
        #: which goes into that turn. Left unset by a flow driven from the command line,
        #: where there is nobody to say anything mid-run.
        self.waiting: Callable[[], list[str]] | None = None
        #: The run this agent is part of, set by whatever is driving the flow and told of
        #: every session this agent opens. Left unset by an agent driven by hand, which is
        #: not a run of anything.
        self.cycle: Cycle | None = None
        # The machine an isolated agent started, once its first turn has started one.
        self._anchor: AnchorConfig | None = None
        self._starting = threading.Lock()

    @property
    def id(self) -> str:
        """What this agent is called, and what a trace groups its sessions under."""
        return self._id

    @property
    def stopped(self) -> bool:
        """Whether this agent has been told to take no further turn.

        Which is not the same as the turn it was taking having failed, though that is how it
        looks from inside one: a process killed under a turn is a turn that could not finish.
        """
        return self._stopped

    @property
    def backend(self) -> str:
        """The coding agent this drives, named as a command line names it.

        Read off the class rather than written down twice: `ClaudeCodeAgent` drives `claude`,
        and an agent whose class says otherwise would be the one thing nobody could check.
        """
        return (
            type(self)
            .__name__.removesuffix("Agent")
            .removesuffix("CLI")
            .removesuffix("Code")
            .lower()
        )

    @property
    def opened(self) -> list[str]:
        """The backend's id for every session this agent has opened, oldest first.

        What :attr:`sessions` cannot say: a flow that drops a session per turn keeps none of
        them, but the backend logged them all, and a trace of the run has to know whose they
        were. Ids rather than sessions, so remembering a day of turns costs a list of strings.
        """
        return list(self._opened)

    @property
    def config(self) -> AgentConfig:
        """The model and effort every session of this agent runs at."""
        return self._config

    @property
    def anchor(self) -> AnchorConfig | None:
        """Where this agent's turns land, or None while they land here.

        An isolated agent starts its machine the first time this is asked for, which is the
        first turn it is given: constructing an agent pulls no image and starts no container,
        and a flow that configures more agents than it drives pays for the ones it drives. The
        machine then stands for as long as the agent does -- its sessions are turns of one
        conversation each, and they must find the workspace as the last turn left it -- and is
        taken down when the agent is collected, or at exit for one held to the end.
        """
        if self._config.isolation is None:
            return self._config.anchor
        # Two sessions of one agent share the machine rather than starting one each.
        with self._starting:
            if self._anchor is None:
                isolation = self._config.isolation.create()
                self._anchor = isolation.start()
                # Held by the finalizer alone, which is what takes the machine down: when the
                # agent is collected, and at exit for one held to the end.
                weakref.finalize(self, isolation.stop)
            return self._anchor

    @property
    def sessions(self) -> list[SessionBase]:
        """The sessions launched on this agent and still held by someone, oldest first.

        Held weakly, so a flow that launches a session per turn -- a Ralph loop runs for days --
        does not grow an agent by one session a turn for as long as it runs.
        """
        return [session for ref in self._sessions if (session := ref()) is not None]

    def stop(self) -> None:
        """Has this agent take no further turn, and ends the one it is taking.

        A turn is where a flow spends its time -- a model can think for minutes -- so a stop
        that waited for one would not read as a stop. What the turn was doing is left where
        it got to; what ends is the agent's part in it.
        """
        self._stopped = True
        for session in self.sessions:
            session.close()

    def watch(self, listener: Callable[[AgentBase, Event], None]) -> None:
        """Has everything this agent's turns say reach `listener` as they say it.

        Args:
          listener: What to tell, as this agent and the thing said.
        """
        self._watchers.append(listener)

    def _heard(self, event: Event) -> None:
        """Tells everyone watching what a turn of this agent just said.

        A watcher that raises is a watcher's own problem: a flow must not fail because
        something looking at it did.

        Args:
          event: What was said.
        """
        for listener in self._watchers:
            with contextlib.suppress(Exception):
                listener(self, event)

    @abstractmethod
    def launch(self) -> SessionBase:
        """Creates a new session, which stays unopened until its first turn.

        Returns:
          A session with no history yet.
        """
