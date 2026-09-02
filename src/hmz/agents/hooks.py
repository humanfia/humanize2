"""The moments a turn stops at, and what whoever is driving it said to do about them.

A coding agent has hooks of its own -- Claude Code, Codex and Kimi Code all take a table of
shell commands to run before a tool, after a prompt, when a turn stops. Those are settings
files, written before anything starts and read by the backend rather than by us, and a flow
that wanted one would have to write a file, name a command, and hope the two ends agreed.

These are the same moments, held here instead: a hook is a Python callable, hung on a live
agent and taken down again while it runs, and what it answers is acted on by the session
driving that agent. So a flow says what to do at a moment in the language it is written in,
and says it to the agent it is holding rather than to a file somewhere under a home directory.

Most of those moments are read off the turn itself, which is what makes them work on every
backend. `PreToolUse` is the one that cannot be: a CLI announces the tool it has reached for
on the stream and then runs it, so a verdict read off that stream arrives after the thing it
was refusing. :class:`Gate` is the answer -- the CLI's *own* hook table, pointed for the
length of one run at a relay that carries the moment back here, so that a refusal is a word
the backend waits for rather than a note about what it already did.

Separate from the base classes for the reason :mod:`hmz.agents.event` is: these are the
values, and every backend needs them without needing what drives one.
"""

from __future__ import annotations

import contextlib
import json
import threading
import weakref
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, Any, ClassVar, Self, cast

from .event import Stopped

if TYPE_CHECKING:
    import socket
    import tempfile
    from collections.abc import Callable, Mapping
    from types import TracebackType

__all__ = [
    "EVERYWHERE",
    "SUBAGENTS",
    "Gate",
    "Hook",
    "Hooks",
    "Hung",
    "Moment",
    "Occasion",
    "Unhooked",
    "Verdict",
    "about",
    "answers",
]


class Moment(StrEnum):
    """A point in a turn where whatever is driving the agent gets a word in.

    Named as the coding agents name their own, so that a flow written against one reads
    against the others and against their documentation: `PreToolUse` here is `PreToolUse`
    there. Not every backend reaches every one of them -- an agent says which it runs in
    :attr:`~hmz.agents.base.AgentBase.moments`, and a flow says which it needs where it
    declares the agents it drives.
    """

    #: A session is about to take its first turn.
    SESSION_START = "SessionStart"
    #: A prompt is about to go to the agent. Refusing it means the turn does not run, and
    #: what is added goes into the prompt.
    USER_PROMPT_SUBMIT = "UserPromptSubmit"
    #: The agent has reached for a tool. Refusing it means the tool does not run, on a backend
    #: whose CLI takes a hook table meant for one run -- which is what :class:`Gate` serves it
    #: from. Elsewhere it is read off the stream a turn is read from, where the CLI has already
    #: said what it reached for, so a refusal there is a flow watching a tool rather than one
    #: stopping it. `hmz.backends` says which backends are which.
    PRE_TOOL_USE = "PreToolUse"
    #: The agent has started an agent of its own, which is what these CLIs call a subagent.
    #: Refusing it is not a thing a backend waits to be told, so it is a moment to be told
    #: about rather than one to answer.
    SUBAGENT_START = "SubagentStart"
    #: One of those has finished.
    SUBAGENT_STOP = "SubagentStop"
    #: The backend is asking whether a tool may run. Refusing it means the tool does not.
    PERMISSION_REQUEST = "PermissionRequest"
    #: The agent has stopped to ask its user something.
    NOTIFICATION = "Notification"
    #: A turn has ended. Refusing it sends the agent on, with what was said as its prompt.
    STOP = "Stop"
    #: A session has been closed.
    SESSION_END = "SessionEnd"


#: The moments a turn passes through wherever it is run, which is every backend driven here:
#: they are read off the turn itself rather than out of anything the backend offers. What is
#: not among them is a moment only some backends reach, and is named on the agents that do.
EVERYWHERE = frozenset(Moment) - {
    Moment.PERMISSION_REQUEST,
    Moment.SUBAGENT_START,
    Moment.SUBAGENT_STOP,
}

