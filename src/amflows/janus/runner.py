"""What starts a flow: the file it is written in, and the agents it says it takes."""

from __future__ import annotations

import inspect
import os
import runpy
from collections.abc import Callable, Sequence
from typing import TYPE_CHECKING, get_args, get_origin, get_type_hints

if TYPE_CHECKING:
    from .agents import AgentBase


class NotAFlow(ValueError):
    """What a command line named, when it was not a flow for the agents it was given.

    Its own kind of error, so that a flow failing as it is imported -- one that reads a prompt
    file beside it and does not find it -- is left to fail as it would anywhere, rather than
    being reported as a command line to correct.
    """


def drives(flow: str | os.PathLike[str]) -> int:
    """How many agents a flow says it drives.

    Read without being given any, so that a caller can ask before it has them -- which is
    what choosing the agents for a flow means.

    Args:
      flow: The Python file the flow is written in. It is run to be read.

    Returns:
      How many agents its entry point declares.

    Raises:
      NotAFlow: If the file is not there, or is not a flow.
    """
    return _read(flow)[1]


def _read(flow: str | os.PathLike[str]) -> tuple[Callable[..., None], int]:
    """Loads a flow and reads how many agents it declares.

    Args:
      flow: The flow: one that came with amflows, by name, or a file of your own.

    Returns:
      Its entry point, and how many agents that entry point drives.

    Raises:
      NotAFlow: If the file is not there, is not a flow -- nothing called `run`, or one whose
        `agents` cannot be read or says nothing about how many it takes.
    """
    from amflows.janus.flows import find

    # Resolved here rather than by whoever is starting one, so that a name works wherever a
    # flow is named -- a command line, an interface, a `Runner` written by hand.
    flow = find(str(flow))
    if not os.path.isfile(flow):
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
    # `tuple[AgentBase, ...]` is any number of them, which is no answer to the question.
    declares = get_args(declared)
    if get_origin(declared) is not tuple or Ellipsis in declares:
        raise NotAFlow(
            f"{flow}: a flow is a run(agents, task) whose agents are annotated with a "
            "tuple of a fixed length -- how many agents the flow drives"
        )
    assert run is not None
    return run, len(declares)


class Runner:
    """A flow, loaded from a file and handed the agents it was written for.

    A flow is a Python file with a ``run(agents: tuple[...], task: str)`` in it, and the tuple
    is how many agents it drives -- the one thing about a flow that cannot be read off the
    command line starting it. Checking it before anything runs is what keeps a two-agent flow
    started with one agent from failing on an unpacking hours into a loop, with a turn's work
    already behind it.
    """

    def __init__(self, flow: str | os.PathLike[str], agents: Sequence[AgentBase]):
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
        run, drives = _read(flow)
        if drives != len(agents):
            raise NotAFlow(f"{flow}: run() drives {drives} agents, {len(agents)} given")
        self._run: Callable[[tuple[AgentBase, ...], str], None] = run
        self._agents = tuple(agents)

    def run(self, task: str) -> None:
        """Runs the flow in this directory, for as long as it keeps running.

        Args:
          task: What the flow is to have its agents do.
        """
        self._run(self._agents, task)
