"""Compiling an atlas: the reading that turns a body into the prophecy a run walks.

An ordinary flow is read by running it, and the one thing nothing can ask it is what it is
about to do. An atlas answers that question before anything runs: its body is a declaration
in a narrower Python, and this is the reading that holds it to that Python and compiles what
it declared into an :class:`~hmz.flows.atlas.Prophecy`.

Pure `ast`, like :mod:`hmz.flows.checking`, and for the same reason: the atlas most worth
compiling is one nobody has read yet -- generated, fetched, forked -- and a compiler that ran
what it was compiling would be the attack it exists to catch. So an atlas is read, and
compiled, and only then loaded to be run.

Every rule here is an error, and every one of them is decidable. That is the bargain an atlas
makes. The reading of an ordinary flow proves absences one function at a time and warns where
it cannot be sure; an atlas is written in the subset where there is nothing to be unsure
about. What flows along an edge either fits what the far end takes or it does not; a branch
either hangs off a logic node or it does not. That reading's warnings still come back over
the node bodies, and still do not block: a node body is ordinary Python, and is read as it.

The subset, in one place. A body holds only these:

- ``x = call(a, b)`` and ``call(a, b)`` -- one node apiece, whose arguments are names the
  body has bound, fields read off them, or one of the flow's own three: the agents, what it
  was called with, what it was set up with.
- ``if x:`` and ``if not x.field:``, with an ``else`` or without, which is a node's several
  ways out.
- ``while x:`` and ``while not x.field:``, which is that with an edge back to the node that
  answered the name being read.
- ``return`` and ``return x``, which is where the run ends.
- ``pass``, and the docstring.

And nothing else. Arithmetic, comprehensions, ``try``, ``with``, ``import``, a call written
inside another call: each of them is a thing a node does, and a node is where each of them
goes. An atlas is the shape of the work rather than the work.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import TYPE_CHECKING, NamedTuple

from .atlas import (
    AGENTS,
    CONFIG,
    INPUT,
    Edge,
    Field,
    Kind,
    Node,
    Prophecy,
    Reads,
    Shape,
    When,
    digest,
)

# The reading beside this one, whose parsing, whose rules and whose small readings of a tree
# this shares: an atlas is a flow, and the whole of what makes it one is read there. Its
# public surface is what a flow-checker is asked for, and these are two readings of one
# package sharing what one of them wrote down -- not a second copy of it, kept here to drift.
from .checking import (
    Finding,
    _annotated,  # pyright: ignore[reportPrivateUsage]
    _elements,  # pyright: ignore[reportPrivateUsage]
    _Mark,  # pyright: ignore[reportPrivateUsage]
    _Node,  # pyright: ignore[reportPrivateUsage]
    _parsed,  # pyright: ignore[reportPrivateUsage]
    _Read,  # pyright: ignore[reportPrivateUsage]
    _root,  # pyright: ignore[reportPrivateUsage]
    _rules,  # pyright: ignore[reportPrivateUsage]
    _tip,  # pyright: ignore[reportPrivateUsage]
    _unquoted,  # pyright: ignore[reportPrivateUsage]
    _Whole,  # pyright: ignore[reportPrivateUsage]
    _whole,  # pyright: ignore[reportPrivateUsage]
)

if TYPE_CHECKING:
    import os

__all__ = ["Prophesied", "is_atlas", "named_as", "prophesied"]

#: The shapes an atlas may carry that are not models: the plain kinds a node may take and
#: answer with. Anything else has fields, and a thing with fields is a model -- so that what
#: flows along an edge is something both ends can be held to.
PLAIN = ("str", "int", "float", "bool")

#: What a node that answers with nothing writes where a shape would go.
NOTHING = "None"

#: What one node's parameter says where a shape would be, for the two places an atlas hands
#: over what the run was started with rather than anything a node answered: the agent a mind
#: drives, and the whole tuple of them a supernode is handed.
ONE_AGENT = "@agent"
THE_AGENTS = "@agents"

#: How many things an atlas's entry point takes: the agents and what it is called with, and
#: for one that says it can be set up, the config after them.
_TAKES = 2
_AND_A_CONFIG = 3


class Prophesied(NamedTuple):
    """What compiling one atlas came to.

    Attributes:
      findings: One per thing the reading found, in file order. Every error among them is a
        reason the atlas did not compile.
      prophecy: The compiled atlas, or None where anything was an error: a graph built out of
        a body the reading refused would be a graph of something nobody wrote.
    """

    findings: tuple[Finding, ...]
    prophecy: Prophecy | None


def prophesied(
    flow: str | os.PathLike[str],
    *,
    name: str = "",
    whole: _Whole | None = None,
    through: tuple[tuple[str, str], ...] = (),
) -> Prophesied:
    """Reads an atlas without running it, and compiles what its body declared.

    Args:
      flow: The atlas: its directory, or the Python file a single-file one is.
      name: Which of the atlases the file holds, and "" for the one it holds under its own
        name -- the half after the colon in `official/review:pass`.
      whole: The files already parsed, for a caller that has read them, which is
        :func:`hmz.flows.checking.checked` handing on the reading it has already done.
      through: The atlases this one is being compiled inside -- where each is and what it
        was named -- so that a supernode reaching back into one of them is refused rather
        than followed forever.

    Returns:
      The findings and, where none of them is an error, the prophecy.
    """
    whole = _whole(flow) if whole is None else whole
    if not whole.compiled or whole.entered is None:
        return Prophesied(
            (
                _said(
                    "not-an-atlas",
                    whole.entry,
                    0,
                    "nothing in it is marked @atlas -- an atlas is a flow whose body is "
                    "compiled, which is how a file says which of its flows is one",
                ),
            ),
            None,
        )
    found = list(_rules(whole))
    for read in whole.read:
        found.extend(_dynamic(read))
    mark = next(
        (one for one in whole.entered.marks if one.atlas and one.name == name), None
    )
    if mark is None:
        held = sorted(one.name for one in whole.entered.marks if one.atlas)
        found.append(
            _said(
                "not-an-atlas",
                whole.entry,
                0,
                f"nothing in it is an atlas called {name!r} -- it holds "
                f"{', '.join(repr(one) for one in held)}",
            )
        )
        return Prophesied(tuple(found), None)
    prophecy, said = _compiled(
        whole, _gathered(whole), mark, name or _stem(whole), through
    )
    found.extend(said)
    if prophecy is not None:
        found.extend(_shipped(whole, prophecy))
    if any(one.severity == "error" for one in found):
        return Prophesied(tuple(found), None)
    return Prophesied(tuple(found), prophecy)


def _shipped(whole: _Whole, prophecy: Prophecy) -> list[Finding]:
    """Whether the prophecy a flow ships is the one its source compiles to.

    A flowverse may ship `prophecy.pkl` beside an atlas, and that is what a run of it walks.
    So a shipped prophecy which is no longer what the source says is a flow that does one
    thing and reads as another -- the one thing shipping it was meant to rule out.

    Args:
      whole: The parsed files.
      prophecy: What the source compiles to now.

    Returns:
      A `stale-prophecy` error where the two differ, and nothing where they agree, where the
      flow ships none, or where what it ships is another of the atlases its file holds.
    """
    from . import ENTRY
    from .atlas import shipped

    # Beside the entry point, which means the flow's own directory: a flow that is a single
    # file has none, and what is beside such a flow is the other flows.
    held = shipped(whole.entry.parent) if whole.entry.name == ENTRY else None
    if held is None:
        return []
    if held.prophecy is None:
        return [
            _said(
                "stale-prophecy",
                held.at,
                0,
                "the prophecy shipped here cannot be read back -- compile the atlas again, "
                "or take the file away and let each run compile it",
            )
        ]
    if held.prophecy.name != prophecy.name:
        return []
    was, now = digest(held.prophecy), digest(prophecy)
    if was == now:
        return []
    return [
        _said(
            "stale-prophecy",
            held.at,
            0,
            f"the prophecy shipped here is {was} and this source compiles to {now} -- a "
            "run walks the shipped one, so the flow does one thing and reads as another",
        )
    ]


def _dynamic(read: _Read) -> list[Finding]:
    """Every place one file reaches for a flow that is not an atlas.

    An atlas calls an atlas. `load` answers with a flow that may be anything -- a loop, a
    branch, a week of turns -- and a prophecy with one of those in it would be a graph with
    a hole where a node should be, which is the one thing a prophecy is for not having.

    Args:
      read: The file.

    Returns:
      A `dynamic-call` error per import of `load`, said where it is imported rather than
      where it is called: a name a file has is a name a body may reach for.
    """
    if not read.load_alias:
        return []
    return [
        _said(
            "dynamic-call",
            read.where,
            node.lineno,
            "an atlas calls an atlas: load() answers with a flow that may be anything, "
            "and what an atlas reaches another by is sub(), which is compiled into the "
            "prophecy reaching for it",
        )
        for node in ast.walk(read.tree)
        if isinstance(node, ast.ImportFrom)
        and node.module == "hmz.flows"
        and any(one.name == "load" for one in node.names)
    ]


def is_atlas(flow: str | os.PathLike[str]) -> bool:
    """Whether one flow is an atlas, which is what says which reading it gets.

    Read off the entry point alone rather than off everything the flow holds: the mark that
    says so is on a function in that file, and whoever is asking has a choice to make before
    paying for the whole reading.

    Args:
      flow: The flow: its directory, or the Python file a single-file one is.

    Returns:
      Whether anything in its entry point is marked `@atlas`. False for a flow that is not
      there, or will not parse -- which is a flow the other reading has plenty to say about.
    """
    from . import ENTRY

    at = Path(flow)
    entry = at / ENTRY if at.is_dir() else at
    if not entry.is_file():
        return False
    read = _parsed(entry)
    return not isinstance(read, Finding) and any(one.atlas for one in read.marks)


def named_as(under: Path, inside_: str = "") -> str:
    """What one atlas is called, given where its flow is and which of them was asked for.

    Args:
      under: The flow's own directory, or the file a single-file flow is.
      inside_: Which of the atlases the file holds was asked for, and "" for the one it
        holds under its own name.

    Returns:
      The name that prophecy carries, which is what a shipped one is matched against.
    """
    return inside_ or (under.stem if under.is_file() else under.name)


def _stem(whole: _Whole) -> str:
    """What the atlas a file holds under its own name is called, which is the file's."""
    from . import ENTRY

    at = whole.entry
    return named_as(at.parent if at.name == ENTRY else at)