#: The two a backend reaches only where it says which of its tool calls start an agent of
#: their own. Named together because they are one thing to be told: a fleet under a turn is
#: visible or it is not, and a backend that says one and not the other would be one whose
#: subagents never finish.
SUBAGENTS = frozenset({Moment.SUBAGENT_START, Moment.SUBAGENT_STOP})


class Unhooked(ValueError):  # noqa: N818  -- what the moment is here, not what went wrong
    """Raised for a hook hung on a moment the agent it was hung on does not run.

    Where it is hung rather than where it would have fired: a hook that quietly never runs is
    a flow that quietly does not do what it says. A flow that declares which moments it needs
    hears about this before its first turn instead, from `Runner`.
    """


@dataclass(frozen=True, slots=True)
class Occasion:
    """What a hook is told when its moment arrives.

    One shape for every moment, because a hook is written against a moment and reads the
    fields that moment fills: a `PreToolUse` reads `tool`, a `Stop` reads `said`. The rest are
    empty rather than absent, so that a hook hung on two moments is not two hooks.

    Attributes:
      moment: Which moment this is.
      agent: What the agent is called, which is the name its flow gave it.
      session: The backend's id for the conversation, or "" before the backend has said one.
      prompt: What the agent is about to be told, for the moments that are about to tell it
        something.
      tool: What the agent reached for, for the moments about a tool. For the moments about
        an agent of its own it is what that agent is called, as its backend named it.
      about: What it reached for it with, as one line -- the path, the command, the query. For
        an agent of its own it is what that agent was asked to do.
      under: The backend's own id for the agent this is about, for the moments about one, so
        that the one that started and the one that finished read as one agent.
      input: What the tool was called with, where the backend says. Empty where it does not.
      said: What the agent said last, which is the answer a turn ended on.
      again: How many times a hook has already sent this turn on rather than let it stop, so
        that one which keeps refusing can decide to stop refusing.
    """

    moment: Moment
    agent: str
    session: str = ""
    prompt: str = ""
    tool: str = ""
    about: str = ""
    under: str = ""
    input: Mapping[str, Any] = field(default_factory=dict[str, Any])
    said: str = ""
    again: int = 0


@dataclass(frozen=True, slots=True)
class Verdict:
    """What a hook says back, which is nothing at all unless it says otherwise.

    Attributes:
      refused: Whether what was about to happen may not: the turn does not run, the tool does
        not run, the turn does not stop. A moment that is only ever told something ignores it,
        which is what :attr:`~hmz.agents.base.AgentBase.moments` is for -- a hook that
        can refuse is hung on an agent that can be refused. At `PreToolUse` that also depends
        on the backend: see :class:`Gate`.
      because: What to say about the refusal, which is what the agent is told. At `Stop` it is
        what the agent is sent on to do, so a refusal with nothing to say is not one.
      adds: What to add to what the agent was about to be told.
    """

    refused: bool = False
    because: str = ""
    adds: str = ""


#: What a flow hangs on a moment: told what is happening, and answering with what to do about
#: it, or with nothing. One that raises is one that has said nothing -- a flow must not fail
#: because something watching it did.
type Hook = Callable[[Occasion], Verdict | None]


