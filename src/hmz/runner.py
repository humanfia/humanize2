"""What starts a flow: the file it is in, the agents it takes, and the line naming both.

The line is read here rather than beside the command that carries it out, because the terminal
interface starts a flow from that same line and then keeps the agents -- which is what lets
something typed while the flow runs reach the one working. A reader that lived in the command
line would be one the interface had to reach up into.
"""

from __future__ import annotations

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

from hmz import backends

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Sequence

    from pydantic import BaseModel

    from .agents import AgentBase, Isolated, Moment, Remote


#: How many arguments a flow's entry point takes when it says it can be set up with
#: something: the agents, the task, and the model that says what there is to set.
_WITH_A_CONFIG = 3

#: A flow's entry point: called with the agents and the task, and done when it returns --
#: or, for one written as `async def run`, when what it returns has been awaited. Which of
#: the two a flow is, is the flow's own business: `Runner.run` waits for it either way.
type Flow = Callable[..., Awaitable[None] | None]


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


def _entered(flow: str) -> Running:
    """Writes down that a flow has started, for whatever is watching the run.

    Args:
      flow: What it was asked for as.

    Returns:
      The record, to be handed back when it ends.
    """
    one = Running(flow, time.monotonic())
    with _TELLING:
        _RUNNING.append((one, threading.current_thread()))
    return one


def _left(one: Running) -> None:
    """Writes down that a flow has ended, however it ended.

    Args:
      one: What :func:`_entered` answered with.
    """
    with _TELLING:
        _RUNNING[:] = [held for held in _RUNNING if held[0] is not one]