# ---------------------------------------------------------------------------------------
# What the flow's files declare, gathered across them.
# ---------------------------------------------------------------------------------------


class _Held(NamedTuple):
    """Everything one atlas's files declare, gathered across them.

    A flow is a directory, and what it declares is spread over the files in it: the models
    in one, the nodes in another, the atlas itself in the entry point. What resolves a name
    in a body is therefore the whole directory rather than the file the body is in.

    Attributes:
      models: The pydantic models, by name -- what a node may take and answer with.
      crews: The NamedTuples, by name -- what a flow declares its agents as.
      nodes: The functions marked `@mind` or `@logic`, by name.
      atlases: The functions marked `@atlas`, by name, each beside the file it is in.
      subs: The atlases of other files this one named, `<local name>: <flow>` apiece.
      protos: The local name of each flow-facing interface, which is how an agent reads.
      fields: The local names of pydantic's `Field`, for reading whether one is required.
    """

    models: dict[str, ast.ClassDef]
    crews: dict[str, ast.ClassDef]
    nodes: dict[str, _Node]
    atlases: dict[str, tuple[_Read, _Mark]]
    subs: dict[str, str]
    protos: dict[str, str]
    fields: set[str]


def _gathered(whole: _Whole) -> _Held:
    """What every file of one atlas declares, in one place.

    Args:
      whole: The parsed files.

    Returns:
      The declarations, by name.
    """
    held = _Held({}, {}, {}, {}, {}, {}, set())
    for read in whole.read:
        held.models.update(read.models)
        held.crews.update(read.crews)
        held.nodes.update(read.nodes)
        held.subs.update(read.subs)
        held.protos.update(read.proto)
        held.fields.update(read.field_alias)
        for mark in read.marks:
            if mark.atlas:
                held.atlases[mark.node.name] = (read, mark)
    return held


