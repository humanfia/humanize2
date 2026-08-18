"""What an atlas is written in, and the prophecy it compiles to.

A flow is a Python file that may branch any way it likes, and the one thing nothing can ask
it is what it is about to do. An atlas is the other bargain: a narrower Python, whose entry
point is read rather than run, and whose shape is therefore a graph that exists before
anything does. This is the vocabulary of both halves -- the marks an atlas is written with,
and the prophecy it is compiled to.

An atlas is a flow. It is marked, found, named, listed and run the way every other flow is,
so nothing that already knows what a flow is has to learn a second thing::

    from hmz.flows import Agent, atlas, logic, mind
    from pydantic import BaseModel

    class Agents(NamedTuple):
        writer: Agent
        reviewer: Agent

    class Draft(BaseModel):
        model_config = {"extra": "forbid"}
        text: str

    class Verdict(BaseModel):
        model_config = {"extra": "forbid"}
        done: bool

    @mind
    def write(agent: Agent, task: str) -> Draft: ...

    @logic
    def judge(said: Draft) -> Verdict: ...

    @atlas
    def run(agents: Agents, task: str) -> None:
        draft = write(agents.writer, task)
        verdict = judge(draft)
        while not verdict.done:
            draft = write(agents.writer, task)

There are two kinds of ordinary node and one kind that is a whole flow. A `mind` is a turn:
real work by a real agent, handed the agent the call site names. A `logic` is a Python
function: no agent, no turn, and a decision anything can read. An atlas called by another
atlas is a supernode -- one node from outside, one prophecy from within.

A mind has one way out and a logic may have several. That is the whole of why the two are
told apart: a branch is a decision, and a decision nothing but a model made is a decision no
reading of the flow can state. So the node a branch hangs off is a logic node, and what a
model said reaches a branch by being read by one.

A prophecy is canonical: the same atlas written twice the same way compiles to the same text,
byte for byte, and :func:`digest` over that text is what a run picked up again checks itself
against. An atlas rewritten between two runs is a different prophecy, and a run that carried on
into it would be a run resuming into somewhere it had never been.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, NamedTuple, overload

if TYPE_CHECKING:
    import os
    from collections.abc import Callable, Iterable

__all__ = [
    "AGENTS",
    "CONFIG",
    "INPUT",
    "Atlas",
    "Edge",
    "Field",
    "Marked",
    "Node",
    "Prophecy",
    "Reads",
    "Shape",
    "Shipped",
    "Sub",
    "When",
    "atlas",
    "canonical",
    "digest",
    "kept",
    "logic",
    "mind",
    "shipped",
    "sub",
    "told",
]

#: What a node reads when it is handed one of the run's agents rather than a value: the
#: agents are what the run was started with rather than anything a node answered, so they
#: are named where a node id would be. Not an identifier, so nothing an atlas can write
#: collides with it.
AGENTS = "@agents"

#: And what it reads when it is handed the flow's own input -- the task a command line gave,
#: or the shape a supernode was called with.
INPUT = "@input"

#: And what it reads when it is handed what the run was set up with, for an atlas that says
#: it takes a config.
CONFIG = "@config"

#: What a node is: a turn taken by an agent, a Python function, or a whole atlas of its own.
#: The first two are what a prophecy is made of, and the third is what one prophecy is made of
#: another by, which is what a supernode is.
type Kind = Literal["mind", "logic", "atlas"]

#: Where a marked node keeps what its mark said, and where an atlas keeps that it is one. On
#: the function rather than in a table, for the reason `flow` puts it there: a file is read
#: by running it, and a mark that travels with the thing it describes is a mark there is only
#: one place to look for.
MARKED = "__humanize_node__"
ATLAS = "__humanize_atlas__"


@dataclass(frozen=True, slots=True)
class Atlas:
    """That a function is an atlas, and what the mark said beyond what `Flow` holds.

    An atlas carries this as well as the :class:`~hmz.flows.Flow` every flow carries, so that
    everything which already reads flows goes on reading this one, and only what compiles it
    has to know the difference.

    Attributes:
      name: What it is called inside its own file, which is the half after the colon, and ""
        for the one the file holds under its own name. The same name `flow` takes, and the
        same name a supernode of another file is reached by.
    """

    name: str = ""


@dataclass(frozen=True, slots=True)
class Marked:
    """What `mind` or `logic` marked a function with.

    Attributes:
      kind: Which of the two it is. A mind takes a turn and has one way out; a logic is
        Python and may have several.
      rerun: Whether a run picked up again runs this node again where the last run was
        stopped inside it. True is what a node says by saying nothing: work that was cut off
        partway is work that was not done. False is for a node that has had its effect by
        the time it can be interrupted -- and such a node answers with nothing, since a run
        stepping past it has no answer of its to carry on with.
    """

    kind: Kind
    rerun: bool = True


@dataclass(frozen=True, slots=True)
class Sub:
    """An atlas of another file, as the atlas reaching for it names it.

    Bound at the top of a file and called in a body, which is the one way an atlas reaches a
    flow that is not beside it::

        review = sub("official/review")

    Never called: an atlas's body is read rather than run, and what runs is the prophecy the
    reading compiled. Calling one is therefore an atlas being run some way this module knows
    nothing about, and says so rather than doing something surprising.

    Attributes:
      named: The flow, by the name `-f` takes.
    """

    named: str

    def __call__(self, *args: object, **kwargs: object) -> object:  # noqa: ARG002
        """Refuses: an atlas's body is compiled, and the prophecy is what runs.

        Args:
          args: Whatever the call was written with, which is read where it is written.
          kwargs: The same.

        Raises:
          TypeError: Always. A supernode is run by the prophecy around it, and a body that ran
            would be an atlas being run as though it were an ordinary flow.
        """
        raise TypeError(
            f"{self.named} is a supernode: an atlas's body is compiled rather than run, "
            "so nothing calls this outside the prophecy it was read into"
        )


def sub(named: str) -> Sub:
    """Names the atlas one supernode is, for a body to call it by.

    The counterpart of :func:`~hmz.flows.load`, and the only one an atlas has: `load` answers
    with a flow that may be anything, and an atlas that called one would be a prophecy with a
    hole where a node should be. So an atlas reaches another atlas, by the name `-f` takes,
    and reaches nothing else.

    Args:
      named: The flow, by the name `-f` takes -- `official/review`, `local/triage:pass`.

    Returns:
      Something for a body to call, which nothing ever calls: it is read where it is written,
      and the atlas it names is compiled into the prophecy reading it.
    """
    return Sub(named)


@overload
def mind[**P, T](call: Callable[P, T], /) -> Callable[P, T]: ...


@overload
def mind[**P, T](
    *, rerun: bool = True
) -> Callable[[Callable[P, T]], Callable[P, T]]: ...


def mind[**P, T](
    call: Callable[P, T] | None = None, /, *, rerun: bool = True
) -> Callable[P, T] | Callable[[Callable[P, T]], Callable[P, T]]:
    """Marks a function as a node an agent takes a turn in -- the work itself.

    A mind is handed the agent the call site named and whatever else flows into it, and
    answers with a shape::

        @mind
        def write(agent: Agent, task: str) -> Draft:
            return agent(f"draft this: {task}", schema=Draft)

    It has exactly one way out. What a model said is not a decision until something read it,
    so a branch is hung off a logic node and never off this: a prophecy that branched on a
    turn would be a prophecy whose shape is whatever the model happened to say.

    Args:
      call: The function, when the mark is written with no arguments at all.
      rerun: Whether a run picked up again runs this node again where the last one stopped
        inside it, which is what a node says by saying nothing.

    Returns:
      The function, unchanged but for what it now says about itself.
    """
    return _noded("mind", call, rerun=rerun)


@overload
def logic[**P, T](call: Callable[P, T], /) -> Callable[P, T]: ...


@overload
def logic[**P, T](
    *, rerun: bool = True
) -> Callable[[Callable[P, T]], Callable[P, T]]: ...


def logic[**P, T](
    call: Callable[P, T] | None = None, /, *, rerun: bool = True
) -> Callable[P, T] | Callable[[Callable[P, T]], Callable[P, T]]:
    """Marks a function as a node that is Python -- the deciding, the counting, the shaping.

    A logic drives no agent and takes no turn::

        @logic
        def judge(said: Draft) -> Verdict:
            return Verdict(done=said.text.endswith("."))

    It may have several ways out, which is what a branch in an atlas's body is: the value it
    answered with is read by the `if` or the `while` that follows it, and each way out is one
    answer to that reading.

    Args:
      call: The function, when the mark is written with no arguments at all.
      rerun: Whether a run picked up again runs this node again where the last one stopped
        inside it, which is what a node says by saying nothing.

    Returns:
      The function, unchanged but for what it now says about itself.
    """
    return _noded("logic", call, rerun=rerun)


def _noded[**P, T](
    kind: Kind, call: Callable[P, T] | None, *, rerun: bool
) -> Callable[P, T] | Callable[[Callable[P, T]], Callable[P, T]]:
    """Marks one function as a node, whichever of the two kinds it is.

    What the two marks share is the whole of how a decorator written bare and one written
    with arguments are told apart, which is a protocol worth having in one place rather than
    two: what differs between them is which kind it is, and what each says for itself.

    Args:
      kind: Which kind of node the mark makes it.
      call: The function, where the mark was written with no arguments at all.
      rerun: Whether a run picked up inside it runs it again.

    Returns:
      The function where there was one, and something to mark one where there was not.
    """

    def marks(said: Callable[P, T]) -> Callable[P, T]:
        setattr(said, MARKED, Marked(kind, rerun=rerun))
        return said

    return marks if call is None else marks(call)


@overload
def atlas[**P, T](call: Callable[P, T], /) -> Callable[P, T]: ...


@overload
def atlas[**P, T](
    *,
    name: str = "",
    about: str = "",
    skills: Iterable[str] = (),
    selectable: bool = True,
) -> Callable[[Callable[P, T]], Callable[P, T]]: ...


def atlas[**P, T](
    call: Callable[P, T] | None = None,
    /,
    *,
    name: str = "",
    about: str = "",
    skills: Iterable[str] = (),
    selectable: bool = True,
) -> Callable[P, T] | Callable[[Callable[P, T]], Callable[P, T]]:
    """Marks a function as an atlas: a flow whose body is a graph rather than a program.

    Everything :func:`~hmz.flows.flow` marks a flow with, this marks too -- the name, the
    line it says about itself, the skills it works by, whether it is offered in a list -- so
    an atlas is found, listed, chosen and run exactly as any other flow is. What it adds is
    that the body is read instead of executed::

        @atlas
        def run(agents: Agents, task: str) -> None:
            draft = write(agents.writer, task)
            verdict = judge(draft)

    The body is a declaration. Each statement in it is one node; the branches between them
    are the edges; and what actually runs is the prophecy that reading compiled, one node at a
    time, which is what lets a run be picked up in the middle of one.

    An atlas can always be picked up again, and says so without being asked: a prophecy is a
    list of nodes with an answer apiece, so what a run of one has done so far is something
    the run itself writes down. Nothing in the body writes state and nothing is handed a
    dict; a node that ran is a node whose answer was kept.

    An atlas that takes a shape rather than a task is a supernode and nothing else::

        @atlas(name="review")
        def review(agents: Agents, draft: Draft) -> Verdict:
            ...

    Args:
      call: The function, when the mark is written with no arguments at all.
      name: What to call this one among the flows its file holds, or "" for the one it holds
        under the file's own name.
      about: One line saying what it does, defaulting to the first line of its docstring.
      skills: The skills it works by that are somewhere else, one git URL apiece.
      selectable: Whether to offer it in flow lists and the flow picker.

    Returns:
      The function, unchanged but for what it now says about itself -- both marks, since an
      atlas is a flow and everything that reads flows must go on reading this one.
    """
    from . import flow

    def marks(said: Callable[P, T]) -> Callable[P, T]:
        setattr(said, ATLAS, Atlas(name=name))
        return flow(
            name=name,
            about=about,
            skills=skills,
            resumable=True,
            selectable=selectable,
        )(said)

    return marks if call is None else marks(call)


# ---------------------------------------------------------------------------------------
# The prophecy itself: what an atlas compiles to, and what a run of one walks.
# ---------------------------------------------------------------------------------------


class Field(NamedTuple):
    """One field of one shape, as the compiling read it off the model that declares it.

    Attributes:
      name: What the field is called.
      shape: The shape it holds, by name.
      required: Whether the model refuses to be built without it, which is what an edge is
        held to: what flows in has to cover what the far end cannot do without.
    """

    name: str
    shape: str
    required: bool


class Shape(NamedTuple):
    """One thing that may flow along an edge, read off the atlas's own files.

    Attributes:
      name: The model's name, or the plain kind -- `str`, `int`, `float`, `bool`.
      fields: One per field the model declares, in the order it declares them, and nothing at
        all for a plain kind, which has none.
    """

    name: str
    fields: tuple[Field, ...] = ()


class Reads(NamedTuple):
    """Where one of a node's arguments comes from.

    A name rather than the node that answered it, because a body may bind a name twice --
    which is what a loop is, the second binding being the one the next round reads. So a run
    keeps what each name holds now, and a node says which of them it wants.

    Attributes:
      reads: The name it reads: one the body bound, or :data:`AGENTS` for the run's agents,
        :data:`INPUT` for what the flow itself was called with, and :data:`CONFIG` for what
        it was set up with.
      field: The field read off it, and "" for the whole of it.
    """

    reads: str
    field: str = ""


class When(NamedTuple):
    """What has to hold for one edge to be the way out that is taken.

    Attributes:
      reads: The name the branch reads, which is one a node bound.
      field: The field read off it, and "" for the whole of it.
      truth: Whether this is the way out taken when that reads as true or as false.
    """

    reads: str
    field: str
    truth: bool


class Node(NamedTuple):
    """One node of a prophecy: one call site of the body it was compiled from.

    A node is a call site rather than a function, since a body that calls one function twice
    is a prophecy with two nodes in it -- each with its own answer, its own place in the run,
    and its own line in what a run picked up again has already done.

    Attributes:
      at: The node id: what it calls, and `:2`, `:3` after it where the body calls that same
        thing more than once. Read off the body's shape rather than off a line number, so
        that a file reformatted compiles to the prophecy it already was.
      kind: Which of the three it is.
      calls: The function it runs, by the name the atlas's own files declare it under -- or,
        for a supernode from another file, the flow by the name `-f` takes.
      takes: Where each of its arguments comes from, in the order it takes them.
      binds: The name its answer is bound to, and "" for a node whose answer nothing takes.
      gives: The shape it answers with, and "" for a node that answers with nothing.
      rerun: Whether a run picked up again runs it again where the last run stopped inside
        it, or steps past it.
      under: For a supernode, the prophecy it is, by the name that prophecy is called. "" for
        every other node.
    """

    at: str
    kind: Kind
    calls: str
    takes: tuple[Reads, ...] = ()
    binds: str = ""
    gives: str = ""
    rerun: bool = True
    under: str = ""


class Edge(NamedTuple):
    """One way from one node to the next.

    Attributes:
      out_of: The node it leaves, and "" for the way into the prophecy.
      into: The node it arrives at, and "" for the way out of it, which is where the run
        ends.
      when: What has to hold for this to be the way taken, and None for a node's only one.
      answers: For a way out of the prophecy, the name the run answers with -- which is what
        the `return` named, and not whatever the last node happened to say. "" everywhere
        else, and for an atlas that answers with nothing.
    """

    out_of: str
    into: str
    when: When | None = None
    answers: str = ""


class Prophecy(NamedTuple):
    """One atlas, compiled: the whole of what a run of it will do.

    Attributes:
      name: The flow, as it was asked for -- which for a supernode of another file is the
        name `-f` takes, and for one beside it is that file's own name for it.
      takes: The shape the flow is called with, which is `str` for one a command line runs
        and a model for one that is only ever a supernode.
      gives: The shape it answers with, and "" for one that answers with nothing.
      config: The shape it is set up with, and "" for one that takes no setting up -- which
        every supernode is, what is set up being the run rather than a node of it.
      agents: What the atlas calls each of the agents it drives, in the order it takes them.
      nodes: Every node, by node id.
      edges: Every way from one node to another, the way in and the way out included.
      shapes: Every shape anything in it carries, the ones its supernodes carry included.
      prophecies: One per supernode, which is the sub-atlas that node is.
    """

    name: str
    takes: str
    gives: str
    config: str
    agents: tuple[str, ...]
    nodes: tuple[Node, ...]
    edges: tuple[Edge, ...]
    shapes: tuple[Shape, ...]
    prophecies: tuple[Prophecy, ...] = ()

    def node(self, at: str) -> Node | None:
        """The node of that id, or None where the prophecy holds none.

        Args:
          at: The node id.

        Returns:
          The node.
        """
        return next((one for one in self.nodes if one.at == at), None)

    def out_of(self, at: str) -> tuple[Edge, ...]:
        """Every way out of one node, in the order they are to be tried.

        Args:
          at: The node id, or "" for the way into the prophecy.

        Returns:
          The edges, the guarded ones first: a node with a branch and a way out that is
          taken otherwise is read as the branch it is rather than as a coin toss.
        """
        found = [one for one in self.edges if one.out_of == at]
        return tuple(sorted(found, key=lambda one: one.when is None))

    def under(self, named: str) -> Prophecy | None:
        """The sub-prophecy of that name, or None where this prophecy holds none.

        Args:
          named: What the supernode said it was.

        Returns:
          The prophecy.
        """
        return next((one for one in self.prophecies if one.name == named), None)


def canonical(prophecy: Prophecy) -> str:
    """One prophecy as the text two readings of the same atlas both answer with.

    Canonical means what it says: everything ordered by what it is rather than by where it
    was written, so a body reformatted, a comment added or two nodes swapped where nothing
    depends on the order compile to the same bytes. That is what makes :func:`digest` worth
    keeping -- a run picked up again asks whether the atlas is still the atlas it was, and an
    answer that changed when somebody reflowed a docstring would be no answer.

    Args:
      prophecy: The compiled atlas.

    Returns:
      JSON, keys sorted, one line: what a script diffs and what a person reads.
    """
    import json

    return json.dumps(_written(prophecy), sort_keys=True, ensure_ascii=False)


def _written(prophecy: Prophecy) -> dict[str, Any]:
    """One prophecy as the plain objects :func:`canonical` writes out.

    Read off the tuples themselves rather than field by field: everything here is a
    NamedTuple, so a field added to one later is a field the canonical text carries and the
    digest sees -- where a hand-written list of them would drop it without saying so, and
    two prophecies that differ would hash the same.

    Args:
      prophecy: The compiled atlas.

    Returns:
      Its nodes by id, its edges in order, its shapes by name and the prophecies under it by
      name -- each sorted, since the order a body happens to be written in is not part of
      what the atlas is.
    """
    return prophecy._asdict() | {
        "nodes": [one._asdict() for one in sorted(prophecy.nodes)],
        "edges": [one._asdict() for one in sorted(prophecy.edges, key=_ordered)],
        "shapes": [one._asdict() for one in sorted(prophecy.shapes)],
        "prophecies": [
            _written(one)
            for one in sorted(prophecy.prophecies, key=lambda one: one.name)
        ],
    }


def _ordered(edge: Edge) -> tuple[str, str, tuple[str, str, bool], str]:
    """One edge as something two of them can be sorted by, an absent guard and all."""
    return (edge.out_of, edge.into, edge.when or ("", "", False), edge.answers)


#: What a shipped prophecy is written with. Fixed rather than highest, so that the same
#: prophecy written by two installations is the same bytes -- a flowverse ships one, and a
#: file whose contents moved under a Python upgrade is a file every checkout re-writes.
_PROTOCOL = 5


def kept(prophecy: Prophecy) -> bytes:
    """One prophecy as the bytes a flowverse ships beside the atlas it compiled.

    Args:
      prophecy: The compiled atlas.

    Returns:
      What goes in `prophecy.pkl`.
    """
    import pickle

    return pickle.dumps(prophecy, protocol=_PROTOCOL)


#: The only classes a shipped prophecy is allowed to name. A pickle says which class to
#: build as it goes, and the reader that took it at its word would run whatever the file
#: asked for -- which the static reading of a flow, whose whole promise is that it executes
#: nothing, must not do for a file it found in a directory it was pointed at.
_SHAPES = frozenset({"Edge", "Field", "Node", "Prophecy", "Reads", "Shape", "When"})


def told(said: bytes) -> Prophecy | None:
    """One shipped prophecy read back, or None where those bytes are not one.

    Note:
      Nothing but a prophecy is built. A pickle names the class to build at every step, so
      one read as it comes runs whatever the file names -- and this file is read by the
      static reading of a flow, which is pointed at code nobody has read and promises to
      execute none of it. So the classes are held to this module's own tuples, and bytes
      naming anything else are bytes that are not a prophecy.

    Args:
      said: The bytes.

    Returns:
      The prophecy, or None for bytes that are not one -- truncated, written by something
      else, written by a humanize whose prophecies had another shape, or naming a class no
      prophecy is made of.
    """
    import io
    import pickle
    import sys as running

    class _Only(pickle.Unpickler):
        """An unpickler that builds this module's own tuples and refuses everything else."""

        def find_class(self, module: str, name: str) -> Any:
            """Refuses every class a prophecy is not made of.

            Args:
              module: The module the bytes name.
              name: The class in it they name.

            Returns:
              The class, for the tuples a prophecy is made of.

            Raises:
              UnpicklingError: For anything else, which is what makes reading this safe.
            """
            if module == __name__ and name in _SHAPES:
                return getattr(running.modules[__name__], name)
            raise pickle.UnpicklingError(f"a prophecy is not made of {module}.{name}")

    try:
        held = _Only(io.BytesIO(said)).load()
    except Exception:  # noqa: BLE001 -- anything a pickle raises is a file that is not one
        return None
    if not isinstance(held, Prophecy):
        return None
    try:
        canonical(held)
    except (AttributeError, TypeError, ValueError):
        # A named tuple of the right class holding the wrong things: written by a humanize
        # whose nodes had another shape, which is a prophecy to compile again rather than
        # one to walk.
        return None
    return held


