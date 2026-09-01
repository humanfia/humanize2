"""What a flow declares, what it brings, and how one is run by another.

A flow is a Python file, and the only thing it has to say about itself is what it drives: how
many agents, what each is for, what each has to be able to do and where each may work. That is
read here, off the annotation on the entry point, so that whatever is starting a flow -- a
command line, the flow picker, another flow -- can put the right questions before anything
runs. A flow given the wrong number of agents, or one that cannot run a moment the flow hangs
a hook on, is refused where it was written down rather than hours into a loop.

And a loop worth having is one another loop can reach for, which is :func:`load`: a flow
found by the same name `-f` takes, handed the agents the calling flow was given, carrying its
own skills and its own kept state, and written down -- in a record of its own, beside the
record of the run that called it -- as running under whatever called it.

Nothing here reads a command line and nothing here opens a cycle: :mod:`hmz.runner` does both,
and asks this what the flow it was named says about itself. A call asks the cycle already open
for a record to be written into, which is not a second cycle: it is part of the one run.
"""

from __future__ import annotations

import contextlib
import inspect
import os
import threading
import time
from pathlib import Path
from typing import (
    TYPE_CHECKING,
    Annotated,
    Any,
    NamedTuple,
    cast,
    get_args,
    get_origin,
    get_type_hints,
)

from hmz import telemetry

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Generator, Iterable, Sequence

    from pydantic import BaseModel

    from hmz.agents import AgentBase, Isolated, Moment, Remote
    from hmz.agents.base import Journal
    from hmz.agents.skills import Loaded
    from hmz.cycle import Sub
    from hmz.machines import MachineBase, MachineConfig, Mapped

    from . import Flow as Marked
    from .agent import Agent, Driven

__all__ = [
    "Entry",
    "NotAFlow",
    "Place",
    "Running",
    "carries",
    "configures",
    "contained",
    "container",
    "declares",
    "drives",
    "entered",
    "lands",
    "lands_in",
    "left",
    "load",
    "readies",
    "resumes",
    "running",
    "set_up",
    "spawn",
    "wanted",
]


#: How many arguments a flow's entry point takes when it says it can be set up with
#: something: the agents, the task, and the model that says what there is to set.
_WITH_A_CONFIG = 3

#: A flow's entry point: called with the agents and the task, and done when it returns --
#: or, for one written as `async def run`, when what it returns has been awaited. Which of
#: the two a flow is, is the flow's own business: `Runner.run` waits for it either way.
type Entry = Callable[..., Awaitable[None] | None]


class NotAFlow(ValueError):  # noqa: N818  -- the name SPEC.md gives it
    """What a command line named, when it was not a flow for the agents it was given.

    Its own kind of error, so that a flow failing as it is imported -- one that reads a prompt
    file beside it and does not find it -- is left to fail as it would anywhere, rather than
    being reported as a command line to correct.
    """


class Running(NamedTuple):
    """One flow that is running now.

    Attributes:
      flow: What it was asked for as -- the name a command line gave, or the one a flow asked
        another for, which is the name worth showing either way.
      since: When it started, on the monotonic clock.
    """

    flow: str
    since: float


#: The flows running now, in the order they started: the one somebody ran, then whatever it
#: called, then whatever that called, each beside the thread it is running on. Kept here
#: rather than asked of the flows, which is the one thing a flow cannot be asked -- it is a
#: Python file and may branch any way it likes -- and read by the interface to say what is
#: running under what.
#:
#: A list rather than a stack, because a flow written as a coroutine may have two of them
#: going at once, and both are running. Under a lock, since a flow runs on whichever thread
#: took it and the interface reads while they run.
_RUNNING: list[tuple[Running, threading.Thread]] = []
_TELLING = threading.Lock()

#: The agents each of those is being driven with, for a report of something that went wrong
#: while they were. Keyed by the record `entered` made, so that it goes when the run does: a
#: crash in the interface an hour after a flow ended must not be filed as a crash in that flow,
#: and a flow that called another must not have the called one's agents put under its name.
_DRIVEN: dict[int, Sequence[Agent]] = {}


def running() -> tuple[Running, ...]:
    """Every flow running now, the one that was started first and whatever it called after it.

    A flow says it has ended as it ends, however it ends -- but only a flow that got the
    chance to. One whose thread has gone was abandoned where it stood rather than finished:
    an interface taken down under it, a test that let go of it. So what is running is checked
    against the threads running it, and a flow with no thread left is not one of them.

    Returns:
      One apiece, in the order they started. Empty where nothing is running.
    """
    with _TELLING:
        _RUNNING[:] = [one for one in _RUNNING if one[1].is_alive()]
        return tuple(flow for flow, _ in _RUNNING)


def entered(flow: str, agents: Sequence[Agent] = ()) -> Running:
    """Writes down that a flow has started, for whatever is watching the run.

    Args:
      flow: What it was asked for as.
      agents: What it is being driven with, for a report of a failure in it.

    Returns:
      The record, to be handed back when it ends.
    """
    one = Running(flow, time.monotonic())
    with _TELLING:
        _RUNNING.append((one, threading.current_thread()))
        _DRIVEN[id(one)] = agents
    return one


def left(one: Running) -> None:
    """Writes down that a flow has ended, however it ended.

    Args:
      one: What :func:`entered` answered with.
    """
    with _TELLING:
        _RUNNING[:] = [held for held in _RUNNING if held[0] is not one]
        _DRIVEN.pop(id(one), None)


#: The container this run is in, or None for a run on this machine. One per process rather
#: than one per flow: a flow that called another is one run, working in one place, and two
#: containers under one run would be two workspaces the second flow could not see the first's
#: work in. Set by `contained` while the run is being got ready and taken down when it ends.
_INSIDE: list[tuple[MachineBase, MachineConfig, Mapped]] = []

#: Held over every look at the list above and every change to it, so that one run at a time
#: is settled rather than raced: two started at once would otherwise both have found nothing
#: there and gone ahead. Held for the look and not for the bringing up, which is a pull of
#: minutes -- the image below is what says the place is taken while that is going on.
_ENTERING = threading.Lock()

#: The image of a container that is on its way up, for as long as that takes. A run is in one
#: from the moment another would have to wait for it rather than from the moment it answers,
#: so that the second of two is refused at once instead of at the end of the first's pull.
_COMING: list[str] = []


def container() -> Mapped | None:
    """The container this run is working in, as the flow's own code reaches it.

    A run may be put in a container of its own, which puts every one of its agents there: the
    project directory is mounted at the path it already has, so a file the flow opens is the
    same file a turn opened, and only the tools differ. What a mounted directory does not
    answer for is a command -- one the flow runs is run by this machine's shell against this
    machine's tools -- so that is what this is for::

        if (held := flows.container()) is not None:
            held.run(["pytest", "-q"])

    Returns:
      The workspace on the machine the run lands on, or None for a run on this machine --
      where a flow does what it always did, since the tools it would reach for are this
      machine's either way.
    """
    return _INSIDE[0][2] if _INSIDE else None


