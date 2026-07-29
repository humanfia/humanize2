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
from typing import TYPE_CHECKING, get_args, get_origin, get_type_hints

from humanize import backends

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from .agents import AgentBase


class NotAFlow(ValueError):  # noqa: N818  -- the name SPEC.md gives it
    """What a command line named, when it was not a flow for the agents it was given.

    Its own kind of error, so that a flow failing as it is imported -- one that reads a prompt
    file beside it and does not find it -- is left to fail as it would anywhere, rather than
    being reported as a command line to correct.
    """


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
    return tuple(name for name, person in _read(flow)[1] if not person)


def _read(
    flow: str | os.PathLike[str],
) -> tuple[
    Callable[..., None],
    tuple[tuple[str, bool], ...],
    Callable[..., tuple[AgentBase, ...]],
]:
    """Loads a flow and reads what it says about the agents it drives.

    Args:
      flow: The flow: one that came with humanize, by name, or a file of your own.

    Returns:
      Its entry point, one (name, is the person) per agent it drives, and what to hand those
      agents over as -- the named tuple the flow declared, or a plain one where it declared
      that.

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
        declared = (
            get_type_hints(run).get("agents") if inspect.isfunction(run) else None
        )
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
        kinds = getattr(declared, "__annotations__", {})
        return (
            run,
            tuple((at, _is_person(kinds.get(at))) for at in fields),
            declared._make,
        )
    # `tuple[AgentBase, ...]` is any number of them, which is no answer to the question.
    declares = get_args(declared)
    if run is None or get_origin(declared) is not tuple or Ellipsis in declares:
        raise NotAFlow(
            f"{flow}: a flow is a run(agents, task) whose agents are annotated with a "
            "tuple of a fixed length -- how many agents the flow drives -- or with a "
            "NamedTuple of them, which also says what each one is for"
        )
    return run, tuple(("", _is_person(kind)) for kind in declares), tuple


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
        return kind.rpartition(".")[2] == HumanAgent.__name__
    return kind is HumanAgent


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
        self, flow: str | os.PathLike[str], agents: Sequence[AgentBase]
    ) -> None:
        """Loads the flow and holds the agents to drive it with.

        Args:
          flow: The Python file the flow is written in. It is run to be read, so whatever it
            does as it is imported happens here, and fails here as it would anywhere.
          agents: The agents to hand it, as many as it declares.

        Raises:
          NotAFlow: If the file is not there, is not a flow -- nothing called ``run``, or one
            whose ``agents`` cannot be read or says nothing about how many it takes -- or is a
            flow that drives a different number of agents than were given.
        """
        from .agents import HumanAgent

        run, places, make = _read(flow)
        wanted = [name for name, person in places if not person]
        if len(wanted) != len(agents):
            raise NotAFlow(
                f"{flow}: run() drives {len(wanted)} agents, {len(agents)} given"
            )
        # The person at the prompt is made here rather than given: nobody chooses what they
        # run, so nothing upstream of this was ever asked about them.
        given = iter(agents)
        driven = [HumanAgent() if person else next(given) for _, person in places]
        for agent, (called, _) in zip(driven, places, strict=True):
            if called:
                agent.rename(called)
        self._run: Callable[[tuple[AgentBase, ...], str], None] = run
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

        Args:
          task: What the flow is to have its agents do.
        """
        from .cycle import Cycle

        with Cycle(self._flow, self._agents, task) as cycle:
            for agent in self._agents:
                agent.cycle = cycle
            self._run(self._agents, task)


def flow_and_agents(argv: list[str]) -> tuple[str, list[AgentBase], str]:
    """Reads an `hmz exec` line into a flow, the agents to drive it, and the task.

    A flow says how many agents it drives, and this is where they come from: one for each, in
    the order the flow takes them, at the model and effort each is to run at.

    Args:
      argv: What followed the command name.

    Returns:
      The flow's path, the agents to drive it with, and the task.

    Raises:
      SystemExit: If the line does not name a flow and an agent apiece, as argparse rejects it.
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
        required=True,
        dest="agents",
        metavar="CLI/MODEL:EFFORT",
        help="one agent, repeated once for each the flow drives, in the order it takes "
        "them; also written cli=CLI,model=MODEL,effort=EFFORT. CLI is one of "
        f"{', '.join(sorted(one.name for one in backends.PROFILES))}",
    )
    parser.add_argument(
        "task",
        help="what the flow is to have the agents do, after -- if it starts with a dash",
    )
    args = parser.parse_args(argv)

    # Only now that the line is known to name agents: `--help` has already exited, and it
    # should not have paid for three backends to say what it takes.
    from .agents import (
        ClaudeCodeAgent,
        ClaudeCodeAgentConfig,
        CodexAgent,
        CodexAgentConfig,
        KimiCodeCLIAgent,
        KimiCodeCLIAgentConfig,
    )

    built = {
        "claude": (ClaudeCodeAgent, ClaudeCodeAgentConfig),
        "codex": (CodexAgent, CodexAgentConfig),
        "kimi": (KimiCodeCLIAgent, KimiCodeCLIAgentConfig),
    }
    agents: list[AgentBase] = []
    for spec in args.agents:
        try:
            profile, model, effort = backends.read(spec)
        except ValueError as bad:
            parser.error(f"bad agent {spec!r}: {bad}")
        agent, config = built[profile.name]
        agents.append(agent(config(model=model, effort=effort)))
    return args.flow, agents, args.task
