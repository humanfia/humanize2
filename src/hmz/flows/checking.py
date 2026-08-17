"""The static read of a flow's legality: what will not run, said before anything runs it.

:mod:`hmz.flows.driving` refuses a flow as it loads it -- the wrong arity, a moment no agent
can run -- but loading a flow means running its file, and the flow most worth checking is one
nobody has read yet: generated, fetched, forked and edited. This is the reading that executes
nothing. Pure `ast` over every Python file the flow's directory holds, answering with findings
rather than raising, so that whatever asked can say everything that is wrong at once.

What a severity means is one line apiece. An error is a flow that cannot run, cannot be
answered, or cannot end -- something no run of it survives. A warning is a flow that runs,
and a run of it that may be regretted: a loop with no bound of its own, a shaped answer read
without a guard, a config that takes anything.

And what the reading does not claim is said as plainly. Every rule is the proof of an
absence -- no exit in this loop, no bound in this function, no guard on this name -- worked
out one function at a time. Nothing here proves an exit reachable or a bound tight, and
nothing follows a value through a call: a flow that keeps its loop in one function and its
bound in another is a flow this reading trusts, and a checker that guessed further would
refuse flows that run.
"""

from __future__ import annotations

import ast
import contextlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Literal, NamedTuple, Protocol

from .agent import Agent, Driven, Person, Session

if TYPE_CHECKING:
    import os
    from collections.abc import Iterator

__all__ = [
    "Capability",
    "Finding",
    "briefed",
    "catalogue",
    "checked",
    "offered",
    "surface",
]


class Finding(NamedTuple):
    """One thing the reading of a flow found, where it found it.

    Attributes:
      code: Which rule found it, as one hyphenated word -- `dead-loop`, `unknown-ask`.
      severity: What finding it is. An error is a flow that cannot run, cannot be answered
        or cannot end; a warning is a flow that runs and may be regretted.
      where: The file it is in.
      line: The line, 1-based, or 0 for a finding about the whole file.
      said: What is wrong, said the way `NotAFlow` says it.
    """

    code: str
    severity: Literal["error", "warning"]
    where: Path
    line: int
    said: str


def surface(protocol: type) -> frozenset[str]:
    """What one of the flow-facing interfaces asks for, by name.

    The one reading of a protocol's members, shared by the checker's own rules and by the
    tests that hold the drivers to the same interfaces -- two readings of what an agent
    answers to would be two readings to drift apart.

    Args:
      protocol: The interface.

    Returns:
      One name per member it declares, its own and whatever it is itself an interface of.
      `__call__` is among them where it is declared, an agent and a session both being things
      a flow calls; the rest of the dunders are Python's and are not part of the contract.
    """
    said: set[str] = set()
    for one in protocol.__mro__:
        if one in (object, Protocol):
            continue
        held = set(vars(one)) | set(getattr(one, "__annotations__", {}))
        said.update(
            name for name in held if not name.startswith("_") or name == "__call__"
        )
    return frozenset(said)


def offered() -> frozenset[str]:
    """Every name a flow may import from `hmz.flows`, which is the whole of its vocabulary.

    What the module says it offers rather than what happens to be reachable on it: a name
    that works today because a submodule leaked it is a name the next release takes away.

    Returns:
      The names: what `__all__` declares, what is handed through by name from the layers a
      flow does not import, and the two modules handed through whole.
    """
    # The package's own tables, read by the package's own checker: private to every
    # flow, and one copy rather than a second one kept here to drift.
    from . import _ELSEWHERE, _MODULES  # pyright: ignore[reportPrivateUsage]
    from . import __all__ as declared

    return frozenset(declared) | frozenset(_ELSEWHERE) | frozenset(_MODULES)


def checked(flow: str | os.PathLike[str]) -> tuple[Finding, ...]:
    """Reads a flow without running it, and answers with everything that reading found.

    Every Python file the flow's directory holds is read -- the entry point and whatever it
    imports beside it -- except what is under its `skills/`, which is content for the agents
    rather than code this process runs. Nothing is imported and nothing is executed, so this
    is safe to point at a flow nobody has read: what running the file would refuse is the
    second reading, :mod:`hmz.flows.proving`, which runs it in a process of its own.

    Args:
      flow: The flow: its directory, or the Python file a single-file flow is.

    Returns:
      One finding per thing found, in file order, and nothing at all for a flow this reading
      has nothing to say about -- which is not a proof, only a reading with nothing to say.
    """
    from . import ENTRY

    at = Path(flow)
    if at.is_dir():
        entry = at / ENTRY
        files = [
            one
            for one in sorted(at.rglob("*.py"))
            if "__pycache__" not in one.relative_to(at).parts
            # The skills are content: one directory per skill, laid out the way every one
            # of these CLIs reads a skill in, and nothing in one is imported by the flow.
            and one.relative_to(at).parts[0] != "skills"
        ]
    else:
        entry = at
        files = [at] if at.is_file() else []
    if not entry.is_file():
        return (
            Finding(
                "not-a-flow",
                "error",
                at,
                0,
                "no flow to read: a flow is a directory with an __init__.py in it",
            ),
        )

    found: list[Finding] = []
    read: list[_Read] = []
    for one in files:
        held = _parsed(one)
        if isinstance(held, Finding):
            found.append(held)
        else:
            read.append(held)

    marked = any(one.marks for one in read)
    entered = next((one for one in read if one.where == entry), None)
    if entered is not None and not marked:
        found.append(
            Finding(
                "not-a-flow",
                "error",
                entry,
                0,
                "nothing in it is marked @flow() -- a flow is a function marked with it, "
                "which is how a file says which of the functions in it is one",
            )
        )
    if entered is not None and ast.get_docstring(entered.tree) is None:
        found.append(
            Finding(
                "unsaid-flow",
                "warning",
                entry,
                0,
                "the flow says nothing about itself -- the first line of this file's "
                "docstring is what every list of flows shows for it",
            )
        )

    # What the flow declared about moments anywhere in its files, for the hooks it hangs:
    # a place annotated in the entry point covers a hook hung in the module beside it.
    declared = frozenset(moment for one in read for moment in one.moments_declared)
    asks = _Asks()
    for one in read:
        found.extend(_imports(one))
        found.extend(_marks(one))
        found.extend(_hooks(one, declared))
        found.extend(_functions(one, asks))
    return tuple(found)


# ---------------------------------------------------------------------------------------
# Reading one file: what it imports, what it marks, and what it declares.
# ---------------------------------------------------------------------------------------

#: The kinds of thing a flow drives, each the name of one flow-facing interface. What a
#: tracked name may be asked is read off the interface itself, so the checker and the
#: drivers are held to one surface.
_KINDS: dict[str, type] = {
    "agent": Agent,
    "person": Person,
    "session": Session,
    "driven": Driven,
}

#: How the local names for those interfaces read where a flow imports them.
_PROTOCOLS = {
    "Agent": "agent",
    "Person": "person",
    "Session": "session",
    "Driven": "driven",
}

#: What an element of a plain tuple of agents may still be asked by name: the tuple's own
#: two methods. A named place is a field of the NamedTuple the flow declared instead.
_OF_A_TUPLE = frozenset({"count", "index"})


class _Mark(NamedTuple):
    """One function a file marked with `@flow`, and what the mark said."""

    node: ast.FunctionDef | ast.AsyncFunctionDef
    name: str
    resumable: bool