class Place(NamedTuple):
    """One of the agents a flow drives, as the flow's own annotation declared it.

    Attributes:
      name: What the flow calls it, or "" for a flow that said how many it drives and no more.
      person: Whether it is the person at the prompt, who is handed over rather than chosen.
      moments: The moments the agent filling it has to run, which the flow said by writing
        `Annotated[AgentBase, Moment.PERMISSION_REQUEST]` where it declared the place. Empty
        where it asked for nothing in particular, which is most places.
      goal: Whether the flow runs this one under the backend's own goal feature, which it
        said by writing `Annotated[AgentBase, Goal]` where it declared the place. Only three
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
      is "" -- the count is all it said. A place it declared as a :class:`HumanAgent` is not
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
    return _read(flow)[3]


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
    return tuple(place for place in _read(flow)[1] if not place.person)


def _read(
    flow: str | os.PathLike[str],
) -> tuple[
    Flow,
    tuple[Place, ...],
    Callable[..., tuple[AgentBase, ...]],
    type[BaseModel] | None,
]:
    """Loads a flow and reads what it says about the agents it drives.

    Args:
      flow: The flow: one that came with humanize, by name, or a file of your own.

    Returns:
      Its entry point, one place per agent it drives, what to hand those agents over as --
      the named tuple the flow declared, or a plain one where it declared that -- and the
      model it can be set up with, or None where it takes no setting up.

    Raises:
      NotAFlow: If the file is not there, is not a flow -- nothing in it marked `@flow()`, or
        one whose `agents` cannot be read or says nothing about how many it takes.
    """
    from hmz.flows import find, inside, loaded

    # Which of the file's flows was asked for, before the name is resolved to a file: a file
    # may hold several, and `humanize1:gen-plan` is one of them.
    wanted = inside(str(flow))
    # Resolved here rather than by whoever is starting one, so that a name works wherever a
    # flow is named -- a command line, an interface, a `Runner` written by hand.
    flow = find(str(flow))
    # The same test `hmz.flows` applies, and for the same reason: a place that cannot
    # be read holds no flow, which `Path.is_file` would raise about rather than answer.
    if not os.path.isfile(flow):  # noqa: PTH113
        raise NotAFlow(f"{flow}: {_unfetched(str(flow))}")
    read = loaded(flow)
    run = _entry(read, wanted)
    if run is None:
        # A file that holds several flows names each of them after itself, so whoever asked
        # for the file alone -- or for one of them under a name it does not have -- is a
        # colon away from what they meant, and saying which ones is what ends it.
        holds = [f"{Path(flow).stem}:{one}" for one in _holds(read)]
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
            run,
            tuple(_place(at, kinds.get(at)) for at in fields),
            declared._make,
            _setting(run, hinted),
        )
    # `tuple[AgentBase, ...]` is any number of them, which is no answer to the question.
    declares = get_args(declared)
    if run is None or get_origin(declared) is not tuple or Ellipsis in declares:
        raise NotAFlow(
            f"{flow}: a flow is a function marked @flow() taking (agents, task), whose "
            "agents are annotated with a tuple of a fixed length -- how many agents the "
            "flow drives -- or with a NamedTuple of them, which also says what each is for"
        )
    return (
        run,
        tuple(_place("", kind) for kind in declares),
        tuple,
        _setting(run, hinted),
    )


def calls(flow: str | os.PathLike[str]) -> Flow:
    """One flow, ready for another flow to run: what it marked, found by name.

    A flow is a loop over agents, and a loop worth having is one another loop can reach for::

        from hmz.flows import flow
        from hmz.runner import calls

        @flow
        def run(agents: tuple[AgentBase, AgentBase], task: str) -> None:
            plan = calls("official/humanize1:gen-plan")
            plan(agents, f"plan this first: {task}")
            agents[0].new()(task)

    The name is the one `-f` takes -- `ralph_loop`, `official/rlar`, `humanize1:gen-plan`, a
    path of your own -- so a flow reaches another flow the way a person does, and a flowverse
    is a library as well as a menu.

    What comes back is the flow's own function, with the run written down around it: what is
    running is what the interface shows, and a flow that called another must not read as the
    flow that was started. It is called the way the flow itself is -- the agents, the task,
    and the config for one that says it takes one -- and answers with whatever the flow
    answers with, so a flow written as a coroutine is awaited by whoever called it::

        await calls("official/rlar")(agents, task)

    Args:
      flow: The flow to call, by the name `-f` takes.

    Returns:
      Something to call with the agents and the task.

    Raises:
      NotAFlow: If there is no such flow, or it is not one. Raised here rather than at the
        call, so that a flow which asks for another by a name that is wrong says so when it is
        asked for rather than an hour into a loop.
    """
    run, places, make, setting = _read(flow)
    named = str(flow)

    def calling(
        agents: Sequence[AgentBase],
        task: str,
        config: BaseModel | dict[str, Any] | None = None,
    ) -> Awaitable[None] | None:
        driven = _handed(named, places, make, agents)
        # Read back through the flow's own model, which is what refuses a config a flow does
        # not take and one it takes another of -- and what puts the settings through its own
        # validators at the moment it is about to run, exactly as a run of it does.
        given = None if config is None else _set_up(named, setting, config)
        settings = () if setting is None else (given,)
        started = _entered(named)
        _wrote(driven, "called", flow=named, task=task)
        try:
            answered = run(driven, task, *settings)
        except BaseException:
            _left(started)
            _wrote(driven, "returned", flow=named)
            raise
        if inspect.isawaitable(answered):
            # A flow written as a coroutine has not run yet: it is running while whoever
            # called it awaits it, so what says it is running has to last that long too.
            return _awaited(answered, driven, started, named)
        _left(started)
        _wrote(driven, "returned", flow=named)
        return None

    return calling


async def _awaited(
    answered: Awaitable[None],
    driven: tuple[AgentBase, ...],
    started: Running,
    named: str,
) -> None:
    """Waits for a called flow that is a coroutine, and writes down that it ended.

    Args:
      answered: What calling it gave back.
      driven: The agents it was called with, for the cycle to write to.
      started: What :func:`_entered` answered with.
      named: The flow, as it was asked for.
    """
    try:
        await answered
    finally:
        _left(started)
        _wrote(driven, "returned", flow=named)


def _handed(
    flow: str,
    places: tuple[Place, ...],
    make: Callable[..., tuple[AgentBase, ...]],
    agents: Sequence[AgentBase],
) -> tuple[AgentBase, ...]:
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
    from .agents import HumanAgent

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
        _lands(flow, agent, place)
    return make(driven)


def _wrote(driven: tuple[AgentBase, ...], event: str, **said: Any) -> None:
    """Writes one line about a called flow into the run's own record, where there is one.

    Through the agents rather than through anything of ours: the cycle belongs to the run that
    was started, the agents were handed it as it began, and a flow called from a `Runner` that
    opened none -- a flow run from a test, a flow called from a flow called from nothing --
    has nowhere to write and nothing to say.

    Args:
      driven: The agents the called flow was handed.
      event: What happened.
      said: What is worth saying about it.
    """
    # Asked what it is rather than taken as read: what an agent asks of a journal is that it
    # can be told a session was opened, and this is asking it for something else.
    from .cycle import Cycle

    for agent in driven:
        if isinstance(agent.cycle, Cycle):
            agent.cycle.write(event, **said)
            return


def _lands(flow: str | os.PathLike[str], agent: AgentBase, place: Place) -> None:
    """Settles where one agent's turns land, and refuses a machine the flow did not allow.

    Where an agent works is the flow's to say and not a setting anybody may reach for: a flow
    is written for one shape of work, and one whose agents read this project cannot have one
    of them reading somebody else's. So a place says nothing and its agent runs here, or says
    `Remote` and its agent may be pointed at a machine by whoever chose it, or says `Isolated`
    and the machine is the flow's own -- a container of the image it named, which nobody else
    has any say in.

    Args:
      flow: The flow, for what a refusal says.
      agent: The agent filling the place.
      place: What the flow declared.

    Raises:
      NotAFlow: If the agent was configured to work somewhere the flow does not put it, or if
        it has already opened a session, which is a conversation that cannot be moved.
    """
    from .agents import Isolated, isolated

    called = place.name or "the agent"
    if isinstance(place.where, Isolated):
        if agent.config.machine is not None:
            raise NotAFlow(
                f"{flow}: {called} works in a container of this flow's own, so there is "
                "nothing to point it at"
            )
        try:
            agent.runs_on(isolated(place.where.image))
        except RuntimeError as opened:
            raise NotAFlow(f"{flow}: {called} {opened}") from opened
        return
    if place.where is None and agent.config.machine is not None:
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
    from hmz.flows import flowverses

    whose, _, rest = named.partition("/")
    for verse in flowverses():
        if verse.name == whose and rest and not verse.fetched:
            return (
                f"the {whose} flowverse has not been fetched yet -- open /flow and press "
                "ctrl+r on it"
            )
    return "no Python file to read a flow from"


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
    from hmz.flows import Flow

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
    from hmz.flows import Flow

    said = (getattr(one, "__humanize_flow__", None) for one in inside.values())
    return [one.name for one in said if isinstance(one, Flow) and one.name]


def _set_up(
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


def _setting(run: Flow, hinted: dict[str, object]) -> type[BaseModel] | None:
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


def _kinds(declared: type, run: Flow) -> dict[str, object]:
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
    from .agents import Isolated, Remote

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
    from .agents import Goal

    if get_origin(kind) is not Annotated:
        return False
    return any(said is Goal for said in get_args(kind)[1:])


def _goals_default(kind: object) -> bool:
    """The initial on/off choice a flow suggests for this agent's goals.

    The suggestion is picker metadata, not runtime policy. The picker resolves it into the
    boolean on `AgentConfig` before constructing the agent.
    """
    from .agents import AgentDefaults

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
    from .agents import Moment

    if get_origin(kind) is not Annotated:
        return ()
    return tuple(said for said in get_args(kind)[1:] if isinstance(said, Moment))


def _is_person(kind: object) -> bool:
    """Whether a place in a flow's agents is the person at the prompt.

    Args:
      kind: What the flow annotated that place with, which is the class itself, or its name
        where the flow put its annotations off until they are asked for.

    Returns:
      True if it is a `HumanAgent`, which is a place nobody is asked to configure.
    """
    from .agents import HumanAgent

    if isinstance(kind, str):
        # Read by the word it names rather than by what that word means, which is all there
        # is to go on: the first thing inside an `Annotated[...]` is the type it is about.
        said = kind.removeprefix("Annotated[").split(",")[0].strip()
        return said.rpartition(".")[2] == HumanAgent.__name__
    return kind is HumanAgent


def _finished(running: Awaitable[None]) -> None:
    """Runs a flow that is a coroutine, until it returns.

    A flow may be written as ``async def run``, which is how one drives many agents at once:
    the loop is the flow's own, started here and closed when the flow returns, so that a flow
    which awaits nothing and one which awaits ten thousand turns are both just run. Starting
    the flow is the same call either way -- whatever is driving one is driving a flow, not an
    event loop, and none of them has to know which kind it took.

    Args:
      running: The flow, as the coroutine calling it made.
    """
    import asyncio
    from concurrent.futures import ThreadPoolExecutor

    async def flowing() -> None:
        # A coroutine of our own around it: `asyncio.run` takes one of those, and what a
        # flow answered with is whatever awaiting it is spelled as where the flow was written.
        await running

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        asyncio.run(flowing())  # nothing is turning here, which is the ordinary way in
        return
    # Started from a thread that is already running a loop of its own -- an interface, a test.
    # A flow cannot be run on that one: it would be the flow waiting for turns that are
    # waiting for the loop the flow is holding, which is a run that never takes its first.
    with ThreadPoolExecutor(max_workers=1, thread_name_prefix="humanize-flow") as apart:
        apart.submit(asyncio.run, flowing()).result()


class Runner:
    """A flow, loaded from a file and handed the agents it was written for.

    A flow is a Python file with a ``run(agents: tuple[...], task: str)`` in it, and the tuple
    is how many agents it drives -- the one thing about a flow that cannot be read off the
    command line starting it. Checking it before anything runs is what keeps a two-agent flow
    started with one agent from failing on an unpacking hours into a loop, with a turn's work
    already behind it. A flow that declares a NamedTuple instead has also said what each of
    its agents is for, and they are called that from here on.
    """

    def __init__(
        self,
        flow: str | os.PathLike[str],
        agents: Sequence[AgentBase],
        config: BaseModel | dict[str, Any] | None = None,
    ) -> None:
        """Loads the flow and holds the agents to drive it with.

        Args:
          flow: The Python file the flow is written in. It is run to be read, so whatever it
            does as it is imported happens here, and fails here as it would anywhere.
          agents: The agents to hand it, as many as it declares.
          config: What it was set up with, for a flow that says it can be -- an instance of
            the model :func:`configures` answers with, or the fields to build one from, which
            is what a YAML file of them reads as. None is a flow left as it comes, and is
            what a flow that takes no setting up is given either way.

        Raises:
          NotAFlow: If the file is not there, is not a flow -- nothing in it marked
            ``@flow()``, or one whose ``agents`` cannot be read or says nothing about how many
            it takes -- or is a
            flow that drives a different number of agents than were given, or one of them
            cannot run a moment the flow said that place has to, or was set up with something
            that is not what it asked for.
        """
        from .agents import HumanAgent

        run, places, make, setting = _read(flow)
        if config is not None:
            config = _set_up(flow, setting, config)
        asked = [place for place in places if not place.person]
        if len(asked) != len(agents):
            raise NotAFlow(
                f"{flow}: the flow drives {len(asked)} agents, {len(agents)} given"
            )
        # Before the first turn, for the reason the count is: a flow that hangs a hook on a
        # moment its agent does not run would otherwise find out hours into a loop, from a
        # hook that raised where it was hung rather than from the line that chose the agent.
        for agent, place in zip(agents, asked, strict=True):
            if short := place.moments - type(agent).moments:
                raise NotAFlow(
                    f"{flow}: {place.name or 'the agent'} has to run "
                    f"{', '.join(sorted(short))}, which {agent.backend} does not"
                )
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
            _lands(flow, agent, place)
        # The person at the prompt is made here rather than given: nobody chooses what they
        # run, so nothing upstream of this was ever asked about them.
        given = iter(agents)
        driven = [HumanAgent() if place.person else next(given) for place in places]
        for agent, place in zip(driven, places, strict=True):
            if place.name:
                agent.rename(place.name)
        self._run: Flow = run
        # Only for a flow that said it takes one, so that every flow written before there
        # was such a thing is still called with the two arguments it declares.
        self._config: BaseModel | None = config if setting is not None else None
        self._setting = setting
        # As the flow declared them: a flow whose agents are a NamedTuple reaches them by
        # name, and one that unpacks a plain tuple sees no difference.
        self._agents = make(driven)
        self._flow = str(
            flow
        )  # as it was named, which is what a run of it is named after

    @property
    def agents(self) -> tuple[AgentBase, ...]:
        """Every agent this drives, in the order the flow takes them.

        Which is not what it was given: a flow that says it talks to the person is driving
        one more agent than anybody chose, and whatever is driving the flow has to reach
        that one too -- it is the one thing here that answers with what was typed.
        """
        return tuple(self._agents)

    def run(self, task: str) -> None:
        """Runs the flow in this directory, for as long as it keeps running.

        The run is written down as it happens: which agents were driven, at what, and which
        sessions each of them opened. Nothing else knows a session was part of a run -- the
        backends log them one by one, under ids of their own -- and the run is over the moment
        this returns, however it returns.

        A flow written as ``async def run`` is run to its return here too, on a loop of its
        own: this waits for the flow either way, so that whatever started one is holding a
        run rather than a coroutine somebody has to remember to await.

        Args:
          task: What the flow is to have its agents do.
        """
        import inspect

        from .cycle import Cycle

        # Written down as running before it is: what a flow calls is written down the same
        # way, so that whatever is watching reads one list of what is running under what,
        # rather than a flow it was told about and a flow it was not.
        started = _entered(self._flow)
        try:
            with Cycle(self._flow, self._agents, task) as cycle:
                for agent in self._agents:
                    agent.cycle = cycle
                if self._setting is None:
                    running_now = self._run(self._agents, task)
                else:
                    # As it was set up, or as it comes: a flow that takes a config takes None
                    # for the run nobody set up, which is the default the flow declared.
                    running_now = self._run(self._agents, task, self._config)
                # Read off what the call answered rather than off the function: a flow is what
                # it does when it is called, and one wrapped in something of its own -- a
                # decorator that times its rounds -- is the same flow.
                if inspect.isawaitable(running_now):
                    _finished(running_now)
        finally:
            _left(started)


def read_agent(
    spec: str,
) -> tuple[backends.Profile, str, str, str, str | None]:
    """Reads and validates one command-line agent specification.

    Args:
      spec: The short or written-out form accepted by ``-a``.

    Returns:
      The backend, model, effort, provider and optional permission rung.

    Raises:
      ValueError: If the specification is malformed or names no permission rung there is.
    """
    from .agents import PERMISSIONS

    parsed = backends.read(spec)
    permission = parsed[-1]
    if permission is not None and permission not in PERMISSIONS:
        raise ValueError(
            f"permission must be one of {', '.join(PERMISSIONS)}, not {permission!r}"
        )
    return parsed


def flow_and_agents(
    argv: list[str],
) -> tuple[str, list[AgentBase], str, dict[str, Any] | None]:
    """Reads an `hmz exec` line into a flow, the agents to drive it, the task, and its setup.

    A flow says how many agents it drives, and this is where they come from: one for each, in
    the order the flow takes them, at the model and effort each is to run at.

    Args:
      argv: What followed the command name.

    Returns:
      The flow's path, the agents to drive it with, the task, and what to set the flow up
      with -- the YAML file `-c` named, read but not yet checked against the flow's own
      model, or None where the line named none.

    Raises:
      SystemExit: If the line does not name a flow and an agent apiece, or names a config
        that cannot be read, as argparse rejects it.
    """
    import argparse

    parser = argparse.ArgumentParser(
        prog="hmz exec", description="Run an agent flow in this directory."
    )
    parser.add_argument(
        "-f",
        "--flow",
        required=True,
        metavar="FLOW",
        help="the flow to drive: one humanize ships or a flowverse holds, by name, or a file "
        "of your own; `<flow>:<name>` for one of several in a file",
    )
    parser.add_argument(
        "-a",
        "--agent",
        action="append",
        # Once for each agent the flow drives, which for a flow that talks only to the person
        # at the prompt is none: the person is handed over rather than chosen, so a line that
        # named one would be naming what nobody picks. A line short of an agent the flow does
        # need is caught where every other miscount is, by the flow's own declaration.
        default=[],
        dest="agents",
        metavar="CLI/MODEL:EFFORT",
        help="one agent, repeated once for each the flow drives, in the order it takes "
        "them; also written cli=CLI,model=MODEL,effort=EFFORT with optional "
        "permission=PERMISSION. CLI is one of "
        f"{', '.join(sorted(one.name for one in backends.PROFILES))}",
    )
    parser.add_argument(
        "-c",
        "--config",
        metavar="PATH",
        help="a YAML file of what to set the flow up with, one field per line, as the flow "
        "declares them; only for a flow that says it can be set up",
    )
    parser.add_argument(
        "task",
        help="what the flow is to have the agents do, after -- if it starts with a dash",
    )
    args = parser.parse_args(argv)
    held = None
    if args.config is not None:
        try:
            held = set_up_from(args.config)
        except ValueError as why:
            parser.error(str(why))

    # Only now that the line is known to name agents: `--help` has already exited, and it
    # should not have paid for three backends to say what it takes.
    from .agents import DRIVEN

    # A command-line agent has no picker to resolve a place's initial suggestion, so resolve
    # it here before constructing the config. Leave malformed or missing flows for Runner to
    # report in its usual place; their agents use the ordinary on default in the meantime.
    try:
        places = wanted(args.flow)
    except NotAFlow:
        places = ()
    agents: list[AgentBase] = []
    for at, spec in enumerate(args.agents):
        try:
            profile, model, effort, provider, permission = read_agent(spec)
        except ValueError as bad:
            parser.error(f"bad agent {spec!r}: {bad}")
        agent, config = DRIVEN[profile.name]
        # Named rather than looked up: an account that is not there is caught by the agent
        # the first time it needs one, which says whose it was and what it was called.
        goals = places[at].goals_default if at < len(places) else True
        configured = (
            config(model=model, effort=effort, provider=provider, goals=goals)
            if permission is None
            else config(
                model=model,
                effort=effort,
                provider=provider,
                permission=permission,
                goals=goals,
            )
        )
        agents.append(agent(configured))
    return args.flow, agents, args.task, held


def set_up_from(said: str | os.PathLike[str]) -> dict[str, Any]:
    """Reads what a flow is to be set up with out of a file of it.

    The file is what `/config` would have been walked through, written down: one field per
    line, under the names the flow declared. It is not checked here -- the flow's own model
    is what checks it, and the model is not there until the flow is loaded.

    Args:
      said: The path to the YAML.

    Returns:
      What it holds, field by field, and nothing at all for a file that is empty.

    Raises:
      ValueError: If the file cannot be read, or holds something that is not a mapping.
    """
    import yaml

    try:
        held = yaml.safe_load(Path(said).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as why:
        raise ValueError(f"cannot read {said}: {why}") from why
    if held is None:
        return {}
    if not isinstance(held, dict):
        raise ValueError(  # noqa: TRY004 -- a file to correct, not a caller's type error
            f"{said}: a flow is set up from a mapping, not a {type(held).__name__}"
        )
    return cast("dict[str, Any]", held)