# ---------------------------------------------------------------------------------------
# The entry point read: what it drives, what it is called with, what it answers with.
# ---------------------------------------------------------------------------------------


def _compiled(
    whole: _Whole,
    held: _Held,
    mark: _Mark,
    named: str,
    through: tuple[tuple[str, str], ...],
) -> tuple[Prophecy | None, list[Finding]]:
    """One atlas's entry point read, and its body walked into a prophecy.

    Args:
      whole: The parsed files.
      held: What those files declare, gathered across them.
      mark: The atlas being compiled.
      named: What to call the prophecy, which is the name the flow is asked for by.
      through: The atlases this one is inside, for the supernode that reaches back.

    Returns:
      The prophecy, or None where the reading refused it, and everything the reading found.
    """
    where = next((one.where for one in whole.read if mark in one.marks), whole.entry)
    found: list[Finding] = []
    node = mark.node
    params = [*node.args.posonlyargs, *node.args.args]
    if isinstance(node, ast.AsyncFunctionDef):
        found.append(
            _said(
                "unstatic-body",
                where,
                node.lineno,
                "an atlas is compiled rather than awaited -- what takes time is a node, "
                "and a node is where an `async def` goes",
            )
        )
    if not _TAKES <= len(params) <= _AND_A_CONFIG:
        found.append(
            _said(
                "unshaped-node",
                where,
                node.lineno,
                "an atlas takes the agents and what it is called with, and after them a "
                f"config for one that says it can be set up -- this takes {len(params)}",
            )
        )
        return None, found
    agents = _agents(params[0], held, where, found)
    takes = _kind(
        params[1].annotation, held, "what the atlas is called with", where, found
    )
    gives = _kind(node.returns, held, "what the atlas answers with", where, found)
    config = (
        _kind(params[2].annotation, held, "what an atlas is set up with", where, found)
        if len(params) == _AND_A_CONFIG
        else ""
    )
    answers = "" if gives == NOTHING else gives
    wiring = _Wiring(
        whole=whole,
        held=held,
        where=where,
        agents=agents,
        takes=takes,
        gives=answers,
        config=config,
        names={params[0].arg: AGENTS, params[1].arg: INPUT}
        | ({params[2].arg: CONFIG} if len(params) == _AND_A_CONFIG else {}),
        through=(*through, (_who(where, mark.name), named)),
    )
    wiring.walk(node.body)
    found.extend(wiring.found)
    if any(one.severity == "error" for one in found):
        return None, found
    return (
        Prophecy(
            name=named,
            takes=takes,
            gives=answers,
            config=config,
            agents=agents,
            nodes=tuple(wiring.nodes),
            edges=tuple(wiring.edges),
            shapes=tuple(_shapes(wiring.carried, held)),
            prophecies=tuple(wiring.prophecies),
        ),
        found,
    )


def _kind(
    annotation: ast.expr | None,
    held: _Held,
    called: str,
    where: Path,
    found: list[Finding],
) -> str:
    """One shape an atlas's entry point declares, having said so where it declares none.

    Args:
      annotation: The annotation.
      held: What the flow's files declare.
      called: What this place is, for a finding.
      where: The file.
      found: What to add a finding to.

    Returns:
      The shape, and "" for an annotation that names none.
    """
    shape = _shape(annotation, held)
    if shape:
        return shape
    found.append(
        _said(
            "unshaped-node",
            where,
            annotation.lineno if annotation is not None else 0,
            f"{called} is annotated {_wrote(annotation)}, which is no shape -- a model it "
            f"declares, one of {', '.join(PLAIN)}, or None for nothing at all",
        )
    )
    return ""


def _agents(
    param: ast.arg, held: _Held, where: Path, found: list[Finding]
) -> tuple[str, ...]:
    """What one atlas calls each of the agents it drives, read off its first parameter.

    An atlas declares its agents as a NamedTuple and not as a plain tuple of them, which is
    the one thing an ordinary flow may leave unsaid: every turn in a prophecy is a node that
    names the agent it drives, and a place with no name is a turn nothing can be pointed at.

    Args:
      param: The entry point's first parameter.
      held: What the flow's files declare.
      where: The file, for a finding.
      found: What to add a finding to.

    Returns:
      One name per agent, in the order the flow takes them.
    """
    crew = held.crews.get(_root(param.annotation) if param.annotation else "")
    if crew is None:
        found.append(
            _said(
                "unnamed-agents",
                where,
                param.lineno,
                "an atlas declares its agents as a NamedTuple of them, so that every turn "
                f"names the agent it drives -- {_wrote(param.annotation)} says only how "
                "many there are",
            )
        )
        return ()
    named: list[str] = []
    for one in crew.body:
        if not isinstance(one, ast.AnnAssign) or not isinstance(one.target, ast.Name):
            continue
        if not _annotated(one.annotation, held.protos):
            found.append(
                _said(
                    "unknown-agent",
                    where,
                    one.lineno,
                    f"{one.target.id} is annotated {_wrote(one.annotation)}, which is not "
                    "an agent -- what an atlas takes first is the agents it drives and "
                    "nothing else",
                )
            )
            continue
        named.append(one.target.id)
    return tuple(named)


# ---------------------------------------------------------------------------------------
# The body walked: one node per call, one edge per way from one to the next.
# ---------------------------------------------------------------------------------------

#: One loose end of a body being walked: the node it leaves and what has to hold to be
#: leaving by it, where "" is the way into the prophecy and None is a node's only way out.
type _Loose = list[tuple[str, When | None]]

#: What one node takes, as the reading of its declaration left it: the parameter's name and
#: the shape it holds, which may be one of the two agent kinds instead.
type _Takes = list[tuple[str, str]]


