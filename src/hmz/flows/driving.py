"""What a flow declares, what it brings, and how one is run by another.

A flow is a Python file, and the only thing it has to say about itself is what it drives: how
many agents, what each is for, what each has to be able to do and where each may work. That is
read here, off the annotation on the entry point, so that whatever is starting a flow -- a
command line, the flow picker, another flow -- can put the right questions before anything
runs. A flow given the wrong number of agents, or one that cannot run a moment the flow hangs
a hook on, is refused where it was written down rather than hours into a loop.

And a loop worth having is one another loop can reach for, which is :func:`load`: a flow
found by the same name `-f` takes, handed the agents the calling flow was given, carrying its
own skills and its own kept state, and written down -- in a record of its own, inside the
record of the flow that called it -- as running under whatever called it.

A run of flows calling flows is a tree rather than a list, and it is tracked as one. Each
flow says which flow called it, and which that was is read off the task the call was made
from rather than off the process: a flow written as a coroutine may gather two calls at once,
those two run at the same moment on one thread, and neither of them is under the other. So a
call made from inside either lands under the one it was made from, a session opened inside it
is written into that one's record, and what is running, read from inside a flow, is the
branch that flow is on and not everything the run happens to be doing.

Nothing here reads a command line and nothing here opens an epic: :mod:`hmz.runner` does both,
and asks this what the flow it was named says about itself. A call asks the epic already open
for a record to be written into, which is not a second epic: it is part of the one run.
"""

from __future__ import annotations

import contextlib
import contextvars
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
    from collections.abc import Awaitable, Callable, Generator, Mapping, Sequence

    from pydantic import BaseModel

    from hmz.agents import (
        AgentBase,
        AgentConfig,
        AgentDefaults,
        Isolated,
        Moment,
        Needs,
        Remote,
    )
    from hmz.agents.base import Journal
    from hmz.agents.skills import Loaded
    from hmz.epic import Epic, Sub
    from hmz.machines import MachineBase, MachineConfig, Mapped

    from . import Flow as Marked
    from .agent import Agent, Driven

__all__ = [
    "Entry",
    "NotAFlow",
    "Place",
    "Running",
    "carries",
    "comes_to",
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
    "runs_at",
    "serves",
    "set_up",
    "wanted",
]


#: How many arguments a flow's entry point takes when it says it can be set up with
#: something: the agents, the task, and the model that says what there is to set.
_WITH_A_CONFIG = 3

#: A flow's entry point: called with the agents and the task, and done when it returns --
#: or, for one written as `async def run`, when what it returns has been awaited. Which of
#: the two a flow is, is the flow's own business: `Runner.run` waits for it either way.
type Entry = Callable[..., Awaitable[None] | None]


class NotAFlow(ValueError):  # noqa: N818  -- the name the SPEC gives it
    """What a command line named, when it was not a flow for the agents it was given.

    Its own kind of error, so that a flow failing as it is imported -- one that reads a prompt
    file beside it and does not find it -- is left to fail as it would anywhere, rather than
    being reported as a command line to correct.
    """


class Running(NamedTuple):
    """One flow that is running now, on the branch of the run it is running on.

    Attributes:
      flow: What it was asked for as -- the name a command line gave, or the one a flow asked
        another for, which is the name worth showing either way.
      since: When it started, on the monotonic clock.
      depth: How far down the calls it is: 0 for the flow somebody started, one more for each
        flow that had to be called to reach it.
      under: The flow that called it, or None for the one somebody started. What makes a run
        a tree rather than a list: two flows gathered at once run at the same moment and
        neither of them is under the other, so only the flow each was called from can say
        where it belongs.
    """

    flow: str
    since: float
    depth: int = 0
    under: Running | None = None


class _Held(NamedTuple):
    """One flow of a run, as whatever is watching the run needs it.

    Attributes:
      one: What it is, and what called it.
      thread: The thread `entered` was called on, which is what says it is still there.
      agents: What it is being driven with, for a report of a failure in it.
    """

    one: Running
    thread: threading.Thread
    agents: Sequence[Agent]


#: Every flow running now, in the order they started: the one somebody ran, then whatever any
#: of them called, each beside the thread it was entered on and the agents it drives. Kept
#: here rather than asked of the flows, which is the one thing a flow cannot be asked -- it is
#: a Python file and may branch any way it likes -- and read by the interface to say what is
#: running under what.
#:
#: Flat, with the shape carried by the records themselves: each one says what called it. It
#: cannot be a stack, because a flow written as a coroutine may have two calls going at once
#: on one thread and neither of those is under the other. Keyed by the identity of the record
#: `entered` made, so that what goes with a flow goes when that flow does: a crash in the
#: interface an hour after a flow ended must not be filed as a crash in that flow, and a flow
#: that called another must not have the called one's agents put under its name.
#:
#: Under a lock, since a flow runs on whichever thread took it and the interface reads while
#: they run.
_RUNNING: dict[int, _Held] = {}
_TELLING = threading.Lock()

#: The flow this task is inside, which is the branch a call made from here goes on. A context
#: variable rather than one slot for the thread or for the process: `asyncio` copies the
#: context into every task it starts, so two flows gathered at once each get one of their own
#: and a third called from either lands under the one that called it rather than under
#: whichever of them happened to start last. A thread that is not running a flow -- an
#: interface drawing a status line, a turn taken on a thread of its own -- has none, and
#: reads the whole of the above instead.
_ON: contextvars.ContextVar[Running | None] = contextvars.ContextVar(
    "hmz_flow_running", default=None
)