@dataclass
class _Read:
    """One file, parsed, and what one pass over its top collected."""

    where: Path
    tree: ast.Module
    #: The local names of :func:`hmz.flows.flow`, `Moment` and pydantic's `Field`.
    flow_alias: set[str] = field(default_factory=set[str])
    moment_alias: set[str] = field(default_factory=set[str])
    field_alias: set[str] = field(default_factory=set[str])
    #: Local name -> which interface, for every flow-facing interface the file imports.
    proto: dict[str, str] = field(default_factory=dict[str, str])
    #: The NamedTuple and pydantic model classes the file itself declares.
    crews: dict[str, ast.ClassDef] = field(default_factory=dict[str, ast.ClassDef])
    models: dict[str, ast.ClassDef] = field(default_factory=dict[str, ast.ClassDef])
    #: Names bound only under `if TYPE_CHECKING:`, which a running flow cannot read.
    unread: set[str] = field(default_factory=set[str])
    #: Every name the file binds at module level as it runs, which excuses the above.
    bound: set[str] = field(default_factory=set[str])
    marks: list[_Mark] = field(default_factory=list["_Mark"])
    #: Every `Moment.X` written inside an annotation, which is a flow declaring a need.
    moments_declared: set[str] = field(default_factory=set[str])


def _parsed(where: Path) -> _Read | Finding:
    """One file read into a tree, or the finding that it could not be.

    Args:
      where: The file.

    Returns:
      What was read, or an `unread` error: a file that will not parse is a flow that will
      not load, said here rather than left for the loading to hit.
    """
    try:
        tree = ast.parse(where.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, SyntaxError, ValueError) as why:
        line = getattr(why, "lineno", 0) or 0
        return Finding(
            "unread",
            "error",
            where,
            line,
            f"nothing here can be read as Python -- {why}",
        )
    read = _Read(where, tree)
    _collected(read, tree.body, type_checking=False)
    # Bound under TYPE_CHECKING and nowhere else: a name a type checker reads and a
    # running flow cannot, which is the one thing `unread-annotation` is about.
    read.unread -= read.bound
    for node in ast.walk(tree):
        if isinstance(node, (ast.AnnAssign, ast.arg)) and node.annotation is not None:
            read.moments_declared.update(_moments_in(node.annotation, read))
    return read


def _collected(read: _Read, body: list[ast.stmt], *, type_checking: bool) -> None:
    """Walks one file's statements for what the rules read off its top.

    Args:
      read: What is being collected into.
      body: The statements, at whatever depth the walk has reached.
      type_checking: Whether these statements are under `if TYPE_CHECKING:`, where a name
        is bound for a type checker and for nothing that runs.
    """
    for node in body:
        if isinstance(node, ast.ImportFrom) and node.module == "hmz.flows":
            for alias in node.names:
                bound = alias.asname or alias.name
                if type_checking:
                    read.unread.add(bound)
                    continue
                read.bound.add(bound)
                if alias.name == "flow":
                    read.flow_alias.add(bound)
                elif alias.name == "Moment":
                    read.moment_alias.add(bound)
                elif alias.name in _PROTOCOLS:
                    read.proto[bound] = _PROTOCOLS[alias.name]
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                bound = (alias.asname or alias.name).split(".")[0]
                (read.unread if type_checking else read.bound).add(bound)
                if (
                    isinstance(node, ast.ImportFrom)
                    and node.module == "pydantic"
                    and alias.name == "Field"
                    and not type_checking
                ):
                    read.field_alias.add(alias.asname or alias.name)
        elif isinstance(node, (ast.Assign, ast.AnnAssign)) and not type_checking:
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            read.bound.update(one.id for one in targets if isinstance(one, ast.Name))
        elif isinstance(node, ast.ClassDef) and not type_checking:
            read.bound.add(node.name)
            bases = {_root(base) for base in node.bases}
            if "NamedTuple" in bases:
                read.crews[node.name] = node
            elif "BaseModel" in bases or bases & set(read.models):
                read.models[node.name] = node
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if not type_checking:
                read.bound.add(node.name)
            mark = _marked(node, read)
            if mark is not None and not type_checking:
                read.marks.append(mark)
        elif isinstance(node, ast.If):
            under = type_checking or _root(node.test) == "TYPE_CHECKING"
            _collected(read, node.body, type_checking=under)
            _collected(read, node.orelse, type_checking=type_checking)
        elif isinstance(node, (ast.Try, ast.With)):
            _collected(read, node.body, type_checking=type_checking)


def _marked(node: ast.FunctionDef | ast.AsyncFunctionDef, read: _Read) -> _Mark | None:
    """The mark on one function, where it carries one.

    Args:
      node: The function.
      read: The file it is in, for what the decorator is called there.

    Returns:
      The mark, or None for a function that is not a flow.
    """
    for one in node.decorator_list:
        if isinstance(one, ast.Name) and one.id in read.flow_alias:
            return _Mark(node, "", resumable=False)
        if (
            isinstance(one, ast.Call)
            and isinstance(one.func, ast.Name)
            and one.func.id in read.flow_alias
        ):
            name = ""
            resumable = False
            for said in one.keywords:
                if said.arg == "name" and isinstance(said.value, ast.Constant):
                    name = str(said.value.value)
                elif said.arg == "resumable" and isinstance(said.value, ast.Constant):
                    resumable = bool(said.value.value)
            return _Mark(node=node, name=name, resumable=resumable)
    return None


def _root(node: ast.expr) -> str:
    """The name at the root of one expression, or "" where there is none."""
    while isinstance(node, ast.Attribute):
        node = node.value
    return node.id if isinstance(node, ast.Name) else ""


def _moments_in(annotation: ast.expr, read: _Read) -> set[str]:
    """Every moment one annotation names, which is a place saying what it needs."""
    return {
        node.attr
        for node in ast.walk(annotation)
        if isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and node.value.id in read.moment_alias
    }


# ---------------------------------------------------------------------------------------
# The import rules: one import, and only the names it offers.
# ---------------------------------------------------------------------------------------


def _imports(read: _Read) -> Iterator[Finding]:
    """What one file imports of humanize's, held to the one import a flow writes.

    Args:
      read: The file.

    Yields:
      A `foreign-import` error per import of a module of humanize's own that is not
      `hmz.flows`, and an `unknown-name` error per name asked of `hmz.flows` that it does
      not offer.
    """
    offers: frozenset[str] | None = None
    for node in ast.walk(read.tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] == "hmz" and alias.name != "hmz.flows":
                    yield Finding(
                        "foreign-import",
                        "error",
                        read.where,
                        node.lineno,
                        f"a flow imports hmz.flows and nothing else of humanize's -- "
                        f"{alias.name} is humanize's own business, and a flow that names "
                        "it breaks whenever humanize moves it",
                    )
        elif isinstance(node, ast.ImportFrom) and node.module:
            said = node.module
            if said.split(".")[0] != "hmz":
                continue
            if said != "hmz.flows":
                yield Finding(
                    "foreign-import",
                    "error",
                    read.where,
                    node.lineno,
                    f"a flow imports hmz.flows and nothing else of humanize's -- "
                    f"{said} is humanize's own business, and a flow that names it "
                    "breaks whenever humanize moves it",
                )
                continue
            if offers is None:
                offers = offered()
            for alias in node.names:
                if alias.name not in offers:
                    yield Finding(
                        "unknown-name",
                        "error",
                        read.where,
                        node.lineno,
                        f"hmz.flows does not offer {alias.name!r} -- what a flow may "
                        "import from it is what it hands through, and a name it does "
                        "not hold fails at the first run",
                    )