class _Declared(NamedTuple):
    """What one thing a body calls is, read off wherever it is declared.

    Attributes:
      kind: Which of the three kinds of node it is.
      takes: Its parameters, as `(name, shape)` pairs, where the shape may be one of the two
        agent kinds instead.
      gives: The shape it answers with, and "" for one that answers with nothing.
      rerun: Whether a run picked up inside it runs it again, or steps past it.
      under: For a supernode, the prophecy it is, by name. "" for every other node.
    """

    kind: Kind
    takes: _Takes
    gives: str
    rerun: bool
    under: str = ""


class _Wiring:
    """One atlas's body being walked into nodes and edges.

    A body is a chain of statements, and the loose ends between them are what the next
    statement is wired to. A branch splits the loose ends and guards each half; a loop wires
    them back to the node whose answer the loop reads; a return wires them to the end.
    """

    def __init__(
        self,
        *,
        whole: _Whole,
        held: _Held,
        where: Path,
        agents: tuple[str, ...],
        takes: str,
        gives: str,
        config: str,
        names: dict[str, str],
        through: tuple[tuple[str, str], ...],
    ) -> None:
        """Holds what one body is being walked into.

        Args:
          whole: The parsed files, for a supernode beside this one.
          held: What the flow's files declare.
          where: The file the body is in.
          agents: What the atlas calls each of the agents it drives.
          takes: The shape the atlas is called with.
          gives: The shape it answers with, and "" for one that answers with nothing.
          config: The shape it can be set up with, and "" for one that takes no setting up.
          names: The entry point's own parameters, by what the body calls each.
          through: The atlases this body is inside, for the supernode that reaches back.
        """
        self.whole = whole
        self.held = held
        self.where = where
        self.agents = agents
        self.takes = takes
        self.gives = gives
        self.config = config
        self.names = names
        self.through = through
        self.nodes: list[Node] = []
        self.edges: list[Edge] = []
        self.prophecies: list[Prophecy] = []
        self.found: list[Finding] = []
        #: What each name the body has bound holds, by shape. A name keeps the shape it was
        #: first bound with: a loop binds the same name every round, and one whose shape
        #: moved would be an edge that fits on the first round and not on the second.
        self.bound: dict[str, str] = {}
        #: How many nodes each callee has been so far, for the id the next one gets.
        self.seen: dict[str, int] = {}
        #: Every shape anything in this prophecy carries, for the shapes it is written with.
        self.carried: set[str] = {one for one in (takes, gives, config) if one}

    def walk(self, body: list[ast.stmt]) -> None:
        """Walks the whole of one atlas's body, and ends whatever it leaves open.

        Args:
          body: The entry point's statements.
        """
        for out_of, when in self._block(body, [("", None)]):
            # A path that runs off the bottom of the body ends the run, and answers with
            # nothing: an atlas that says it answers with something says so on every way
            # out of it, which is what a `return` there is.
            if self.gives:
                self.found.append(
                    _said(
                        "shape-mismatch",
                        self.where,
                        body[-1].lineno if body else 0,
                        f"the atlas answers with {self.gives}, and this way out of it ends "
                        "without returning anything",
                    )
                )
                break
            self.edges.append(Edge(out_of, "", when))
        if not self.nodes:
            self.found.append(
                _said(
                    "unstatic-body",
                    self.where,
                    body[0].lineno if body else 0,
                    "an atlas with no nodes in it is not a graph -- a body is a call "
                    "apiece to the minds and logics that do the work",
                )
            )

    # -- the statements -------------------------------------------------------------

    def _block(self, body: list[ast.stmt], loose: _Loose) -> _Loose:
        """One run of statements, each wired to whatever the last one left open.

        Args:
          body: The statements.
          loose: The ends coming in.

        Returns:
          The ends left open at the bottom, which is nothing at all after a `return`.
        """
        for at, one in enumerate(body):
            if _is_docstring(one, at) or isinstance(one, ast.Pass):
                continue
            if not loose:
                self._refuse(one, "nothing here can run: the atlas ends above it")
                return []
            if isinstance(one, ast.Assign) and isinstance(one.value, ast.Call):
                loose = self._call(one.value, self._target(one), loose)
            elif isinstance(one, ast.Expr) and isinstance(one.value, ast.Call):
                loose = self._call(one.value, "", loose)
            elif isinstance(one, ast.If):
                loose = self._branch(one, loose)
            elif isinstance(one, ast.While):
                loose = self._loop(one, loose)
            elif isinstance(one, ast.Return):
                self._return(one, loose)
                loose = []
            else:
                self._refuse(one, f"`{_wrote(one).splitlines()[0]}` is not one of them")
        return loose

    def _return(self, node: ast.Return, loose: _Loose) -> None:
        """A `return`, which is where the run ends.

        Args:
          node: The statement.
          loose: The ends arriving at it.
        """
        given = NOTHING
        answers = ""
        if node.value is not None:
            if not isinstance(node.value, ast.Name):
                self._refuse(
                    node,
                    "an atlas returns a name a node bound, whole -- a field of one is a "
                    "thing a logic node reads",
                )
                return
            answers = node.value.id
            given = self._shape_of(Reads(answers)) or NOTHING
        if given != (self.gives or NOTHING):
            self.found.append(
                _said(
                    "shape-mismatch",
                    self.where,
                    node.lineno,
                    f"the atlas answers with {self.gives or NOTHING} and this returns "
                    f"{given}",
                )
            )
        for out_of, when in loose:
            self.edges.append(Edge(out_of, "", when, answers))

    def _branch(self, node: ast.If, loose: _Loose) -> _Loose:
        """An `if`, which is the several ways out of the node above it.

        Args:
          node: The statement.
          loose: The ends arriving at it, each of which the branch guards.

        Returns:
          The ends both arms left open.
        """
        read = self._branched(node.test, loose)
        if read is None:
            return loose
        said, truth = read
        taken: _Loose = [(out_of, When(*said, truth)) for out_of, _ in loose]
        otherwise: _Loose = [(out_of, When(*said, not truth)) for out_of, _ in loose]
        return [*self._block(node.body, taken), *self._block(node.orelse, otherwise)]

    def _loop(self, node: ast.While, loose: _Loose) -> _Loose:
        """A `while`, which is a branch with an edge back to the node it reads.

        The node above the loop is its head: it answers the name the test reads, the body
        runs while that holds, and the body's last node wires back to the head -- so the
        head answers again with whatever the round changed, which is what ends the loop.

        Args:
          node: The statement.
          loose: The ends arriving at it, which is one and no more.

        Returns:
          The one end the loop leaves open, guarded by the test not holding.
        """
        if node.orelse:
            self._refuse(
                node, "a `while` in an atlas has no `else`: the loop is its edges"
            )
            return loose
        if len(loose) != 1:
            self._refuse(
                node,
                "a loop leaves the one node it reads again each round -- put a logic node "
                "between the branch above and this, so the loop has a head",
            )
            return loose
        read = self._branched(node.test, loose)
        if read is None:
            return loose
        head = loose[0][0]
        said, truth = read
        opens: _Loose = [(head, When(*said, truth))]
        for out_of, when in self._block(node.body, opens):
            self.edges.append(Edge(out_of, head, when))
        self._endless(node, head)
        ends: _Loose = [(head, When(*said, not truth))]
        return ends

    def _endless(self, node: ast.While, head: str) -> None:
        """Whether one loop's head can ever answer differently, which is whether it ends.

        Args:
          node: The loop.
          head: The node it reads again each round, by node id.
        """
        wrote = {
            one.id
            for said in ast.walk(node)
            if isinstance(said, ast.Assign)
            for one in said.targets
            if isinstance(one, ast.Name)
        }
        reading = self._above(head)
        if reading is not None and not wrote & {one.reads for one in reading.takes}:
            self.found.append(
                _said(
                    "dead-loop",
                    self.where,
                    node.lineno,
                    f"nothing in this loop changes what {head} reads, so it answers the "
                    "same thing every round and the loop never ends",
                )
            )

    def _branched(self, test: ast.expr, loose: _Loose) -> tuple[Reads, bool] | None:
        """What one branch reads, and whether the nodes above it may be branched on.

        Args:
          test: The `if` or `while` test.
          loose: The ends arriving at the branch.

        Returns:
          What the branch reads, and whether the first way out is the one taken when that
          reads as true. None where the branch is refused.
        """
        said = test.operand if isinstance(test, ast.UnaryOp) else test
        truth = not _is_not(test)
        read = self._reads(said)
        if read is None:
            self._refuse(
                test,
                f"a branch reads a name a node bound, or one field of it -- `{_wrote(test)}`"
                " is work, and work is what a logic node is for",
            )
            return None
        if self._shape_of(read) is None:
            self.found.append(
                _said(
                    "unbound-read",
                    self.where,
                    test.lineno,
                    f"nothing here has bound {_names(read)}",
                )
            )
            return None
        for out_of, when in loose:
            if when is not None:
                self._refuse(
                    test,
                    "a branch follows a node and not another branch -- an `elif`, or an "
                    "arm with nothing in it, is two decisions carried on one edge; put a "
                    "logic node between them so each way out belongs to what decided it",
                )
                return None
            above = self._above(out_of)
            if above is None:
                self._refuse(
                    test, "a branch follows a node, and nothing has run here yet"
                )
                return None
            if above.kind == "mind":
                self.found.append(
                    _said(
                        "branching-mind",
                        self.where,
                        test.lineno,
                        f"{out_of} is a turn, and a turn has one way out -- read what it "
                        "answered with a logic node, and branch on that",
                    )
                )
                return None
        return read, truth

    def _above(self, at: str) -> Node | None:
        """The node of that id, or None for the way into the prophecy."""
        return next((one for one in self.nodes if one.at == at), None)

    def _target(self, node: ast.Assign) -> str:
        """The one name an assignment binds, having said so where it binds anything else."""
        if len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            return node.targets[0].id
        self._refuse(
            node,
            "a node binds one name -- nothing here is unpacked, and nothing bound twice",
        )
        return ""

    # -- one node -------------------------------------------------------------------

    def _call(self, call: ast.Call, binds: str, loose: _Loose) -> _Loose:
        """One call, which is one node of the prophecy.

        Args:
          call: The call.
          binds: The name its answer is bound to, and "" for one nothing takes.
          loose: The ends arriving at it.

        Returns:
          The one end it leaves open.
        """
        if not isinstance(call.func, ast.Name):
            self._refuse(call, "a node is one call to a name this flow declares")
            return loose
        called = call.func.id
        if call.keywords or any(isinstance(one, ast.Starred) for one in call.args):
            self._refuse(
                call,
                "a node is handed its arguments in order, by name -- no keywords and "
                "nothing unpacked, so that what flows along each edge is one thing",
            )
            return loose
        declared = self._declared(call, called)
        if declared is None:
            return loose
        kind, takes, gives, rerun, under = declared
        reads = self._arguments(call, called, takes)
        if reads is None:
            return loose
        if not rerun and gives:
            self.found.append(
                _said(
                    "skipped-answer",
                    self.where,
                    call.lineno,
                    f"{called} is stepped past when a run is picked up inside it, and "
                    f"answers with {gives} -- a node a run steps past has no answer for "
                    "what comes next, so such a node answers with nothing",
                )
            )
        at = self._id(called)
        self.nodes.append(
            Node(
                at=at,
                kind=kind,
                calls=under or called,
                takes=tuple(reads),
                binds=binds,
                gives=gives,
                rerun=rerun,
                under=under,
            )
        )
        self.carried.update(
            shape for _, shape in takes if shape not in (ONE_AGENT, THE_AGENTS)
        )
        if gives:
            self.carried.add(gives)
        if binds:
            self._binds(call, binds, gives)
        for out_of, when in loose:
            self.edges.append(Edge(out_of, at, when))
        return [(at, None)]

    def _declared(self, call: ast.Call, called: str) -> _Declared | None:
        """What the thing one call names is, and what it takes and answers with.

        Args:
          call: The call, for a finding.
          called: The name it calls.

        Returns:
          Its declaration, or None where the name is not something an atlas may call.
        """
        held = self.held.nodes.get(called)
        if held is not None:
            return self._noded(call, called, held)
        if called in self.held.atlases or called in self.held.subs:
            return self._supernode(call, called)
        self._refuse(
            call,
            f"{called} is not a node: an atlas calls what it marked @mind or @logic, an "
            "atlas beside it, or one it named with sub()",
        )
        return None

    def _noded(self, call: ast.Call, called: str, held: _Node) -> _Declared | None:
        """One `@mind` or `@logic` node, read off the function that declares it.

        Args:
          call: The call, for a finding.
          called: The name it calls.
          held: What the mark said.

        Returns:
          Its declaration, or None where the function's shapes cannot be read.
        """
        params = [*held.node.args.posonlyargs, *held.node.args.args]
        takes: _Takes = []
        for at, one in enumerate(params):
            agent = bool(_annotated(one.annotation, self.held.protos))
            if agent and at == 0 and held.kind == "mind":
                takes.append((one.arg, ONE_AGENT))
                continue
            if agent:
                self.found.append(
                    _said(
                        "unagented-node",
                        self.where,
                        call.lineno,
                        f"{called} takes an agent as {one.arg} -- a mind takes one and it "
                        "is the first thing it takes, and a logic takes none at all",
                    )
                )
                return None
            shape = _shape(one.annotation, self.held)
            if not shape or shape == NOTHING:
                self.found.append(
                    _said(
                        "unshaped-node",
                        self.where,
                        call.lineno,
                        f"{called} takes {one.arg} annotated {_wrote(one.annotation)}, "
                        "which is no shape -- a node takes a model this flow declares, or "
                        f"one of {', '.join(PLAIN)}",
                    )
                )
                return None
            takes.append((one.arg, shape))
        if held.kind == "mind" and not (takes and takes[0][1] == ONE_AGENT):
            self.found.append(
                _said(
                    "unagented-node",
                    self.where,
                    call.lineno,
                    f"{called} is a turn and takes no agent -- what a mind takes first is "
                    "the agent it drives",
                )
            )
            return None
        gives = _shape(held.node.returns, self.held)
        if not gives:
            self.found.append(
                _said(
                    "unshaped-node",
                    self.where,
                    call.lineno,
                    f"{called} answers with {_wrote(held.node.returns)}, which is no "
                    f"shape -- a model this flow declares, one of {', '.join(PLAIN)}, or "
                    "None for nothing at all",
                )
            )
            return None
        kind: Kind = "mind" if held.kind == "mind" else "logic"
        return _Declared(
            kind, takes, "" if gives == NOTHING else gives, rerun=held.rerun
        )

    def _supernode(self, call: ast.Call, called: str) -> _Declared | None:
        """One supernode: a whole atlas, compiled into the prophecy reaching for it.

        Args:
          call: The call, for a finding.
          called: The name it calls.

        Returns:
          Its declaration, or None where the atlas under it did not compile.
        """
        named = self.held.subs.get(called, called)
        under = next((one for one in self.prophecies if one.name == named), None)
        if under is None:
            under = self._under(call, called, named)
            if under is None:
                return None
            self.prophecies.append(under)
        if under.config:
            self.found.append(
                _said(
                    "unstatic-body",
                    self.where,
                    call.lineno,
                    f"{named} says it can be set up, and a supernode is a node: what is "
                    "set up is the run, so an atlas that takes a config is one to start "
                    "rather than one to reach for",
                )
            )
            return None
        short = set(under.agents) - set(self.agents)
        if short:
            self.found.append(
                _said(
                    "unknown-agent",
                    self.where,
                    call.lineno,
                    f"{named} drives {', '.join(sorted(short))}, which this atlas does "
                    "not -- a supernode is handed the agents of the run around it, by the "
                    "names it calls them",
                )
            )
            return None
        return _Declared(
            "atlas",
            [("agents", THE_AGENTS), ("said", under.takes)],
            under.gives,
            rerun=True,
            under=named,
        )

    def _under(self, call: ast.Call, called: str, named: str) -> Prophecy | None:
        """The prophecy one supernode is, compiled where it stands.

        Args:
          call: The call, for a finding.
          called: The name it calls.
          named: The atlas it is, as this flow named it.

        Returns:
          The prophecy, or None where compiling it found an error.
        """
        beside = self.held.atlases.get(called)
        if beside is not None:
            read, mark = beside
            if self._circular(call, named, _who(read.where, mark.name)):
                return None
            made, found = _compiled(self.whole, self.held, mark, named, self.through)
            self.found.extend(found)
            return made
        from . import ENTRY, find, inside

        at = Path(find(named))
        if self._circular(call, named, _who(at, inside(named))):
            return None
        held = prophesied(
            at.parent if at.name == ENTRY else at,
            name=inside(named),
            through=self.through,
        )
        self.found.extend(
            one
            for one in held.findings
            # A supernode is compiled where it is reached for, so what its own reading
            # found is said once. The name it was reached by is what places it.
            if one.severity == "error" or one.code != "unsaid-flow"
        )
        if held.prophecy is None and not any(
            one.severity == "error" for one in held.findings
        ):
            self.found.append(
                _said(
                    "not-an-atlas",
                    self.where,
                    call.lineno,
                    f"{named} is not an atlas -- an atlas calls an atlas, and reaches an "
                    "ordinary flow through nothing at all",
                )
            )
            return None
        return None if held.prophecy is None else held.prophecy._replace(name=named)

    def _circular(self, call: ast.Call, named: str, who: str) -> bool:
        """Whether one supernode reaches back into an atlas already being compiled.

        Asked of where the atlas is and what it is called there rather than of the name the
        body wrote: one atlas is reached as `deeper` beside it and as `cycle:deeper` from
        anywhere else, and a check that compared spellings would follow that forever.

        Args:
          call: The call, for a finding.
          named: The atlas, as this body named it.
          who: Which atlas it is: where it is declared, and what it is called there.

        Returns:
          Whether it does, having said so where it does.
        """
        if who not in {one for one, _ in self.through}:
            return False
        self.found.append(
            _said(
                "circular-atlas",
                self.where,
                call.lineno,
                f"{named} is being compiled already -- a supernode is one graph inside "
                f"another, and {' inside '.join((*(said for _, said in self.through), named))}"
                " has no bottom",
            )
        )
        return True

    def _arguments(
        self, call: ast.Call, called: str, takes: _Takes
    ) -> list[Reads] | None:
        """Where each of one node's arguments comes from, held to what it takes.

        Args:
          call: The call.
          called: What it calls, for a finding.
          takes: The node's parameters as `(name, shape)` pairs.

        Returns:
          One per argument, or None where the call does not fit what it calls.
        """
        if len(call.args) != len(takes):
            self.found.append(
                _said(
                    "shape-mismatch",
                    self.where,
                    call.lineno,
                    f"{called} takes {len(takes)} and is handed {len(call.args)}",
                )
            )
            return None
        reads: list[Reads] = []
        for one, (param, shape) in zip(call.args, takes, strict=True):
            read = self._reads(one)
            if read is None:
                self._refuse(
                    one,
                    "an argument is a name a node bound or a field of one -- "
                    f"`{_wrote(one)}` is work, and work is what a node is for",
                )
                return None
            if not self._fits(call, called, param, shape, read):
                return None
            reads.append(read)
        return reads

    def _fits(
        self, call: ast.Call, called: str, param: str, shape: str, read: Reads
    ) -> bool:
        """Whether what flows into one parameter is what that parameter takes.

        Args:
          call: The call, for a finding.
          called: What it calls.
          param: The parameter's name.
          shape: What it takes, or one of the two agent kinds.
          read: The name and field being handed to it.

        Returns:
          Whether it fits, having said why where it does not.
        """
        if shape in (ONE_AGENT, THE_AGENTS):
            return self._agented(call, called, param, shape, read)
        given = self._shape_of(read)
        if given is None:
            self.found.append(
                _said(
                    "unbound-read",
                    self.where,
                    call.lineno,
                    f"nothing here has bound {_names(read)}",
                )
            )
            return False
        if not given or not _same(given, shape, self.held):
            self.found.append(
                _said(
                    "shape-mismatch",
                    self.where,
                    call.lineno,
                    f"{called} takes {param}: {shape}, and {_names(read)} is "
                    f"{given or _wrote(None)}",
                )
            )
            return False
        return True

    def _agented(
        self, call: ast.Call, called: str, param: str, shape: str, read: Reads
    ) -> bool:
        """Whether what flows into an agent's place is one of the run's own agents.

        Args:
          call: The call, for a finding.
          called: What it calls.
          param: The parameter's name.
          shape: Which of the two agent kinds it is.
          read: The name and field being handed to it.

        Returns:
          Whether it fits, having said why where it does not.
        """
        reads, field = read
        one = shape == ONE_AGENT
        if reads != AGENTS or bool(field) != one:
            self.found.append(
                _said(
                    "unagented-node",
                    self.where,
                    call.lineno,
                    f"{called} takes {'one of the agents' if one else 'the agents'} as "
                    f"{param}, and is handed {_names(read)}",
                )
            )
            return False
        if one and field not in self.agents:
            self.found.append(
                _said(
                    "unknown-agent",
                    self.where,
                    call.lineno,
                    f"this atlas drives {', '.join(self.agents) or 'nothing'}, and "
                    f"{_names(read)} is none of them",
                )
            )
            return False
        return True

    # -- the names a body binds and reads --------------------------------------------

    def _reads(self, node: ast.expr) -> Reads | None:
        """One name a body reads, and the field read off it.

        Args:
          node: The expression.

        Returns:
          `(the name, the field)`, the field being "" for the whole of it -- or None where
          this is not a name at all.
        """
        if isinstance(node, ast.Name):
            return Reads(self.names.get(node.id, node.id))
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            return Reads(self.names.get(node.value.id, node.value.id), node.attr)
        return None

    def _shape_of(self, read: Reads) -> str | None:
        """What one name, or one field of it, holds.

        Args:
          read: The name and the field read off it.

        Returns:
          The shape; "" for something bound whose field is no shape an edge may carry; and
          None for a name nothing here has bound.
        """
        reads, field = read
        held = {INPUT: self.takes, CONFIG: self.config}.get(reads) or self.bound.get(
            reads
        )
        if held is None or reads == AGENTS:
            return None
        if not field:
            return held
        model = self.held.models.get(held)
        if model is None:
            return None
        return next(
            (
                _shape(one.annotation, self.held) or ""
                for one in model.body
                if isinstance(one, ast.AnnAssign)
                and isinstance(one.target, ast.Name)
                and one.target.id == field
            ),
            None,
        )

    def _binds(self, call: ast.Call, binds: str, gives: str) -> None:
        """Binds one name to what the node answered with, once and for the whole body.

        Args:
          call: The call, for a finding.
          binds: The name.
          gives: The shape it now holds.
        """
        held = self.bound.get(binds)
        if held is not None and held != gives:
            self.found.append(
                _said(
                    "shape-mismatch",
                    self.where,
                    call.lineno,
                    f"{binds} is {held} above and {gives or NOTHING} here -- a name keeps "
                    "the shape it was bound with, so that an edge which fits on the first "
                    "round fits on every round",
                )
            )
            return
        self.bound[binds] = gives

    def _id(self, called: str) -> str:
        """The node id one more call to the same thing gets."""
        self.seen[called] = at = self.seen.get(called, 0) + 1
        return called if at == 1 else f"{called}:{at}"

    def _refuse(self, node: ast.stmt | ast.expr, said: str) -> None:
        """Says one thing the body holds that the subset an atlas is written in does not."""
        self.found.append(_said("unstatic-body", self.where, node.lineno, said))