@contextlib.contextmanager
def contained(image: str, workspace: str = "") -> Generator[MachineConfig | None]:
    """Puts a whole run in one container, for as long as the block lasts.

    Which is the convenience it is: an agent may already be pointed at a machine one at a
    time, and a run that wanted all of them in a container was a flow declaring `Isolated`
    beside every place it drives. This is that said once, from outside the flow -- the
    container is started here, every agent is pointed at it, and the flow's own reads,
    writes and commands reach it through :func:`container`.

    One container for the run rather than one per agent, which is the whole point: the agents
    are working on one thing, so what one of them writes is what the next one reads. And one
    at a time in a process for the same reason, the container being the process's own rather
    than any one run's: two started at once with an image between them would be two runs
    reaching for one container, so the second is refused rather than handed the first's.

    Args:
      image: The image to run, which needs a `python3` for coganchor's target half and
        whatever else the run expects its agents to reach for. "" is a run on this machine,
        which starts nothing at all.
      workspace: The project directory to give it, defaulting to this one. It is the
        directory itself that goes there rather than a copy, at the path it already has, so
        the work outlives the container.

    Yields:
      The machine every agent of the run is to be pointed at, or None for a run on this
      machine.

    Raises:
      FileNotFoundError: If there is no workspace to give it, or no `docker` to give it to.
      RuntimeError: If a run of this process is in a container already, or if the container
        cannot be started.
    """
    if not image:
        yield None
        return
    from hmz.machines import AnchoredConfig, DockerConfig, Mapped

    with _ENTERING:
        if _INSIDE or _COMING:
            raise RuntimeError(
                "a run of this process is in a container already, and the container is "
                "the process's rather than any one run's -- so a second run started beside "
                "it would be reaching for the first's"
            )
        _COMING.append(image)
    try:
        machine = DockerConfig(image=image, workspace=workspace or None).create()
        # Started once and named by the anchor that reaches it, so that every agent of the
        # run is pointed at the container that is already up rather than starting one apiece.
        anchor = machine.start()
        held = Mapped(anchor)
        where_ = AnchoredConfig(anchor=anchor)
    except BaseException:
        with _ENTERING:
            _COMING.clear()
        raise
    with _ENTERING:
        _INSIDE.append((machine, where_, held))
        _COMING.clear()
    try:
        yield where_
    finally:
        with _ENTERING:
            _INSIDE[:] = [one for one in _INSIDE if one[0] is not machine]
        held.close()
        machine.stop()


def lands_in(agents: Sequence[Agent], where_: MachineConfig) -> None:
    """Puts every agent of a run in the container the run is working in.

    Over whatever each was configured with, because that is what asking for a run to be in a
    container means: it is said once, from outside, about all of them. An agent the flow
    itself put in a container of its own is left where the flow put it -- where an agent works
    is the flow's to say, and this is a convenience rather than a way round that -- and so is
    the person at the prompt, who takes no turn anywhere.

    Args:
      agents: The agents of the run, the person among them.
      where_: The machine they are all to land on.

    Raises:
      RuntimeError: If one of them has already opened a conversation, which is a conversation
        that cannot be moved.
    """
    from hmz.agents import HumanAgent
    from hmz.machines import DockerConfig

    for one in agents:
        if isinstance(one, HumanAgent) or isinstance(one.config.machine, DockerConfig):
            continue
        cast("Driven", one).runs_on(where_)


class Writing(NamedTuple):
    """Where one called flow is being written down, and what its agents wrote to before it.

    Attributes:
      record: The record opened for the call, or None for a call nobody is keeping one of --
        one from a flow run from a test, or from a flow that was called from nothing.
      before: What each of its agents was writing to when it was called, to be handed back
        when it returns: the agents belong to the run, and a flow that called another goes
        on writing its own record afterwards.
    """

    record: Sub | None
    before: tuple[Journal | None, ...]


class Place(NamedTuple):
    """One of the agents a flow drives, as the flow's own annotation declared it.

    Attributes:
      name: What the flow calls it, or "" for a flow that said how many it drives and no more.
      person: Whether it is the person at the prompt, who is handed over rather than chosen.
      moments: The moments the agent filling it has to run, which the flow said by writing
        `Annotated[Agent, Moment.PERMISSION_REQUEST]` where it declared the place. Empty
        where it asked for nothing in particular, which is most places.
      goal: Whether the flow runs this one under the backend's own goal feature, which it
        said by writing `Annotated[Agent, Goal]` where it declared the place. Only four
        backends have one, so a flow built on it is not a flow any agent can drive.
      goals_default: Whether the agent picker initially offers backend goals on or off for
        this place, which a flow may suggest with `AgentDefaults(goals=False)`. Once selected,
        the effective value belongs to the agent's config. A required `Goal` always starts on.
      where: Where the agent filling it may work, which the flow said the same way -- `Remote`
        for one that may be pointed at another machine, an `Isolated` for one that works in a
        container the flow itself names the image of. None for a place the flow said nothing
        about, which runs here and may not be sent anywhere: a flow is written for a shape of
        work, and where its agents work is the flow's to say rather than a setting somebody
        reaches for.
    """

    name: str
    person: bool
    moments: frozenset[Moment]
    where: type[Remote] | Remote | Isolated | None = None
    goal: bool = False
    goals_default: bool = True


def drives(flow: str | os.PathLike[str]) -> tuple[str, ...]:
    """What a flow calls each of the coding agents it drives, in the order it takes them.

    Read without being given any, so that a caller can ask before it has them -- which is
    what choosing the agents for a flow means.

    Args:
      flow: The Python file the flow is written in. It is run to be read.

    Returns:
      One name per agent its entry point declares that somebody has to choose, which is how
      many it has to be given. A flow that declares a plain tuple has not named them, and each
      is "" -- the count is all it said. A place it declared as a :class:`~hmz.flows.Person` is not
      among them: nobody chooses what the person at the prompt runs, so nobody is asked.

    Raises:
      NotAFlow: If the file is not there, or is not a flow.
    """
    return tuple(place.name for place in wanted(flow))


def configures(flow: str | os.PathLike[str]) -> type[BaseModel] | None:
    """What a flow can be set up with before it is run, if it takes anything at all.

    A flow says so by taking a third argument annotated with a pydantic model or None: the
    model is the whole of what may be asked, since the fields, their types, what each one is
    for and the combinations the flow refuses are already written down in it. So whatever is
    starting a flow can put the questions to somebody without knowing what any of them mean.

    Args:
      flow: The Python file the flow is written in. It is run to be read.

    Returns:
      The model to ask with, or None for a flow that takes the agents and the task and
      nothing else -- which is most of them, and is what every flow was before this.

    Raises:
      NotAFlow: If the file is not there, or is not a flow.
    """
    return declares(flow)[3]