# ---------------------------------------------------------------------------------------
# The mark rules: what the entry point declares, read as the loader will read it.
# ---------------------------------------------------------------------------------------

#: How many arguments a resumable flow's entry point takes at the least: the agents, the
#: task, and somewhere for what the last run of it wrote to be handed back in.
_WITH_A_STATE = 3

#: The one sentence the loader says about a flow that does not state its arity, said here
#: too so that the two readings refuse the same flow in the same words.
_UNSIZED = (
    "a flow is a function marked @flow() taking (agents, task), whose agents are "
    "annotated with a tuple of a fixed length -- how many agents the flow drives -- or "
    "with a NamedTuple of them, which also says what each is for"
)


def _marks(read: _Read) -> Iterator[Finding]:
    """What each flow one file marks says about itself, held to what a run needs said.

    Args:
      read: The file.

    Yields:
      `unsized-agents` and `unread-annotation` errors for an arity a run cannot read back,
      `stateless-resume` for a flow that says it can be picked up and takes nothing to be
      picked up with, `twice-named` for two flows under one name, `state-kept` for kept
      state nothing ever clears, and the config findings for the model an entry declares.
    """
    named: set[str] = set()
    configured: set[str] = set()
    for mark in read.marks:
        if mark.name in named:
            yield Finding(
                "twice-named",
                "warning",
                read.where,
                mark.node.lineno,
                f"two flows here are both {_said_name(mark.name)} -- the first of them "
                "wins, and the second can never be run",
            )
        named.add(mark.name)
        yield from _sized(mark, read)
        yield from _resumes(mark, read)
        for model in _settings(mark.node, read):
            if model not in configured:
                configured.add(model)
                yield from _configured(read.models[model], read)


def _said_name(name: str) -> str:
    """How a flow's name reads in a finding about two of them."""
    return f"called {name!r}" if name else "the one their file holds under its own name"


def _sized(mark: _Mark, read: _Read) -> Iterator[Finding]:
    """Whether one flow states how many agents it drives where a run can read it back."""
    args = mark.node.args
    params = [*args.posonlyargs, *args.args]
    kind = params[0].annotation if params else None
    if kind is None:
        yield Finding("unsized-agents", "error", read.where, mark.node.lineno, _UNSIZED)
        return
    unread = sorted(_names_in(kind) & read.unread)
    if unread:
        yield Finding(
            "unread-annotation",
            "error",
            read.where,
            mark.node.lineno,
            f"the flow's agents cannot be read here ({', '.join(unread)} is imported "
            "under TYPE_CHECKING) -- import what the annotation names at runtime, so "
            "the count it states can be checked",
        )
        return
    said = _unquoted(kind)
    if said is None:
        return
    if isinstance(said, ast.Name) and said.id == "tuple":
        yield Finding(
            "unsized-agents",
            "error",
            read.where,
            mark.node.lineno,
            _UNSIZED,
        )
        return
    if (
        isinstance(said, ast.Subscript)
        and _root(said.value) == "tuple"
        and any(
            isinstance(one, ast.Constant) and one.value is Ellipsis
            for one in _elements(said.slice)
        )
    ):
        yield Finding(
            "unsized-agents",
            "error",
            read.where,
            mark.node.lineno,
            _UNSIZED,
        )


def _resumes(mark: _Mark, read: _Read) -> Iterator[Finding]:
    """Whether a flow that says it can be picked up takes anything to be picked up with."""
    if not mark.resumable:
        return
    args = mark.node.args
    params = [*args.posonlyargs, *args.args]
    taken = len(params)
    third = params[2].annotation if taken >= _WITH_A_STATE else None
    settles = third is not None and bool(_names_in(third) & set(read.models))
    if taken < _WITH_A_STATE or (taken == _WITH_A_STATE and settles):
        yield Finding(
            "stateless-resume",
            "error",
            read.where,
            mark.node.lineno,
            "the flow says it can be picked up, and takes nothing to be picked up with "
            "-- a resumable flow is handed a dict as its last argument, holding what it "
            "wrote there last time",
        )
        return
    yield from _kept(mark, read, params[-1].arg)


def _kept(mark: _Mark, read: _Read, state: str) -> Iterator[Finding]:
    """Whether kept state something writes is state anything ever clears.

    Args:
      mark: The resumable flow.
      read: Its file.
      state: What its entry point calls the dict it is handed.
    """
    held = {state}
    wrote = 0
    cleared = False
    for node in ast.walk(mark.node):
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            if isinstance(target, ast.Name) and any(
                isinstance(one, ast.Name) and one.id in held
                for one in ast.walk(node.value)
            ):
                held.add(target.id)
        elif isinstance(node, ast.Subscript) and isinstance(node.ctx, ast.Store):
            if _root(node.value) in held:
                wrote = wrote or node.lineno
        elif (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and _root(node.func.value) in held
        ):
            if node.func.attr in {"update", "setdefault"}:
                wrote = wrote or node.lineno
            elif node.func.attr == "clear":
                cleared = True
    if wrote and not cleared:
        yield Finding(
            "state-kept",
            "warning",
            read.where,
            wrote,
            "the flow writes its kept state and never clears it -- a run that is over "
            "leaves what the next run here opens on, so a loop that has ended clears "
            "what it kept",
        )


def _settings(
    node: ast.FunctionDef | ast.AsyncFunctionDef, read: _Read
) -> Iterator[str]:
    """The config models one entry point declares, of the ones its own file holds."""
    args = node.args
    for param in [*args.posonlyargs, *args.args][2:]:
        if param.annotation is not None:
            yield from (
                name for name in _names_in(param.annotation) if name in read.models
            )


def _configured(model: ast.ClassDef, read: _Read) -> Iterator[Finding]:
    """One config model, held to refusing what it does not take and saying what it does.

    Args:
      model: The model a flow's entry point says it can be set up with.
      read: The file it is declared in.

    Yields:
      A `loose-config` warning for one that takes anything, and an `unsaid-field` warning
      per field that says nothing about itself -- the descriptions are what whoever sets
      the flow up is shown, and a field without one is a question nobody can answer.
    """
    if not _strict(model, read, set()):
        yield Finding(
            "loose-config",
            "warning",
            read.where,
            model.lineno,
            "the config takes anything -- set model_config to extra: forbid or frozen: "
            "True, so a setting that is misspelled is refused rather than quietly "
            "ignored",
        )
    for node in model.body:
        if not isinstance(node, ast.AnnAssign) or not isinstance(node.target, ast.Name):
            continue
        name = node.target.id
        if name.startswith("_") or _root(node.annotation) == "ClassVar":
            continue
        bare = node.value is None
        unsaid = (
            isinstance(node.value, ast.Call)
            and _root(node.value.func) in read.field_alias
            and not any(one.arg == "description" for one in node.value.keywords)
        )
        if bare or unsaid:
            yield Finding(
                "unsaid-field",
                "warning",
                read.where,
                node.lineno,
                f"the config field {name!r} says nothing about itself -- give it a "
                "Field(description=...), which is what whoever sets the flow up is "
                "shown",
            )


