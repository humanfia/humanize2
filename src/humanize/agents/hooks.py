"""The moments a turn stops at, and what whoever is driving it said to do about them.

A coding agent has hooks of its own -- Claude Code, Codex and Kimi Code all take a table of
shell commands to run before a tool, after a prompt, when a turn stops. Those are settings
files, written before anything starts and read by the backend rather than by us, and a flow
that wanted one would have to write a file, name a command, and hope the two ends agreed.

These are the same moments, held here instead: a hook is a Python callable, hung on a live
agent and taken down again while it runs, and what it answers is acted on by the session
driving that agent. So a flow says what to do at a moment in the language it is written in,
and says it to the agent it is holding rather than to a file somewhere under a home directory.

Separate from the base classes for the reason :mod:`humanize.agents.event` is: these are the
values, and every backend needs them without needing what drives one.
"""

from __future__ import annotations

import contextlib
import threading
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, Any, Self

from .event import Stopped

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping
    from types import TracebackType

__all__ = [
    "EVERYWHERE",
    "Hook",
    "Hooks",
    "Hung",
    "Moment",
    "Occasion",
    "Unhooked",
    "Verdict",
]


class Moment(StrEnum):
    """A point in a turn where whatever is driving the agent gets a word in.

    Named as the coding agents name their own, so that a flow written against one reads
    against the others and against their documentation: `PreToolUse` here is `PreToolUse`
    there. Not every backend reaches every one of them -- an agent says which it runs in
    :attr:`~humanize.agents.base.AgentBase.moments`, and a flow says which it needs where it
    declares the agents it drives.
    """

    #: A session is about to take its first turn.
    SESSION_START = "SessionStart"
    #: A prompt is about to go to the agent. Refusing it means the turn does not run, and
    #: what is added goes into the prompt.
    USER_PROMPT_SUBMIT = "UserPromptSubmit"
    #: The agent has reached for a tool.
    PRE_TOOL_USE = "PreToolUse"
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
EVERYWHERE = frozenset(Moment) - {Moment.PERMISSION_REQUEST}


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
      tool: What the agent reached for, for the moments about a tool.
      about: What it reached for it with, as one line -- the path, the command, the query.
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
    input: Mapping[str, Any] = field(default_factory=dict[str, Any])
    said: str = ""
    again: int = 0


@dataclass(frozen=True, slots=True)
class Verdict:
    """What a hook says back, which is nothing at all unless it says otherwise.

    Attributes:
      refused: Whether what was about to happen may not: the turn does not run, the tool does
        not run, the turn does not stop. A moment that is only ever told something ignores it,
        which is what :attr:`~humanize.agents.base.AgentBase.moments` is for -- a hook that
        can refuse is hung on an agent that can be refused.
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

        Called from the thread the turn is running on, which waits here: a hook is a word in
        the turn rather than a note about it, and one that takes a while is a turn that takes
        a while. A hook that raises has said nothing, in the way a watcher that raises has --
        a flow must not fail because something hung off it did.

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
