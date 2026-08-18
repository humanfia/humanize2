"""Running a prophecy: one node at a time, and picking one up where it stopped.

What an ordinary flow does is whatever its body does, and a run of it that was stopped is a
run that has to start again -- a flow keeps a handful of things in a dict and works out the
rest. An atlas is the other bargain. Its body was compiled before anything ran, so a run of
one is a walk over the prophecy: take the node, run it, write down what it answered, follow
the edge whose guard holds. What a run has done is therefore the list of answers it has, and
picking one up is walking the same prophecy again over the same answers until it reaches the
node that has none.

Which node that is decides what happens next. By default it runs: a node stopped partway is
work that was not done, and doing it again is the only honest reading of a turn that was cut
off. A node may say otherwise -- `@mind(rerun=False)` -- and is then stepped past, having
already had its effect by the time anything could interrupt it. Such a node answers with
nothing, which is what makes stepping past it possible at all: there is no answer for what
comes next to be missing.

A run is picked up into the same prophecy or not at all. What was written down is written
down against :func:`~hmz.flows.atlas.digest`, and an atlas rewritten between two runs of it
is a different prophecy whose nodes happen to share their names -- so the digest is checked,
and a run whose prophecy has moved starts from the top rather than resuming into somewhere it
has never been.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from .atlas import AGENTS, CONFIG, INPUT, Node, Reads, digest, shipped

if TYPE_CHECKING:
    import os
    from collections.abc import Mapping

    from pydantic import BaseModel

    from .agent import Agent
    from .atlas import Edge, Prophecy
    from .driving import Entry

__all__ = ["walking"]

#: What the state a run writes down keeps: which prophecy it is a run of, which node it was
#: inside when it stopped, and what each node it has finished answered.
_PROPHECY = "prophecy"
_AT = "at"
_DONE = "done"

#: What one visit to a node is written down under: the node, and how many times the run has
#: been through it -- a loop is one node visited again, and a round whose answer overwrote
#: the last round's would be a run that could not be picked up inside a loop.
_VISIT = "#"

#: And what a supernode's own nodes are written down under: its visit, then theirs.
_UNDER = "/"


def walking(
    flow: str | os.PathLike[str], inside: Mapping[str, Any], entry: Entry
) -> Entry:
    """Compiles one atlas, and answers with something that runs the prophecy.

    Called where a flow is about to be run rather than where it is merely read, which is
    what makes an atlas a flow checked before anything happens: a body that does not compile
    is a flow refused before its first node, with everything wrong with it said at once.

    Args:
      flow: The atlas, as it was asked for -- which is also which of the ones its file holds
        is wanted.
      inside: What running the flow's file left behind, which is where the nodes are.
      entry: The atlas's own entry point, whose body is the declaration that was compiled
        and is therefore never called. What it was marked with is carried onto the answer, so
        that everything reading a flow off its entry point goes on reading this one.

    Returns:
      Something to call the way any flow is called -- the agents, the task, the config for
      one that takes one, and the dict a resumable flow is handed.

    Raises:
      NotAFlow: If the atlas does not compile, saying each reason on a line of its own.
    """
    import functools

    from . import inside as which
    from . import reading
    from .driving import NotAFlow
    from .prophesying import named_as, prophesied

    named = str(flow)
    under = Path(reading(named))
    wanted = named_as(under, which(named))
    prophecy = _shipped(under, wanted)
    if prophecy is None:
        held = prophesied(under, name=which(named))
        if held.prophecy is None:
            why = "\n".join(
                f"  {one.where}:{one.line}: {one.code}: {one.said}"
                for one in held.findings
                if one.severity == "error"
            )
            raise NotAFlow(f"{flow}: the atlas does not compile\n{why}")
        prophecy = held.prophecy
    walked = prophecy

    def running(agents: Any, task: Any, *said: Any) -> Any:
        # A resumable flow is handed its state last and its config before it, and an atlas
        # is always resumable: what a run of one has done is which of its nodes answered.
        state: dict[str, Any] = said[-1] if said else {}
        config = said[0] if len(said) > 1 else None
        return _stepped(walked, inside, agents, task, config, state)

    # Whatever the entry point was marked with, and not the two marks known today: both
    # `flow` and `atlas` set theirs into the function's own `__dict__`, which is exactly
    # what this copies -- so a third mark added later travels without this line moving.
    return functools.update_wrapper(running, entry, assigned=(), updated=("__dict__",))


def _shipped(under: Path, wanted: str) -> Prophecy | None:
    """The prophecy a flow's own directory ships, where it ships the one being asked for.

    Preferred over compiling the atlas again: the compiling is where an atlas is refused,
    and a repository that has been through it has an answer worth carrying. A directory
    holds one prophecy and a file may hold several atlases, so the one shipped is the one it
    is named after -- and the rest are compiled where they are asked for.

    Args:
      under: The flow's own directory, or the file a single-file flow is, which ships none.
      wanted: Which of the atlases the file holds is being run.

    Returns:
      The prophecy, or None where the flow ships none, or ships one for another atlas.

    Raises:
      NotAFlow: If it ships one that cannot be read back. Refused rather than compiled
        again: what a flowverse shipped is what it meant to be run, and quietly running
        something else would be the one thing shipping it was meant to rule out.
    """
    from .driving import NotAFlow

    held = shipped(under)
    if held is None:
        return None
    if held.prophecy is None:
        raise NotAFlow(
            f"{held.at}: the prophecy shipped here cannot be read -- compile the atlas "
            "again, or take the file away and let the run compile it"
        )
    return held.prophecy if held.prophecy.name == wanted else None


@dataclass(slots=True)
class _Walk:
    """One prophecy being walked, and everything every step of it is against.

    Held once rather than handed down: what changes as a run goes is which node it is at and
    what each name holds, and everything else is the same at every step. A supernode makes
    another of these -- its own prophecy, its own file, its own agents -- and keeps what the
    whole run shares.

    Attributes:
      prophecy: The compiled atlas being walked.
      inside: What running the file it was compiled from left behind, which is where the
        functions its nodes are get looked up.
      agents: The run's agents, by the name this prophecy calls each.
      state: The whole run's state, which is where it says what node it stopped inside.
      kept: What each visit to a node that has answered answered, for the whole run.
      under: What this prophecy's visits are written down beneath, "" for the outermost.
      beside: What each flow reached by name left behind when it was read, for the whole
        run. Read once: a run walks one prophecy, and a sub-flow re-read between two rounds
        of a loop would be new code running under a graph that had already been settled.
      nodes: The prophecy's nodes by id, and its ways out by the node each leaves. Built
        once rather than scanned at every step, a prophecy being what it is for the length
        of the walk.
      ways: As above.
    """

    prophecy: Prophecy
    inside: Mapping[str, Any]
    agents: dict[str, Agent]
    state: dict[str, Any]
    kept: dict[str, Any]
    under: str
    beside: dict[str, Mapping[str, Any]]
    nodes: dict[str, Node] = field(init=False)
    ways: dict[str, tuple[Edge, ...]] = field(init=False)

    def __post_init__(self) -> None:
        """Reads the prophecy into what a step of the walk asks it."""
        self.nodes = {one.at: one for one in self.prophecy.nodes}
        self.ways = {
            at: self.prophecy.out_of(at)
            for at in {"", *(one.out_of for one in self.prophecy.edges)}
        }


def _stepped(
    prophecy: Prophecy,
    inside: Mapping[str, Any],
    agents: Any,
    given: Any,
    config: BaseModel | None,
    state: dict[str, Any],
) -> Any:
    """Runs one whole atlas, from whatever a run of it has already done.

    Args:
      prophecy: The compiled atlas.
      inside: What running its file left behind.
      agents: The agents, as the atlas declared them.
      given: What the atlas was called with -- the task, or the shape a supernode takes.
      config: What the run was set up with, or None for an atlas that takes no setting up.
      state: What the run before this one wrote down, and what this one writes into.

    Returns:
      Whatever the prophecy answers with, and None for one that answers with nothing.
    """
    written = digest(prophecy)
    if state.get(_PROPHECY) != written:
        # A different prophecy: the atlas was rewritten between the two runs, so what the
        # last one did, it did somewhere else. Cleared rather than merged, since a node
        # that kept its name is not thereby the node it was.
        state.clear()
        state[_PROPHECY] = written
    walk = _Walk(
        prophecy=prophecy,
        inside=inside,
        agents={one: getattr(agents, one) for one in prophecy.agents},
        state=state,
        kept=state.setdefault(_DONE, {}),
        under="",
        beside={},
    )
    return _walked(walk, given, config)


def _walked(walk: _Walk, given: Any, config: BaseModel | None) -> Any:
    """Walks one prophecy from its way in to its way out.

    Args:
      walk: The prophecy being walked, and what every step of it is against.
      given: What it was called with.
      config: What the run was set up with.

    Returns:
      What the prophecy answers with, which is what the `return` it left by named.
    """
    bound: dict[str, Any] = {AGENTS: walk.agents, INPUT: given, CONFIG: config}
    seen: dict[str, int] = {}
    at = ""
    while True:
        edge = _way(walk, at, bound)
        node = None if edge is None else walk.nodes.get(edge.into)
        if node is None:
            # What the `return` named, and not whatever the last node happened to say: a
            # body may answer with something it bound three nodes ago.
            return bound.get(edge.answers) if edge is not None else None
        seen[node.at] = visit = seen.get(node.at, 0) + 1
        held = f"{walk.under}{node.at}{_VISIT}{visit}"
        answered = _answered(walk, bound, node, held)
        if node.binds:
            bound[node.binds] = answered
        at = node.at


def _way(walk: _Walk, at: str, bound: dict[str, Any]) -> Edge | None:
    """Which way out of one node this run takes.

    Args:
      walk: The prophecy being walked.
      at: The node it is leaving, and "" for the way in.
      bound: What each name holds now.

    Returns:
      The edge. One whose far end is "" is the way out of the prophecy, and what the run
      answers with is on it; None is a node nothing leads on from, which nothing that
      compiled can be.
    """
    for edge in walk.ways.get(at, ()):
        when = edge.when
        if (
            when is None
            or bool(_read(bound, Reads(when.reads, when.field))) is when.truth
        ):
            return edge
    return None


def _answered(walk: _Walk, bound: dict[str, Any], node: Node, held: str) -> Any:
    """What one node answers with: what it answered last time, or what it answers now.

    Args:
      walk: The prophecy being walked.
      bound: What each name holds now.
      node: The node.
      held: What this visit to it is written down under.

    Returns:
      Its answer, rebuilt through the shape it declared where this is a visit the run is
      picking up rather than one it is taking.
    """
    if held in walk.kept:
        return _rebuilt(walk.kept[held], node.gives, walk.inside)
    if held == walk.state.get(_AT) and not node.rerun:
        # Where the last run stopped, in a node that says it is not to be run again: it had
        # its effect before anything could interrupt it, so the run steps past. It answers
        # with nothing -- the compiling refuses one that does not -- so there is nothing for
        # what comes next to be missing.
        walk.kept[held] = None
        _saved(walk.state)
        return None
    # Written down before the node runs and saved once: `State` saves itself as it is
    # written into, and what goes into `kept` below is a change inside a value it holds and
    # cannot see -- which is the one that has to ask.
    walk.state[_AT] = held
    answered = _ran(walk, bound, node, held)
    walk.kept[held] = _written(answered)
    _saved(walk.state)
    return answered


def _ran(walk: _Walk, bound: dict[str, Any], node: Node, held: str) -> Any:
    """Runs one node for real: a turn, a Python function, or a whole prophecy.

    Args:
      walk: The prophecy being walked.
      bound: What each name holds now.
      node: The node.
      held: What this visit to it is written down under.

    Returns:
      What it answered.

    Raises:
      NotAFlow: If the file the prophecy was compiled from no longer holds what it declared,
        which is a flow rewritten under a run of it.
    """
    from .driving import NotAFlow

    said = [_read(bound, one) for one in node.takes]
    if node.kind == "atlas":
        return _supernode(walk, node, held, said)
    call = walk.inside.get(node.calls)
    if not callable(call):
        raise NotAFlow(
            f"{walk.prophecy.name}: nothing in the flow is called {node.calls!r} -- the "
            "prophecy was compiled from a file that has since been rewritten"
        )
    return call(*said)


def _supernode(walk: _Walk, node: Node, held: str, said: list[Any]) -> Any:
    """Runs one supernode, which is a whole prophecy inside this one.

    Args:
      walk: The prophecy the node is in.
      node: The node.
      held: What this visit to it is written down under, which its own nodes go beneath.
      said: What it was handed -- the agents, then the one shape it takes.

    Returns:
      What the prophecy under it answered with.

    Raises:
      NotAFlow: If the prophecy names a supernode it does not hold, which nothing that
        compiled should be able to say.
    """
    from . import find, loaded
    from .driving import NotAFlow

    under = walk.prophecy.under(node.under)
    if under is None:
        raise NotAFlow(
            f"{walk.prophecy.name}: nothing under it is called {node.under!r}"
        )
    # Beside it or elsewhere: a supernode of this flow's own is in the file this prophecy
    # was compiled from, and one reached by name is a flow of its own, run to be read as any
    # flow is. Read once for the run rather than once a visit: the graph was settled before
    # the run started, and a file re-read between two rounds of a loop would be new code
    # running under a shape that had already been agreed.
    if node.calls in walk.inside:
        beside = walk.inside
    elif node.calls not in walk.beside:
        walk.beside[node.calls] = beside = loaded(find(node.calls))
    else:
        beside = walk.beside[node.calls]
    return _walked(
        _Walk(
            prophecy=under,
            inside=beside,
            agents={one: walk.agents[one] for one in under.agents},
            state=walk.state,
            kept=walk.kept,
            under=f"{held}{_UNDER}",
            beside=walk.beside,
        ),
        said[1],
        None,
    )


def _read(bound: dict[str, Any], one: Reads) -> Any:
    """What one node reads, which is a name a node bound or a field of it.

    Args:
      bound: What each name holds now.
      one: The reading.

    Returns:
      The value. Nothing at all for a name nothing has bound, which the compiling refuses
      and which a file rewritten under a run could still produce.
    """
    held = bound.get(one.reads)
    if not one.field:
        return held
    # The agents are the one thing a name holds that is not a node's answer, and they are
    # held by name: everything else a body binds is a model or a plain kind.
    if isinstance(held, dict):
        return cast("dict[str, Any]", held).get(one.field)
    return getattr(held, one.field, None)


def _written(answered: Any) -> Any:
    """One node's answer as something a run picked up again can be handed back.

    Args:
      answered: What the node answered.

    Returns:
      JSON for a model, and the value itself for the plain kinds -- which is the whole of
      what a node may answer with, the compiling having refused everything else.
    """
    dump = getattr(answered, "model_dump", None)
    return dump(mode="json") if callable(dump) else answered


def _rebuilt(written: Any, gives: str, inside: Mapping[str, Any]) -> Any:
    """One node's kept answer, back in the shape the node declared.

    Args:
      written: What was written down.
      gives: The shape the node answers with, and "" for one that answers with nothing.
      inside: What running the flow's file left behind, which is where the model is.

    Returns:
      The value, rebuilt through the model where the flow still declares one -- and as it
      was written where it does not, a run picked up into a rewritten flow being one whose
      prophecy has already been checked against the digest.
    """
    validate = getattr(inside.get(gives), "model_validate", None)
    return validate(written) if callable(validate) and written is not None else written


def _saved(state: dict[str, Any]) -> None:
    """Writes the run's state where it is kept, for a run stopped after this node.

    A `hmz.cycle.State` saves itself as it is written into, and a plain dict is what a flow
    run from a test is handed. Both are dicts here, and only one of them has anything to do:
    what is written inside `done` is written inside a value the mapping cannot see change.

    Args:
      state: What the run is writing down.
    """
    save = getattr(state, "save", None)
    if callable(save):
        save()