# ---------------------------------------------------------------------------------------
# The shapes: what may flow along an edge, and whether one fits another.
# ---------------------------------------------------------------------------------------


def _shape(annotation: ast.expr | None, held: _Held) -> str | None:
    """What one annotation says flows there, by shape name.

    Args:
      annotation: The annotation, which may be missing.
      held: What the flow's files declare.

    Returns:
      The model's name, one of :data:`PLAIN`, `None` for a place that carries nothing, or
      None where the annotation is no shape at all. `X | None` is `X`: a shape that may be
      missing is the shape, and whether it is there is what a branch reads.
    """
    if annotation is None:
        return None
    if isinstance(annotation, ast.Constant) and annotation.value is None:
        return NOTHING
    # A quoted annotation is the annotation: a flow written under `from __future__ import
    # annotations` and one written without it declare the same node.
    said = _unquoted(annotation)
    if said is None:
        return None
    if said is not annotation:
        return _shape(said, held)
    annotation = said
    if isinstance(annotation, ast.Constant):
        return None
    if isinstance(annotation, ast.BinOp) and isinstance(annotation.op, ast.BitOr):
        sides = [_shape(annotation.left, held), _shape(annotation.right, held)]
        said = [one for one in sides if one is not None and one != NOTHING]
        return said[0] if len(said) == 1 and None not in sides else None
    if isinstance(annotation, ast.Subscript) and _tip(annotation.value) == "Annotated":
        return _shape(_elements(annotation.slice)[0], held)
    if not isinstance(annotation, ast.Name):
        return None
    if annotation.id in held.models or annotation.id in PLAIN:
        return annotation.id
    return NOTHING if annotation.id == NOTHING else None