def _strict(model: ast.ClassDef, read: _Read, seen: set[str]) -> bool:
    """Whether one config model refuses what it does not take, its local bases included."""
    seen.add(model.name)
    for node in model.body:
        if (
            isinstance(node, ast.Assign)
            and any(
                isinstance(one, ast.Name) and one.id == "model_config"
                for one in node.targets
            )
            and isinstance(node.value, ast.Dict)
        ):
            said = {
                key.value: value.value
                for key, value in zip(node.value.keys, node.value.values, strict=True)
                if isinstance(key, ast.Constant) and isinstance(value, ast.Constant)
            }
            if said.get("extra") == "forbid" or said.get("frozen") is True:
                return True
    return any(
        _strict(read.models[base], read, seen)
        for base in {_root(one) for one in model.bases}
        if base in read.models and base not in seen
    )


# ---------------------------------------------------------------------------------------
# The hook rule: a moment only some backends run is a moment the flow says it needs.
# ---------------------------------------------------------------------------------------


def _hooks(read: _Read, declared: frozenset[str]) -> Iterator[Finding]:
    """Every moment one file hangs a hook on, held to the moments the flow declared.

    Args:
      read: The file.
      declared: Every moment named in an annotation anywhere in the flow, which is how a
        place says what the agent filling it has to run.

    Yields:
      An `unsaid-moment` warning per hook hung on a moment only some backends reach that
      no place declares: the run finds out from `Unhooked`, mid-flow, where a declaration
      would have refused the agent before its first turn.
    """
    everywhere: frozenset[str] | None = None
    for node in ast.walk(read.tree):
        if not (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "on"
            and node.args
        ):
            continue
        moment = node.args[0]
        if not (
            isinstance(moment, ast.Attribute)
            and isinstance(moment.value, ast.Name)
            and moment.value.id in read.moment_alias
        ):
            continue
        if everywhere is None:
            # Read off the live enum rather than copied out of it, so that a moment
            # humanize adds is a moment this rule already knows. Fetched here rather
            # than imported with the module: the vocabulary lives beside the drivers.
            from hmz.agents import EVERYWHERE

            everywhere = frozenset(one.name for one in EVERYWHERE)
        if moment.attr in everywhere or moment.attr in declared:
            continue
        yield Finding(
            "unsaid-moment",
            "warning",
            read.where,
            node.lineno,
            f"a hook is hung on Moment.{moment.attr}, which only some backends run, and "
            "no place declares it -- write Annotated[Agent, Moment."
            f"{moment.attr}] where the place is declared, so an agent that cannot run "
            "it is refused before its first turn rather than hours in",
        )


# ---------------------------------------------------------------------------------------
# The function rules: what is asked of what the flow drives, and how its loops end.
# ---------------------------------------------------------------------------------------


class _Crew(NamedTuple):
    """A tuple of agents as one function holds it: the places, or only the count.

    Attributes:
      fields: One (name, kinds) pair per place for a NamedTuple of them, or None for a
        plain tuple, which named nothing. Kinds of None is a place whose annotation this
        file cannot read, which is tracked and asked nothing.
      kinds: The kind of each element by position, for a plain tuple that said them.
    """

    fields: tuple[tuple[str, frozenset[str] | None], ...] | None
    kinds: tuple[frozenset[str] | None, ...] = ()

    def held(self) -> frozenset[str] | None:
        """What one element of this crew is, where every place is the same thing."""
        each = (
            [kinds for _, kinds in self.fields]
            if self.fields is not None
            else list(self.kinds)
        )
        if not each or any(not one for one in each):
            return None
        return frozenset(kind for one in each if one for kind in one)


class _Answer(NamedTuple):
    """One name holding what a turn answered, and how the turn was taken."""

    shaped: bool
    suppressed: bool
    line: int


@dataclass
class _Asks:
    """What each kind of tracked thing may be asked, read once per checking."""

    _surfaces: dict[str, frozenset[str]] = field(
        default_factory=dict[str, frozenset[str]]
    )

    def allowed(self, kinds: frozenset[str]) -> frozenset[str]:
        """Every name something of these kinds answers to."""
        held: frozenset[str] = frozenset()
        for kind in kinds:
            if kind not in self._surfaces:
                self._surfaces[kind] = surface(_KINDS[kind])
            held |= self._surfaces[kind]
        return held


@dataclass
class _Scope:
    """One function being read: what is bound to what, and what was found so far."""

    read: _Read
    asks: _Asks
    bindings: dict[str, frozenset[str] | _Crew] = field(
        default_factory=dict[str, "frozenset[str] | _Crew"]
    )
    answers: dict[str, _Answer] = field(default_factory=dict[str, "_Answer"])
    guarded: set[str] = field(default_factory=set[str])
    #: Attribute reads off a shaped, suppressed answer: (name, line) apiece.
    reads: list[tuple[str, int]] = field(default_factory=list[tuple[str, int]])
    #: Whether the function holds a bound of its own -- a spent() call, a range(), an
    #: ordering comparison against a number -- which is what excuses its loops.
    bounded: bool = False
    findings: list[Finding] = field(default_factory=list[Finding])

    def forgot(self, name: str) -> None:
        """Stops tracking one name, which is what any doubtful binding does to it."""
        self.bindings.pop(name, None)
        self.answers.pop(name, None)


def _functions(read: _Read, asks: _Asks) -> Iterator[Finding]:
    """Reads every function in one file for what it asks and how its loops end.

    Args:
      read: The file.
      asks: The interface surfaces, shared across the files of one checking.

    Yields:
      The findings, function by function.
    """
    for node in read.tree.body:
        yield from _defined(node, read, asks, {})


def _defined(
    node: ast.stmt,
    read: _Read,
    asks: _Asks,
    inherited: dict[str, frozenset[str] | _Crew],
) -> Iterator[Finding]:
    """One top-level statement, read for the functions in it."""
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        yield from _function(node, read, asks, inherited)
    elif isinstance(node, ast.ClassDef):
        for held in node.body:
            yield from _defined(held, read, asks, inherited)
    elif isinstance(node, ast.If):
        for held in [*node.body, *node.orelse]:
            yield from _defined(held, read, asks, inherited)


def _function(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    read: _Read,
    asks: _Asks,
    inherited: dict[str, frozenset[str] | _Crew],
) -> Iterator[Finding]:
    """One function: bindings followed in order, then its loops read against them.

    Args:
      node: The function.
      read: Its file.
      asks: The interface surfaces.
      inherited: What the enclosing function had bound, which a closure reads.
    """
    scope = _Scope(read, asks, bindings=dict(inherited))
    args = node.args
    params = [*args.posonlyargs, *args.args, *args.kwonlyargs]
    for param in params:
        scope.forgot(param.arg)
        kind = _annotated(param.annotation, read)
        crew = _crewed(param.annotation, read) if not kind else None
        if kind:
            scope.bindings[param.arg] = kind
        elif crew is not None:
            scope.bindings[param.arg] = crew
    for one in (args.vararg, args.kwarg):
        if one is not None:
            scope.forgot(one.arg)
    _statements(node.body, scope, read, asks)
    yield from scope.findings
    for name, line in scope.reads:
        if name not in scope.guarded:
            yield Finding(
                "unguarded-answer",
                "warning",
                read.where,
                line,
                f"{name} may be None here -- a suppressed turn held to a shape answers "
                "with nothing when it fails, and a field read off nothing ends the run "
                "where a guard would have taken the turn again",
            )
    if not _yields(node):
        yield from _loops(node, scope)


