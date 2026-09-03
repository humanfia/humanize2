"""What a flow drives: an agent, the conversations it opens, and the person at the prompt.

Interfaces and nothing else. A flow is written against what it may ask of an agent -- a turn,
a session, a goal, what the turn cost -- and not against the class that answers: which CLI is
behind it, how a turn is spelled to that CLI, where its logs go and how it is stopped are all
:mod:`hmz.agents`'s business and none of the flow's. So the contract is written here, where a
flow can import it beside the mark that makes it a flow, and the drivers implement it.

Structurally rather than by inheritance, which is what keeps the arrow pointing one way: a
flow names what it drives, and a driver is written without ever naming a flow. What holds the
two together is checked where a type checker can see it, at the foot of this file, so that a
driver which stops answering to this reads as a driver to correct rather than as a flow that
fails on its first turn.

A flow never makes one of these. The agents are chosen where the flow is started -- a command
line, the flow picker, another flow handing over its own -- and arrive as the tuple the flow
declared::

    @flow
    def run(agents: tuple[Agent, Agent], task: str) -> None:
        builder, reviewer = agents
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar, Protocol, overload

if TYPE_CHECKING:
    import os
    from collections.abc import Callable, Iterable, Iterator, Sequence

    from pydantic import BaseModel

    from hmz.agents import (
        AgentConfig,
        Board,
        Event,
        Hooks,
        Moment,
        Question,
        Tool,
        Usage,
    )
    from hmz.agents.base import Journal
    from hmz.agents.skills import Loaded
    from hmz.machines import MachineConfig

__all__ = ["Agent", "Driven", "Person", "Session"]


class Session(Protocol):
    """One conversation with one agent, kept alive across turns.

    The first turn opens it and every later one resumes it, so the agent still has the earlier
    turns in context. Letting go of it is how a flow forgets: the next one starts from nothing,
    which is what a Ralph loop is made of.
    """

    #: Whether this backend can be held to a shape rather than asked to keep to one. A flow
    #: that reads an answer as an object gets one either way; this is how sure it can be. A
    #: fact of the backend, so it is written on the class -- a stand-in for one says it the
    #: same way, `shapes: ClassVar[bool] = True`.
    shapes: ClassVar[bool]

    #: Whether this backend can be given a tool the flow wrote. A fact of the backend, said
    #: the same way, so a flow that offers a callback can be written to ask first rather than
    #: to catch the refusal.
    takes_tools: ClassVar[bool]

    #: Whether this backend has a native history operation that branches a conversation in
    #: place, which is what :meth:`fork` reaches for. Only Claude and Codex do; a flow that
    #: forks declares the place with `Annotated[Agent, Forks]`, and the run is refused a
    #: backend without it before the first turn.
    forks: ClassVar[bool]

    @property
    def id(self) -> str:
        """What the backend calls this conversation, once a turn has landed in it.

        Raises:
          RuntimeError: If no turn has landed yet, so the backend has not named it.
        """
        ...

    @property
    def named(self) -> str | None:
        """The same name, or None while the backend has not said one."""
        ...

    @property
    def last_turn_id(self) -> str | None:
        """The backend's id for the latest completed turn, where it exposes one.

        What a fork names its boundary by; None for a backend with no intermediate boundary
        and before any turn has completed. A forked child starts empty here.
        """
        ...

    def fork(
        self, *, last_turn_id: str | None = None, permission: str | None = None
    ) -> Session:
        """Branches this conversation into an independent one, preserving its prefix.

        Eager and prompt-free: the returned child already has its backend id, and the parent
        is left open, idle and unchanged, so it may be driven on at once while the child runs
        on its own. Only an open, idle, unmoved session may be forked.

        Args:
          last_turn_id: The completed turn to fork through, inclusive. None forks through the
            latest completed turn; Codex also accepts an earlier one, and Claude raises
            NotImplementedError for a non-None boundary.
          permission: The rung the child runs at, or None to inherit the parent's.

        Returns:
          The child session, already named by the backend.
        """
        ...

    @property
    def cwd(self) -> str:
        """The directory this conversation works in, as whoever is watching would name it."""
        ...

    @property
    def effort(self) -> str:
        """How hard the next turn of this conversation is to think."""
        ...

    @effort.setter
    def effort(self, effort: str) -> None: ...

    @property
    def skills(self) -> tuple[str, ...]:
        """The flow's skills this conversation carries, by name, in the flow's own order."""
        ...

    @property
    def tools(self) -> tuple[Tool, ...]:
        """The flow's own callbacks this conversation is putting in front of the agent."""
        ...

    def offers(self, tools: Iterable[Tool] | None) -> None:
        """Says which callbacks of the flow's the agent may reach for, from the next turn on.

        A callback is a function of the flow's own, and the agent reaching for it is that
        function running in the flow's process -- so a tool whose callback runs another flow
        is an agent that can call a flow::

            session.offers([Tool(name="review", about="have the reviewer read a file",
                                 takes=Reviewing, call=lambda said: reviewer(said.path))])

        Args:
          tools: The callbacks, or None to take back whatever this conversation was offering.

        Raises:
          NotImplementedError: On a backend with no way of being given a tool it was not
            shipped with, which `takes_tools` says of the class beforehand.
        """
        ...

    def loads(self, skills: Iterable[str] | None) -> None:
        """Says which of the flow's skills this conversation carries from its next turn on.

        The one thing about what an agent works by that changes while it is working, and it
        is the conversation's rather than the agent's: an agent is what it was made as, and a
        conversation is a thing that gets somewhere. A loop that has finished reading and
        started writing says so here.

        Args:
          skills: The names to carry, or None for every one the flow brought. A name the flow
            does not bring is ignored rather than refused, so a session asking for one a fork
            of the flow no longer has carries the rest.
        """
        ...

    @overload
    def __call__(self, prompt: str, *, suppress: bool = False) -> str: ...

    @overload
    def __call__[T: BaseModel](
        self, prompt: str, *, suppress: bool = False, schema: type[T]
    ) -> T | None: ...

    def __call__[T: BaseModel](
        self, prompt: str, *, suppress: bool = False, schema: type[T] | None = None
    ) -> str | T | None:
        """Sends one turn, opening the session on the first call and resuming it after."""
        ...

    @overload
    async def aturn(self, prompt: str, *, suppress: bool = False) -> str: ...

    @overload
    async def aturn[T: BaseModel](
        self, prompt: str, *, suppress: bool = False, schema: type[T]
    ) -> T | None: ...

    async def aturn[T: BaseModel](
        self, prompt: str, *, suppress: bool = False, schema: type[T] | None = None
    ) -> str | T | None:
        """The same turn, awaited: `await session.aturn(prompt)`."""
        ...

    def pursue(self, objective: str, *, suppress: bool = False) -> str:
        """Runs the backend's own goal feature in this conversation, until it stops."""
        ...

    async def apursue(self, objective: str, *, suppress: bool = False) -> str:
        """The same goal, awaited."""
        ...

    def stream(
        self, prompt: str, *, schema: type[BaseModel] | None = None
    ) -> Iterator[Event]:
        """Sends one turn, saying what the agent says as it says it."""
        ...

    def spent(self) -> Usage:
        """What this conversation has cost so far, by the kind of token it went on."""
        ...

    def rate(self, over: float = ...) -> Usage:
        """How fast it is spending, by kind, over the last stretch of it."""
        ...

    def juice(self, over: float = ...) -> float:
        """What an average turn of the model came out with, over that stretch."""
        ...

    def interject(self, text: str) -> None:
        """Says something into the turn now running, for a backend that can be told."""
        ...

    def steering(self, text: str, ticket: str = "") -> str:
        """Notes something said to this conversation that the agent has not yet said it has."""
        ...

    def took(self, ticket: str) -> str | None:
        """What was said under that ticket, once the agent has said it has it."""
        ...

    def unsteered(self, text: str) -> None:
        """Takes back something said that the agent will now never hear."""
        ...

    def close(self) -> None:
        """Ends this conversation, and takes away whatever it put in the workspace."""
        ...