def _same(given: str, wanted: str, held: _Held) -> bool:
    """Whether what one node answers with is what the next one takes.

    The name where both are the same shape, and the fields where they are not: a model that
    holds every field another requires, at the same shape apiece, is a model that model can
    be built from -- which is what an edge between two of them means.

    Args:
      given: The shape flowing in.
      wanted: The shape the far end takes.
      held: What the flow's files declare.

    Returns:
      Whether it fits.
    """
    if given == wanted:
        return True
    one, two = held.models.get(given), held.models.get(wanted)
    if one is None or two is None:
        return False
    holds = {field.name: field.shape for field in _fields(one, held)}
    return all(
        holds.get(field.name) == field.shape
        for field in _fields(two, held)
        if field.required
    )


def _fields(model: ast.ClassDef, held: _Held) -> list[Field]:
    """Every field one model declares, and whether it refuses to be built without it.

    Args:
      model: The class.
      held: What the flow's files declare, for a base declared beside it.

    Returns:
      One per field, the bases' first: a model is what it inherits and what it adds.
    """
    said: list[Field] = []
    for base in model.bases:
        beside = held.models.get(_root(base))
        if beside is not None and beside is not model:
            said.extend(_fields(beside, held))
    for one in model.body:
        if not isinstance(one, ast.AnnAssign) or not isinstance(one.target, ast.Name):
            continue
        name = one.target.id
        if name.startswith("_") or _root(one.annotation) == "ClassVar":
            continue
        said = [was for was in said if was.name != name]
        said.append(
            Field(name, _wrote(one.annotation), required=_required(one.value, held))
        )
    return said


