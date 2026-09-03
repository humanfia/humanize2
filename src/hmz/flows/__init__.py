"""What a flow is called, where it is found, and how one says it holds more than one.

A flow is a directory: an `__init__.py` that is the flow itself, whatever that imports beside
it, and a `skills/` of the skills it brings -- laid out the way every one of these CLIs lays a
skill out, one directory apiece with a `SKILL.md` in it. So a flow is a thing that can be
copied, forked and edited whole, and what it needs to do its work travels with it.

Named rather than pathed: `hmz exec -f ralph_loop` is a name, and a path is what is left for
a flow that is nowhere any of them are kept. A name is looked for in the places flows come
from, which is every [flowverse](verses.py) there is -- the ones humanize ships, the ones its
own repository holds, whatever has been added, and the flows of your own in `.humanize/flows`
here and in your home directory. Those last two are `local` and `user`, and are flowverses
like the rest of them: one place a flow is read from, one rule for what it is called, and one
list to look in.

Which of them a bare name means is nearest first -- yours, then everybody else's -- so a flow
of your own may stand in for one of humanize's by taking its name, and `local/chat` is the
spelling that says which one it is.

A flow is a function marked with :func:`flow`, and nothing else is one. `@flow()` is the flow
its directory holds under the directory's own name; `@flow(name="draft")` is one of several it
holds, called `<flow>:draft` -- so that three phases of one thing live in one flow and are
three things to run. What the function is called is the flow's own business: `run`, `main`,
`draft_it`, all the same to a name that never mentions it.

And this is the whole of what a flow imports::

    from hmz.flows import Agent, Moment, flow

    @flow
    def run(agents: tuple[Agent, Agent], task: str) -> None:
        ...

One import rather than four, because a flow is written against one thing: what it drives, what
it may ask of it, and what it is worth saying about a turn. Which of humanize's own modules any
of that is written in is humanize's business -- a flow that named them would be a flow that
breaks when one of them moves, and a flow is somebody else's repository. So :mod:`hmz.flows`
gathers them: the interfaces in [agent.py](agent.py), the mark and the finding here, calling
another flow in [driving.py](driving.py), and the vocabulary a turn is described in from
:mod:`hmz.agents` -- the moments a hook hangs on, what a turn cost, what an agent is
configured with -- passed straight through.
"""

from __future__ import annotations

import contextlib
import os
import runpy
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, NamedTuple, overload