def resumes(flow: str | os.PathLike[str]) -> bool:
    """Whether a flow says it can be picked up where the last run of it left off.

    Which is a thing about the flow rather than about any run of it: a run wrote down what
    the flow said when it ran, and the flow may have been rewritten since -- so whatever is
    offering to pick a run up asks the flow as it is now.

    Args:
      flow: The Python file the flow is written in. It is run to be read.

    Returns:
      True for a flow marked `@flow(resumable=True)`, which is one handed the state of the
      last run of it.

    Raises:
      NotAFlow: If the file is not there, or is not a flow.
    """
    return declares(flow)[4].resumable


def _marked(run: Entry) -> Marked:
    """What a flow said about itself where it was marked.

    Args:
      run: Its entry point, which is what carries the mark.

    Returns:
      The mark. Never None: only a marked function is a flow, so anything that got this far
      has one -- and a flow whose mark cannot be read is read as one that said nothing.
    """
    from . import Flow as Said

    held = getattr(run, "__humanize_flow__", None)
    return held if isinstance(held, Said) else Said()


def wanted(flow: str | os.PathLike[str]) -> tuple[Place, ...]:
    """Every agent a flow needs chosen for it, and what each of them has to be able to do.

    What :func:`drives` says, and what the flow asked of each place besides a name: a flow
    that hangs a hook on a moment only some backends run says so in the annotation, and
    whoever is choosing the agents can then offer only the ones that would work.

    Args:
      flow: The Python file the flow is written in. It is run to be read.

    Returns:
      One place per agent somebody has to choose, in the order the flow takes them.

    Raises:
      NotAFlow: If the file is not there, or is not a flow.
    """
    return tuple(place for place in declares(flow)[1] if not place.person)


def spawn(template: Agent, names: Iterable[str]) -> tuple[Agent, ...]:
    """Makes runtime agents from one configured template and joins them to its run.

    A flow declares the agents it needs before it starts. Some work only reveals its fan-out
    after a turn has landed, such as a triage agent choosing which specialists are needed. The
    flow declares one template for that role, then expands it once the work is known::

        experts = spawn(agents.expert, (f"expert-{at + 1}" for at in range(len(tasks))))
        await asyncio.gather(
            *(expert.aturn(task) for expert, task in zip(experts, tasks, strict=True))
        )

    Each result is a distinct agent with the template's backend, configuration, machine and
    skills. When the template belongs to a running flow, the new agents join that same cycle:
    their sessions are traced under their own names and stopping the run stops them too.

    Args:
      template: The agent whose settled configuration each new agent inherits.
      names: One non-empty, unique name per agent to create. The iterable's length is the
        runtime fan-out.

    Returns:
      The new agents, in the same order as ``names``.

    Raises:
      ValueError: If a name is empty or repeated, or collides with an agent already in the run.
    """
    requested = tuple(str(name).strip() for name in names)
    if any(not name for name in requested):
        raise ValueError("spawned agent names must not be empty")
    if len(set(requested)) != len(requested):
        raise ValueError("spawned agent names must be unique")

    creating: list[Agent] = []
    try:
        for name in requested:
            creating.append(template.clone(name=name))  # noqa: PERF401 -- cleanup needs partial clones
    except BaseException:
        for agent in creating:
            with contextlib.suppress(Exception):
                agent.stop()
        raise
    made = tuple(creating)
    if template.cycle is None:
        return made
    joins = getattr(template.cycle, "spawned", None)
    if callable(joins):
        try:
            joins(template, made)
        except BaseException:
            for agent in made:
                with contextlib.suppress(Exception):
                    agent.stop()
            raise
    else:
        # A flow may be driven under a journal of its own. It can still trace the sessions even
        # when that journal predates runtime agent registration.
        for agent in made:
            agent.cycle = template.cycle
    return made


def declares(
    flow: str | os.PathLike[str],
) -> tuple[
    Entry,
    tuple[Place, ...],
    Callable[..., tuple[Agent, ...]],
    type[BaseModel] | None,
    Marked,
]:
    """Loads a flow and reads what it says about the agents it drives.

    Args:
      flow: The flow: one that came with humanize, by name, or a file of your own.

    Returns:
      Its entry point, one place per agent it drives, what to hand those agents over as --
      the named tuple the flow declared, or a plain one where it declared that -- the model
      it can be set up with, or None where it takes no setting up, and what the flow said
      about itself where it was marked.

    Raises:
      NotAFlow: If the file is not there, is not a flow -- nothing in it marked `@flow()`, or
        one whose `agents` cannot be read or says nothing about how many it takes.
    """
    from . import find, inside, loaded

    named = str(flow)
    # Which of the file's flows was asked for, before the name is resolved to a file: a file
    # may hold several, and `humanize1:gen-plan` is one of them.
    wanted = inside(named)
    # Resolved here rather than by whoever is starting one, so that a name works wherever a
    # flow is named -- a command line, an interface, a `Runner` written by hand.
    flow = find(named)
    # The same test `find` applies, and for the same reason: a place that cannot be read
    # holds no flow, which `Path.is_file` would raise about rather than answer.
    if not os.path.isfile(flow):  # noqa: PTH113
        raise NotAFlow(f"{flow}: {_unfetched(str(flow))}")
    read = loaded(flow)
    run = _entry(read, wanted)
    if run is None:
        # A file that holds several flows names each of them after itself, so whoever asked
        # for the file alone -- or for one of them under a name it does not have -- is a
        # colon away from what they meant, and saying which ones is what ends it.
        holds = [f"{_called(flow)}:{one}" for one in _holds(read)]
        missing = f"{flow}: nothing in it is a flow called {wanted!r}"
        if wanted and holds:
            raise NotAFlow(f"{missing}; it holds {', '.join(holds)}")
        if wanted:
            raise NotAFlow(missing)
        if holds:
            raise NotAFlow(
                f"{flow}: nothing in it is marked @flow(), and it holds "
                f"{', '.join(holds)} -- name the one to run"
            )
        raise NotAFlow(
            f"{flow}: nothing in it is marked @flow() -- a flow is a function marked with "
            "it, which is how a file says which of the functions in it is one"
        )
    try:
        # A function, so that what is read below is what the entry point will be called
        # with: a class or a partial answers with annotations that are somebody else's.
        # Extras and all: what a flow wrote beside the type is what it asks of the agent.
        hinted = (
            get_type_hints(run, include_extras=True) if inspect.isfunction(run) else {}
        )
        declared = hinted.get("agents")
    except NameError as unresolved:
        # A flow whose agents are imported under TYPE_CHECKING states how many it drives
        # where nothing can read it back, which is the one thing a flow is asked to say.
        raise NotAFlow(
            f"{flow}: the flow's agents cannot be read here ({unresolved}) -- import what "
            "the annotation names at runtime, so the count it states can be checked"
        ) from unresolved
    # A named tuple is a tuple that also says what each of its places is for, and `_fields`
    # is where it says it. `_make` builds one from a sequence, exactly as `tuple` does, so
    # the flow is handed the type it asked for either way.
    if (
        run is not None
        and declared is not None
        and (fields := getattr(declared, "_fields", None))
    ):
        kinds = _kinds(declared, run)
        return (
            _compiled(named, read, run),
            tuple(_place(at, kinds.get(at)) for at in fields),
            declared._make,
            _setting(run, hinted),
            _marked(run),
        )
    # `tuple[Agent, ...]` is any number of them, which is no answer to the question.
    declares = get_args(declared)
    if run is None or get_origin(declared) is not tuple or Ellipsis in declares:
        raise NotAFlow(
            f"{flow}: a flow is a function marked @flow() taking (agents, task), whose "
            "agents are annotated with a tuple of a fixed length -- how many agents the "
            "flow drives -- or with a NamedTuple of them, which also says what each is for"
        )
    return (
        _compiled(named, read, run),
        tuple(_place("", kind) for kind in declares),
        tuple,
        _setting(run, hinted),
        _marked(run),
    )