def _required(value: ast.expr | None, held: _Held) -> bool:
    """Whether a field with that default refuses to be built without being given one.

    Args:
      value: What the field was declared with, and None where it was declared with nothing.
      held: What the flow's files declare, for what each of them calls pydantic's `Field`.

    Returns:
      Whether a model of it cannot be built without being handed one.
    """
    if value is None:
        return True
    if isinstance(value, ast.Call) and _root(value.func) in held.fields:
        named = {one.arg for one in value.keywords}
        return not (value.args or named & {"default", "default_factory"})
    return False


def _shapes(carried: set[str], held: _Held) -> list[Shape]:
    """Every shape one prophecy carries, written out with the fields each holds.

    Args:
      carried: The shape names, as the compiling gathered them.
      held: What the flow's files declare.

    Returns:
      One per shape, in name order. A plain kind has no fields, having none to have -- and
      nor has a model another flow declares, which a supernode's edges name and this flow
      cannot read.
    """
    return [
        Shape(name, tuple(_fields(model, held)) if model is not None else ())
        for name in sorted(carried)
        if name and name != NOTHING
        for model in (held.models.get(name),)
    ]


# ---------------------------------------------------------------------------------------
# The small readings the rules above are written in terms of.
# ---------------------------------------------------------------------------------------