class Hung:
    """One hook, hung on one moment, until it is taken down.

    Answered by :meth:`Hooks.on` so that whatever hung it can take it down again, and a
    context manager so that a flow which wants one for a while says so in one line::

        with agent.hooks.on(Moment.PRE_TOOL_USE, refuse_rm):
            agent(task)
    """

    def __init__(self, hooks: Hooks, moment: Moment, hook: Hook, tool: str) -> None:
        """Initializes a hook that is hanging.

        Args:
          hooks: Where it is hung.
          moment: What it is hung on.
          hook: What to call.
          tool: The tool it is only about, or "" for every tool.
        """
        self.moment = moment
        self.hook = hook
        self.tool = tool
        self._hooks = hooks

    def off(self) -> None:
        """Takes this hook down, whether or not it is still up."""
        self._hooks.off(self)

    def __enter__(self) -> Self:
        """Answers with itself, being already hung."""
        return self

    def __exit__(
        self,
        kind: type[BaseException] | None,
        error: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Takes the hook down, however the block ended."""
        self.off()


class Hooks:
    """What is hung on one agent's moments, and what happens when one of them arrives.

    Held by the agent rather than by a session, so that a hook hung on an agent is on every
    conversation it holds -- and so that hanging one is something done to a flow that is
    already running, which is the whole point of these being callables rather than a file.
    """

    def __init__(self, moments: frozenset[Moment], agent: str) -> None:
        """Initializes an agent's hooks, with nothing hung on any of them.

        Args:
          moments: The moments the agent runs, which are the ones a hook may be hung on.
          agent: What the agent is called, which is what an occasion says it happened to.
        """
        self._moments = moments
        #: What the agent is called, which is what an occasion says it happened to. Public
        #: because a flow may name an agent after it was made, and a name that went stale
        #: here would be the name a refused hook complained about.
        self.agent = agent
        self._hung: dict[Moment, list[Hung]] = {}
        #: Where the CLI's own table reaches these moments, for the backends that take one,
        #: and None until something asks for it. Held here rather than on the agent so that
        #: it outlives a CLI process restarted mid-session, exactly as what is hung does.
        self._gate: Gate | None = None
        # Hung and taken down from wherever the flow happens to be, and fired from the thread
        # a turn is running on, which is not that one.
        self._lock = threading.Lock()

    @property
    def moments(self) -> frozenset[Moment]:
        """The moments a hook may be hung on here, which is what this backend runs."""
        return self._moments

    def on(self, moment: Moment, hook: Hook, *, tool: str = "") -> Hung:
        """Hangs a hook on a moment, from now until it is taken down.

        Args:
          moment: When to call it.
          hook: What to call, which is told an :class:`Occasion` and answers with a
            :class:`Verdict` or with None.
          tool: The one tool to call it about, for the moments that are about a tool, or ""
            to be called about every one of them.

        Returns:
          What takes it down again, which is also a context manager for a hook that is only
          wanted for a while.

        Raises:
          Unhooked: If this agent does not run that moment.
        """
        if moment not in self._moments:
            raise Unhooked(f"{self.agent} does not run {moment}")
        hanging = Hung(self, moment, hook, tool)
        with self._lock:
            self._hung.setdefault(moment, []).append(hanging)
        return hanging

    def off(self, hung: Hung) -> None:
        """Takes a hook down, whether or not it is still up.

        Args:
          hung: What :meth:`on` answered with.
        """
        with self._lock, contextlib.suppress(KeyError, ValueError):
            self._hung[hung.moment].remove(hung)

    def hooked(self, moment: Moment) -> bool:
        """Whether anything is hung on a moment.

        Args:
          moment: The moment.

        Returns:
          True if a hook would be called, which is what lets a session pay for a moment only
          where somebody is listening for it.
        """
        with self._lock:
            return bool(self._hung.get(moment))

    def fire(self, occasion: Occasion) -> Verdict:
        """Tells everything hung on a moment that it has arrived, and gathers what they said.

        Called from the thread the turn is running on, or -- for the one moment a backend asks
        about itself -- from the thread serving that question, which is the CLI's own turn
        waiting on the other end of a socket. Either way whatever called this waits here: a
        hook is a word in the turn rather than a note about it, and one that takes a while is
        a turn that takes a while. The ones that arrive through a gate are one at a time, so
        a CLI reaching for three tools at once still puts them one after another; what a turn
        fires off its own stream is not held behind those, being the same thread the turn is
        on. A hook that raises has said nothing, in the way a watcher that raises has -- a
        flow must not fail because something hung off it did.

        Args:
          occasion: What is happening.

        Returns:
          One verdict for all of them: refused if any of them refused, said with the first
          reason there was, and adding everything any of them added, in the order they were
          hung. Nothing at all where nothing is hung.

        Raises:
          Stopped: If a hook drove an agent that has been stopped. The one thing a hook may
            raise out of the turn it was called in: a run ended by hand has to read as ended
            by hand, and swallowing this would let the turn stop and the flow finish.
        """
        with self._lock:
            hanging = list(self._hung.get(occasion.moment, ()))
        refused = False
        because = ""
        adds: list[str] = []
        for hung in hanging:
            if hung.tool and hung.tool != occasion.tool:
                continue
            said: Verdict | None = None
            try:
                said = hung.hook(occasion)
            except Stopped:
                raise
            except Exception:  # noqa: BLE001, S110 -- a hook that failed has said nothing
                pass
            if said is None:
                continue
            if said.refused and not refused:
                refused, because = True, said.because
            if said.adds:
                adds.append(said.adds)
        return Verdict(refused=refused, because=because, adds="\n\n".join(adds))

    def gate(self) -> Gate:
        """The gate these moments are served through, made the first time it is asked for.

        Made here rather than beside the agent so that it lives exactly as long as what it
        serves: a CLI restarted mid-session, or an app server holding every conversation of
        an agent at once, reaches the same socket it always did.

        Returns:
          The gate, which has bound nothing until something asks where it is.
        """
        with self._lock:
            if self._gate is None:
                self._gate = Gate(self)
                # Taken down when these hooks are, which is when the agent holding them is
                # collected or this process exits. Held by the finalizer alone, exactly as
                # the toolbox is: nothing else ever has cause to close one, and a gate left
                # serving would be a socket, a thread and a directory per agent that ever ran.
                # It works because the gate holds *these* weakly -- a gate that held them back
                # would be a cycle, and a cycle is collected when the collector gets round to
                # it rather than when the agent goes.
                weakref.finalize(self, self._gate.close)
            return self._gate

    def gated(self, moment: Moment) -> bool:
        """Whether a moment is one the backend itself asks about and waits for the answer.

        Args:
          moment: The moment.

        Returns:
          True where a gate is serving it, which is what tells a session not to say the moment
          a second time off the stream it is reading: the CLI has already asked, and a turn
          that fired the moment twice would be one whose hooks ran twice for one tool. False
          for a gate that could not be served at all, whose turns go on reading the moment off
          the stream rather than reading it nowhere.
        """
        with self._lock:
            return (
                self._gate is not None
                and moment in self._gate.moments
                and self._gate.serving
            )


#: How long a CLI is told to wait on one of these before giving up on it, in seconds. As
#: generous as the window a turn may say nothing for, and for the same reason: a hook is a
#: word in the turn, a flow may put that word to a person, and somebody taking a quarter of
#: an hour over it is not a hook that has wedged. The relay answers at once where the flow
#: has gone, so a long wait costs nothing when there is nobody to wait for.
WAITING = 900

#: What a hook table is told it is about, for the tables that take a matcher: every tool.
_MATCHES = "*"

#: How long a socket that nothing has connected to is waited on before the thread serving it
#: looks again at whether it has been closed, as :mod:`hmz.agents.tools` does it.
_LOOKING = 0.2

#: What a gate answers where it has nothing to say, which is a tool the CLI goes on to run.
_NOTHING = "{}"


def about(called: Mapping[str, Any]) -> str:
    """What a tool was called with, as the one line a row of a transcript has room for.

    Args:
      called: The tool's input, as its CLI sent it.

    Returns:
      The first thing in it that is words -- the path, the command, the query -- or "".
    """
    return next(
        (
            str(value)
            for value in called.values()
            if isinstance(value, str) and value.strip()
        ),
        "",
    )


def answers(line: str, hooks: Hooks) -> str:
    """What one call of a CLI's own hook table is answered with.

    Written as a function of the line so that what the two ends agreed is one thing to read
    and one thing to test, whatever is carrying it -- which is how
    :func:`hmz.agents.tools.serve` is written, for the same reason.

    Args:
      line: What the CLI wrote to its hook, which is one JSON object.
      hooks: What is hung on the agent whose turn this is.

    Returns:
      The line to answer with. An empty object is a gate with nothing to say, which every one
      of these CLIs reads as the tool going ahead exactly as it would have -- a refusal and
      whatever a hook added are what make it anything else.
    """
    try:
        held: object = json.loads(line)
    except ValueError:
        return _NOTHING
    if not isinstance(held, dict):
        return _NOTHING
    said = cast("dict[str, Any]", held)
    named = str(said.get("hook_event_name") or "")
    moment = next((one for one in Gate.moments if one.value == named), None)
    if moment is None:
        # A table pointed here for something this serves no answer to. Answered with nothing
        # rather than refused: a CLI that grows an event is a CLI whose turns must go on
        # running, and a moment nothing here knows is not a moment anybody refused.
        return _NOTHING
    given = said.get("tool_input")
    # Checked rather than trusted: one of these CLIs writes the input as whatever the
    # tool takes, and a string where an object was expected would be a thread that died
    # reading it and a gate that then answered nothing at all.
    called = cast("dict[str, Any]", given) if isinstance(given, dict) else {}
    occasion = Occasion(
        moment=moment,
        agent=hooks.agent,
        session=str(said.get("session_id") or ""),
        tool=str(said.get("tool_name") or ""),
        about=about(called),
        input=called,
    )
    try:
        verdict = hooks.fire(occasion)
    except Stopped as stopped:
        # The one thing a hook raises out of a turn -- and this is not that turn's thread, so
        # there is nowhere here to raise it to. What the stop does to the run it does anyway;
        # what this end owes is that the tool it was reaching for does not run in the meantime.
        verdict = Verdict(refused=True, because=str(stopped))
    said_back: dict[str, Any] = {"hookEventName": named}
    if verdict.refused:
        said_back |= {
            "permissionDecision": "deny",
            "permissionDecisionReason": verdict.because
            or f"{occasion.tool} was refused",
        }
    if verdict.adds:
        # What a hook adds is what the agent is told, at this moment as at every other: the
        # gate is the only place `PreToolUse` is served on these backends, so a verdict that
        # only adds would otherwise be a hook that said nothing at all. `additionalContext`
        # is the key Claude Code gave it and the rest of these CLIs copied.
        said_back["additionalContext"] = verdict.adds
    if len(said_back) == 1:
        return _NOTHING
    return json.dumps({"hookSpecificOutput": said_back}, separators=(",", ":"))


def _accepts(
    whose: weakref.ReferenceType[Hooks],
    sock: socket.socket,
    closed: threading.Event,
    one_at_a_time: threading.Lock,
) -> None:
    """Takes each call to a gate and serves it on a thread of its own.

    A function of the pieces rather than a method of the gate, and holding what it answers for
    weakly: a thread that held its agent's hooks would be a thread that kept the agent up, and
    an agent nobody holds any more is one whose socket and whose thread go with it.

    Args:
      whose: The hooks this gate serves, weakly. Gone is a gate whose agent has gone, and the
        thread ends with it.
      sock: What is listening. Held strongly, being what the thread is waiting on -- it is
        closed by the gate, and the wait ends when it is.
      closed: Whether the gate has been taken down by hand.
      one_at_a_time: What keeps two of these from firing a moment at once.
    """
    while not closed.is_set() and whose() is not None:
        try:
            held, _from = sock.accept()
        except TimeoutError:
            continue
        except OSError:
            return  # closed under us, which is what closing does
        threading.Thread(
            target=_serves,
            args=(held, whose, one_at_a_time),
            name="humanize-hook",
            daemon=True,
        ).start()


def _serves(
    held: socket.socket,
    whose: weakref.ReferenceType[Hooks],
    one_at_a_time: threading.Lock,
) -> None:
    """Answers one relay for as long as it is connected.

    Args:
      held: The connection.
      whose: The hooks to ask, weakly, for the reason :func:`_accepts` holds them weakly.
      one_at_a_time: Taken for the whole of each answer. A CLI reaches for several tools at
        once and each is a relay of its own, so without this a hook would be running in as
        many threads as the model asked for tools -- where the same hook on the same agent has
        always been one at a time, being a word in the turn. Per gate, so one agent's moments
        wait on each other and nobody else's do.
    """
    # A relay that has gone is not a failure: its CLI may have been stopped by hand, or given
    # up on a hook that took longer than it waits, either of which leaves this end writing an
    # answer to a socket with nobody on it. Said nowhere rather than as a traceback out of a
    # thread nothing is watching, which is what would land in the middle of a flow's output.
    with contextlib.suppress(OSError, ValueError), held, held.makefile("rwb") as stream:
        for line in stream:
            hooks = whose()
            if hooks is None:
                return
            with one_at_a_time:
                said = answers(line.decode("utf-8", "replace"), hooks)
            stream.write((said + "\n").encode())
            stream.flush()


class Gate:
    """One agent's moments, served where the CLI's own hook table can reach them.

    A CLI takes a hook as a program to run, so there is a program -- `hmz hook --at <socket>`,
    which does nothing but carry the one call back to this process. The socket is in a
    directory this user alone may enter, made in this process and taken away with it, and what
    answers is the flow's own :class:`Hooks`: the same callables a turn fires from its own
    thread, fired here from the CLI's instead. Which is the whole of the difference this
    makes -- the CLI is *waiting* for the answer, so a refusal stops the tool rather than
    describing one that has already run.

    Scoped to the run and to nothing else. Every table this is written into is one the CLI was
    told about on its own command line or through a file of ours, for the length of one run:
    nothing of the user's own settings is read, written or replaced, so a person's own hooks go
    on being theirs and a flow that ends leaves nothing behind.

    Started once and held for as long as the agent is, rather than per turn and rather than
    only while something is hung: a hook is hung on a live agent and taken down again while it
    runs, so a table installed only for the hooks that happened to be up when the CLI started
    would be a flow whose later hooks quietly did nothing. What is hung is asked at the moment
    it fires, which is the only moment the answer is true.
    """

    #: The moments a CLI's own table is pointed here for. One, because one is what this is
    #: for: every other moment of a turn is read off the turn itself on every backend, and a
    #: table that fired them again would fire them twice. `PreToolUse` is the exception,
    #: because a stream says a tool was reached for and then the tool runs, so the only place
    #: to refuse one is where the CLI is waiting to be told.
    moments: ClassVar[frozenset[Moment]] = frozenset({Moment.PRE_TOOL_USE})

    def __init__(self, hooks: Hooks) -> None:
        """Initializes a gate that is serving nothing yet.

        Args:
          hooks: What is hung on the agent whose turns this gates.
        """
        # Weakly, so that this is not what keeps them up: the hooks hold the gate, the agent
        # holds the hooks, and an agent nobody holds any more is collected by its count rather
        # than waiting on the collector to find a cycle. Which is what makes the finalizer
        # `Hooks.gate` hangs on them fire when the agent goes rather than whenever.
        self._hooks = weakref.ref(hooks)
        self._lock = threading.Lock()
        self._at = ""
        self._sock: socket.socket | None = None
        self._closed = threading.Event()
        self._where: tempfile.TemporaryDirectory[str] | None = None
        #: Whether making a socket was tried and could not be done, which is the one thing
        #: that turns this gate off: a machine with none to spare is a turn whose moment is
        #: read off the stream again rather than one pointed at a socket nobody is on.
        self._refused = False
        #: Taken for the whole of one answer, so that a CLI reaching for several tools at once
        #: still puts them to a hook one at a time.
        self._one_at_a_time = threading.Lock()

    def address(self) -> str:
        """Where this gate is reached, starting it if nothing has yet.

        Returns:
          The path of the socket it serves on, which is under a directory of its own so that
          nothing else on the machine can name it.
        """
        import socket
        import tempfile
        from pathlib import Path

        with self._lock:
            if self._sock is not None:
                return self._at
            # A gate served again after it was closed is an agent still being driven: the
            # thread that looks would otherwise see the old answer and stop before it began.
            self._closed.clear()
            try:
                self._where = tempfile.TemporaryDirectory(
                    prefix="humanize-hook-", ignore_cleanup_errors=True
                )
                # Inside a directory this user alone may enter: a socket is a way into this
                # process, and one anybody could connect to is a way in for anybody.
                where = Path(self._where.name)
                where.chmod(0o700)
                self._at = str(where / "hook.sock")
                self._sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                self._sock.bind(self._at)
                self._sock.listen(8)
                self._sock.settimeout(_LOOKING)
                self._refused = False
            except OSError:
                # A machine with no socket to spare, or a temporary directory whose name is
                # longer than a Unix socket path may be. The same answer the preload layer
                # gives: a turn whose `PreToolUse` is read off the stream rather than gated
                # is weaker than one that is gated, and far better than a turn that will not
                # run at all. `gated` then says False, so the moment is read off the stream.
                self._closed.set()
                self._shut()
                self._refused = True
                return ""
            # Given what it needs rather than the gate itself, and given the hooks weakly: a
            # thread holding its agent's hooks would be what kept the agent up, and an agent
            # nobody holds any more is one whose socket, its thread and its directory go the
            # same way without anything having to be told to close them.
            threading.Thread(
                target=_accepts,
                args=(self._hooks, self._sock, self._closed, self._one_at_a_time),
                name="humanize-hooks",
                daemon=True,
            ).start()
            return self._at

    def command(self) -> list[str]:
        """What a CLI's own hook table is told to run to reach these moments.

        Returns:
          The relay, as argv: it carries the one call its CLI writes on a program's stdin to
          the socket this is served on, so that the hook runs in this process.
        """
        import sys

        return [sys.executable, "-m", "hmz", "hook", "--at", self.address()]

    def table(self, wait: int) -> dict[str, Any]:
        """These moments as the hook table a CLI's own settings hold.

        Args:
          wait: How long that CLI is to wait on one of these, in whichever unit that CLI
            reads the number in -- Claude Code counts seconds and Qwen Code milliseconds,
            under the one spelling, so the caller says it in the unit its own CLI means.
            :data:`WAITING` is the length; this is what it is written as.

        Returns:
          The mapping of event to what runs for it, in the shape Claude Code wrote and the
          rest of these CLIs copied: one matcher standing for every tool, and one command --
          and nothing at all where the gate could not be served, a table naming a socket that
          is not there being a hook that fails to start before every tool call.
        """
        import shlex

        if not self.address():
            return {}
        return {
            moment.value: [
                {
                    "matcher": _MATCHES,
                    "hooks": [
                        {
                            "type": "command",
                            "command": shlex.join(self.command()),
                            "timeout": wait,
                        }
                    ],
                }
            ]
            for moment in sorted(self.moments)
        }

    @property
    def serving(self) -> bool:
        """Whether a CLI's own table may be pointed here at all.

        True for a gate with a socket up and for one nothing has asked the address of yet,
        which is a gate that will have one the moment a CLI is started. False only where
        making one was tried and could not be done -- the one case a session has to go on
        reading the moment off its own stream for, rather than reading it nowhere.
        """
        return not self._refused

    def close(self) -> None:
        """Stops serving, and takes the socket away. Doing it twice does it once."""
        self._closed.set()
        with self._lock:
            self._shut()

    def _shut(self) -> None:
        """Drops the socket and the directory holding it, with this gate's lock held."""
        sock, self._sock = self._sock, None
        where, self._where = self._where, None
        self._at = ""
        if sock is not None:
            sock.close()
        if where is not None:
            where.cleanup()