from .agent import Agent, Driven, Person, Session
from .atlas import (
    Edge,
    Node,
    Prophecy,
    Shape,
    Shipped,
    atlas,
    canonical,
    digest,
    kept,
    logic,
    mind,
    shipped,
    sub,
    told,
)
from .driving import (
    NotAFlow,
    Place,
    Running,
    carries,
    configures,
    container,
    drives,
    load,
    resumes,
    running,
    wanted,
)
from .verses import (
    BUILTIN,
    FLOWS,
    LOCAL,
    MINE,
    OFFICIAL,
    USER,
    Flowverse,
    flowverses,
    holds,
    nearest,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable

    from hmz import backends, home, models
    from hmz.agents import (
        EVERYWHERE,
        PERMISSIONS,
        SWARM,
        WINDOW,
        AgentConfig,
        AgentDefaults,
        Board,
        Event,
        Failed,
        Forks,
        Goal,
        Hook,
        Hooks,
        HumanAgent,
        Hung,
        Isolated,
        Item,
        Moment,
        Occasion,
        Question,
        Refused,
        Remote,
        Stopped,
        Tool,
        Unhooked,
        Unrecoverable,
        Usage,
        Verdict,
    )
    from hmz.backends import Model, Profile

    from .checking import Capability, Finding, briefed, catalogue, checked
    from .prophesying import Prophesied, is_atlas, prophesied
    from .proving import (
        ALWAYS_DONE,
        NEVER_DONE,
        SILENT,
        Outcome,
        Proof,
        Scenario,
        proved,
    )

__all__ = [
    "ALWAYS_DONE",
    "BUILTIN",
    "BUILTIN_AT",
    "ENTRY",
    "EVERYWHERE",
    "FLOWS",
    "LOCAL",
    "MINE",
    "NEVER_DONE",
    "OFFICIAL",
    "PERMISSIONS",
    "PROPHECY",
    "SILENT",
    "SWARM",
    "USER",
    "WINDOW",
    "Agent",
    "AgentConfig",
    "AgentDefaults",
    "Board",
    "Capability",
    "Driven",
    "Edge",
    "Event",
    "Failed",
    "Finding",
    "Flow",
    "Flowverse",
    "Forks",
    "Goal",
    "Hook",
    "Hooks",
    "HumanAgent",
    "Hung",
    "Isolated",
    "Item",
    "Model",
    "Moment",
    "Node",
    "NotAFlow",
    "Occasion",
    "Offer",
    "Outcome",
    "Person",
    "Place",
    "Profile",
    "Proof",
    "Prophecy",
    "Prophesied",
    "Question",
    "Refused",
    "Remote",
    "Running",
    "Scenario",
    "Session",
    "Shape",
    "Shipped",
    "Stopped",
    "Tool",
    "Unhooked",
    "Unrecoverable",
    "Usage",
    "Verdict",
    "about",
    "at",
    "atlas",
    "backends",
    "briefed",
    "canonical",
    "carries",
    "catalogue",
    "checked",
    "configures",
    "container",
    "digest",
    "drives",
    "entry",
    "find",
    "flow",
    "flowverses",
    "foretold",
    "fork",
    "found",
    "held",
    "holds",
    "home",
    "inside",
    "is_atlas",
    "kept",
    "load",
    "loaded",
    "logic",
    "mind",
    "models",
    "nearest",
    "offered",
    "offers",
    "prophesied",
    "proved",
    "reading",
    "resumes",
    "running",
    "shipped",
    "sub",
    "told",
    "wanted",
]

#: The two modules of humanize's own that a flow reaches through here whole: what each CLI
#: is, and what each of them runs. A loop that turns the effort down when a model starts
#: writing less asks the second of them what rungs there are, which is a question about a
#: backend rather than about any agent -- so it is handed through as it stands rather than
#: flattened into a name apiece.
_MODULES = ("backends", "models")

#: And the names a flow imports from here that are written down elsewhere: the vocabulary a
#: turn is described in, where humanize keeps what outlives a run, and the two readings of a
#: flow -- which are thousands of lines of `ast` apiece and are asked for by the one command
#: that checks a flow rather than by anything that lists, finds or runs one.
_ELSEWHERE = {
    "ALWAYS_DONE": "hmz.flows.proving",
    "Capability": "hmz.flows.checking",
    "Finding": "hmz.flows.checking",
    "NEVER_DONE": "hmz.flows.proving",
    "Outcome": "hmz.flows.proving",
    "Proof": "hmz.flows.proving",
    "Prophesied": "hmz.flows.prophesying",
    "SILENT": "hmz.flows.proving",
    "Scenario": "hmz.flows.proving",
    "briefed": "hmz.flows.checking",
    "catalogue": "hmz.flows.checking",
    "checked": "hmz.flows.checking",
    "is_atlas": "hmz.flows.prophesying",
    "prophesied": "hmz.flows.prophesying",
    "proved": "hmz.flows.proving",
    "AgentConfig": "hmz.agents",
    "Board": "hmz.agents",
    "AgentDefaults": "hmz.agents",
    "EVERYWHERE": "hmz.agents",
    "Event": "hmz.agents",
    "Failed": "hmz.agents",
    "Forks": "hmz.agents",
    "Goal": "hmz.agents",
    "Hook": "hmz.agents",
    "Hooks": "hmz.agents",
    "HumanAgent": "hmz.agents",
    "Hung": "hmz.agents",
    "Isolated": "hmz.agents",
    "Item": "hmz.agents",
    "Model": "hmz.backends",
    "Moment": "hmz.agents",
    "Occasion": "hmz.agents",
    "PERMISSIONS": "hmz.agents",
    "Profile": "hmz.backends",
    "Question": "hmz.agents",
    "Refused": "hmz.agents",
    "Remote": "hmz.agents",
    "SWARM": "hmz.agents",
    "Stopped": "hmz.agents",
    "Tool": "hmz.agents",
    "Unhooked": "hmz.agents",
    "Unrecoverable": "hmz.agents",
    "Usage": "hmz.agents",
    "Verdict": "hmz.agents",
    "WINDOW": "hmz.agents",
    "home": "hmz",
}


def __getattr__(name: str) -> object:
    """Hands through what a flow imports from here that is written down elsewhere.

    Fetched when it is asked for rather than imported at the top of this file, because this
    module is also what a list of flows is drawn from and what `hmz exec --help` loads to say
    what the line takes: importing it must not cost every coding agent driver there is. A flow
    that actually names one of these is a flow about to be run, and pays for it then.

    Args:
      name: What was asked for.

    Returns:
      The same object the module it is written in holds, so that a flow and humanize itself
      are talking about one thing -- `Moment.STOP` here is `Moment.STOP` there.

    Raises:
      AttributeError: If nothing here is called that, as for any other module.
    """
    from importlib import import_module

    if name in _MODULES:
        return import_module(f"hmz.{name}")
    where_ = _ELSEWHERE.get(name)
    if where_ is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    return getattr(import_module(where_), name)


#: Where the flows humanize itself ships are: a directory of them, rather than beside this
#: file -- what is beside this file is how a flow is found, which is not one. They are the
#: whole of what is there, so there is no `flows/` in it to tell them from the rest.
BUILTIN_AT = Path(__file__).parent / "builtin"

#: What a flow's directory holds the flow itself in. The rest of the directory is what it
#: imports and the `skills/` it brings, so the entry point is named rather than guessed.
ENTRY = "__init__.py"

#: And what an atlas's directory may hold the prophecy it was already compiled to in. A
#: flowverse that ships one ships the graph its flow was checked into, and that graph is
#: what runs: the compiling is where an atlas is refused, and a repository which has been
#: through it once has an answer worth carrying rather than working out again.
PROPHECY = "prophecy.pkl"

#: What a flow's own name is separated from the one inside it by. A flow that holds one flow
#: is named by itself; one that holds three names each of them after it.
_INSIDE = ":"


@dataclass(frozen=True, slots=True)
class Flow:
    """What a flow says about itself where it is written.

    Attributes:
      name: What it is called inside its own directory, which is the half after the colon.
        "" for the one it holds under the directory's own name, which is what `@flow()` marks.
      about: One line saying what it does, for whoever is choosing between them. Read off the
        function's own docstring where the decorator was not told one, and off the module's
        where the flow is one flow and its function says nothing.
      skills: The skills it works by that live somewhere else, each a git repository anything
        can clone with an optional `#<skill>` saying which of the ones in it is wanted. What
        the flow keeps in its own `skills/` is not among them: that is every flow in the
        directory's, and is found by looking rather than by being declared.
      resumable: Whether it can be picked up where the last run of it left off. One that says
        so is handed a dict as its last argument -- what it wrote there last time -- which is
        kept in the run's own cycle and read back into the run after it. A flow that says
        nothing is run from the top every time, which is what every flow was before this.
      selectable: Whether people are offered this flow in lists and the flow picker. An
        internal composition may set this false while remaining callable by name.
    """

    name: str = ""
    about: str = ""
    skills: tuple[str, ...] = ()
    resumable: bool = False
    selectable: bool = True


#: Where a decorated function keeps what it said about itself. On the function rather than in
#: a table, because a file is read by running it: a table would be one more thing to find,
#: and this travels with the thing it describes.
_SAID = "__humanize_flow__"


@overload
def flow[**P, T](call: Callable[P, T], /) -> Callable[P, T]: ...


@overload
def flow[**P, T](
    *,
    name: str = "",
    about: str = "",
    skills: Iterable[str] = (),
    resumable: bool = False,
    selectable: bool = True,
) -> Callable[[Callable[P, T]], Callable[P, T]]: ...


def flow[**P, T](
    call: Callable[P, T] | None = None,
    /,
    *,
    name: str = "",
    about: str = "",
    skills: Iterable[str] = (),
    resumable: bool = False,
    selectable: bool = True,
) -> Callable[P, T] | Callable[[Callable[P, T]], Callable[P, T]]:
    """Marks a function as a flow. Nothing else is one.

    Written with no name, it is the flow its file holds under the file's own name::

        @flow
        def run(agents: tuple[Agent], task: str) -> None:
            ...

    is `ralph_loop`, in `ralph_loop/__init__.py`. Written with one, it is one of several that
    flow holds, and is called `<flow>:<name>`::

        @flow(name="gen-idea", about="opens a loose idea into a repo-grounded draft")
        def first_pass(agents: Agents, task: str) -> None:
            ...

    is `humanize1:gen-idea`. What the function is called is the flow's own business either
    way: a name that is written down where a flow is run is a name to keep, and one taken
    from the function would change under whoever renamed it.

    A flow may also name skills that live somewhere else, which are mounted onto every session
    its agents open alongside the ones in its own `skills/`::

        @flow(skills=("https://github.com/humanfia/flowverse#deep-research",))

    And a flow may say that it can be picked up where the last run of it left off, which is
    what a loop that is meant to run for a week is::

        @flow(resumable=True)
        def run(agents: tuple[Agent], task: str, state: dict[str, Any]) -> None:
            state["round"] = state.get("round", 0) + 1

    Such a flow is handed a dict as its last argument -- after the config, for one that takes
    a config -- holding whatever it wrote there last time. It is kept in the run's own cycle
    and saved as the flow writes it, so a run that was stopped or killed is one the next run
    picks up from rather than one whose week is gone.

    A helper used only by another flow remains callable without cluttering the flow picker::

        @flow(name="engine", selectable=False)
        def engine(agents: tuple[Agent], task: str) -> None:
            ...

    Args:
      call: The function, when the decorator is written with no arguments at all.
      name: What to call this one among the flows its directory holds, or "" for the one it
        holds under the directory's own name.
      about: One line saying what it does, defaulting to the first line of its docstring.
      skills: The skills it works by that are somewhere else, one git URL apiece with an
        optional `#<skill>`. What it keeps in its own `skills/` needs no declaring.
      resumable: Whether it takes the state of the last run of it, and is handed a dict to
        write the next run's into.
      selectable: Whether to offer it in flow lists and the flow picker. False keeps an
        internal composition callable by name without presenting it as a flow to start.

    Returns:
      The function, unchanged but for what it now says about itself: a flow is called the way
      it always was, and a decorator that wrapped it would put itself between the flow and
      whatever reads its arguments.
    """

    def marks(said: Callable[P, T]) -> Callable[P, T]:
        setattr(
            said,
            _SAID,
            Flow(
                name=name,
                about=about or _first(said.__doc__),
                skills=tuple(skills),
                resumable=resumable,
                selectable=selectable,
            ),
        )
        return said

    return marks if call is None else marks(call)


def loaded(where_: str | os.PathLike[str]) -> dict[str, Any]:
    """Runs a flow's entry point and answers with what it left behind.

    With its own directory importable while it runs, and only while: a flow is a directory of
    what it needs, and one that reaches for the module next to it is reaching for something
    that came with it. The directory the flows are in is importable too, for what a flowverse
    keeps beside them for all of them. Put back afterwards, since what a flow imports is not
    something the rest of this process should be able to.

    Run each time rather than cached: a flow rewritten while a run is going is the flow that
    runs next, which is what lets a flow -- or an agent driving one -- rewrite it and go on.

    Args:
      where_: The flow: its directory, or the Python file to run outright.

    Returns:
      Everything running it defined, by name.
    """
    where_ = os.path.join(where_, ENTRY) if os.path.isdir(where_) else where_
    beside = os.path.dirname(os.path.abspath(where_))
    among = os.path.dirname(beside)
    sys.path[:0] = [beside, among]
    try:
        return runpy.run_path(str(where_))
    finally:
        for one in (beside, among):
            with contextlib.suppress(ValueError):
                sys.path.remove(one)
        _forgotten(beside, among)


def _forgotten(*under: str) -> None:
    """Forgets what was imported from beside a flow, so nothing of it outlives the run.

    A flow imports the module next to it by its plain name -- `import prompts` -- and every
    flow may have one. Left in `sys.modules`, the first flow loaded in a process owns that name
    for the life of it: the next flow's `import prompts` is answered with the last one's, and a
    menu drawing the list of flows is enough to settle who won. Taken out, each run of a flow
    reads what is beside that flow -- which is also what makes a flow edited between two runs
    of it run as it is now, module beside it and all.

    What is dropped is only what was loaded out of these directories, found by the file each
    module says it came from. Nothing of humanize's own is: a flow kept inside humanize's own
    tree would otherwise unload the package that is running it.

    Args:
      under: The directories, as absolute paths.
    """
    roots = tuple(one + os.sep for one in under)
    for name, module in list(sys.modules.items()):
        if name == __package__ or name.startswith("hmz"):
            continue
        at = getattr(module, "__file__", None)
        if at and os.path.abspath(at).startswith(roots):
            del sys.modules[name]


def held(where_: str | os.PathLike[str]) -> list[Flow]:
    """Every flow one file holds: its own first, and the rest as it declares them.

    Args:
      where_: The flow -- its directory, or the file to read outright. It is run to be read,
        so whatever it does as it is imported happens here.

    Returns:
      One per function it marked with :func:`flow`, the one it marked with no name first --
      which is the flow the file holds under its own name. Nothing at all for a file that
      marks none, or cannot be read: this is asked while a list is being drawn, and a file
      that will not import is one line of that list rather than the end of it.
    """
    try:
        inside = loaded(where_)
    except Exception:  # noqa: BLE001 -- a file that will not run holds no flows to list
        return []
    return _flows_of(inside)


def _flows_of(inside: dict[str, Any]) -> list[Flow]:
    """Every flow in what running one file left behind.

    Args:
      inside: What the file defined, by name.

    Returns:
      One per function the file marked with :func:`flow`, in the order it declared them --
      which for three phases of one thing is their order -- and the one it marked with no name
      first, since that is the one the file is named after and a list that put it third would
      read as the third thing in the file. Nothing at all for a file that marks nothing, which
      a directory of flows may well have in it: something the flows beside it import, or the
      file that sets their tests up. A name declared twice is the first of them: a file that
      holds two flows of one name is a file to correct, and picking one of them at random is
      not the way to say so.
    """
    said: list[Flow] = []
    for one in inside.values():
        marked = getattr(one, _SAID, None)
        if not isinstance(marked, Flow) or any(
            marked.name == already.name for already in said
        ):
            continue
        # The file's own docstring where the flow it holds says nothing: a file that is one
        # flow is documented as that flow, and its first line is what it does.
        if not marked.name and not marked.about:
            marked = Flow(
                name="",
                about=_first(inside.get("__doc__")),
                skills=marked.skills,
                resumable=marked.resumable,
                selectable=marked.selectable,
            )
        said.append(marked)
    return [one for one in said if not one.name] + [one for one in said if one.name]


class Offer(NamedTuple):
    """One flow there is to run, as whatever is offering them lists it.

    Attributes:
      whose: Where it came from: a flowverse by name, or `local` and `user` for the flows of
        this project and of yours.
      name: What to call it, which is what `-f` takes.
      about: The line it says about itself, or "" for one that says nothing.
    """

    whose: str
    name: str
    about: str = ""


def found() -> list[Offer]:
    """Every flow there is to run, and where each came from.

    Every place asked the same question, which is :func:`offers`, and asked it in the order
    they are offered in: the flows humanize ships, then the ones its own repository holds,
    then whatever flowverses have been added, then this project's own flows and yours. One
    place works out what a flow is called and one place lists them, because two of either is
    two things to drift apart -- and a name that has drifted is a name `-f` will not take.

    Returns:
      One per flow. A flow humanize ships is called by a bare name and every other by
      `<where it came from>/<name>` -- `official/rlar`, `local/scheduler` -- so a flow of
      yours that happens to share a name with one of humanize's is a different flow here
      rather than the same one, and is written down, offered and remembered under a name of
      its own. A file that holds several says so, `<name>:<inside>` apiece.
    """
    return [one for verse in flowverses() for one in offers(verse)]


def entry(under: Path, name: str) -> Path | None:
    """The file to run for the flow of that name in one directory of flows.

    A flow is a module, and there are two shapes of one: a directory with an `__init__.py` in
    it -- which is what a flow that brings skills or imports what came with it has to be --
    and a single `.py` file, which is what a flow that is one function still is. The directory
    wins where both are there, being the one that says most about itself.

    Args:
      under: The directory the flows are in.
      name: The flow, by the name it is offered under.

    Returns:
      The path to run, or None where there is no such flow.
    """
    beside = under / name / ENTRY
    if beside.is_file():
        return beside
    alone = under / f"{name}.py"
    return alone if alone.is_file() else None


def offered(under: Path) -> list[str]:
    """Every flow in one directory of flows, by the name each is offered under.

    Args:
      under: The directory the flows are in, which may not be there at all.

    Returns:
      One name apiece, alphabetically and without repeating a name that is there both ways.
      A name starting with an underscore is not a flow but something the flows beside it
      import; nor is a directory with no entry point in it. Nothing at all where there is no
      such directory.
    """
    found_: list[str] = []
    try:
        held = sorted(under.iterdir())
    except OSError:
        return []
    for path in held:
        name = path.name.removesuffix(".py")
        if name.startswith("_") or name in found_:
            continue
        if (path / ENTRY).is_file() or (path.is_file() and path.suffix == ".py"):
            found_.append(name)
    return found_


def offers(one: Flowverse) -> list[Offer]:
    """Every flow one flowverse offers, and the name each is offered by.

    The one place that rule is written down. :func:`found` asks this of every flowverse in
    turn, and so does anything that wants a single one's -- two places working out what a flow
    is called is two places to drift, and a name that drifts is a name `-f` will not take.

    Args:
      one: The flowverse.

    Returns:
      One per flow, by directory, alphabetically: `<flowverse>/<flow>`, except for the flows
      humanize ships, which are called by a bare name. Yours are named the same way as anybody
      else's -- `local/scheduler`, `user/scheduler` -- so that a flow of yours sharing a name
      with one of humanize's is listed beside it under a name of its own rather than instead
      of it. A flow that holds several names each of them, `<flow>:<inside>` apiece, and a
      directory that holds none is not among them -- a directory of flows has directories
      beside them that are not one.

      Nothing at all for a flowverse that has not been fetched, which is not the same answer as
      one that holds nothing, and is why :class:`Flowverse` says which it is.

    Note:
      Reading a flow means running it, so the entry point of every flow in the directory the
      flowverse holds its flows in is run to find out what it holds -- and nothing outside it,
      which is what that directory is for. Whoever added it is trusting that repository with
      this machine; this is where that trust is spent.
    """
    from .verses import flows

    return [
        Offer(one.name, name if one.name == BUILTIN else f"{one.name}/{name}", said)
        for base in flows(one)
        if (at_ := entry(holds(one), base)) is not None
        for name, said in _named(at_, base)
    ]


def _named(at: Path, called: str) -> list[tuple[str, str]]:
    """What each flow in one file is called, given what the file itself is called.

    Args:
      at: The file.
      called: What the file is called where it was found.

    Returns:
      One `(name, what it says about itself)` pair per flow: the file's own name for the flow
      it holds under it, and `<called>:<inside>` for each of the rest. Nothing at all for a
      file that holds no flow -- a directory of flows has files beside them that are not one --
      but just the file's name for one that could not be read: a file that will not import is
      still a flow somebody named, and saying so where they pick it is better than leaving it
      off the list.
    """
    try:
        inside = loaded(at)
    except Exception:  # noqa: BLE001 -- named as a flow, and not readable to be sure it is
        return [(called, "")]
    return [
        (called if not one.name else f"{called}{_INSIDE}{one.name}", one.about)
        for one in _flows_of(inside)
        if one.selectable
    ]


def about(named_: str) -> str:
    """The line one flow says about itself, for whoever is choosing between them.

    Args:
      named_: What the flow is called, as :func:`found` calls it.

    Returns:
      The line, or "" for a flow that says nothing or cannot be read.
    """
    at, inside = _split(named_)
    for one in held(find(at)):
        if one.name == inside:
            return one.about
    return ""


def _split(named_: str) -> tuple[str, str]:
    """One flow's name, split into the file and the flow inside it.

    Args:
      named_: What the flow is called.

    Returns:
      The file's name and the name inside it, which is "" for a file's own flow. A colon in a
      path -- a Windows drive, a URL somebody pasted -- is not one of these: only the last
      one is read, and only where what follows it is a name rather than a path.
    """
    at, sep, inside = named_.rpartition(_INSIDE)
    if not sep or os.sep in inside or "/" in inside:
        return named_, ""
    return at, inside


def find(named_: str) -> str:
    """Where the entry point of the flow called this is.

    Args:
      named_: A flow's name -- `ralph_loop`, `official/rlar`, `local/scheduler`,
        `humanize1:gen-plan` -- or the path to a flow taken as given, `~` and all: its
        directory, or the file to run outright.

    Returns:
      The path to run: the flow the flowverse named holds, else the nearest flow of that
      name, else what the path names -- and `named_` itself if nothing answers to it, so
      that whatever named it hears about it. Resolved, since a flow is free to change the
      working directory the name was resolved against.
    """
    at_, _ = _split(named_)
    whose, _, rest = at_.partition("/")
    if rest:
        # Named outright -- `official/rlar`, `local/scheduler` -- which is the one spelling
        # that says which place it came from, and so the one that cannot be stood in for.
        for verse in flowverses():
            beside = entry(holds(verse), rest)
            if whose == verse.name and beside is not None:
                return str(beside.resolve())
    else:
        # Nearest wins: this project, then yours, then whatever there is to run -- so a flow
        # of your own may stand in for one of humanize's by taking its name.
        for verse in nearest():
            beside = entry(holds(verse), at_)
            if beside is not None:
                return str(beside.resolve())
    # A path taken as given, in both the shapes a flow is: the directory it is, the file it is
    # for whoever points at one outright -- a flow being written, a file a test wrote out --
    # and the `.py` beside a path with the extension left off, which is how a single-file flow
    # is written down anywhere its name is not what it is called by.
    said = os.path.expanduser(at_)
    for shape in (os.path.join(said, ENTRY), said, f"{said}.py"):
        if os.path.isfile(shape):
            return os.path.realpath(shape)
    return at_


def reading(named_: str) -> str:
    """What to point a reading of one flow at, which is not always what runs it.

    A flow is a directory or a single file, and the two readings of one -- the checking and
    the compiling -- take the whole of it either way: the directory where there is one, so
    that what the entry point imports beside it is read too, and the file where there is
    not. :func:`find` answers with the entry point instead, that being what is run.

    Args:
      named_: A flow's name, as :func:`find` takes it.

    Returns:
      The path to read: the flow's own directory, or the file a single-file flow is. A name
      nothing answers to comes back as :func:`find` left it, so whatever asked hears about
      it where it looks rather than here.
    """
    found_ = find(named_)
    if os.path.isfile(found_) and os.path.basename(found_) == ENTRY:
        return os.path.dirname(found_)
    return found_


def foretold(named_: str) -> str:
    """Where the prophecy one flow ships is, for a flow that ships one.

    An atlas is compiled before it runs, and a flowverse may ship what compiling it came
    to: `prophecy.pkl`, beside the entry point, holding the graph the atlas was read into.
    Where there is one it is what runs -- the compiling having already happened, in the
    repository the flow came from, over the source that repository holds.

    What is beside it still matters. A prophecy names the functions its nodes are, and
    those are in the flow's own Python: a directory holding a prophecy and no entry point
    is not a flow, the same way a directory holding neither is not one.

    Args:
      named_: A flow's name, as :func:`find` takes it.

    Returns:
      The path to it, and "" for a flow that ships none -- which is every flow that is not
      an atlas, and most atlases.
    """
    from .atlas import shipped

    beside = at(named_)
    held = shipped(beside) if beside else None
    return "" if held is None else str(held.at)


def at(named_: str) -> str:
    """The flow's own directory, which is where what it brings with it lives.

    Args:
      named_: A flow's name, as :func:`find` takes it.

    Returns:
      The directory its `__init__.py` is in, and "" for a name nothing answers to -- and for
      a flow that is a single file, which has no directory of its own: what is beside such a
      flow is the other flows, and none of it came with this one.
    """
    found_ = find(named_)
    if not os.path.isfile(found_) or os.path.basename(found_) != ENTRY:
        return ""
    return os.path.dirname(found_)


def inside(named_: str) -> str:
    """Which of the flows in a file this name asks for.

    Args:
      named_: What the flow is called.

    Returns:
      The name after the colon, or "" for the flow a file holds under its own name.
    """
    return _split(named_)[1]


def _first(said: str | None) -> str:
    """The first line of a docstring, which is what a flow says about itself in a list.

    "" for a docstring that is blank, which is a docstring somebody left room in rather than
    a flow to refuse: a flow says what it does or it does not.
    """
    lines = (said or "").strip().splitlines()
    return lines[0].strip() if lines else ""


def fork(named_: str, into: str | os.PathLike[str] | None = None) -> str:
    """Copies one flow into this project's own, to be changed however you like.

    A flow is a directory, which is what makes this a copy rather than a rewrite: the entry
    point, whatever it imports beside it and the `skills/` it brings all come across, and what
    lands is a flow of yours under the name it already had. Yours are looked in first, so from
    then on that name means the copy -- `official/rlar` forked is `rlar`, and `-f rlar` runs
    what you have since made of it.

    Which is the way to change a flow at all: a flowverse is somebody else's repository and is
    fetched again over whatever was written into it, so an edit made there is an edit that
    goes away the next time it is fetched.

    Args:
      named_: The flow to copy, by the name it is offered under.
      into: Where to put it, defaulting to this project's own flows.

    Returns:
      The directory it was copied to.

    Raises:
      ValueError: If there is no such flow, or there is already one of that name there --
        which is a copy to edit, run or take away rather than one to write over.
    """
    import shutil
    import tempfile

    found_ = find(named_)
    if not os.path.isfile(found_):
        raise ValueError(f"there is no flow called {named_} to copy")
    beside = os.path.dirname(found_)
    whole = os.path.basename(found_) == ENTRY
    name = os.path.basename(beside) if whole else os.path.basename(found_)
    mine = os.path.expanduser(str(into) if into is not None else MINE[LOCAL])
    at_ = os.path.join(mine, name)
    # Both shapes of the name, whichever this one is: a flow is a directory or a file, the
    # directory wins the name where there is one of each, and a copy that landed beside a
    # flow of yours would take that flow's name away without touching the file it is in.
    stem = at_.removesuffix(".py")
    if os.path.exists(stem) or os.path.exists(stem + ".py"):
        raise ValueError(f"there is already a flow of your own at {at_}")
    os.makedirs(mine, exist_ok=True)
    # Copied beside and then moved into place: a copy that fails partway -- a disk that filled,
    # a file that could not be read -- would otherwise leave half a flow under the name, which
    # is a flow that will not run, cannot be forked again, and hides the one it was copied from.
    holding = tempfile.mkdtemp(dir=mine, prefix=f".{name}.")
    try:
        held = os.path.join(holding, name)
        if whole:
            # The whole directory: what a flow is made of travels with it, which is what makes
            # a copy of one a flow rather than half of one.
            shutil.copytree(beside, held)
        else:
            # A flow that is one file is copied as one: a flow is a module, and this is the
            # shape that module has.
            shutil.copy2(found_, held)
        os.replace(held, at_)
    finally:
        shutil.rmtree(holding, ignore_errors=True)
    return at_
