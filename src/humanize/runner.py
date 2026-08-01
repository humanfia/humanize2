"""What starts a flow: the file it is in, the agents it takes, and the line naming both.

The line is read here rather than beside the command that carries it out, because the terminal
interface starts a flow from that same line and then keeps the agents -- which is what lets
something typed while the flow runs reach the one working. A reader that lived in the command
line would be one the interface had to reach up into.
"""

from __future__ import annotations

import inspect
import os
import runpy
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

from humanize import backends

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Sequence

    from pydantic import BaseModel

    from .agents import AgentBase, Moment


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


class Place(NamedTuple):
    """One of the agents a flow drives, as the flow's own annotation declared it.

    Attributes:
      name: What the flow calls it, or "" for a flow that said how many it drives and no more.
      person: Whether it is the person at the prompt, who is handed over rather than chosen.
      moments: The moments the agent filling it has to run, which the flow said by writing
        `Annotated[AgentBase, Moment.PERMISSION_REQUEST]` where it declared the place. Empty
        where it asked for nothing in particular, which is most places.
    """

    name: str
    person: bool
    moments: frozenset[Moment]


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
      NotAFlow: If the file is not there, is not a flow -- nothing called `run`, or one whose
        `agents` cannot be read or says nothing about how many it takes.
    """
    from humanize.flows import find

    # Resolved here rather than by whoever is starting one, so that a name works wherever a
    # flow is named -- a command line, an interface, a `Runner` written by hand.
    flow = find(str(flow))
    # The same test `humanize.flows` applies, and for the same reason: a place that cannot
    # be read holds no flow, which `Path.is_file` would raise about rather than answer.
    if not os.path.isfile(flow):  # noqa: PTH113
        raise NotAFlow(f"{flow}: no Python file to read a flow from")
    run = runpy.run_path(str(flow)).get("run")
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
            f"{flow}: run()'s agents cannot be read here ({unresolved}) -- import what "
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
            f"{flow}: a flow is a run(agents, task) whose agents are annotated with a "
            "tuple of a fixed length -- how many agents the flow drives -- or with a "
            "NamedTuple of them, which also says what each one is for"
        )
    return (
        run,
        tuple(_place("", kind) for kind in declares),
        tuple,
        _setting(run, hinted),
    )


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
        raise NotAFlow(f"{flow}: run() takes no config, and one was given")
    if not isinstance(config, dict) and type(config).__name__ != setting.__name__:
        raise NotAFlow(
            f"{flow}: run() takes a {setting.__name__} to be set up with, not a "
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
    if get_origin(kind) is Annotated:
        kind = get_args(kind)[0]
    return Place(name=name, person=_is_person(kind), moments=moments)


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
          NotAFlow: If the file is not there, is not a flow -- nothing called ``run``, or one
            whose ``agents`` cannot be read or says nothing about how many it takes -- or is a
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
                f"{flow}: run() drives {len(asked)} agents, {len(agents)} given"
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

        with Cycle(self._flow, self._agents, task) as cycle:
            for agent in self._agents:
                agent.cycle = cycle
            if self._setting is None:
                running = self._run(self._agents, task)
            else:
                # As it was set up, or as it comes: a flow that takes a config takes None for
                # the run nobody set up, which is the default the flow itself declared.
                running = self._run(self._agents, task, self._config)
            # Read off what the call answered rather than off the function: a flow is what it
            # does when it is called, and one wrapped in something of its own -- a decorator
            # that times its rounds -- is the same flow.
            if inspect.isawaitable(running):
                _finished(running)


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
        metavar="PATH",
        help="the flow to drive: one that came with humanize, by name, or a file of your own",
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

    agents: list[AgentBase] = []
    for spec in args.agents:
        try:
            profile, model, effort, provider, permission = read_agent(spec)
        except ValueError as bad:
            parser.error(f"bad agent {spec!r}: {bad}")
        agent, config = DRIVEN[profile.name]
        # Named rather than looked up: an account that is not there is caught by the agent
        # the first time it needs one, which says whose it was and what it was called.
        configured = (
            config(model=model, effort=effort, provider=provider)
            if permission is None
            else config(
                model=model,
                effort=effort,
                provider=provider,
                permission=permission,
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