def running() -> tuple[Running, ...]:
    """Every flow running now: the branch this is asked from, or all of them from outside.

    Asked from inside a flow -- by the flow's own code, by a hook it hung, by a callback an
    agent reached for -- it answers with the branch that flow is on: the one somebody
    started, then each flow that was called to get here, innermost last. That is what a flow
    can truthfully be told, and the only thing a flow gathering two calls at once can be:
    the sibling running beside it is not running under it and is none of its business.

    Asked from outside one -- the interface drawing a status line, a report being written --
    it answers with every flow of the run, oldest first, each saying how deep it is and what
    called it. A run is a tree, and from outside there is no branch to be on.

    A flow says it has ended as it ends, however it ends -- but only a flow that got the
    chance to. One whose thread has gone was abandoned where it stood rather than finished:
    an interface taken down under it, a test that let go of it. So what is running is checked
    against the threads running it, and a flow with no thread left is not one of them.

    Returns:
      One apiece. Empty where nothing is running.
    """
    with _TELLING:
        for key in [
            key for key, held in _RUNNING.items() if not held.thread.is_alive()
        ]:
            del _RUNNING[key]
        here = _ON.get()
        if here is None:
            return tuple(held.one for held in _RUNNING.values())
        branch = list[Running]()
        while here is not None:
            branch.append(here)
            here = here.under
        # Only the ones still running: a branch is read off records that hold each other,
        # and one whose thread has gone was pruned above rather than left to be reported.
        # A branch with nothing left on it is nothing running here, and never everything
        # running anywhere -- what a flow must not be handed is its siblings.
        return tuple(one for one in reversed(branch) if id(one) in _RUNNING)


def entered(flow: str, agents: Sequence[Agent] = ()) -> Running:
    """Writes down that a flow has started here, under whatever called it here.

    Under whatever called it *in this task*, which is what makes a run a tree: a called flow
    runs on the branch of the flow that called it, and two called at once run on two branches
    of it. What this task is inside is written down as well as answered with, so that a flow
    called from inside this one lands under it.

    Args:
      flow: What it was asked for as.
      agents: What it is being driven with, for a report of a failure in it.

    Returns:
      The record, to be handed back when it ends.
    """
    under = _ON.get()
    one = Running(
        flow, time.monotonic(), 0 if under is None else under.depth + 1, under
    )
    with _TELLING:
        _RUNNING[id(one)] = _Held(one, threading.current_thread(), agents)
    _ON.set(one)
    return one


def left(one: Running) -> None:
    """Writes down that a flow has ended, however it ended.

    What this task is inside goes back to whatever called that flow, rather than to a token
    taken when it started: a flow written as a coroutine is entered where the call was
    written and left inside the task that ran it, and those are two contexts -- while the
    branch it was on is the same one read from either.

    Args:
      one: What :func:`entered` answered with.
    """
    with _TELLING:
        _RUNNING.pop(id(one), None)
    if _ON.get() is one:
        _ON.set(one.under)


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
      where: Where the agent filling it may work, which the flow said the same way -- `Remote`
        for one that may be pointed at another machine, an `Isolated` for one that works in a
        container the flow itself names the image of. None for a place the flow said nothing
        about, which runs here and may not be sent anywhere: a flow is written for a shape of
        work, and where its agents work is the flow's to say rather than a setting somebody
        reaches for.
      permission: What the agent filling it may do without being asked, which the flow said
        with `AgentDefaults(permission=...)` beside the place. `bypass` for a place that said
        nothing, which is the loosest rung there is and so settles nothing: what an agent
        already carries is never loosened to reach one of these.
      goals: Whether the backend's own goal feature is available to it, said the same way.
        A place run under a `Goal` has them, whatever else it wrote.
      web_search: Whether it may search the web, said the same way.
      needs: What filling this place takes, which the flow said by writing
        `Annotated[Agent, Needs("steer", where=("isolated",))]` where it declared it -- what
        the backend has to serve, and what the machine its turns land on has to come to.
        None for a place the flow said nothing about, which is most of them: what every
        backend serves and every machine holds is nothing a flow has to ask for.
    """

    name: str
    person: bool
    moments: frozenset[Moment]
    where: type[Remote] | Remote | Isolated | None = None
    goal: bool = False
    permission: str = "bypass"
    goals: bool = True
    web_search: bool = True
    needs: Needs | None = None


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
    pulled an image and opened an epic.

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
    if (loaded := _brought(flow)) is None:
        return
    for agent in agents:
        _settles(agent).loads(loaded)


def _brought(flow: str | os.PathLike[str]) -> tuple[Loaded, ...] | None:
    """The skills one flow works by, read off the flow as it is on disk now.

    Worked out rather than mounted, so that what a called flow is to carry can be settled
    before the call takes the agents: a call that is refused between the two must not leave
    the flow that made it driving agents carrying somebody else's skills.

    Args:
      flow: The flow, as it was named.

    Returns:
      One apiece, or None for a flow that says nothing about skills at all -- which is a
      flow that leaves the agents carrying whatever they carry rather than one that empties
      them.

    Raises:
      NotAFlow: If a repository the flow names cannot be reached.
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
        return None
    try:
        return tuple(brought(where, declared))
    except OSError as unreachable:
        raise NotAFlow(f"{flow}: {unreachable}") from unreachable


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


def _carried(
    flow: str, agents: Sequence[Agent], *, inherit: bool
) -> list[tuple[Loaded, ...]]:
    """What each agent is to carry inside a called flow, worked out before the call takes it.

    Args:
      flow: The flow being called, as it was asked for.
      agents: The agents it is being handed, carrying the calling flow's own.
      inherit: Whether what they carry now stays reachable inside the call, after the called
        flow's own and only where the names do not collide.

    Returns:
      One tuple apiece, in the order the agents were given.
    """
    child = _brought(flow)
    if child is None:
        # A flow that says nothing about skills leaves them as they are, which is what a run
        # of such a flow does too.
        return [agent.loaded for agent in agents]
    if not inherit:
        return [child for _ in agents]
    named = {one.name for one in child}
    return [
        child + tuple(one for one in agent.loaded if one.name not in named)
        for agent in agents
    ]


