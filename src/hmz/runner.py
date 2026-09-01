"""What starts a flow: the file it is in, the agents it takes, and the line naming both.

The line is read here rather than beside the command that carries it out, because the terminal
interface starts a flow from that same line and then keeps the agents -- which is what lets
something typed while the flow runs reach the one working. A reader that lived in the command
line would be one the interface had to reach up into.

What a flow is, and what it says it drives, is :mod:`hmz.flows`. This asks it, hands the flow
the agents it declared under the names it calls them, and writes the run down as a cycle.
Nothing a flow itself reaches for is here: a flow names one module of humanize's, and it is
not this one.
"""

from __future__ import annotations

import contextlib
import threading
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from hmz import backends

if TYPE_CHECKING:
    import os
    from collections.abc import Awaitable, Callable, Sequence

    from pydantic import BaseModel

    from .agents import AgentBase
    from .flows.driving import Entry

__all__ = ["Runner", "flow_and_agents", "read_agent", "set_up_from"]


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
        resume: str | os.PathLike[str] | None = None,
        container: str = "",
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
          resume: The cycle to pick up from, for a flow that says it can be picked up: the
            state that run left behind is what this one is handed. None is the last run of
            this flow here, which is what running a resumable flow again means -- a loop
            meant to run for a week is one that carries on where it stopped. A flow that
            says nothing about being resumable ignores this, having nowhere to put it.
          container: The image to run the whole of this in, or "" to run it on this machine.
            A convenience rather than a second way of saying where an agent works: it starts
            one container, points every agent of the run at it, and lets the flow's own code
            reach it through `hmz.flows.container()` -- which is what a run in a container
            is, said once from outside rather than agent by agent inside.

        Raises:
          NotAFlow: If the flow is not there, is not a flow -- nothing in it marked
            ``@flow()``, or one whose ``agents`` cannot be read or says nothing about how many
            it takes -- or is a
            flow that drives a different number of agents than were given, or one of them
            cannot run a moment the flow said that place has to, or was set up with something
            that is not what it asked for, or brings a skill from a repository that cannot be
            reached.
        """
        from .agents import HumanAgent
        from .cycle import resumed
        from .flows.driving import NotAFlow, carries, declares, lands, readies, set_up

        run, places, make, setting, mark = declares(flow)
        # Before anything is chosen or opened: an atlas whose body does not compile is a
        # flow refused where the run is set up rather than from inside one that has already
        # pulled an image and opened a cycle.
        readies(run)
        if config is not None:
            config = set_up(flow, setting, config)
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
            lands(flow, agent, place)
        # The person at the prompt is made here rather than given: nobody chooses what they
        # run, so nothing upstream of this was ever asked about them.
        given = iter(agents)
        driven = [HumanAgent() if place.person else next(given) for place in places]
        for agent, place in zip(driven, places, strict=True):
            if place.name:
                agent.rename(place.name)
        # What the flow works by, mounted onto every session these agents open. Before the
        # first turn, since a repository the flow named is fetched to get it: a run that
        # cannot reach one says so here rather than an hour into a loop.
        carries(flow, driven)
        self._run: Entry = run
        # Only for a flow that said it takes one, so that every flow written before there
        # was such a thing is still called with the two arguments it declares.
        self._config: BaseModel | None = config if setting is not None else None
        self._setting = setting
        # The drivers themselves, which is what the run is written down out of and what
        # whoever started the flow reaches for: the person the flow talks to is among them,
        # having been made here rather than chosen.
        self._driven = tuple(driven)
        self._agents_lock = threading.Lock()
        self._all_agents = list(self._driven)
        self._agent_watchers: list[Callable[[AgentBase], None]] = []
        self._stopping = False
        # And the same agents as the flow declared them: a flow whose agents are a NamedTuple
        # reaches them by name, and one that unpacks a plain tuple sees no difference.
        self._agents = make(driven)
        self._flow = str(
            flow
        )  # as it was named, which is what a run of it is named after
        #: Whether the flow says it can be picked up where the last run of it left off, and
        #: which run that was. Asked here rather than when the run starts, so that a cycle
        #: named at the prompt is one whoever named it hears about before anything runs.
        self._resumable = mark.resumable
        #: The image the whole run works in, or "" for a run on this machine. The container
        #: is started as the flow starts rather than here: constructing a runner reads a
        #: flow, and reading one must not pull an image.
        self._container = container
        self._picked_up: Path | None = None
        if self._resumable:
            self._picked_up = (
                Path(resume) if resume is not None else resumed(self._flow)
            )

    @property
    def agents(self) -> tuple[AgentBase, ...]:
        """Every agent this drives, in the order the flow takes them.

        Which is not what it was given: a flow that says it talks to the person is driving
        one more agent than anybody chose, and whatever is driving the flow has to reach
        that one too -- it is the one thing here that answers with what was typed.
        """
        with self._agents_lock:
            return tuple(self._all_agents)

    def watch_agents(self, listener: Callable[[AgentBase], None]) -> None:
        """Calls ``listener`` for each agent the flow adds while it is running.

        The agents declared by the flow are already available through :attr:`agents`; this
        watches only agents made later with :func:`hmz.flows.spawn`.
        """
        with self._agents_lock:
            self._agent_watchers.append(listener)

    def _joined(self, agents: tuple[AgentBase, ...]) -> None:
        """Makes newly spawned agents visible to controllers of this runner."""
        with self._agents_lock:
            self._all_agents.extend(agents)
            listeners = tuple(self._agent_watchers)
            stopping = self._stopping
        for agent in agents:
            for listener in listeners:
                # Watching a run is observational. A broken display callback must not turn a
                # successfully admitted agent into a failed flow.
                with contextlib.suppress(Exception):
                    listener(agent)
            if stopping:
                with contextlib.suppress(Exception):
                    agent.stop()

    def stop(self) -> None:
        """Stops every agent in this run, including ones it adds concurrently."""
        with self._agents_lock:
            self._stopping = True
            agents = tuple(self._all_agents)
        for agent in agents:
            with contextlib.suppress(Exception):
                agent.stop()

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

        from .cycle import Cycle, state
        from .flows.driving import contained, entered, lands_in, left
        from .settings import Settings

        # Written down as running before it is: what a flow calls is written down the same
        # way, so that whatever is watching reads one list of what is running under what,
        # rather than a flow it was told about and a flow it was not.
        started = entered(self._flow, self._driven)
        picked_up = self._picked_up
        with self._agents_lock:
            self._all_agents = list(self._driven)
        try:
            # One container for the run, started here rather than where the runner was made:
            # reading a flow must not pull an image, and a run that never starts must not
            # leave one behind. Every agent is pointed at it as it comes up, and what the
            # flow itself reads, writes and runs there is `hmz.flows.container`.
            with (
                contained(self._container) as where_,
                Cycle(
                    self._flow,
                    self._driven,
                    task,
                    resumable=self._resumable,
                    picked_up=picked_up.name if picked_up is not None else "",
                    # Whether this workspace asked for its runs to be profiled as well as
                    # traced, which is a thing about the project being worked on: a repository
                    # whose tests take an hour is a different question from one whose take a
                    # minute. Read here rather than in the cycle, which is the run written down
                    # rather than the settings under it.
                    profile=Settings().profiling,
                    joined=self._joined,
                ) as cycle,
            ):
                for agent in self._driven:
                    agent.cycle = cycle
                if where_ is not None:
                    lands_in(self._driven, where_)
                # As it was set up, or as it comes: a flow that takes a config takes None
                # for the run nobody set up, which is the default the flow declared. And
                # after it, for a flow that says it can be picked up, what the run it is
                # being picked up from left behind -- which is a dict it writes into, kept
                # in this run's own cycle as it writes.
                said: list[Any] = [self._agents, task]
                if self._setting is not None:
                    said.append(self._config)
                if self._resumable:
                    said.append(
                        cycle.state(
                            self._flow,
                            state(picked_up, self._flow)
                            if picked_up is not None
                            else None,
                        )
                    )
                running_now = self._run(*said)
                # Read off what the call answered rather than off the function: a flow is what
                # it does when it is called, and one wrapped in something of its own -- a
                # decorator that times its rounds -- is the same flow.
                if inspect.isawaitable(running_now):
                    _finished(running_now)
        finally:
            left(started)
            with self._agents_lock:
                # A Runner may be used for another run after this one unwinds. Keep the
                # stop request scoped to this run; the next run can admit fresh clones.
                self._stopping = False


def read_agent(
    spec: str,
) -> tuple[
    backends.Profile,
    str,
    str,
    str,
    str,
    str | None,
    bool | None,
    tuple[tuple[str, str], ...],
]:
    """Reads and validates one command-line agent specification.

    Args:
      spec: The short or written-out form accepted by ``-a``.

    Returns:
      The backend, model, effort, common service tier, provider, optional permission rung,
      whether it may search the web -- None where nobody said -- and backend-native
      ``config.KEY`` pairs.

    Raises:
      ValueError: If the specification is malformed or names no permission rung there is.
    """
    from .agents import PERMISSIONS, SERVICE_TIERS

    profile, model, effort, service_tier, provider, permission, searches, overrides = (
        backends.read(spec)
    )
    if service_tier not in SERVICE_TIERS:
        raise ValueError(
            f"service_tier must be one of {', '.join(SERVICE_TIERS)}, "
            f"not {service_tier!r}"
        )
    if permission is not None and permission not in PERMISSIONS:
        raise ValueError(
            f"permission must be one of {', '.join(PERMISSIONS)}, not {permission!r}"
        )
    return (
        profile,
        model,
        effort,
        service_tier,
        provider,
        permission,
        searches,
        overrides,
    )


def flow_and_agents(
    argv: list[str],
) -> tuple[str, list[AgentBase], str, dict[str, Any] | None, str]:
    """Reads an `hmz exec` line into a flow, the agents to drive it, the task, and its setup.

    A flow says how many agents it drives, and this is where they come from: one for each, in
    the order the flow takes them, at the model and effort each is to run at.

    Args:
      argv: What followed the command name.

    Returns:
      The flow's path, the agents to drive it with, the task, what to set the flow up with --
      the YAML file `-c` named, read but not yet checked against the flow's own model, or
      None where the line named none -- and the image to run the whole of it in, or "" for a
      run on this machine.

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
        "service_tier=SERVICE_TIER, permission=PERMISSION, web_search=on|off and "
        "backend-native config.KEY=VALUE. CLI is one of "
        f"{', '.join(sorted(one.name for one in backends.profiles()))}",
    )
    parser.add_argument(
        "-c",
        "--config",
        metavar="PATH",
        help="a YAML file of what to set the flow up with, one field per line, as the flow "
        "declares them; only for a flow that says it can be set up",
    )
    parser.add_argument(
        "--container",
        default="",
        metavar="IMAGE",
        help="run the whole of it in a container of this image: every agent's turns land "
        "there, the project directory is mounted at the path it already has, and the flow "
        "reaches it through hmz.flows.container()",
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
    from .agents import driver

    # A command-line agent has no picker to resolve a place's initial suggestion, so resolve
    # it here before constructing the config. Leave malformed or missing flows for Runner to
    # report in its usual place; their agents use the ordinary on default in the meantime.
    from .flows.driving import wanted

    try:
        places = wanted(args.flow)
    except Exception:  # noqa: BLE001 -- reading it is a convenience; running it is the report
        # Anything at all, because a flow is a Python file and reading one runs it: a flow
        # that opens a prompt beside it and does not find it raises whatever that raised, and
        # a line read for its goal defaults must not be where that lands. `Runner` loads it
        # again a moment later, in the one place that reports it as a line to correct.
        places = ()
    agents: list[AgentBase] = []
    for at, spec in enumerate(args.agents):
        try:
            (
                profile,
                model,
                effort,
                service_tier,
                provider,
                permission,
                searches,
                overrides,
            ) = read_agent(spec)
        except ValueError as bad:
            parser.error(f"bad agent {spec!r}: {bad}")
        agent, config = driver(profile.name)
        # Named rather than looked up: an account that is not there is caught by the agent
        # the first time it needs one, which says whose it was and what it was called.
        goals = places[at].goals_default if at < len(places) else True
        extra: dict[str, Any] = {"service_tier": service_tier}
        if permission is not None:
            extra["permission"] = permission
        if searches is not None:
            extra["web_search"] = searches
        if overrides and profile.name == "codex":
            extra["overrides"] = overrides
        elif overrides:
            extra["allowed_tools"] = tuple(value for _key, value in overrides)
        try:
            configured = config(
                model=model, effort=effort, provider=provider, goals=goals, **extra
            )
            agents.append(agent(configured))
        except ValueError as bad:
            parser.error(f"bad agent {spec!r}: {bad}")
    return args.flow, agents, args.task, held, args.container


def set_up_from(said: str | os.PathLike[str]) -> dict[str, Any]:
    """Reads what a flow is to be set up with out of a file of it.

    The file is what the flow menu would have asked, written down: one field per
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