def _who(where: Path, name: str) -> str:
    """Which atlas one name resolves to: where it is declared, and what it is called there.

    Args:
      where: The file it is declared in.
      name: What the mark called it inside that file.

    Returns:
      The two, as one string -- what a supernode reaching back into a compiling is caught by.
    """
    return f"{where.resolve()}::{name}"


def _said(code: str, where: Path, line: int, why: str) -> Finding:
    """One finding, which for an atlas is always a reason it did not compile."""
    return Finding(code, "error", where, line, why)


def _is_docstring(node: ast.stmt, at: int) -> bool:
    """Whether one statement is the docstring a body opens with."""
    return (
        at == 0
        and isinstance(node, ast.Expr)
        and isinstance(node.value, ast.Constant)
        and isinstance(node.value.value, str)
    )


def _is_not(node: ast.expr) -> bool:
    """Whether one test is `not` something, which is the branch's other way out."""
    return isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not)


def _names(read: Reads) -> str:
    """How one name and the field read off it read in a finding."""
    reads, field = read
    said = {
        AGENTS: "the agents",
        INPUT: "what the atlas was called with",
        CONFIG: "the config",
    }.get(reads, reads)
    return f"{said}.{field}" if field else said


def _wrote(node: ast.expr | ast.stmt | None) -> str:
    """One piece of a body as it was written, for a finding to quote back."""
    return "nothing" if node is None else ast.unparse(node)