class _Claim(NamedTuple):
    """One call's hold on one agent, for as long as that call runs.

    Attributes:
      on: The branch the call is on, which is what says whether two claims are one under the
        other or two beside each other.
      record: Where that call is written down, or None for a call nobody is keeping a record
        of.
      skills: What the called flow works by, which its agents carry while it runs.
      config: What that call settled the agent to run as: the rung it may work at, its
        goals and its searching. The person at the prompt's is what it already was, that
        being a place a flow says none of these about.
    """

    on: Running
    record: Sub | None
    skills: tuple[Loaded, ...]
    config: AgentConfig


class _Claimed(NamedTuple):
    """One agent, as it was before any call took it and as the calls that have it want it.

    Attributes:
      was: Where it was writing before the first of them took it.
      carried: What it was carrying then.
      ran: What it was set up as then, which is what it goes back to once every call that
        took it has let go.
      held: Every call that has it now, in the order they took it.
    """

    was: Journal | None
    carried: tuple[Loaded, ...]
    ran: AgentConfig
    held: list[_Claim]


#: Which calls have each agent now, by the agent's own identity. An agent belongs to the run
#: rather than to any one flow of it, and a called flow points it at that call's own record
#: and that flow's own skills for as long as the call lasts -- so what it was before has to
#: be kept somewhere, and a swap remembered by whoever swapped it is a swap two calls going
#: at once put back in the wrong order.
#:
#: Read and written under `_TELLING`, beside what is running, since the two answer one
#: question: which flow this agent is working for now.
_CLAIMED: dict[int, _Claimed] = {}

#: Where each flow of a run is writing, by the identity of its record. What a call made from
#: inside a flow is written under, which is the flow's own record and not the agents': an
#: agent two calls have at once is writing where both of them were called from, and a third
#: flow called from inside one of those belongs under that one.
_WRITTEN: dict[int, Sub | None] = {}


def _beneath(one: Running, of: Running) -> bool:
    """Whether one flow is the other, or is running somewhere under it.

    Args:
      one: The flow being asked about.
      of: The flow it may be running under.

    Returns:
      True where it is, which is what makes two claims on one agent a nesting rather than a
      pair of siblings.
    """
    at: Running | None = one
    while at is not None:
        if at is of:
            return True
        at = at.under
    return False


def _points(agent: Agent, claimed: _Claimed) -> None:
    """Points one agent at where the calls that have it agree it is working.

    One call has it: that call's record and that flow's skills, which is a called flow being
    driven as a run of it would be. Two calls that are one under the other: the inner one's,
    which is the same thing said twice. Two calls beside each other -- a flow that gathered
    two calls sharing the agents it was handed -- and neither of them may have it: what a
    session opened by that agent is part of is the flow they were both called from, and
    writing it into whichever of them started last would be filing it under a flow that
    happened to be there. A flow that wants a branch of its own writes down the agents for
    it, which is what `drives` and `Agent.clone` are for.

    Which is the flow they were both called from and not the run: the fork may be five flows
    down, and an agent dropped all the way back to the run's own record would be filed under
    a flow that was not even in the room. So it is the deepest call holding this agent that
    every one of them is running under -- and only where the fork is the run's own flow, which
    holds nothing, does that come back to what the agent was before any of them took it.

    Args:
      agent: The agent.
      claimed: What it was, and what has it now.
    """
    deep = sorted(claimed.held, key=lambda one: one.on.depth, reverse=True)
    # The innermost, where the calls holding it are a chain -- a flow that called a flow.
    if all(_beneath(deep[0].on, one.on) for one in claimed.held):
        found = deep[0]
    else:
        # Otherwise the fork: the deepest of them that all of them are running under.
        found = next(
            (
                each
                for each in deep
                if all(_beneath(one.on, each.on) for one in claimed.held)
            ),
            None,
        )
    if found is None:
        agent.epic, skills = claimed.was, claimed.carried
        runs = claimed.ran
    else:
        agent.epic, skills = found.record, found.skills
        runs = found.config
    _settles(agent).loads(skills)
    if agent.config != runs:
        # What it may do, whether it has goals and whether it reads the internet: the call
        # holding it said them, and a call that has ended said them no longer. Nothing here
        # can be refused -- every one of these was accepted on the way in.
        _settles(agent).reconfigure(runs)


def _takes(
    driven: Sequence[Agent],
    started: Running,
    record: Sub | None,
    skills: Sequence[tuple[Loaded, ...]],
    runs: Sequence[AgentConfig],
) -> None:
    """Hands the agents to a call: its record to write into, its flow's skills to carry.

    Args:
      driven: The agents the called flow was handed.
      started: What :func:`entered` answered with.
      record: Where the call is written down, or None for one nobody is keeping a record of.
      skills: What each of the agents is to carry, in the order they were given.
      runs: What each of them was set up as before this call, in the same order.
    """
    with _TELLING:
        _WRITTEN[id(started)] = record
        for agent, carrying, was in zip(driven, skills, runs, strict=True):
            held = _CLAIMED.setdefault(
                id(agent), _Claimed(agent.epic, agent.loaded, was, [])
            )
            held.held.append(_Claim(started, record, carrying, agent.config))
            _points(agent, held)


def _gives_back(driven: Sequence[Agent], started: Running) -> Sub | None:
    """Hands the agents back as the call found them, and answers with the call's record.

    However the call ended, and whichever order two calls going at once end in: what an agent
    goes back to is what it was before any call took it rather than what the call that is
    ending happened to see, which two ending out of order would put back as each other's.

    Args:
      driven: The agents the called flow was handed.
      started: What :func:`entered` answered with.

    Returns:
      Where the call was written down, or None for one nobody kept a record of.
    """
    with _TELLING:
        record = _WRITTEN.pop(id(started), None)
        for agent in driven:
            held = _CLAIMED.get(id(agent))
            if held is None:
                continue
            held.held[:] = [one for one in held.held if one.on is not started]
            if held.held:
                _points(agent, held)
                continue
            del _CLAIMED[id(agent)]
            agent.epic = held.was
            _settles(agent).loads(held.carried)
            if agent.config != held.ran:
                _settles(agent).reconfigure(held.ran)
    return record