def _annotated(annotation: ast.expr | None, read: _Read) -> frozenset[str] | None:
    """What kinds of driven thing one annotation says a name is, or None for no answer."""
    said = _unquoted(annotation)
    if said is None:
        return None
    if isinstance(said, ast.Subscript) and _root(said.value) == "Annotated":
        first = next(iter(_elements(said.slice)), None)
        return _annotated(first, read)
    if isinstance(said, ast.Subscript) and _root(said.value) == "Optional":
        first = next(iter(_elements(said.slice)), None)
        return _annotated(first, read)
    if isinstance(said, ast.BinOp) and isinstance(said.op, ast.BitOr):
        left = _annotated(said.left, read)
        right = _annotated(said.right, read)
        if left is None and right is None:
            return None
        # `Agent | None` is an agent to be guarded; `Agent | Session` is either, and is
        # asked only what both answer to being too strict -- so it is asked the union.
        return (left or frozenset()) | (right or frozenset())
    if isinstance(said, ast.Constant) and said.value is None:
        return frozenset()
    if isinstance(said, ast.Name) and said.id in read.proto:
        return frozenset({read.proto[said.id]})
    return None


def _crewed(annotation: ast.expr | None, read: _Read) -> _Crew | None:
    """The tuple of agents one annotation declares, where this file can read it.

    A crew it is not sure of is no crew at all: a NamedTuple with one place this file
    cannot read as an interface is somebody's data rather than the agents, and tracking
    it would find askings that are nobody's business here.
    """
    said = _unquoted(annotation)
    if said is None:
        return None
    if isinstance(said, ast.Name) and said.id in read.crews:
        fields = [
            (node.target.id, _annotated(node.annotation, read))
            for node in read.crews[said.id].body
            if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name)
        ]
        if fields and all(kinds for _, kinds in fields):
            return _Crew(tuple(fields))
        return None
    if isinstance(said, ast.Subscript) and _root(said.value) == "tuple":
        kinds = tuple(
            _annotated(one, read)
            for one in _elements(said.slice)
            if not (isinstance(one, ast.Constant) and one.value is Ellipsis)
        )
        if kinds and all(kinds):
            return _Crew(None, kinds)
    return None


def _unquoted(annotation: ast.expr | None) -> ast.expr | None:
    """One annotation with any quoting read through, since a string is still the words."""
    if isinstance(annotation, ast.Constant) and isinstance(annotation.value, str):
        try:
            return ast.parse(annotation.value, mode="eval").body
        except (SyntaxError, ValueError):
            return None
    return annotation


def _elements(slice_: ast.expr) -> tuple[ast.expr, ...]:
    """The elements of one subscript, one or many."""
    return tuple(slice_.elts) if isinstance(slice_, ast.Tuple) else (slice_,)


def _names_in(annotation: ast.expr) -> set[str]:
    """Every plain name one annotation mentions, quoting and all."""
    said = _unquoted(annotation)
    if said is None:
        return set()
    return {node.id for node in ast.walk(said) if isinstance(node, ast.Name)}