def _compiled(named: str, read: dict[str, Any], run: Entry) -> Entry:
    """One flow's entry point, or -- for an atlas -- something that runs its prophecy.

    An atlas is a flow whose body is a declaration: what it says is compiled before anything
    runs, and what runs is the prophecy that compiling made. So the entry point itself is
    never called, and what everything else holds is the walk over the prophecy instead --
    swapped here, where a flow is loaded, so that every way of running one gets both the
    compiling and the walking without knowing there are two kinds of flow.

    Args:
      named: The flow, as it was asked for.
      read: What running its file left behind.
      run: Its entry point.

    Returns:
      The entry point for an ordinary flow, and the walk for an atlas.
    """
    from .atlas import ATLAS

    if getattr(run, ATLAS, None) is None:
        return run
    return _Walked(named, read, run)


class _Walked:
    """An atlas's entry point, compiled when the run reaches it and not before.

    :func:`declares` is asked by everything that wants to know what a flow says as well as by
    the two places that run one: how many agents it drives, what it can be set up with,
    whether it can be picked up. Every one of those is answered off the entry point's own
    annotation, and compiling the atlas to answer them would mean reading every file the flow
    holds -- and, for one that does not compile, refusing a question the flow can answer. A
    flow picker asking whether an atlas can be picked up would then be told no.

    So the compiling waits for the call, which is still before the first node runs: an atlas
    is a flow checked before anything happens rather than one checked before anything is
    read. Once compiled it is held, since this is one run of one flow.
    """

    def __init__(self, named: str, read: dict[str, Any], entry: Entry) -> None:
        """Holds what it takes to compile one atlas, for the moment something runs it.

        Args:
          named: The flow, as it was asked for.
          read: What running its file left behind.
          entry: The atlas's own entry point, which is never called.
        """
        self._named = named
        self._read = read
        self._entry = entry
        self._walk: Entry | None = None
        # What the entry point was marked with, so that whatever reads a flow off what
        # `declares` answered reads what it would have read off the entry point itself.
        self.__dict__.update(entry.__dict__)

    def __call__(self, *said: Any) -> Awaitable[None] | None:
        """Runs the atlas, compiling it first if this is the first call.

        Args:
          said: What any flow is called with -- the agents, the task, the config for one
            that takes one, and the dict a resumable flow is handed.

        Returns:
          Whatever the prophecy answers with.

        Raises:
          NotAFlow: If the atlas does not compile, saying each reason on a line of its own.
        """
        return self.ready()(*said)

    def ready(self) -> Entry:
        """Compiles the atlas, if this is the first thing to ask for it.

        Returns:
          The walk over the prophecy.

        Raises:
          NotAFlow: If the atlas does not compile, saying each reason on a line of its own.
        """
        if self._walk is None:
            from .stepping import walking

            self._walk = walking(self._named, self._read, self._entry)
        return self._walk


def readies(run: Entry) -> Entry:
    """Compiles whatever a flow has to have compiled before a run of it starts.

    An atlas is compiled when something reaches for the run rather than when a flow is read,
    so that asking what a flow drives, what it can be set up with or whether it can be picked
    up neither pays for a reading of every file it holds nor is refused by one. The two
    places that are about to run one ask here instead: a body that does not compile is then
    refused where the run is being set up, rather than from inside a run that has already
    pulled an image and opened a cycle.

    Args:
      run: What :func:`declares` answered with.

    Returns:
      The same thing, ready to be called.

    Raises:
      NotAFlow: If it is an atlas that does not compile.
    """
    if isinstance(run, _Walked):
        run.ready()
    return run


def _settles(agent: Agent) -> Driven:
    """One agent as whoever hands it to a flow holds it, rather than as a flow does.

    A flow sees an agent through :class:`~hmz.flows.agent.Agent`, which is what a flow may
    ask of one and says nothing about setting it up: an agent is what somebody already chose,
    and a flow that could change it would be a flow rewriting that choice. This module is one
    of the three places entitled to -- it settles where an isolated agent works, and what the
    flow it is about to run works by -- so it says so here rather than reaching through a
    class it must not name.

    Args:
      agent: The agent, as the flow holds it.

    Returns:
      The same agent, as whoever hands it over holds it.
    """
    return cast("Driven", agent)


def carries(flow: str | os.PathLike[str], agents: Sequence[Agent]) -> None:
    """Gives every agent of a flow the skills that flow works by.

    A flow is a directory, and what it keeps in `skills/` -- plus whatever it named where it
    was declared -- is mounted onto every session these agents open. Told to the agents rather
    than configured on them: the skills are the flow's, and the same agent under another flow
    carries that flow's instead.

    Worked out here rather than at each session, because a repository named by a flow is
    fetched to get it: a run that cannot reach one says so before the first turn rather than
    an hour into a loop. Worked out afresh each time a flow is run or called, so that a flow
    which has rewritten its own skills is driven by what it has now.

    Args:
      flow: The flow, as it was named.
      agents: The agents it is being run with.
    """
    from . import at as directory
    from .skills import brought

    where = directory(str(flow))
    declared: tuple[str, ...] = ()
    with contextlib.suppress(Exception):
        # What the flow said where it was declared, which is read off the flow that was asked
        # for. A flow that will not load is left to the loading to report.
        declared = _brings(flow)
    # A flow that is one file has no directory of its own and so brings no skills of its own
    # -- but it may still name skills that live somewhere else, and those are as much what it
    # works by as a directory flow's are.
    if not where and not declared:
        return
    try:
        loaded = brought(where, declared)
    except OSError as unreachable:
        raise NotAFlow(f"{flow}: {unreachable}") from unreachable
    for agent in agents:
        _settles(agent).loads(loaded)