def _writes(driven: Sequence[Agent]) -> Epic | None:
    """The record the flow running here writes to, which is what a call of its own goes under.

    Read off the branch this task is on rather than off the agents it is driving. An agent two
    calls have at once is writing where both of them were called from, and a third flow called
    from inside one of those belongs under that one rather than under what the two share.

    The flow nobody called keeps no record of its own here -- it writes the run's, which
    whatever opened the run handed to the agents *it* started with. Those, and not the ones
    this call is being made with: a branch driving agents of its own, which is what `drives`
    and `Agent.clone` hand it, would otherwise be a branch that could not find the run it is
    part of and would be written down nowhere, along with everything under it.

    Args:
      driven: The agents the call is being made with, for a call from a thread with no branch
        on it: one made from a tool a turn reached for, or from outside any flow at all.

    Returns:
      The record, or None for a call from a flow nothing is keeping a record of -- one run
      from a test, one called from nothing.
    """
    from hmz.epic import Epic

    at = _ON.get()
    if at is None:
        # No branch to read: a call made from a thread that is not running a flow -- a tool
        # a turn reached for, which is the flow's own code on somebody else's thread. What
        # the agents are writing to now is then the only thing that knows.
        return next(
            (one for one in (each.epic for each in driven) if isinstance(one, Epic)),
            None,
        )
    over: Sequence[Agent] = driven
    with _TELLING:
        while at is not None:
            if id(at) in _WRITTEN:
                return _WRITTEN[id(at)]
            if (held := _RUNNING.get(id(at))) is not None and held.agents:
                over = held.agents
            at = at.under
        # What the agents of the outermost flow were handed as the run began -- and what they
        # are still writing to unless a call has them, which is what was kept when it did.
        was = [
            _CLAIMED[id(one)].was if id(one) in _CLAIMED else one.epic for one in over
        ]
    return next((one for one in was if isinstance(one, Epic)), None)


#: How deep one flow calling another goes before the next call is refused. A `load` chain has
#: no natural bottom -- a flow may call itself, and one that decides how deep to go from its
#: own config or from what a model said may decide wrong -- and what an unbounded one comes to
#: is a `RecursionError` out of whatever the innermost call happened to be importing, which
#: names no flow and blames the wrong line. High enough that no chain anybody writes on
#: purpose reaches it, low enough to be reached long before the interpreter's own limit is.
_DEEPEST = 64


def _deep(flow: str) -> None:
    """Refuses a call from a chain of flows that has gone deeper than one goes.

    Args:
      flow: The flow being called, as it was asked for.

    Raises:
      NotAFlow: If calling it would be deeper than :data:`_DEEPEST` flows down.
    """
    at = _ON.get()
    if at is None or at.depth + 1 <= _DEEPEST:
        return
    walked = " > ".join(one.flow for one in running()[-3:])
    raise NotAFlow(
        f"{flow}: called {at.depth + 1} flows deep, and a chain of flows calling flows "
        f"goes {_DEEPEST} -- a flow with no bottom to it is a flow to correct, and this "
        f"one reached here through … > {walked}"
    )


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

    A call may also say what the flow it is calling runs at, which is `drives`: a mapping
    from the name the called flow gives one of its places -- or the name of the agent filling
    it -- to the config that branch is to be driven at::

        await asyncio.gather(
            load("official/rlar")(agents, task),
            load("official/rlar")(agents, task, drives={"actor": careful}),
        )

    What each of those is handed is a clone at that config rather than the agent set up
    again: an agent is what it was made as, so two efforts are two agents. They are the
    call's own -- written into the call's own record, carrying the called flow's skills --
    which is also what makes two calls gathered at once two branches with nothing shared
    between them.

    Each call is written down as the run of a flow it is. The record of the flow that called
    it gets a line saying so -- one record per call, named for the flow and for this call of
    it -- and what the called flow opens, keeps and calls in turn goes there rather than into
    the record of whatever started the run. So a flow calling a flow calling a flow reads
    back as the tree it ran as, however deep it went and however many of it ran at once. The
    record that called it says `called` and `returned` with the filename, at both ends,
    because two calls going at once end in an order nothing can pair by.

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

    def calling(
        agents: Sequence[Agent],
        task: str,
        config: BaseModel | dict[str, Any] | None = None,
        *,
        drives: Mapping[str, AgentConfig] | None = None,
    ) -> Awaitable[None] | None:
        # Read afresh, which is what makes a flow rewritten since the last call the flow that
        # runs now: a flow is a directory, and reading one is running its entry point.
        run, places, make, setting, mark = declares(flow)
        driven = _handed(named, places, make, agents, drives)
        # Read back through the flow's own model, which is what refuses a config a flow does
        # not take and one it takes another of -- and what puts the settings through its own
        # validators at the moment it is about to run, exactly as a run of it does. Before the
        # skills below, because a refusal here is a call that never happened: a caller that
        # catches it -- to try another config, or to go on without this flow -- must not be
        # left driving agents that are carrying the skills of a flow that never ran.
        given = None if config is None else set_up(named, setting, config)
        settings = () if setting is None else (given,)
        # And refused where a chain of them has no bottom, for the same reason and in the
        # same breath: before anything has been taken, carried or written down.
        _deep(named)
        if _awaits(run):
            # Nothing is taken until the flow itself starts. A coroutine has not run when it
            # is made -- one gathered and then cancelled before its first step never runs at
            # all -- so a call written down as started by the making of it would be a call
            # nothing ever ends, holding agents nothing ever hands back. It is also where
            # the branch has to be taken: `asyncio` copies the context into the task that
            # runs it, and two gathered at once are two tasks with a context apiece.
            return _running(
                run,
                driven,
                named,
                places,
                task,
                settings,
                resumable=mark.resumable,
                inherit=inherit_skills,
            )
        started, held = _begins(
            named,
            places,
            driven,
            task,
            resumable=mark.resumable,
            inherit=inherit_skills,
        )
        try:
            answered = run(driven, task, *settings, *held)
        except BaseException as why:
            _ended(driven, started, type(why))
            raise
        if inspect.isawaitable(answered):
            # A flow that is not a coroutine function and answered with something to await
            # all the same -- one wrapped in a decorator of its own, a compiled atlas. It
            # runs while whoever called it awaits it, so what says it is running has to last
            # that long too, and the branch goes back to the caller until it does: here is
            # the caller, and two of these gathered at once share it.
            _ON.set(started.under)
            return _awaited(answered, driven, started)
        _ended(driven, started)
        return None

    return calling