def _statements(body: list[ast.stmt], scope: _Scope, read: _Read, asks: _Asks) -> None:
    """Walks statements in order, checking what they ask and following what they bind."""
    for node in body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            scope.findings.extend(_function(node, read, asks, dict(scope.bindings)))
            scope.forgot(node.name)
        elif isinstance(node, ast.ClassDef):
            for held in node.body:
                if isinstance(held, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    scope.findings.extend(_function(held, read, asks, {}))
            scope.forgot(node.name)
        elif isinstance(node, ast.Assign):
            _expression(node.value, scope)
            _assigned(node.targets, node.value, scope)
        elif isinstance(node, ast.AnnAssign):
            if node.value is not None:
                _expression(node.value, scope)
            if isinstance(node.target, ast.Name):
                scope.forgot(node.target.id)
                kind = _annotated(node.annotation, scope.read)
                if kind:
                    scope.bindings[node.target.id] = kind
                elif node.value is not None:
                    _assigned([node.target], node.value, scope)
            else:
                _expression(node.target, scope)
        elif isinstance(node, ast.AugAssign):
            _expression(node.value, scope)
            if isinstance(node.target, ast.Name):
                scope.forgot(node.target.id)
        elif isinstance(node, (ast.For, ast.AsyncFor)):
            _expression(node.iter, scope)
            _bound_target(node.target, _element_of(node.iter, scope), scope)
            _statements(node.body, scope, read, asks)
            _statements(node.orelse, scope, read, asks)
        elif isinstance(node, (ast.While, ast.If)):
            _guards(node.test, scope)
            _expression(node.test, scope)
            _statements(node.body, scope, read, asks)
            _statements(node.orelse, scope, read, asks)
        elif isinstance(node, (ast.With, ast.AsyncWith)):
            for item in node.items:
                _expression(item.context_expr, scope)
                if item.optional_vars is not None:
                    _bound_target(item.optional_vars, None, scope)
            _statements(node.body, scope, read, asks)
        elif isinstance(node, ast.Try):
            _statements(node.body, scope, read, asks)
            for handler in node.handlers:
                if handler.name:
                    scope.forgot(handler.name)
                _statements(handler.body, scope, read, asks)
            _statements(node.orelse, scope, read, asks)
            _statements(node.finalbody, scope, read, asks)
        elif isinstance(node, ast.Assert):
            _guards(node.test, scope)
            _expression(node.test, scope)
        elif isinstance(node, ast.Delete):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    scope.forgot(target.id)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                scope.forgot((alias.asname or alias.name).split(".")[0])
        elif isinstance(node, (ast.Return, ast.Expr)):
            if node.value is not None:
                _expression(node.value, scope)
        elif isinstance(node, ast.Raise):
            for held in (node.exc, node.cause):
                if held is not None:
                    _expression(held, scope)
        elif isinstance(node, ast.Match):
            _expression(node.subject, scope)
            for case in node.cases:
                for name in _captured(case.pattern):
                    scope.forgot(name)
                if case.guard is not None:
                    _expression(case.guard, scope)
                _statements(case.body, scope, read, asks)


def _captured(pattern: ast.pattern) -> set[str]:
    """Every name one match pattern binds, all of which stop being tracked."""
    said: set[str] = set()
    for node in ast.walk(pattern):
        if isinstance(node, (ast.MatchAs, ast.MatchStar)) and node.name:
            said.add(node.name)
        elif isinstance(node, ast.MatchMapping) and node.rest:
            said.add(node.rest)
    return said


def _assigned(targets: list[ast.expr], value: ast.expr, scope: _Scope) -> None:
    """Follows one assignment: what the targets are now bound to, if anything tracked."""
    held = _valued(value, scope)
    for target in targets:
        if isinstance(target, ast.Name):
            scope.forgot(target.id)
            if isinstance(held, _Answer):
                scope.answers[target.id] = held
            elif held is not None:
                scope.bindings[target.id] = held
        elif isinstance(target, (ast.Tuple, ast.List)):
            _unpacked(target, value, scope)
        else:
            _expression(target, scope)


def _unpacked(target: ast.Tuple | ast.List, value: ast.expr, scope: _Scope) -> None:
    """Follows a tuple unpacking, which is how `(agent,) = agents` hands a place over."""
    crew = scope.bindings.get(value.id) if isinstance(value, ast.Name) else None
    each = crew.held() if isinstance(crew, _Crew) else None
    kinds: list[frozenset[str] | None] | None = None
    if isinstance(crew, _Crew):
        held = (
            [one for _, one in crew.fields]
            if crew.fields is not None
            else list(crew.kinds)
        )
        kinds = held if len(held) == len(target.elts) else None
    for at, one in enumerate(target.elts):
        if isinstance(one, ast.Name):
            scope.forgot(one.id)
            bound = kinds[at] if kinds is not None else each
            if isinstance(crew, _Crew) and bound:
                scope.bindings[one.id] = bound
        elif isinstance(one, (ast.Tuple, ast.List)):
            _unpacked(one, value, scope)
        elif isinstance(one, ast.Starred) and isinstance(one.value, ast.Name):
            scope.forgot(one.value.id)


def _bound_target(target: ast.expr, kind: frozenset[str] | None, scope: _Scope) -> None:
    """Binds a loop or with target: to the element kind where there is one, else to doubt."""
    if isinstance(target, ast.Name):
        scope.forgot(target.id)
        if kind:
            scope.bindings[target.id] = kind
    elif isinstance(target, (ast.Tuple, ast.List)):
        for one in target.elts:
            _bound_target(one, None, scope)


def _element_of(iterable: ast.expr, scope: _Scope) -> frozenset[str] | None:
    """What iterating one expression yields, where it is a tracked crew."""
    if isinstance(iterable, ast.Name):
        held = scope.bindings.get(iterable.id)
        if isinstance(held, _Crew):
            return held.held()
    return None


def _valued(value: ast.expr, scope: _Scope) -> frozenset[str] | _Crew | _Answer | None:
    """What one expression is, as far as the bindings can say.

    Args:
      value: The expression on the right of an assignment.
      scope: The function so far.

    Returns:
      A kind for something driven, a crew for a tuple of them, an answer for what a turn
      of one said, and None for anything this reading does not follow -- which stops the
      target being tracked rather than mistracking it.
    """
    if isinstance(value, ast.Name):
        return scope.bindings.get(value.id)
    if isinstance(value, ast.Await):
        return _valued(value.value, scope)
    if isinstance(value, ast.Attribute):
        held = (
            scope.bindings.get(value.value.id)
            if isinstance(value.value, ast.Name)
            else None
        )
        if isinstance(held, _Crew) and held.fields is not None:
            return next(
                (kinds for name, kinds in held.fields if name == value.attr), None
            )
        return None
    if isinstance(value, ast.Subscript):
        held = (
            scope.bindings.get(value.value.id)
            if isinstance(value.value, ast.Name)
            else None
        )
        return held.held() if isinstance(held, _Crew) else None
    if isinstance(value, ast.Call):
        return _called(value, scope)
    return None


def _called(value: ast.Call, scope: _Scope) -> frozenset[str] | _Crew | _Answer | None:
    """What calling one thing answers with, where what is called is tracked."""
    func = value.func
    opened = isinstance(func, ast.Attribute) and func.attr in {"new", "clone"}
    target = func.value if isinstance(func, ast.Attribute) and opened else func
    held = _valued(target, scope) if opened else None
    if isinstance(func, ast.Attribute) and func.attr == "new":
        if isinstance(held, frozenset) and held:
            return frozenset({"session"})
        return None
    if isinstance(func, ast.Attribute) and func.attr == "clone":
        return held if isinstance(held, frozenset) else None
    spoken = _valued(func, scope)
    if isinstance(spoken, frozenset) and spoken:
        # Calling an agent or a session is a turn, and what it answers is an answer.
        return _Answer(
            shaped=any(one.arg == "schema" for one in value.keywords),
            suppressed=any(
                one.arg == "suppress"
                and isinstance(one.value, ast.Constant)
                and one.value.value is True
                for one in value.keywords
            ),
            line=value.lineno,
        )
    if isinstance(func, ast.Attribute) and func.attr in {"aturn", "pursue", "apursue"}:
        asked = _valued(func.value, scope)
        if isinstance(asked, frozenset) and asked:
            return _Answer(
                shaped=any(one.arg == "schema" for one in value.keywords),
                suppressed=any(
                    one.arg == "suppress"
                    and isinstance(one.value, ast.Constant)
                    and one.value.value is True
                    for one in value.keywords
                ),
                line=value.lineno,
            )
    return None


#: The comparisons that read as a bound: a count against something, ordered.
_ORDERED = (ast.Lt, ast.LtE, ast.Gt, ast.GtE)


def _expression(node: ast.expr, scope: _Scope) -> None:
    """Checks one expression tree against the bindings, and notes what it holds.

    What is checked is every attribute asked of a tracked name; what is noted is every
    guard on an answer, and whether the function holds a bound of its own.
    """
    if isinstance(node, ast.Attribute):
        _asked(node, scope)
        _expression(node.value, scope)
        return
    if isinstance(node, ast.Call):
        if isinstance(node.func, ast.Attribute) and node.func.attr == "spent":
            scope.bounded = True
        if isinstance(node.func, ast.Name) and node.func.id == "range":
            scope.bounded = True
        for one in [node.func, *node.args]:
            _expression(one, scope)
        for kw in node.keywords:
            _expression(kw.value, scope)
        return
    if isinstance(node, ast.Compare):
        if any(isinstance(op, _ORDERED) for op in node.ops) and any(
            isinstance(side, ast.Constant)
            and isinstance(side.value, (int, float))
            and not isinstance(side.value, bool)
            for side in [node.left, *node.comparators]
        ):
            scope.bounded = True
        _guards(node, scope)
        for one in [node.left, *node.comparators]:
            _expression(one, scope)
        return
    if isinstance(node, ast.BoolOp):
        _guards(node, scope)
        for one in node.values:
            _expression(one, scope)
        return
    if isinstance(node, ast.IfExp):
        _guards(node.test, scope)
        for one in (node.test, node.body, node.orelse):
            _expression(one, scope)
        return
    if isinstance(node, ast.NamedExpr):
        _expression(node.value, scope)
        scope.forgot(node.target.id)
        held = _valued(node.value, scope)
        if isinstance(held, _Answer):
            scope.answers[node.target.id] = held
        elif held is not None:
            scope.bindings[node.target.id] = held
        return
    if isinstance(node, ast.Lambda):
        return  # its own scope, and nothing in it runs here
    if isinstance(node, (ast.ListComp, ast.SetComp, ast.GeneratorExp, ast.DictComp)):
        _comprehended(node, scope)
        return
    for one in ast.iter_child_nodes(node):
        if isinstance(one, ast.expr):
            _expression(one, scope)


def _comprehended(
    node: ast.ListComp | ast.SetComp | ast.GeneratorExp | ast.DictComp,
    scope: _Scope,
) -> None:
    """One comprehension, read with its own targets bound for as long as it lasts."""
    before = dict(scope.bindings)
    for gen in node.generators:
        _expression(gen.iter, scope)
        _bound_target(gen.target, _element_of(gen.iter, scope), scope)
        for test in gen.ifs:
            _guards(test, scope)
            _expression(test, scope)
    if isinstance(node, ast.DictComp):
        _expression(node.key, scope)
        _expression(node.value, scope)
    else:
        _expression(node.elt, scope)
    scope.bindings = before


def _guards(test: ast.expr, scope: _Scope) -> None:
    """Notes every answer one test stands guard over.

    A guard is the answer read as a truth -- `if worked:` -- or compared against None,
    either way round. Noted wherever it appears rather than matched to a branch: what the
    warning is for is the answer nobody tested at all.
    """
    if isinstance(test, ast.Name):
        scope.guarded.add(test.id)
    elif isinstance(test, ast.UnaryOp) and isinstance(test.operand, ast.Name):
        scope.guarded.add(test.operand.id)
    elif isinstance(test, ast.BoolOp):
        for one in test.values:
            _guards(one, scope)
    elif isinstance(test, ast.Compare):
        sides = [test.left, *test.comparators]
        against_none = any(
            isinstance(side, ast.Constant) and side.value is None for side in sides
        )
        if against_none:
            for side in sides:
                if isinstance(side, ast.Name):
                    scope.guarded.add(side.id)


def _asked(node: ast.Attribute, scope: _Scope) -> None:
    """One attribute asked of a name, checked where the name is tracked."""
    if not isinstance(node.value, ast.Name) or node.attr.startswith("_"):
        return
    name = node.value.id
    answer = scope.answers.get(name)
    if answer is not None and answer.shaped and answer.suppressed:
        scope.reads.append((name, node.lineno))
        return
    held = scope.bindings.get(name)
    if held is None:
        return
    if isinstance(held, _Crew):
        places: frozenset[str] = (
            frozenset(field for field, _ in held.fields)
            if held.fields is not None
            else frozenset()
        )
        if node.attr in places | _OF_A_TUPLE:
            return
        which = (
            ", ".join(field for field, _ in held.fields)
            if held.fields
            else "how many there are, and nothing else"
        )
        scope.findings.append(
            Finding(
                "unknown-ask",
                "error",
                scope.read.where,
                node.lineno,
                f"the agents have no place called {node.attr!r} -- the flow declares "
                f"{which}, and a place it does not declare is not one it was handed",
            )
        )
        return
    if node.attr in scope.asks.allowed(held):
        return
    what = " or ".join(f"hmz.flows.{kind.capitalize()}" for kind in sorted(held))
    scope.findings.append(
        Finding(
            "unknown-ask",
            "error",
            scope.read.where,
            node.lineno,
            f"nothing here answers to {node.attr!r} -- what a flow may ask is written "
            f"on {what}, and a name that is not there fails at the first turn",
        )
    )


# ---------------------------------------------------------------------------------------
# The loop rules: a loop is legal when something inside it can end it.
# ---------------------------------------------------------------------------------------


def _yields(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """Whether one function is a generator, whose loops end where their consumer stops."""
    waiting: list[ast.AST] = list(ast.iter_child_nodes(node))
    while waiting:
        held = waiting.pop()
        if isinstance(held, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            continue
        if isinstance(held, (ast.Yield, ast.YieldFrom)):
            return True
        waiting.extend(ast.iter_child_nodes(held))
    return False


class _Exit(NamedTuple):
    """One way out of a loop, and the conditions standing between the loop and it."""

    line: int
    conditions: tuple[ast.expr, ...]


def _loops(
    node: ast.FunctionDef | ast.AsyncFunctionDef, scope: _Scope
) -> Iterator[Finding]:
    """Every constant-true loop in one function, read for how it ends.

    Args:
      node: The function, with its bindings already followed.
      scope: What following them collected.

    Yields:
      A `dead-loop` error for one nothing inside can end, a `sleeping-loop` error for one
      that only sleeps -- alive from the outside and doing nothing -- and an
      `unbounded-loop` warning for one whose every way out waits for an agent to say so,
      in a function with no bound of its own.
    """
    for loop in _whiles(node.body):
        if not (isinstance(loop.test, ast.Constant) and loop.test.value):
            continue
        exits = _exits(loop.body, ())
        if not exits:
            if _sleeps(loop.body):
                code = "sleeping-loop"
                said = (
                    "this loop only sleeps -- from outside it looks alive, and each "
                    "round does nothing; a loop earns its keep by doing something "
                    "that can end it"
                )
            else:
                code = "dead-loop"
                said = (
                    "this loop cannot end -- no break, no return, no raise inside "
                    "it; a loop is legal when something inside it can end it"
                )
            yield Finding(code, "error", scope.read.where, loop.lineno, said)
            continue
        if scope.bounded:
            continue
        shaped = {name for name, answer in scope.answers.items() if answer.shaped}
        if all(_by_verdict(one, shaped) for one in exits):
            yield Finding(
                "unbounded-loop",
                "warning",
                scope.read.where,
                loop.lineno,
                "every way out of this loop waits for an agent to say so, and an agent "
                "may never say it -- give the loop a bound of its own: a budget read "
                "off spent(), a cap on the rounds, a range",
            )


def _whiles(body: list[ast.stmt]) -> Iterator[ast.While]:
    """Every while loop in one function's own body, nested functions left to themselves."""
    for node in body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        if isinstance(node, ast.While):
            yield node
        for held in _blocks(node):
            yield from _whiles(held)


def _blocks(node: ast.stmt) -> Iterator[list[ast.stmt]]:
    """The statement blocks one statement holds, whichever shape it is."""
    for name in ("body", "orelse", "finalbody"):
        held = getattr(node, name, None)
        if isinstance(held, list) and held and isinstance(held[0], ast.stmt):
            yield held
    for handler in getattr(node, "handlers", []):
        yield handler.body
    for case in getattr(node, "cases", []):
        yield case.body


def _exits(body: list[ast.stmt], conditions: tuple[ast.expr, ...]) -> list[_Exit]:
    """Every way out of a loop with this body, each with the conditions guarding it.

    A `break` of the loop's own, a `return`, a `raise`: anything that ends the loop or the
    function around it. A `break` inside a nested loop ends that loop instead, and is not
    one; a `return` inside one still ends the function, and is.
    """
    found: list[_Exit] = []
    for node in body:
        if isinstance(node, (ast.Break, ast.Return, ast.Raise)):
            found.append(_Exit(node.lineno, conditions))
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        elif isinstance(node, ast.If):
            found.extend(_exits(node.body, (*conditions, node.test)))
            found.extend(_exits(node.orelse, (*conditions, node.test)))
        elif isinstance(node, (ast.While, ast.For, ast.AsyncFor)):
            # A break in there is that loop's; a return or a raise is still a way out.
            for held in _blocks(node):
                found.extend(
                    one
                    for one in _exits(held, conditions)
                    if not _breaks_at(node, one.line)
                )
        else:
            for held in _blocks(node):
                found.extend(_exits(held, conditions))
    return found


def _breaks_at(loop: ast.stmt, line: int) -> bool:
    """Whether the exit at this line is a break belonging to this nested loop."""
    return any(
        isinstance(node, ast.Break) and node.lineno == line
        for node in ast.walk(loop)
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    )


def _by_verdict(exit_: _Exit, shaped: set[str]) -> bool:
    """Whether one way out waits on a field of what an agent answered.

    The `review.done` shape: a condition reading an attribute off an answer the turn was
    held to. A turn merely having landed -- `if said:` -- is not one, since a loop that
    takes a failed turn again is bounded by the turns landing, not by what they say.
    """
    for condition in exit_.conditions:
        for node in ast.walk(condition):
            if (
                isinstance(node, ast.Attribute)
                and isinstance(node.value, ast.Name)
                and node.value.id in shaped
                and not node.attr.startswith(("_", "model_"))
            ):
                return True
    return False


def _sleeps(body: list[ast.stmt]) -> bool:
    """Whether a loop body does nothing but wait: sleeps, passes, and constants."""
    for node in body:
        if isinstance(node, (ast.Pass, ast.Continue)):
            continue
        if isinstance(node, ast.Expr):
            value = node.value
            if isinstance(value, ast.Constant):
                continue
            if isinstance(value, ast.Call) and (
                (isinstance(value.func, ast.Name) and value.func.id == "sleep")
                or (
                    isinstance(value.func, ast.Attribute) and value.func.attr == "sleep"
                )
            ):
                continue
            return False
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant):
            continue
        return False
    return True


# ---------------------------------------------------------------------------------------
# The capability catalogue: what this installed humanize serves, read off it live.
# ---------------------------------------------------------------------------------------


class Capability(NamedTuple):
    """One thing a flow may build on, and which backends serve it.

    Attributes:
      name: What it is called: a primitive by one word, and a moment only some backends
        reach as `moment:<its own name>`.
      backends: The backends that serve it, or empty for one every backend serves.
      said: What the ask looks like, with the code spelled out: this is what a compiler
        or a person choosing what to build on is shown.
    """

    name: str
    backends: frozenset[str]
    said: str


def catalogue() -> tuple[Capability, ...]:
    """Everything a flow may build on here, read off the installed interface at call time.

    At call time rather than written down, because this is what keeps a generated flow
    honest across versions: the moments come off the live enum, the backend sets off the
    driver classes' own declarations, and the asks off the same interfaces `surface` reads
    -- so what the catalogue promises is what this installation serves, not what some
    edition of it once did.

    Returns:
      One capability apiece: the primitives every backend serves, then what only some do
      -- each moment outside `EVERYWHERE`, the shape a turn can be held to, the tools a
      flow may offer, and the goal feature.
    """
    import inspect
    import sys as running

    from hmz.agents import DRIVEN, EVERYWHERE, Moment

    agents = {name: held[0] for name, held in DRIVEN.items()}
    sessions: dict[str, type] = {}
    for name, cls in agents.items():
        # The session class, read off what `new` says it answers with: the class itself
        # is what carries `shapes` and `takes_tools`. By the name in the driver's own
        # module rather than through `get_type_hints`, which would ask every annotation
        # in the signature to resolve -- and a driver is free to keep `os` under
        # TYPE_CHECKING.
        told: object = None
        with contextlib.suppress(Exception):
            told = inspect.signature(cls.new).return_annotation
            if isinstance(told, str):
                told = vars(running.modules[cls.__module__]).get(told)
        if isinstance(told, type):
            sessions[name] = told
    held: list[Capability] = [
        Capability(
            "turns",
            frozenset(),
            "one turn in a session of its own -- agent(prompt, suppress=True) -- or many "
            "at once with agent.batch(prompts); suppress=True makes a failed turn answer "
            "'' (or None, for a shaped one) instead of raising",
        ),
        Capability(
            "sessions",
            frozenset(),
            "one conversation held across turns -- session = agent.new(cwd=...) then "
            "session(prompt) -- and dropping the session is how a flow forgets",
        ),
        Capability(
            "schema",
            frozenset(),
            "a turn read back as an object -- session(prompt, suppress=True, "
            "schema=Model) answers the model or None, and the answer is guarded before a "
            "field is read off it",
        ),
        Capability(
            "budgets",
            frozenset(),
            "what a loop's bound reads -- agent.spent().output climbs as the run spends, "
            "and session.rate() and session.juice() say how fast",
        ),
        Capability(
            "hooks",
            frozenset(),
            "a word in at the moments of a turn -- agent.hooks.on(Moment.STOP, hook) "
            "hangs a callable, and a Stop hook that refuses sends the agent on with what "
            "it said",
        ),
        Capability(
            "subflows",
            frozenset(),
            "one flow runs another -- load('official/rlar')(agents, task) -- found by "
            "the same name -f takes, and refused where it is asked for if nothing "
            "answers to it",
        ),
        Capability(
            "person",
            frozenset(),
            "the person at the prompt is a place like any other -- agents that include a "
            "Person field -- and person(said) asks them; run where nobody is at a "
            "prompt, they answer nothing, and a flow written to stop on nothing stops",
        ),
        Capability(
            "board",
            frozenset(),
            "named lines the flow and the person both write on and neither waits at -- "
            "person.board.put('todo', said) and person.board.get('todo')",
        ),
        Capability(
            "state",
            frozenset(),
            "a flow marked @flow(resumable=True) is handed a dict as its last argument, "
            "holding what it wrote there last time -- and clears it when the run is over",
        ),
        Capability(
            "config",
            frozenset(),
            "what a flow can be set up with is a pydantic model third argument -- "
            "config: Config | None = None -- whose model_config refuses extras and whose "
            "every field carries Field(description=...)",
        ),
        Capability(
            "skills",
            frozenset(),
            "a flow's own skills live in its skills/ directory, one directory per skill "
            "with a SKILL.md in it, and a session says which it carries with "
            "session.loads([...])",
        ),
        Capability(
            "clone",
            frozenset(),
            "an agent set up differently is another agent -- "
            "agent.clone(config=replace(agent.config, effort='high')) -- having opened "
            "nothing and spent nothing",
        ),
        Capability(
            "moments",
            frozenset(),
            "the moments every backend reaches, for a hook to hang on: "
            + ", ".join(f"Moment.{one.name}" for one in Moment if one in EVERYWHERE),
        ),
    ]
    for moment in Moment:
        if moment in EVERYWHERE:
            continue
        held.append(
            Capability(
                f"moment:{moment.value}",
                frozenset(
                    name for name, cls in agents.items() if moment in cls.moments
                ),
                f"Moment.{moment.name} is reached only where the backend says so -- "
                f"declare it on the place, Annotated[Agent, Moment.{moment.name}], and "
                "the run is refused an agent that cannot run it before its first turn",
            )
        )
    held.append(
        Capability(
            "shapes",
            frozenset(
                name for name, one in sessions.items() if getattr(one, "shapes", False)
            ),
            "a turn held to the shape rather than asked to keep to it -- every backend "
            "takes schema=, and these are the ones the answer is certain on",
        )
    )
    held.append(
        Capability(
            "tools",
            frozenset(
                name
                for name, one in sessions.items()
                if getattr(one, "takes_tools", False)
            ),
            "a flow's own callbacks put in front of the agent -- "
            "session.offers([Tool(...)]) -- which a backend not among these refuses; "
            "type(session).takes_tools says so beforehand",
        )
    )
    pursuing = frozenset(name for name, cls in agents.items() if cls.pursues)
    held.append(
        Capability(
            "pursue",
            pursuing,
            "the backend's own goal feature -- session.pursue(objective) keeps the "
            "agent going until it decides for itself the objective is met",
        )
    )
    held.append(
        Capability(
            "goal",
            pursuing,
            "a place run under that feature declares it -- Annotated[Agent, Goal] -- "
            "and is refused an agent whose backend has none before the first turn",
        )
    )
    return tuple(held)


def briefed() -> str:
    """The catalogue rendered as the one page a compiler steers by.

    Returns:
      What every backend serves, then what only some do -- each with the backends that
      do, so that a flow built on one can say where it runs.
    """
    held = catalogue()
    lines = [
        "What a flow may build on here, read off this installed humanize.",
        "",
        "Every backend:",
    ]
    lines.extend(f"- {one.name}: {one.said}" for one in held if not one.backends)
    lines += [
        "",
        (
            "Only some backends -- a flow built on one of these says so where it "
            "declares the place, and is refused an unfit agent before the first turn:"
        ),
    ]
    lines.extend(
        f"- {one.name} ({', '.join(sorted(one.backends))}): {one.said}"
        for one in held
        if one.backends
    )
    return "\n".join(lines)