class Agent(Protocol):
    """A coding agent behind a uniform interface: structure only, and no history.

    An agent says which model to run at which effort, and is one agent apart from that: a flow
    that reviews its own work runs two of them at one configuration, and they are not the same
    agent. The conversation lives in the :class:`Session` it opens, so a flow decides for
    itself whether turns share context -- a fresh session per turn is a Ralph loop, one session
    across turns is a stateful one.
    """

    #: The moments of a turn a hook may be hung on here. A flow that needs one only some
    #: backends reach says so where it declares the place, and is then given an agent that
    #: runs it rather than finding out from a hook that raised hours in.
    moments: ClassVar[frozenset[Moment]]

    #: Whether this backend has a goal feature of its own, which is what :meth:`pursue`
    #: reaches for. A flow that runs an agent under one says so where it declares the place.
    #:
    #: Both are facts of the backend rather than of any one agent, so both are written on the
    #: class -- and a stand-in written for a test says them the same way, annotation and all:
    #: `pursues: ClassVar[bool] = True`.
    pursues: ClassVar[bool]

    #: Where the run this agent is being driven in is written down, or None for an agent
    #: nobody is keeping a record of -- one driven from a test, or by a flow that was called
    #: from nothing. Set by whatever started the run rather than by the flow.
    cycle: Journal | None

    @property
    def id(self) -> str:
        """What this agent is called, which is what a trace groups its sessions under."""
        ...

    @property
    def backend(self) -> str:
        """Which CLI is behind it, by the name a command line calls that CLI."""
        ...

    @property
    def config(self) -> AgentConfig:
        """The model, effort, account and permission every session of this agent runs at."""
        ...

    @property
    def hooks(self) -> Hooks:
        """What is hung on the moments of this agent's turns."""
        ...

    @property
    def sessions(self) -> Sequence[Session]:
        """The conversations opened on it and still held by someone, oldest first."""
        ...

    @property
    def opened(self) -> list[str]:
        """The backend's id for each conversation it has opened, in the order it opened them."""
        ...

    @property
    def stopped(self) -> bool:
        """Whether it has been told to take no further turn."""
        ...

    @property
    def goals_enabled(self) -> bool:
        """Whether its backend's own goal feature is switched on for it."""
        ...

    @property
    def loaded(self) -> tuple[Loaded, ...]:
        """The skills the flow it is being driven by mounts onto every session it opens."""
        ...

    @property
    def effort(self) -> str:
        """How hard its next turn is to think, in that backend's own word for it."""
        ...

    @effort.setter
    def effort(self, effort: str) -> None: ...

    def new(self, cwd: str | os.PathLike[str] | None = None) -> Session:
        """Opens a conversation, which stays unopened with the backend until its first turn."""
        ...

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
        """Runs one turn in a session of its own, and keeps nothing."""
        ...

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
        """The same turn, awaited: `await agent.aturn(prompt)`."""
        ...

    def pursue(
        self,
        objective: str,
        *,
        suppress: bool = False,
        cwd: str | os.PathLike[str] | None = None,
    ) -> str:
        """Runs a goal in a session of its own, and keeps nothing."""
        ...

    async def apursue(
        self,
        objective: str,
        *,
        suppress: bool = False,
        cwd: str | os.PathLike[str] | None = None,
    ) -> str:
        """The same goal, awaited."""
        ...

    def batch_new(
        self, count: int, cwd: str | os.PathLike[str] | None = None
    ) -> Sequence[Session]:
        """Opens as many conversations as it is asked for, at once."""
        ...

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
        """Runs many turns at once, each in a session of its own, and keeps none of them."""
        ...

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
        """The same batch, awaited."""
        ...

    def spent(self) -> Usage:
        """What every conversation of this agent has cost, by the kind of token."""
        ...

    def rate(self, over: float = ...) -> Usage:
        """How fast it is spending, by kind, over the last stretch of the run."""
        ...

    def juice(self, over: float = ...) -> float:
        """What an average turn of the model came out with, over that stretch."""
        ...

    def stop(self) -> None:
        """Has it take no further turn, and ends the one it is taking."""
        ...

    def watch(self, listener: Callable[[Agent, Session | None, Event], None]) -> None:
        """Has everything its turns say reach `listener` as they say it."""
        ...

    def clone(
        self,
        *,
        config: AgentConfig | None = None,
        name: str | None = None,
        skills: Iterable[Loaded] | None = None,
    ) -> Agent:
        """Another agent of this one's backend, differing in what this names and nothing else.

        The one way a flow has of getting an agent that is not quite the one it was handed,
        and it is a second agent rather than this one changed::

            careful = agent.clone(config=replace(agent.config, effort="max"))

        Everything an agent *is* is settled where it is made, so this is where it is settled
        for the new one and there is nowhere it can be said again. What a run puts on an agent
        rather than sets it up with does not come across: the clone has opened no conversation,
        spent nothing, is watched by nobody and is being written down nowhere -- and it is not
        one of the agents the run was started with, so what it does is its own.

        Args:
          config: What every session of it runs at, or None for this agent's own.
          name: What to call it, or None for one nothing else answers to: two agents are two
            agents, and a trace that read a clone as its original would read a comparison of
            two efforts as one agent changing its mind.
          skills: The flow's skills it carries, or None for the ones this agent carries.

        Returns:
          The new agent.
        """
        ...

    def asked(self, question: Question) -> str | None:
        """Puts something a turn stopped to ask to whoever is driving this agent."""
        ...

    def prompted(self) -> str | None:
        """Waits for the next thing to say to it, for a flow that is a conversation."""
        ...