def _brings(flow: str | os.PathLike[str]) -> tuple[str, ...]:
    """The skills one flow named where it was declared, which live somewhere else.

    Args:
      flow: The flow, as it was named -- the half after the colon says which of the flows in
        the directory was asked for.

    Returns:
      One identifier apiece, and nothing at all for a flow that named none.
    """
    from . import Flow as Marked
    from . import find, inside, loaded

    wanted = inside(str(flow))
    for one in loaded(find(str(flow))).values():
        said = getattr(one, "__humanize_flow__", None)
        if isinstance(said, Marked) and said.name == wanted:
            return said.skills
    return ()


def _called(flow: str | os.PathLike[str]) -> str:
    """What a flow is called, given the file its entry point is in.

    Args:
      flow: The path that was run.

    Returns:
      The directory's name for a flow laid out as one -- the entry point is `__init__.py` in
      every flow there is, and naming a flow after that would name them all the same -- and
      the file's own name for a file somebody pointed at outright.
    """
    from . import ENTRY

    said = Path(flow)
    return said.parent.name if said.name == ENTRY else said.stem


class _CalledSkills:
    """Template for handing agents into a called flow and restoring them afterwards."""

    def carry(self, flow: str, agents: Sequence[Agent]) -> list[tuple[Loaded, ...]]:
        """Loads the called flow's skills under this policy, returning the prior state."""
        before = [agent.loaded for agent in agents]
        carries(flow, agents)
        for agent, parent in zip(agents, before, strict=True):
            _settles(agent).loads(self.combine(parent, agent.loaded))
        return before

    def combine(
        self, parent: tuple[Loaded, ...], child: tuple[Loaded, ...]
    ) -> tuple[Loaded, ...]:
        """Chooses what the called flow carries; isolation is the default policy."""
        del parent
        return child


class _InheritedCalledSkills(_CalledSkills):
    """Carries a child's skills plus parent skills whose names the child did not replace."""

    def combine(
        self, parent: tuple[Loaded, ...], child: tuple[Loaded, ...]
    ) -> tuple[Loaded, ...]:
        """Merges child first so its version wins every same-name skill."""
        child_names = {one.name for one in child}
        return child + tuple(one for one in parent if one.name not in child_names)


_ISOLATED_SKILLS = _CalledSkills()
_INHERITED_SKILLS = _InheritedCalledSkills()


def load(flow: str | os.PathLike[str], *, inherit_skills: bool = False) -> Entry:
    """One flow, ready for another flow to run: what it marked, found by name.

    A flow is a loop over agents, and a loop worth having is one another loop can reach for::

        from hmz.flows import Agent, flow, load

        @flow
        def run(agents: tuple[Agent, Agent], task: str) -> None:
            plan = load("official/humanize1:gen-plan")
            plan(agents, f"plan this first: {task}")
            agents[0].new()(task)

    The name is the one `-f` takes -- `ralph_loop`, `official/rlar`, `humanize1:gen-plan`, a
    path of your own -- so a flow reaches another flow the way a person does, and a flowverse
    is a library as well as a menu.

    Loading rather than calling, because that is what this does: what comes back is a flow to
    run, and running it is the caller's own line. It is not :func:`hmz.flows.loaded`, which is
    what running a flow's file leaves behind -- one loads a flow, the other reads a file.

    What comes back is the flow's own function, with the run written down around it: what is
    running is what the interface shows, and a flow that called another must not read as the
    flow that was started. It is called the way the flow itself is -- the agents, the task,
    and the config for one that says it takes one -- and answers with whatever the flow
    answers with, so a flow written as a coroutine is awaited by whoever called it::

        await load("official/rlar")(agents, task)

    The flow is read again at each call, and so are the skills it brings. A flow is a
    directory on disk, and one that has been rewritten between two calls of it -- by hand, or
    by an agent this very flow is driving -- is run as it is now rather than as it was when
    somebody first asked for it. That is what makes a loop that improves its own flow, or its
    own skills, a loop that then runs the improved one.

    A called flow carries only its own skills by default. A wrapper flow may explicitly pass
    its skills through with ``inherit_skills=True``. The called flow still owns the result:
    its skill wins when parent and child use the same name, and the agents are restored to
    exactly what the caller carried when the call returns or raises.

    Each call is written down as the run of a flow it is. The cycle of the run that called it
    gets a record of that call -- one file per call, named for the flow and for this call of
    it -- and what the called flow opens, keeps and calls in turn goes there rather than into
    the record of whatever started the run. The record that called it says `called` and
    `returned` with the filename, so a run reads back as the shape it ran in.

    Args:
      flow: The flow to call, by the name `-f` takes.
      inherit_skills: Whether skills carried by the calling flow remain available inside the
        called flow, after the called flow's own and only where their names do not collide.

    Returns:
      Something to call with the agents and the task.

    Raises:
      NotAFlow: If there is no such flow, or it is not one. Raised here rather than at the
        call, so that a flow which asks for another by a name that is wrong says so when it is
        asked for rather than an hour into a loop -- and again at each call, for a flow that
        was rewritten into something that is no longer one.
    """
    # Said now, so a name that is wrong -- or an atlas whose body will not compile -- is
    # wrong where it was written rather than an hour into a loop.
    readies(declares(flow)[0])
    named = str(flow)
    skill_policy = _INHERITED_SKILLS if inherit_skills else _ISOLATED_SKILLS

    def calling(
        agents: Sequence[Agent],
        task: str,
        config: BaseModel | dict[str, Any] | None = None,
    ) -> Awaitable[None] | None:
        # Read afresh, which is what makes a flow rewritten since the last call the flow that
        # runs now: a flow is a directory, and reading one is running its entry point.
        run, places, make, setting, mark = declares(flow)
        driven = _handed(named, places, make, agents)
        # Read back through the flow's own model, which is what refuses a config a flow does
        # not take and one it takes another of -- and what puts the settings through its own
        # validators at the moment it is about to run, exactly as a run of it does. Before the
        # skills below, because a refusal here is a call that never happened: a caller that
        # catches it -- to try another config, or to go on without this flow -- must not be
        # left driving agents that are carrying the skills of a flow that never ran.
        given = None if config is None else set_up(named, setting, config)
        settings = () if setting is None else (given,)
        # And what it left behind last time, for a flow that says it can be picked up: kept
        # under its own name in the cycle of the run that called it, since a flow that called
        # another is two flows and neither writes the other's.
        held = () if not mark.resumable else (_holding(driven, named),)
        # And the skills it works by, which are the flow's rather than the agents': a called
        # flow brings its own, mounted onto whatever sessions it opens, and hands the agents
        # back as it found them so that the flow which called it goes on carrying its own.
        before = skill_policy.carry(named, driven)
        started = entered(named, driven)
        # And a record of its own to write into, in the cycle of the run that called it: a
        # called flow opens sessions and calls flows of its own, and what it did is its own
        # rather than a run's that happened to start it.
        writing = _opened(driven, named, task, resumable=mark.resumable)
        try:
            answered = run(driven, task, *settings, *held)
        except BaseException as why:
            _ended(driven, started, before, writing, type(why))
            raise
        if inspect.isawaitable(answered):
            # A flow written as a coroutine has not run yet: it is running while whoever
            # called it awaits it, so what says it is running has to last that long too.
            return _awaited(answered, driven, started, before, writing)
        _ended(driven, started, before, writing)
        return None

    return calling


