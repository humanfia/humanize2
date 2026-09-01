"""What starts a flow: the file it is in, the agents it takes, and the line naming both.

The line is read here rather than beside the command that carries it out, because the terminal
interface starts a flow from that same line and then keeps the agents -- which is what lets
something typed while the flow runs reach the one working. A reader that lived in the command
line would be one the interface had to reach up into.

What a flow is, and what it says it drives, is :mod:`hmz.flows`. This asks it, hands the flow
the agents it declared under the names it calls them, and writes the run down as an epic.
Nothing a flow itself reaches for is here: a flow names one module of humanize's, and it is
not this one.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from hmz import backends

if TYPE_CHECKING:
    import os
    from argparse import ArgumentParser
    from collections.abc import Awaitable, Sequence

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
    import contextvars
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
    #
    # The context goes with it, since a thread is otherwise handed an empty one: what the run
    # was entered as is held there, and a flow that called another from a thread that had
    # never heard of the run would be a flow with no branch to be on.
    with ThreadPoolExecutor(max_workers=1, thread_name_prefix="humanize-flow") as apart:
        apart.submit(contextvars.copy_context().run, asyncio.run, flowing()).result()


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
          resume: The epic to pick up from, for a flow that says it can be picked up: the
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
        from .epic import resumed
        from .flows.driving import (
            NotAFlow,
            carries,
            declares,
            lands,
            readies,
            runs_at,
            serves,
            set_up,
        )

        run, places, make, setting, mark = declares(flow)
        # Before anything is chosen or opened: an atlas whose body does not compile is a
        # flow refused where the run is set up rather than from inside one that has already
        # pulled an image and opened an epic.
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
            serves(flow, agent, place)
            # Told what the whole run will be put in, because nothing is pointed at that
            # container until the run starts: a place needing somewhere remote must not be
            # refused here and then allowed when a flow called another inside the same run.
            lands(flow, agent, place, container=container)
            # And what the flow says this one may do, whether it has goals and whether it
            # reads the internet -- over whatever it was made with, because those three are
            # the flow's and nobody else's: whoever chose the agent chose a CLI, a model, an
            # effort and an account, and none of that says what the work is.
            runs_at(flow, agent, place)
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
        # And the same agents as the flow declared them: a flow whose agents are a NamedTuple
        # reaches them by name, and one that unpacks a plain tuple sees no difference.
        self._agents = make(driven)
        self._flow = str(
            flow
        )  # as it was named, which is what a run of it is named after
        #: Whether the flow says it can be picked up where the last run of it left off, and
        #: which run that was. Asked here rather than when the run starts, so that an epic
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
        return self._driven

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

        from .epic import Epic, state
        from .flows.driving import contained, entered, lands_in, left
        from .settings import Settings

        # Written down as running before it is: what a flow calls is written down the same
        # way, so that whatever is watching reads one list of what is running under what,
        # rather than a flow it was told about and a flow it was not.
        started = entered(self._flow, self._driven)
        picked_up = self._picked_up
        try:
            # One container for the run, started here rather than where the runner was made:
            # reading a flow must not pull an image, and a run that never starts must not
            # leave one behind. Every agent is pointed at it as it comes up, and what the
            # flow itself reads, writes and runs there is `hmz.flows.container`.
            with (
                contained(self._container) as where_,
                Epic(
                    self._flow,
                    self._driven,
                    task,
                    resumable=self._resumable,
                    picked_up=picked_up.name if picked_up is not None else "",
                    # Whether this workspace asked for its runs to be profiled as well as
                    # traced, which is a thing about the project being worked on: a repository
                    # whose tests take an hour is a different question from one whose take a
                    # minute. Read here rather than in the epic, which is the run written down
                    # rather than the settings under it.
                    profile=Settings().profiling,
                ) as epic,
            ):
                for agent in self._driven:
                    agent.epic = epic
                if where_ is not None:
                    lands_in(self._driven, where_)
                # As it was set up, or as it comes: a flow that takes a config takes None
                # for the run nobody set up, which is the default the flow declared. And
                # after it, for a flow that says it can be picked up, what the run it is
                # being picked up from left behind -- which is a dict it writes into, kept
                # in this run's own epic as it writes.
                said: list[Any] = [self._agents, task]
                if self._setting is not None:
                    said.append(self._config)
                if self._resumable:
                    said.append(
                        epic.state(
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


def read_agent(spec: str) -> tuple[str, backends.Profile, str, str, str]:
    """Reads and validates one command-line agent specification.

    The grammar itself is `hmz.backends.read`, an agent being a backend before it is anything
    else. This is the name the line's own reading of one goes by, kept because that is what
    the spec calls it -- and holding nothing of its own, since everything it used to check
    moved into the grammar when the written-out spelling went.

    Args:
      spec: One agent, as `-a` spells one. An `-a` naming several is split into them first.

    Returns:
      The place the agent fills -- "" for one the line left to fill a place in order -- the
      backend, model, effort and provider. What the agent may do, whether it has goals and
      whether it may search the web are not among them: those are the flow's, said where it
      declares the place, and a line that says one is a line to correct.

    Raises:
      ValueError: If the specification is malformed, or says what the flow says.
    """
    return backends.read(spec)


def flow_and_agents(
    argv: list[str],
) -> tuple[str, list[AgentBase], str, dict[str, Any] | None, bool]:
    """Reads an `hmz exec` line into a flow, the agents to drive it, the task, and its setup.

    A flow says how many agents it drives and what it calls each of them, and this is where
    they come from: one for each, at the model and effort each is to run at, in the order the
    flow takes them or each naming the place it fills.

    Args:
      argv: What followed the command name.

    Returns:
      The flow's path, the agents to drive it with in the order the flow takes them, the task,
      what to set the flow up with -- the YAML file `-c` named, read but not yet checked
      against the flow's own model, or None where the line named none -- and whether a program
      is reading the run rather than a person.

    Raises:
      SystemExit: If the line does not name a flow and an agent apiece, names a place the flow
        has not got, or names a config that cannot be read, as argparse rejects it.
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
        # One agent for each the flow drives, which for a flow that talks only to the person
        # at the prompt is none: the person is handed over rather than chosen, so a line that
        # named one would be naming what nobody picks. A line short of an agent the flow does
        # need is caught where every other miscount is, by the flow's own declaration.
        default=[],
        dest="agents",
        metavar="SPEC[,SPEC...]",
        help="the agents to drive the flow with, each [NAME=]CLI[@PROVIDER]/MODEL:EFFORT -- "
        "several to one option, separated by commas, and the option repeated as often as "
        "suits. Unnamed they fill the flow's places in the order it takes them; NAME fills "
        "the place the flow calls that, and either every one of them names a place or none "
        f"does. CLI is one of {', '.join(sorted(one.name for one in backends.profiles()))}",
    )
    parser.add_argument(
        "-c",
        "--config",
        metavar="PATH",
        help="a YAML file of what to set the flow up with, one field per line, as the flow "
        "declares them; only for a flow that says it can be set up",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="as_json",
        help="write the run as NDJSON on stdout -- one object per thing an agent says, "
        "flushed as it is said -- for a program to read instead of a person",
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

    agents: list[AgentBase] = []
    places: list[str] = []
    # The list is split here rather than where one agent is read: every `-a` on the line adds
    # to the same list, so what the line names is one list however it was typed -- and one
    # mistyped agent among three is then reported as itself rather than as all three.
    for spec in (one for said in args.agents for one in said.split(",")):
        try:
            place, profile, model, effort, provider = read_agent(spec)
        except ValueError as bad:
            parser.error(f"bad agent {spec!r}: {bad}")
        agent, config = driver(profile.name)
        try:
            # What it may do, whether it has goals and whether it may search the web are
            # left as they come: `Runner` settles all three from what the flow declared,
            # which is the one place any of them is said.
            configured = config(model=model, effort=effort, provider=provider)
            agents.append(agent(configured))
        except ValueError as bad:
            parser.error(f"bad agent {spec!r}: {bad}")
        places.append(place)
    return (
        args.flow,
        _as_declared(parser, args.flow, agents, places),
        args.task,
        held,
        args.as_json,
    )


def _as_declared(
    parser: ArgumentParser,
    flow: str,
    agents: list[AgentBase],
    places: list[str],
) -> list[AgentBase]:
    """Puts the agents in the order the flow takes them, for a line that named their places.

    A line that named none is in that order already, having been written in it. One that named
    them is read against what the flow declares here, before anything runs: an actor handed
    the reviewer's place is an hour of the wrong work, and which places there are is a
    question the flow answers without being given any agents at all.

    Args:
      parser: The line, for reporting one to correct.
      flow: The flow, as the line named it.
      agents: The agents, in the order the line named them.
      places: What each was named for, "" for one the line named no place for.

    Returns:
      The same agents, in the order the flow takes them.

    Raises:
      SystemExit: If some of them name a place and some do not, if the flow calls its agents
        nothing, or if the names are not one apiece of the ones it declares.
    """
    if not any(places):
        return agents
    if not all(places):
        parser.error(
            "name every agent or none of them: an agent that names no place fills the flow's "
            "next one, which cannot be counted while the others are filled by name"
        )
    from .flows.driving import NotAFlow, drives

    try:
        declared = drives(flow)
    except NotAFlow:
        # A flow that cannot be read is `Runner`'s to report and not this line's: reading one
        # here is for the names, and a line refused twice is refused in two voices.
        return agents
    if not declared:
        # A flow that has nobody to choose for it is a line with one agent too many, which
        # is a miscount like every other and `Runner`'s to report.
        return agents
    if not any(declared):
        parser.error(
            f"{flow} declares a plain tuple and calls the agents it drives nothing, so they "
            "are given in the order it takes them rather than by name"
        )
    for place in places:
        if place not in declared:
            parser.error(
                f"{flow} drives no agent called {place}; it drives {', '.join(declared)}"
            )
        if places.count(place) > 1:
            parser.error(
                f"{flow} drives one agent called {place}, and the line names "
                f"{places.count(place)}"
            )
    if unfilled := [one for one in declared if one not in places]:
        parser.error(
            f"{flow} also drives {', '.join(unfilled)}, which the line names nothing for"
        )
    held = dict(zip(places, agents, strict=True))
    return [held[one] for one in declared]


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