class Shipped(NamedTuple):
    """What one flow's own directory ships beside its entry point.

    Attributes:
      at: The file it is in, which is `prophecy.pkl` beside the flow.
      prophecy: What it says, and None for bytes that are not a prophecy at all -- which is
        a file to compile again rather than a graph to guess at. Every reader of a shipped
        prophecy decides that for itself: one refuses the run, one says so as a finding.
    """

    at: Path
    prophecy: Prophecy | None


def shipped(under: str | os.PathLike[str]) -> Shipped | None:
    """The prophecy one flow's own directory ships, where it ships one.

    The one place `prophecy.pkl` is opened. Where it is, whether it is there, and what it
    takes to read it back are one rule rather than one per reader -- and what to do about a
    file that will not read back is each reader's own, since a run refuses and a checking
    says so.

    Args:
      under: The flow's own directory. A flow that is a single file has none, and passing
        the file is answered the same way as passing a directory with nothing in it.

    Returns:
      Where it is and what it says, or None where the flow ships nothing.
    """
    from . import PROPHECY

    at = Path(under) / PROPHECY
    if not at.is_file():
        return None
    return Shipped(at, told(at.read_bytes()))


def digest(prophecy: Prophecy) -> str:
    """What one compiled atlas is, in sixteen characters.

    What it is for is a run picked up again: what a run has already done is written down
    against the prophecy it was doing it in, and an atlas rewritten between two runs of it is a
    different prophecy whose nodes happen to share their names. Carrying on into it would be a
    run resuming into somewhere it has never been, so the digest is checked and a run whose
    prophecy has moved starts from the top.

    Args:
      prophecy: The compiled atlas.

    Returns:
      The first sixteen hex characters of the SHA-256 of :func:`canonical`.
    """
    import hashlib

    return hashlib.sha256(canonical(prophecy).encode()).hexdigest()[:16]