class Driven(Agent, Protocol):
    """An agent as whoever hands it to a flow holds it: everything above, and settling it.

    The line between the two is who is entitled to say what an agent is. A flow is handed
    agents and drives them; what each of them runs, where its turns land, what it is called
    and which of the flow's skills it carries are answers somebody already gave -- at a
    prompt, on a command line, in a settings file -- and a flow that could change them would
    be a flow rewriting the choice it was started with. So they are not on :class:`Agent`,
    and a flow that wants one set up differently makes one with :meth:`Agent.clone`.

    They are still on something, because somebody does settle them: `hmz.runner` before the
    first turn, `hmz.flows.driving` around a flow that called another, and the interface when
    somebody watching a run says this agent is to go on as something else. That is this.
    """

    def rename(self, name: str) -> None:
        """Calls it something else, which is what a trace will group its sessions under."""
        ...

    def runs_on(self, machine: MachineConfig | None) -> None:
        """Points its turns at a machine, or at this one, before any of them has landed.

        Settled by whatever hands the agent to a flow rather than by the flow: where an agent
        works is what the flow's own declaration said, and a flow that moved one afterwards
        would be undoing what it declared.
        """
        ...

    def reconfigure(self, config: AgentConfig) -> None:
        """Has its next session run at another model, effort, account or permission."""
        ...

    def loads(self, skills: Iterable[Loaded]) -> None:
        """Tells it which of a flow's skills its sessions may carry from now on."""
        ...

    def disable_goals(self) -> None:
        """Switches its backend's own goal feature off for the rest of the run."""
        ...