def _awaits(run: Entry) -> bool:
    """Whether a flow is one that has to be awaited, asked before it is called rather than after.

    Asked beforehand because a coroutine flow must be written down as started where it starts
    rather than where it was made, and what it was made by is the only thing there is to ask
    at that point. A flow that is not one of these and answers with something to await anyway
    -- one wrapped in a decorator of its own -- is left to be found out by the answer.

    Args:
      run: The flow's entry point.

    Returns:
      True where calling it gives back a coroutine.
    """
    if inspect.iscoroutinefunction(run):
        return True
    # A flow that is an object rather than a function, which is what a compiled atlas is.
    called = getattr(run, "__call__", None)  # noqa: B004 -- asked of it, not called
    return called is not None and inspect.iscoroutinefunction(called)


def _begins(
    named: str,
    places: tuple[Place, ...],
    driven: tuple[Agent, ...],
    task: str,
    *,
    resumable: bool,
    inherit: bool,
) -> tuple[Running, tuple[Any, ...]]:
    """Puts a call on the branch it runs on, and takes the agents for it.

    Args:
      named: The flow being called, as it was asked for.
      places: What it declared, which is what says how its agents run while it has them.
      driven: The agents it is being handed.
      task: What it was called with.
      resumable: Whether it says it can be picked up again.
      inherit: Whether the calling flow's skills stay reachable inside it.

    Returns:
      What :func:`entered` answered with, and what the flow is to be called with after the
      task and its settings.

    Raises:
      NotAFlow: If one of the agents cannot be told what the flow says its place runs at.
    """
    # Where it is written down, which is under the flow running here rather than under
    # whatever the agents happen to be writing to: two calls sharing one agent leave it
    # writing where they were both called from, and a third called from inside one of them
    # belongs under that one.
    under = _writes(driven)
    # What it left behind last time, for a flow that says it can be picked up: kept under its
    # own name in the epic of the run that called it, since a flow that called another is two
    # flows and neither writes the other's.
    held = () if not resumable else (_holding(under, named),)
    # And the skills it works by, which are the flow's rather than the agents': a called flow
    # brings its own, mounted onto whatever sessions it opens, and hands the agents back as
    # it found them so that the flow which called it goes on carrying its own.
    carrying = _carried(named, driven, inherit=inherit)
    started = entered(named, driven)
    try:
        # A record of its own to write into, in the epic of the run that called it: a called
        # flow opens sessions and calls flows of its own, and what it did is its own rather
        # than a run's that happened to start it.
        writing = _opened(under, driven, named, task, resumable=resumable)
        # And what it says its agents may do, whether they have goals and whether they read
        # the internet, which are the called flow's for the length of the call: they are
        # handed back as they came, as they are with the skills and the record.
        were = _settled(named, places, driven)
        _takes(driven, started, writing, carrying, were)
    except BaseException:
        # A record that could not be opened is a call that never started: leaving it on the
        # branch would put every later call of this task under a flow that is not running.
        left(started)
        raise
    return started, held


async def _running(
    run: Entry,
    driven: tuple[Agent, ...],
    named: str,
    places: tuple[Place, ...],
    task: str,
    settings: tuple[Any, ...],
    *,
    resumable: bool,
    inherit: bool,
) -> None:
    """Runs a flow written as a coroutine, taking its agents where it actually starts.

    Args:
      run: The flow's entry point.
      driven: The agents it was called with.
      named: The flow, as it was asked for.
      places: What it declared.
      task: What it was called with.
      settings: What it was set up with, or nothing for a flow that takes none.
      resumable: Whether it says it can be picked up again.
      inherit: Whether the calling flow's skills stay reachable inside it.
    """
    started, held = _begins(
        named, places, driven, task, resumable=resumable, inherit=inherit
    )
    try:
        # Asked of the answer all the same: what says it has to be awaited is what it was
        # written as, and a flow is what it does when it is called.
        if inspect.isawaitable(answered := run(driven, task, *settings, *held)):
            await answered
    except BaseException as why:
        # Cancellation among them: a task taken down mid-await unwinds through here, which
        # hands its agents back, closes its record and takes it off the branch -- and does so
        # at every level, each level being a task or a frame of its own.
        _ended(driven, started, type(why))
        raise
    _ended(driven, started)


async def _awaited(
    answered: Awaitable[None],
    driven: tuple[Agent, ...],
    started: Running,
) -> None:
    """Waits for a flow that answered with something to await, and writes down that it ended.

    The branch is taken here rather than where the call was written, for the reason a
    coroutine flow's is: it is here that the flow is actually running, and here is a task of
    its own where a sibling was gathered beside it.

    Args:
      answered: What calling it gave back.
      driven: The agents it was called with.
      started: What :func:`entered` answered with.
    """
    _ON.set(started)
    try:
        await answered
    except BaseException as why:
        _ended(driven, started, type(why))
        raise
    _ended(driven, started)