async def _awaited(
    answered: Awaitable[None],
    driven: tuple[Agent, ...],
    started: Running,
    before: Sequence[tuple[Loaded, ...]],
    writing: Writing,
) -> None:
    """Waits for a called flow that is a coroutine, and writes down that it ended.

    Args:
      answered: What calling it gave back.
      driven: The agents it was called with.
      started: What :func:`entered` answered with.
      before: What each of them was carrying before it was called.
      writing: What :func:`_opened` answered with.
    """
    try:
        await answered
    except BaseException as why:
        _ended(driven, started, before, writing, type(why))
        raise
    _ended(driven, started, before, writing)


def _opened(
    driven: tuple[Agent, ...],
    named: str,
    task: str,
    *,
    resumable: bool,
) -> Writing:
    """Opens the record a called flow is written to, and points its agents at it.

    Found through the agents rather than through anything of ours: the cycle belongs to the
    run that was started, the agents were handed it as it began, and a flow called from a
    `Runner` that opened none -- a flow run from a test, a flow called from a flow called
    from nothing -- has nowhere to write and nothing to say.

    The agents write into it for as long as the call lasts, which is what puts a session
    opened inside a called flow in that flow's record rather than in the record of whatever
    started the run. They are pointed back at what they were writing to when it returns, the
    way they are handed back the skills they carried.

    Args:
      driven: The agents the called flow was handed.
      named: The flow, as it was asked for.
      task: What it was called with.
      resumable: Whether it says it can be picked up again.

    Returns:
      The record and what to hand the agents back.
    """
    # Asked what it is rather than taken as read: what an agent asks of a journal is that it
    # can be told a session was opened, and this is asking it for something else.
    from hmz.cycle import Cycle

    under = next((one.cycle for one in driven if isinstance(one.cycle, Cycle)), None)
    if under is None:
        return Writing(None, ())
    # Cast because a flow sees its agents through `Agent`, which says what a flow may ask
    # of one and nothing about what it was configured with -- and what a record says it
    # was driven by is exactly that. They are the run's own agents either way.
    record = under.called(
        named, cast("Sequence[AgentBase]", driven), task, resumable=resumable
    )
    was = tuple(agent.cycle for agent in driven)
    for agent in driven:
        agent.cycle = record
    return Writing(record, was)


def _ended(
    driven: tuple[Agent, ...],
    started: Running,
    before: Sequence[tuple[Loaded, ...]],
    writing: Writing,
    kind: type[BaseException] | None = None,
) -> None:
    """Writes down that a called flow has ended, and hands its agents back as they came.

    Args:
      driven: The agents it was called with.
      started: What :func:`entered` answered with.
      before: The skills each of them carried before the call, which are the calling flow's.
      writing: What :func:`_opened` answered with.
      kind: What was raised out of the called flow, if anything.
    """
    left(started)
    if writing.record is not None:
        for agent, wrote in zip(driven, writing.before, strict=True):
            agent.cycle = wrote
        writing.record.ended(kind)
    for agent, held in zip(driven, before, strict=True):
        _settles(agent).loads(held)


def _handed(
    flow: str,
    places: tuple[Place, ...],
    make: Callable[..., tuple[Agent, ...]],
    agents: Sequence[Agent],
) -> tuple[Agent, ...]:
    """The agents a called flow is handed, as the tuple that flow declared.

    A flow is called with what it drives, so a caller hands over as many agents as the flow
    declares -- and may hand over one fewer where the flow talks to the person, since the
    person is made rather than chosen. Nothing is renamed: the agents belong to the flow that
    was started, and a name changed under it would change what the run has already been
    written down as.

    Args:
      flow: The flow being called, for what a refusal says.
      places: What it declared.
      make: What to build its agents as -- the named tuple it declared, or a plain one.
      agents: What the caller handed over.

    Returns:
      The agents, as the flow declared them.

    Raises:
      NotAFlow: If that is the wrong number of them, if one of them cannot run a moment the
        flow says that place has to, or if one is somewhere the flow does not put it.
    """
    from hmz.agents import HumanAgent

    given = list(agents)
    asked = [place for place in places if not place.person]
    if len(given) == len(places):
        driven = given
    elif len(given) == len(asked):
        # The person is made rather than chosen, exactly as a run of the flow makes one.
        taking = iter(given)
        driven = [HumanAgent() if place.person else next(taking) for place in places]
    else:
        raise NotAFlow(
            f"{flow}: the flow drives {len(asked)} agents, {len(given)} given"
        )
    for agent, place in zip(driven, places, strict=True):
        if short := place.moments - type(agent).moments:
            raise NotAFlow(
                f"{flow}: {place.name or 'the agent'} has to run "
                f"{', '.join(sorted(short))}, which {agent.backend} does not"
            )
        # The same as a run of this flow asks, and asked here for the same reason: a place
        # run under a goal, filled by an agent that has no goal feature or has had it
        # switched off, is a call that fails at its first `pursue` -- hours in, from inside
        # the called flow, rather than where the call was written.
        if place.goal and not type(agent).pursues:
            raise NotAFlow(
                f"{flow}: {place.name or 'the agent'} is run under a goal, which "
                f"{agent.backend} has no feature for"
            )
        if place.goal and not agent.goals_enabled:
            raise NotAFlow(
                f"{flow}: {place.name or 'the agent'} is run under a goal, but goals "
                "were switched off for it"
            )
        lands(flow, agent, place)
    return make(driven)