class Person(Agent, Protocol):
    """The person at the prompt, driven as an agent so that a flow can talk to them.

    Everything an :class:`Agent` is, and the answers are typed rather than generated. A flow
    declares one where it wants to be able to ask -- `agents: tuple[Agent, Person]` -- and it
    is made rather than chosen: nobody picks a model for the person, so nothing that starts a
    flow asks about this place. Run where nobody is at a prompt, it answers with nothing, and
    a flow written to stop when it is told nothing stops.
    """

    @property
    def board(self) -> Board:
        r"""What the flow and the person both write on, and neither waits at.

        The other half of talking to them. A question stops the turn until it is answered;
        this stops nothing at all -- a handful of named lines kept beside the run and shown
        where the run is shown, which the flow reads and writes whenever it likes and the
        person changes whenever they like::

            while waiting := person.board.get("todo").splitlines():
                person.board.put("doing", waiting[0])
                builder(waiting[0])
                person.board.put("todo", "\n".join(waiting[1:]))

        A line may be one side's alone -- `whose="flow"` for a note the person is to read and
        not rewrite, `whose="user"` for one the flow is to read and not -- and the other side
        is refused where it writes rather than quietly ignored.
        """
        ...


if TYPE_CHECKING:
    from hmz.agents import AgentBase, HumanAgent, SessionBase

    #: The one line that says :mod:`hmz.agents` answers to the interfaces above. Written as
    #: an assignment rather than as inheritance because the arrow points the other way: a
    #: flow names what it drives, and a driver is written without ever naming a flow -- so
    #: what joins the two is checked here, where a type checker reads it, and a driver that
    #: stops answering to this reads as a driver to correct rather than as a flow that fails
    #: on its first turn.
    _implemented: tuple[type[Agent], type[Driven], type[Session], type[Person]] = (
        AgentBase,
        AgentBase,
        SessionBase,
        HumanAgent,
    )