def _opened(
    under: Epic | None,
    driven: tuple[Agent, ...],
    named: str,
    task: str,
    *,
    resumable: bool,
) -> Sub | None:
    """Opens the record a called flow is written to, inside the record that called it.

    Args:
      under: The record of the flow making the call, or None for a call from a flow nobody is
        keeping a record of -- one run from a test, one called from nothing.
      driven: The agents the called flow was handed.
      named: The flow, as it was asked for.
      task: What it was called with.
      resumable: Whether it says it can be picked up again.

    Returns:
      The record, or None where there is nowhere to write.
    """
    if under is None:
        return None
    # Cast because a flow sees its agents through `Agent`, which says what a flow may ask
    # of one and nothing about what it was configured with -- and what a record says it
    # was driven by is exactly that. They are the run's own agents either way.
    return under.called(
        named, cast("Sequence[AgentBase]", driven), task, resumable=resumable
    )


def _ended(
    driven: tuple[Agent, ...],
    started: Running,
    kind: type[BaseException] | None = None,
) -> None:
    """Writes down that a called flow has ended, and hands its agents back as they came.

    Args:
      driven: The agents it was called with.
      started: What :func:`entered` answered with.
      kind: What was raised out of the called flow, if anything.
    """
    if (record := _gives_back(driven, started)) is not None:
        record.ended(kind)
    left(started)