def _holding(driven: tuple[Agent, ...], named: str) -> dict[str, Any]:
    """The dict a called flow that can be picked up writes what it wants back into.

    Kept in the cycle of the run that called it, under the called flow's own name: a flow
    that called another is two flows, each with its own to keep, and both of them part of one
    run. A call from a flow that opened no cycle -- one run from a test, one called from
    nothing -- is handed a dict that is nowhere, which is a flow that runs and leaves nothing
    rather than a call that fails.

    Args:
      driven: The agents the called flow is being handed, which is what holds the cycle.
      named: The called flow, as it was asked for.

    Returns:
      What it left behind last time, as something to write this time's into.
    """
    from hmz.cycle import Cycle, resumed, state

    for agent in driven:
        if isinstance(agent.cycle, Cycle):
            at = resumed(named, agent.cycle.workspace)
            return agent.cycle.state(
                named, state(at, named) if at is not None else None
            )
    return {}


def lands(flow: str | os.PathLike[str], agent: Agent, place: Place) -> None:
    """Settles where one agent's turns land, and refuses a machine the flow did not allow.

    Where an agent works is the flow's to say and not a setting anybody may reach for: a flow
    is written for one shape of work, and one whose agents read this project cannot have one
    of them reading somebody else's. So a place says nothing and its agent runs here, or says
    `Remote` and its agent may be pointed at a machine by whoever chose it, or says `Isolated`
    and the machine is the flow's own -- a container of the image it named, which nobody else
    has any say in.

    A whole run put in a container from outside is none of those three: it was said once,
    about every agent, by whoever started the run, and an agent standing in it was pointed
    nowhere by anybody. So a place that says nothing takes one, and goes on refusing the
    machine somebody actually chose for it. A place that says `Isolated` does not: that flow
    named an image of its own, and being handed the run's container instead is being pointed
    at a machine, which is what it says nobody may do.

    Args:
      flow: The flow, for what a refusal says.
      agent: The agent filling the place.
      place: What the flow declared.

    Raises:
      NotAFlow: If the agent was configured to work somewhere the flow does not put it, or if
        it has already opened a session, which is a conversation that cannot be moved.
    """
    from hmz.agents import Isolated, isolated

    called = place.name or "the agent"
    if isinstance(place.where, Isolated):
        if agent.config.machine is not None:
            raise NotAFlow(
                f"{flow}: {called} works in a container of this flow's own, so there is "
                "nothing to point it at"
            )
        try:
            _settles(agent).runs_on(isolated(place.where.image))
        except RuntimeError as opened:
            raise NotAFlow(f"{flow}: {called} {opened}") from opened
        return
    # The container the whole run works in, which is a convenience rather than a second way
    # of saying where an agent works -- so a flow this one called must not read it as one.
    # By identity, since what is exempt is that container and not the idea of a machine.
    inside = bool(_INSIDE) and agent.config.machine is _INSIDE[0][1]
    if place.where is None and agent.config.machine is not None and not inside:
        raise NotAFlow(
            f"{flow}: {called} runs on this machine -- this flow does not say it works "
            "anywhere else, so it cannot be pointed at one"
        )


def _unfetched(named: str) -> str:
    """Why a flow that was named is not there, as far as that can be told.

    Args:
      named: What was asked for, as it was written.

    Returns:
      The reason: that the flowverse it named has not been fetched yet, where that is what
      happened, and otherwise that there is no such file. A flowverse is offered before it is
      fetched -- `official` is there from the start -- so "no such file" would be the answer
      to a name that is right, given by the one thing that knows it has not been downloaded.
    """
    from . import flowverses

    whose, _, rest = named.partition("/")
    for verse in flowverses():
        if verse.name == whose and rest and not verse.fetched:
            return (
                f"the {whose} flowverse has not been fetched yet -- open /flowverses and "
                "press r on it"
            )
    return "no flow to read: a flow is a directory with an __init__.py in it"


def _entry(inside: dict[str, Any], wanted: str) -> Callable[..., Any] | None:
    """The flow a file was asked for, out of everything in it.

    By what it was marked with and never by what it is called: a file is run to be read, and
    the functions it leaves behind are its flows, whatever it imported and whatever it broke a
    flow into. `@flow()` is the one the file holds under its own name.

    Args:
      inside: What running the file left behind.
      wanted: Which of its flows was asked for, or "" for the one it holds under its own name.

    Returns:
      The entry point, or None where the file holds no such flow.
    """
    from . import Flow

    for one in inside.values():
        said = getattr(one, "__humanize_flow__", None)
        if isinstance(said, Flow) and said.name == wanted:
            return cast("Callable[..., Any]", one)
    return None


def _holds(inside: dict[str, Any]) -> list[str]:
    """What a file calls each of the flows it holds under a name of its own.

    Args:
      inside: What running the file left behind.

    Returns:
      One name apiece, in the order the file declared them. Its `run` is not among them: it
      is the flow the file holds under its own name, and has no name of its own.
    """
    from . import Flow

    said = (getattr(one, "__humanize_flow__", None) for one in inside.values())
    return [one.name for one in said if isinstance(one, Flow) and one.name]


def set_up(
    flow: str | os.PathLike[str],
    setting: type[BaseModel] | None,
    config: BaseModel | dict[str, Any],
) -> BaseModel:
    """Reads a config back into the model the flow has just declared.

    Read back rather than taken as it comes, because a flow is loaded by running its file:
    the class it declared last time is not the class it declares this time, so what was set
    up against one is a stranger to the other. What survives that is the fields, which is
    what a config is -- and reading them back is also what puts them through the flow's own
    validators one last time, at the moment the flow is about to run. A mapping of the same
    fields, which is what a YAML file of them reads as, is read back the same way.

    Args:
      flow: The flow, for what a refusal says.
      setting: What it says it can be set up with, or None where it said nothing.
      config: What it is being set up with.

    Returns:
      The same settings, as an instance of the model this loading of the flow declared.

    Raises:
      NotAFlow: If the flow takes no config, or takes another one, or will not accept these
        settings -- each of which is a caller to correct before anything runs.
    """
    from pydantic import ValidationError

    if setting is None:
        raise NotAFlow(f"{flow}: the flow takes no config, and one was given")
    if not isinstance(config, dict) and type(config).__name__ != setting.__name__:
        raise NotAFlow(
            f"{flow}: the flow takes a {setting.__name__} to be set up with, not a "
            f"{type(config).__name__}"
        )
    fields = config if isinstance(config, dict) else config.model_dump()
    try:
        return setting.model_validate(fields)
    except ValidationError as refused:
        raise NotAFlow(f"{flow}: {refused}") from refused