def _handed(
    flow: str,
    places: tuple[Place, ...],
    make: Callable[..., tuple[Agent, ...]],
    agents: Sequence[Agent],
    drives: Mapping[str, AgentConfig] | None = None,
) -> tuple[Agent, ...]:
    """The agents a called flow is handed, as the tuple that flow declared.

    A flow is called with what it drives, so a caller hands over as many agents as the flow
    declares -- and may hand over one fewer where the flow talks to the person, since the
    person is made rather than chosen. Nothing is renamed: the agents belong to the flow that
    was started, and a name changed under it would change what the run has already been
    written down as.

    A caller may say what a place of the called flow is to be driven at, and what fills that
    place is then a clone at that config -- a second agent rather than this one set up again,
    since what an agent is is settled where it is made. It is checked exactly as the agent it
    replaces would have been: a config that puts a place somewhere the flow does not is
    refused where the call was written.

    Args:
      flow: The flow being called, for what a refusal says.
      places: What it declared.
      make: What to build its agents as -- the named tuple it declared, or a plain one.
      agents: What the caller handed over.
      drives: What to drive one or more of its places at, by the name the called flow gives
        the place or the name of the agent filling it, or None to drive them all as they come.

    Returns:
      The agents, as the flow declared them.

    Raises:
      NotAFlow: If that is the wrong number of them, if one of them cannot run a moment the
        flow says that place has to, if one of them does not serve what the flow says that
        place needs, if one is somewhere the flow does not put it, or if `drives` names
        something the flow does not drive.
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
    if drives:
        driven = _differently(flow, places, driven, drives)
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
        serves(flow, agent, place)
        lands(flow, agent, place)
    return make(driven)


def _settled(
    flow: str,
    places: tuple[Place, ...],
    driven: Sequence[Agent],
) -> tuple[AgentConfig, ...]:
    """Sets every agent of a called flow up as that flow says its places run.

    Args:
      flow: The flow being called, for what a refusal says.
      places: What it declared.
      driven: The agents it is being called with, in the order it declared them.

    Returns:
      What each of them was set up as before this, in the same order, to be handed back when
      the call ends -- the person among them left alone, who takes no turn a rung means
      anything about.

    Raises:
      NotAFlow: If one of them cannot be told what the flow says its place runs at. The ones
        settled before it are put back first: a call that never happened must leave the flow
        that tried it driving the agents it had, exactly as a refused config does.
    """
    were: list[AgentConfig] = []
    try:
        for agent, place in zip(driven, places, strict=True):
            were.append(agent.config if place.person else runs_at(flow, agent, place))
    except NotAFlow:
        for agent, was in zip(driven, were, strict=False):
            if agent.config != was:
                _settles(agent).reconfigure(was)
        raise
    return tuple(were)


def _differently(
    flow: str,
    places: tuple[Place, ...],
    driven: Sequence[Agent],
    drives: Mapping[str, AgentConfig],
) -> list[Agent]:
    """The agents of a call that said what one of its places is to be driven at.

    A clone apiece rather than the agents set up again, because that is what an agent set up
    differently is: an agent is what it was made as, and two efforts are two agents. Each
    carries what the one it stands in for carries and is named nothing, which is what tells
    a comparison of two efforts from one agent that changed its mind.

    Args:
      flow: The flow being called, for what a refusal says.
      places: What it declared, which is what its places are called.
      driven: The agents it would have been handed.
      drives: What to drive one or more of those places at.

    Returns:
      The agents to hand over, the clones among them.

    Raises:
      NotAFlow: If it names something the flow does not drive, something two of its places
        answer to, or the person at the prompt -- who runs nothing anybody chose and so has
        nothing to be driven at.
    """
    from hmz.agents import HumanAgent

    made = list(driven)
    where: dict[str, int | None] = {}
    for at, agent in enumerate(made):
        # None for a name two places answer to -- one agent handed to a flow twice, two named
        # the same -- since what a caller meant by it is then not a thing to guess at.
        where[agent.id] = None if agent.id in where else at
    # The called flow's own names over the agents' own: a caller says what the flow it is
    # calling is to drive its reviewer at, and what the flow it was handed calls that agent
    # is the caller's business rather than the callee's.
    for at, place in enumerate(places):
        if place.name:
            where[place.name] = at
    for name, config in drives.items():
        if name in where and where[name] is None:
            raise NotAFlow(
                f"{flow}: two of the agents it is being handed are called {name!r}, so "
                "which of them is to be driven at that is not a thing to work out"
            )
        at = where.get(name)
        if at is None:
            raise NotAFlow(
                f"{flow}: nothing it drives is called {name!r} -- it drives "
                f"{', '.join(place.name or 'an agent' for place in places)}"
            )
        if isinstance(made[at], HumanAgent):
            raise NotAFlow(
                f"{flow}: {name} is the person at the prompt, who takes no turn anywhere "
                "and so runs nothing to be driven at"
            )
        made[at] = made[at].clone(config=config)
    return made


def _holding(under: Epic | None, named: str) -> dict[str, Any]:
    """The dict a called flow that can be picked up writes what it wants back into.

    Kept in the epic of the run that called it, under the called flow's own name: a flow
    that called another is two flows, each with its own to keep, and both of them part of one
    run. A call from a flow that opened no epic -- one run from a test, one called from
    nothing -- is handed a dict that is nowhere, which is a flow that runs and leaves nothing
    rather than a call that fails.

    Found through the flow making the call rather than through the agents it is handing over,
    for the reason the record is: a branch driving agents of its own would otherwise leave
    nothing behind and be picked up as a run that never happened.

    Args:
      under: The record the flow making the call is writing, which is what holds the epic.
      named: The called flow, as it was asked for.

    Returns:
      What it left behind last time, as something to write this time's into.
    """
    from hmz.epic import resumed, state

    if under is None:
        return {}
    at = resumed(named, under.workspace)
    return under.state(named, state(at, named) if at is not None else None)


def serves(flow: str | os.PathLike[str], agent: Agent, place: Place) -> None:
    """Refuses an agent whose backend does not serve what the flow says its place takes.

    Before the first turn, for the reason a moment the place hangs a hook on is checked
    before it: a flow built on a turn that can be talked to while it runs, or on one held to
    a shape, finds out from the call that reached for it otherwise -- hours into a loop,
    rather than from the line that chose the agent. So it is asked of the driver class and of
    what is written down about the CLI, neither of which needs an agent to have opened
    anything, and a flow that cannot be driven by what it was handed says so at once.

    Args:
      flow: The flow, for what a refusal says.
      agent: The agent filling the place.
      place: What the flow declared.

    Raises:
      NotAFlow: If the backend does not serve something the place says it has to.
    """
    if place.needs is None or not place.needs.of_agent:
        return
    if short := place.needs.of_agent - comes_to(agent.backend):
        raise NotAFlow(
            f"{flow}: {place.name or 'the agent'} has to serve "
            f"{', '.join(sorted(short))}, which {agent.backend} does not"
        )


def comes_to(backend: str) -> frozenset[str]:
    """What one backend serves, by the names a flow asks for it under.

    Read out of the one catalogue rather than off the driver classes again: what a flow may
    build on -- the shape a turn can be held to, the tools it may be offered, the word put
    into a turn already running, the goal feature, the fork, each moment outside the ones
    every backend reaches -- is already read off those classes there, and a second reading
    here would be a second place for it to be wrong. What the catalogue leaves to the
    backend's own facts is read where those are written down, which is the same profile it
    reads.

    By name rather than by agent, so that whoever is *choosing* an agent can ask before there
    is one: the picker rules a CLI out for a place it could not fill, and a run refuses one
    that was handed over anyway, and both are asking this one question.

    Args:
      backend: The coding agent, named as a command line names it.

    Returns:
      The names it serves. What every backend here serves is in it too: the catalogue names
      no backend against those because they are true of all of them, and a place that asked
      for one would otherwise be refused every agent there is.
    """
    from hmz.backends import named

    from .checking import catalogue

    comes = {
        one.name for one in catalogue() if not one.backends or backend in one.backends
    }
    profile = named(backend)
    return frozenset(comes if profile is None else comes | profile.tags())


def lands(
    flow: str | os.PathLike[str],
    agent: Agent,
    place: Place,
    *,
    container: str = "",
) -> None:
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
      container: The image the whole run works in, for a run put in one from outside, or ""
        for a run on this machine. Named rather than read off the agent because the container
        is started where the run starts and nothing is pointed at it until then: a place that
        needs somewhere remote would otherwise be refused at the top of a run that is about
        to put every agent of it somewhere remote, and allowed inside that same run when a
        flow called another. It is one question, so it is asked of one answer.

    Raises:
      NotAFlow: If the agent was configured to work somewhere the flow does not put it, if
        where it works does not come to what the flow says that place needs, or if it has
        already opened a session, which is a conversation that cannot be moved.
    """
    from hmz.agents import Isolated, isolated

    called = place.name or "the agent"
    if isinstance(place.where, Isolated):
        if agent.config.machine is not None:
            raise NotAFlow(
                f"{flow}: {called} works in a container of this flow's own, so there is "
                "nothing to point it at"
            )
        # Against the container this flow named, and before the agent is put in it: a call
        # that is refused must leave the flow which made it driving the agents it had, and
        # one whose place had already been moved would hand back an agent pointed somewhere.
        box = isolated(place.where.image)
        _somewhere(flow, called, box, place)
        try:
            _settles(agent).runs_on(box)
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
    _somewhere(flow, called, agent.config.machine or _run_in(container), place)


def _run_in(image: str) -> MachineConfig | None:
    """The machine a run put in a container from outside will be working in.

    Built rather than started: what a container comes to is its settings' to answer, and
    reading a flow must not pull an image.

    Args:
      image: The image the whole run works in, or "" for a run on this machine.

    Returns:
      The settings every agent of that run will be pointed at, or None for a run here.
    """
    from hmz.agents import isolated

    return isolated(image) if image else None