def _setting(run: Entry, hinted: dict[str, object]) -> type[BaseModel] | None:
    """The model a flow says it can be set up with, read off its third argument.

    Third rather than named, because that is where it is: `run(agents, task, config)` is the
    entry point, and a flow which takes nothing more has two arguments and is left alone.

    Args:
      run: The flow's entry point.
      hinted: Its annotations, resolved.

    Returns:
      The model, or None where the flow takes no third argument or annotated it with
      something that is not one -- a flow is not refused for the shape of an argument
      nothing has to fill.
    """
    from pydantic import BaseModel

    taken = list(inspect.signature(run).parameters)
    if len(taken) < _WITH_A_CONFIG:
        return None
    kind = hinted.get(taken[_WITH_A_CONFIG - 1])
    # `Model | None` is the annotation a flow writes, and is two arguments to a union; one
    # written as the model alone is the same question with no way to answer it as unasked.
    for said in (*get_args(kind), kind):
        if isinstance(said, type) and issubclass(said, BaseModel):
            return said
    return None


def _kinds(declared: type, run: Entry) -> dict[str, object]:
    """What a flow annotated each place of its agents with, resolved where it can be.

    Against the flow's own globals, which are where its names are: a flow loaded by running
    the file is not a module anything can look up, so the class cannot resolve its own
    annotations on its own.

    Args:
      declared: The named tuple the flow declared its agents as.
      run: Its entry point, which is what carries those globals.

    Returns:
      One annotation per place, resolved if they could be resolved and as they were written
      if they could not -- a name that will not resolve is still a name to read.
    """
    try:
        return dict(
            get_type_hints(
                declared, globalns=dict(run.__globals__), include_extras=True
            )
        )
    except (NameError, TypeError):
        return dict(getattr(declared, "__annotations__", {}))


def _place(name: str, kind: object) -> Place:
    """One place in a flow's agents, read off what the flow annotated it with.

    Args:
      name: What the flow calls it, or "" where it named none of them.
      kind: The annotation, which may be an `Annotated` carrying what the flow asks of
        whoever fills the place.

    Returns:
      The place.
    """
    moments = frozenset(_moments(kind))
    where = _where(kind)
    goal = _goal(kind)
    goals_default = _goals_default(kind)
    if get_origin(kind) is Annotated:
        kind = get_args(kind)[0]
    return Place(
        name=name,
        person=_is_person(kind),
        moments=moments,
        where=where,
        goal=goal,
        goals_default=True if goal else goals_default,
    )


def _where(kind: object) -> type[Remote] | Remote | Isolated | None:
    """Where a flow said the agent filling a place may work.

    Args:
      kind: What the flow annotated the place with.

    Returns:
      What it wrote beside the type -- `Remote`, or an `Isolated` naming an image -- and None
      for a place it annotated with the type alone, which is one that works here.
    """
    from hmz.agents import Isolated, Remote

    if get_origin(kind) is not Annotated:
        return None
    for said in get_args(kind)[1:]:
        if said is Remote or isinstance(said, (Remote, Isolated)):
            return said
    return None


def _goal(kind: object) -> bool:
    """Whether a flow said the agent filling a place is run under its backend's goal feature.

    Args:
      kind: What the flow annotated the place with.

    Returns:
      True if it wrote `Goal` beside the type, and False for a place annotated with the type
      alone -- which is one driven by turns like every other.
    """
    from hmz.agents import Goal

    if get_origin(kind) is not Annotated:
        return False
    return any(said is Goal for said in get_args(kind)[1:])


def _goals_default(kind: object) -> bool:
    """The initial on/off choice a flow suggests for this agent's goals.

    The suggestion is picker metadata, not runtime policy. The picker resolves it into the
    boolean on `AgentConfig` before constructing the agent.
    """
    from hmz.agents import AgentDefaults

    if get_origin(kind) is not Annotated:
        return True
    for said in get_args(kind)[1:]:
        if isinstance(said, AgentDefaults):
            return said.goals
    return True


def _moments(kind: object) -> tuple[Moment, ...]:
    """The moments a flow asked the agent filling a place to run.

    Args:
      kind: What the flow annotated the place with.

    Returns:
      Whatever moments it wrote beside the type, in the order it wrote them, and nothing at
      all for a place it annotated with the type alone.
    """
    from hmz.agents import Moment

    if get_origin(kind) is not Annotated:
        return ()
    return tuple(said for said in get_args(kind)[1:] if isinstance(said, Moment))


def _is_person(kind: object) -> bool:
    """Whether a place in a flow's agents is the person at the prompt.

    Args:
      kind: What the flow annotated that place with, which is the class itself, or its name
        where the flow put its annotations off until they are asked for.

    Returns:
      True if it is a `Person`, which is a place nobody is asked to configure. The class that
      answers to that interface is taken for it too: a flow written before there was one names
      the driver, and the place it meant is the same place.
    """
    from hmz.agents import HumanAgent

    from .agent import Person

    people = (Person, HumanAgent)
    if isinstance(kind, str):
        # Read by the word it names rather than by what that word means, which is all there
        # is to go on: the first thing inside an `Annotated[...]` is the type it is about.
        said = kind.removeprefix("Annotated[").split(",")[0].strip()
        return said.rpartition(".")[2] in {one.__name__ for one in people}
    return any(kind is one for one in people)


def _about() -> dict[str, Any]:
    """What is running now, for a report of something that went wrong while it was.

    Read off what is running rather than off whichever run registered last: a flow that called
    another is two runs, and a crash after both have ended belongs to neither. Names and never
    contents -- which flow, how long it has been going, and for each of its agents the backend
    it drives, the model at the effort, the account by the name it was made under, what it may
    do, where its work lands and which skills the flow mounted onto it. What the flow was told,
    what any agent said and what is in any file are not here and are not reachable from what is.

    Returns:
      The description, as plain values something can write out as YAML. The flow named at the
      top is the one somebody started, which is the one a report is about; whatever it called
      is under `running` beneath it.
    """
    with _TELLING:
        held = [
            (one, _DRIVEN.get(id(one), ()))
            for one, thread in _RUNNING
            if thread.is_alive()
        ]
    return {
        "flow": held[0][0].flow if held else "",
        "running": [
            {
                "flow": one.flow,
                "for": round(time.monotonic() - one.since),
                "agents": [
                    {
                        "called": each.id,
                        "cli": each.backend,
                        "model": each.config.model,
                        "effort": each.config.effort,
                        "service_tier": each.config.service_tier,
                        "account": each.config.provider
                        or "as this machine is signed in",
                        "may": each.config.permission,
                        "goals": each.config.goals,
                        "web_search": each.config.web_search,
                        "works": "here" if each.config.machine is None else "elsewhere",
                        "skills": [loaded.name for loaded in each.loaded],
                    }
                    for each in agents
                ],
            }
            for one, agents in held
        ],
    }


# What a report of a failure carries about the run it happened in: asked for only if one is
# ever made, and never otherwise. Registered once, here, because what it answers is what is
# running at the moment of the report rather than anything one run holds.
telemetry.about("flow", _about)