def _somewhere(
    flow: str | os.PathLike[str],
    called: str,
    machine: MachineConfig | None,
    place: Place,
) -> None:
    """Refuses a place whose machine does not come to what the flow says the work takes.

    Asked of the machine's settings and never of a machine, which is the whole reason those
    settings answer it: a flow whose work has to happen somewhere isolated must be refusable
    before an image has been pulled, and one whose work has to happen on Linux before a
    connection has been made. What only the machine itself can settle it does not claim --
    the platform of somebody else's machine is read from the handshake, and a machine that
    turns out not to be what its settings promised fails as it starts -- so nothing here
    waits on anything being up.

    Args:
      flow: The flow, for what a refusal says.
      called: What the flow calls the place.
      machine: The settings the work would land under, or None for this machine.
      place: What the flow declared.

    Raises:
      NotAFlow: If those settings do not come to something the place says it needs. An agent
        pointed nowhere works on this machine, which comes to nothing at all, so a place that
        needs anything of where it works needs a machine first.
    """
    if place.needs is None or not place.needs.where:
        return
    at: frozenset[str] = machine.capabilities if machine is not None else frozenset()
    if short := place.needs.where - at:
        raise NotAFlow(
            f"{flow}: {called} has to work somewhere that comes to "
            f"{', '.join(sorted(short))}, which "
            f"{'the machine it works on' if machine is not None else 'this machine'} "
            "does not"
        )


def runs_at(flow: str | os.PathLike[str], agent: Agent, place: Place) -> AgentConfig:
    """Settles what one agent may do, whether it has goals and whether it reads the internet.

    The three things a flow says about the work rather than about the agent, and the flow is
    the only one that says them: whoever chose the agent chose a CLI, a model, an effort and
    an account, and a rung typed there would be somebody outside the flow deciding what the
    flow's reviewer is allowed to rewrite. So a place carries them, and this is where they
    reach the agent -- before its first turn, over whatever it was constructed with.

    Tighter only, never looser. A place that declares nothing declares the loosest of each --
    `bypass`, goals on, the web readable -- and what an agent already carries is never
    loosened to reach it, so a flow declaring nothing runs its agents at exactly what they
    came with. It is the same rule that makes a call safe: a flow running at `read-only` that
    called one which declared nothing would otherwise run that one at `bypass`, and calling a
    flow somebody else wrote would be how a person's `read-only` gets undone.

    Args:
      flow: The flow, for what a refusal says.
      agent: The agent filling the place.
      place: What the flow declared.

    Returns:
      What the agent was set up as before this, so that a flow which called another can hand
      it back exactly as it found it.

    Raises:
      NotAFlow: If the backend has no way of being told what the flow said -- a CLI that
        cannot be told not to search the web is a CLI that would go on searching, which is a
        declaration that lies rather than one that holds.
    """
    from dataclasses import replace

    from hmz.agents import PERMISSIONS

    was = agent.config
    wanted = replace(
        was,
        permission=min(was.permission, place.permission, key=PERMISSIONS.index),
        # A place run under a goal has one whatever the agent came with: an agent with goals
        # switched off is refused where the place is filled rather than quietly run without.
        goals=place.goals if place.goal else (was.goals and place.goals),
        web_search=was.web_search and place.web_search,
    )
    if wanted == was:
        return was
    try:
        _settles(agent).reconfigure(wanted)
    except ValueError as refused:
        raise NotAFlow(
            f"{flow}: {place.name or 'the agent'} cannot be run as this flow declares "
            f"-- {refused}"
        ) from refused
    return was


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
    runs = _runs(kind)
    needs = _needs(kind)
    if get_origin(kind) is Annotated:
        kind = get_args(kind)[0]
    return Place(
        name=name,
        person=_is_person(kind),
        moments=moments,
        where=where,
        goal=goal,
        permission=runs.permission,
        # A place the flow runs under a goal has one: `Goal` is the more particular of the
        # two things it wrote, and a flow that asked for both ways at once is a flow the
        # checker says so about rather than one that quietly does neither.
        goals=True if goal else runs.goals,
        web_search=runs.web_search,
        needs=needs,
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


def _needs(kind: object) -> Needs | None:
    """What a flow said filling a place takes, of the agent and of where it works.

    Args:
      kind: What the flow annotated the place with.

    Returns:
      The `Needs` it wrote beside the type, and None for a place it wrote none beside --
      which is one any backend may fill, working wherever the rest of the annotation allows.
    """
    from hmz.agents import Needs

    if get_origin(kind) is not Annotated:
        return None
    for said in get_args(kind)[1:]:
        if isinstance(said, Needs):
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


def _runs(kind: object) -> AgentDefaults:
    """What a flow said the agent filling a place runs at.

    Args:
      kind: What the flow annotated the place with.

    Returns:
      The `AgentDefaults` it wrote beside the type, and the ordinary one -- `bypass`, goals
      on, the web readable -- for a place it wrote none beside, which settles nothing: those
      are the loosest of each, and what an agent carries is never loosened.
    """
    from hmz.agents import AgentDefaults

    if get_origin(kind) is Annotated:
        for said in get_args(kind)[1:]:
            if isinstance(said, AgentDefaults):
                return said
    return AgentDefaults()


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
      is under `running` beneath it, each saying how deep it is and what called it -- a run
      is a tree, and a report of one that flattened it would say a flow ran under the wrong
      one.
    """
    with _TELLING:
        held = [one for one in _RUNNING.values() if one.thread.is_alive()]
    return {
        "flow": next((one.one.flow for one in held if one.one.under is None), ""),
        "running": [
            {
                "flow": each_of.one.flow,
                "deep": each_of.one.depth,
                "under": (
                    each_of.one.under.flow if each_of.one.under is not None else ""
                ),
                "for": round(time.monotonic() - each_of.one.since),
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
                    for each in each_of.agents
                ],
            }
            for each_of in held
        ],
    }


# What a report of a failure carries about the run it happened in: asked for only if one is
# ever made, and never otherwise. Registered once, here, because what it answers is what is
# running at the moment of the report rather than anything one run holds.
telemetry.about("flow", _about)
