"""Compiling an atlas: the narrower Python it is written in, and the prophecy it becomes.

An ordinary flow is read by running it, and what it will do is nobody's to ask. An atlas
answers that before anything runs: its body is a declaration, this is the reading that holds
it to the subset a declaration is written in, and what comes out is a graph -- nodes, edges,
and the shapes that flow along them. Everything here is refused or compiled without importing
a line of it.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

from hmz.flows import PROPHECY, canonical, checked, digest, kept
from hmz.flows.prophesying import Prophesied, prophesied
from tests.stubs import written

if TYPE_CHECKING:
    from pathlib import Path

#: What every atlas below is written against: who it drives, what flows between its nodes,
#: and the two nodes themselves. The bodies are what differ, which is what is on trial.
HEAD = '''"""An atlas, for the reading to have something to read."""

from typing import NamedTuple

from pydantic import BaseModel, Field

from hmz.flows import Agent, atlas, logic, mind


class Agents(NamedTuple):
    """Who it drives."""

    writer: Agent


class Draft(BaseModel):
    """What the writer produced."""

    model_config = {"extra": "forbid"}

    text: str = Field(description="the draft")


class Verdict(BaseModel):
    """What was made of it."""

    model_config = {"extra": "forbid"}

    done: bool = Field(description="whether it is finished")


@mind
def write(agent: Agent, task: str) -> Draft:
    """One turn of writing."""
    return agent(task, shape=Draft)


@logic
def judge(said: Draft) -> Verdict:
    """Reads the draft, which is what a branch hangs off."""
    return Verdict(done=bool(said.text))


@logic(rerun=False)
def stamp(said: Draft) -> None:
    """A node a run picked up again steps past."""


'''

#: The straight one: a turn, a reading of it, and a loop that ends when the reading says so.
LOOP = '''@atlas
def run(agents: Agents, task: str) -> None:
    """Writes until the reading of it says it is done."""
    draft = write(agents.writer, task)
    verdict = judge(draft)
    while not verdict.done:
        draft = write(agents.writer, task)
'''


def _held(under: Path, body: str, name: str = "one") -> Prophesied:
    """Writes one atlas out and compiles it.

    Args:
      under: Where the flows are kept.
      body: The body under :data:`HEAD`.
      name: What to call the flow.

    Returns:
      What compiling it came to.
    """
    return prophesied(written(under, name, HEAD + body))


def _codes(under: Path, body: str) -> list[str]:
    """Every error one atlas's body is refused for, by code."""
    held = _held(under, body)
    assert held.prophecy is None
    return [one.code for one in held.findings if one.severity == "error"]


def test_a_body_compiles_to_the_graph_it_declares(tmp_path: Path) -> None:
    """One node per call, one edge per way from one to the next, and nothing run."""
    held = _held(tmp_path, LOOP)

    assert held.findings == ()
    prophecy = held.prophecy
    assert prophecy is not None
    assert [one.at for one in prophecy.nodes] == ["write", "judge", "write:2"]
    assert [one.kind for one in prophecy.nodes] == ["mind", "logic", "mind"]
    assert prophecy.agents == ("writer",)
    assert prophecy.takes == "str"


def test_a_loop_is_an_edge_back_to_the_node_the_branch_reads(tmp_path: Path) -> None:
    """Which is what makes the head answer again with whatever the round changed."""
    prophecy = _held(tmp_path, LOOP).prophecy
    assert prophecy is not None

    ways = {(one.out_of, one.into): one.when for one in prophecy.edges}
    assert ways[("", "write")] is None  # the way in
    assert ways[("write", "judge")] is None
    rounds = ways[("judge", "write:2")]
    assert rounds is not None
    assert rounds.truth is False  # round again while the reading says it is not done
    assert ways[("write:2", "judge")] is None  # and back to the node that reads it
    over = ways[("judge", "")]
    assert over is not None
    assert over.truth is True  # and out of the graph when it is


def test_the_same_body_written_twice_compiles_to_the_same_bytes(tmp_path: Path) -> None:
    """Canonical means what it says: a comment is not part of what the atlas is."""
    one = _held(tmp_path, LOOP, "one").prophecy
    two = _held(
        tmp_path,
        LOOP.replace(
            "    draft = write", "    # a comment nobody compiles\n    draft = write", 1
        ),
        "two",
    ).prophecy
    assert one is not None
    assert two is not None

    assert canonical(one) == canonical(two._replace(name="one"))
    assert digest(one) == digest(two._replace(name="one"))


def test_what_a_node_answers_with_is_written_down_field_by_field(
    tmp_path: Path,
) -> None:
    """A shape is what an edge carries, and what carries it is what both ends are held to."""
    prophecy = _held(tmp_path, LOOP).prophecy
    assert prophecy is not None

    said = json.loads(canonical(prophecy))
    assert {one["name"] for one in said["shapes"]} == {"Draft", "Verdict", "str"}
    verdict = next(one for one in said["shapes"] if one["name"] == "Verdict")
    assert verdict["fields"] == [["done", "bool", True]]


@pytest.mark.parametrize(
    ("why", "body", "code"),
    [
        (
            "a turn has one way out",
            '''@atlas
def run(agents: Agents, task: str) -> None:
    """Says it."""
    draft = write(agents.writer, task)
    if draft.text:
        draft = write(agents.writer, task)
''',
            "branching-mind",
        ),
        (
            "work is what a node is for",
            '''@atlas
def run(agents: Agents, task: str) -> None:
    """Says it."""
    draft = write(agents.writer, task)
    said = draft.text + "!"
''',
            "unstatic-body",
        ),
        (
            "what flows in is what the far end takes",
            '''@atlas
def run(agents: Agents, task: str) -> None:
    """Says it."""
    draft = write(agents.writer, task)
    again = write(agents.writer, draft)
''',
            "shape-mismatch",
        ),
        (
            "an agent it does not drive",
            '''@atlas
def run(agents: Agents, task: str) -> None:
    """Says it."""
    draft = write(agents.reviewer, task)
''',
            "unknown-agent",
        ),
        (
            "a loop nothing inside can end",
            '''@atlas
def run(agents: Agents, task: str) -> None:
    """Says it."""
    draft = write(agents.writer, task)
    verdict = judge(draft)
    while not verdict.done:
        pass
''',
            "dead-loop",
        ),
        (
            "a node stepped past has no answer to leave behind",
            '''@logic(rerun=False)
def marked(said: Draft) -> Verdict:
    """Answers, and says it is stepped past."""
    return Verdict(done=True)


@atlas
def run(agents: Agents, task: str) -> None:
    """Says it."""
    draft = write(agents.writer, task)
    verdict = marked(draft)
''',
            "skipped-answer",
        ),
        (
            "a name nothing bound",
            '''@atlas
def run(agents: Agents, task: str) -> None:
    """Says it."""
    verdict = judge(nowhere)
''',
            "unbound-read",
        ),
        (
            "a plain tuple says only how many",
            '''@atlas
def run(agents: tuple[Agent], task: str) -> None:
    """Says it."""
    draft = write(agents.writer, task)
''',
            "unnamed-agents",
        ),
        (
            "two decisions carried on one edge",
            '''@atlas
def run(agents: Agents, task: str) -> None:
    """Says it."""
    draft = write(agents.writer, task)
    verdict = judge(draft)
    if verdict.done:
        draft = write(agents.writer, task)
    elif verdict.done:
        draft = write(agents.writer, task)
''',
            "unstatic-body",
        ),
        (
            "a name keeps the shape it was bound with",
            '''@atlas
def run(agents: Agents, task: str) -> None:
    """Says it."""
    draft = write(agents.writer, task)
    draft = judge(draft)
''',
            "shape-mismatch",
        ),
        (
            "a graph with no nodes",
            '''@atlas
def run(agents: Agents, task: str) -> None:
    """Says it."""
''',
            "unstatic-body",
        ),
        (
            "a node that says nothing about what flows through it",
            '''@logic
def loose(said):
    """Says nothing."""
    return said


@atlas
def run(agents: Agents, task: str) -> None:
    """Says it."""
    said = loose(task)
''',
            "unshaped-node",
        ),
        (
            "a logic handed an agent",
            '''@logic
def turned(agent: Agent, said: Draft) -> Verdict:
    """Takes one, and is not a turn."""
    return Verdict(done=True)


@atlas
def run(agents: Agents, task: str) -> None:
    """Says it."""
    draft = write(agents.writer, task)
    verdict = turned(agents.writer, draft)
''',
            "unagented-node",
        ),
    ],
)
def test_the_body_an_atlas_may_not_hold(
    tmp_path: Path, why: str, body: str, code: str
) -> None:
    """Every one of these is decidable, which is the bargain an atlas makes."""
    assert code in _codes(tmp_path, body), why


def test_an_atlas_reaches_an_atlas_and_nothing_else(tmp_path: Path) -> None:
    """`load` answers with a flow that may be anything, which is a hole in a graph."""
    body = '''from hmz.flows import load

chat = load("chat")


@atlas
def run(agents: Agents, task: str) -> None:
    """Says it."""
    draft = write(agents.writer, task)
'''
    assert "dynamic-call" in _codes(tmp_path, body)


def test_a_supernode_is_the_atlas_under_it_compiled(tmp_path: Path) -> None:
    """One node from outside, one prophecy from within."""
    body = '''@atlas(name="inner")
def inner(agents: Agents, said: Draft) -> Verdict:
    """A whole atlas, reached as one node."""
    verdict = judge(said)
    return verdict


@atlas
def run(agents: Agents, task: str) -> None:
    """Says it."""
    draft = write(agents.writer, task)
    verdict = inner(agents, draft)
'''
    prophecy = _held(tmp_path, body).prophecy
    assert prophecy is not None

    node = prophecy.node("inner")
    assert node is not None
    assert node.kind == "atlas"
    assert node.under == "inner"
    under = prophecy.under("inner")
    assert under is not None
    assert [one.at for one in under.nodes] == ["judge"]
    assert under.takes == "Draft"
    assert under.gives == "Verdict"


def test_a_supernode_that_reaches_back_into_its_own_graph_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A graph inside a graph inside itself has no bottom, however it is spelled.

    Reached by name here rather than beside it, since the two spellings of one atlas are
    exactly what a check comparing names would follow forever.
    """
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.chdir(tmp_path)
    body = '''from hmz.flows import sub

again = sub("one:inner")


@atlas(name="inner")
def inner(agents: Agents, said: Draft) -> Verdict:
    """Reaches back into itself."""
    verdict = again(agents, said)
    return verdict


@atlas
def run(agents: Agents, task: str) -> None:
    """Says it."""
    draft = write(agents.writer, task)
    verdict = inner(agents, draft)
'''
    assert "circular-atlas" in _codes(tmp_path / ".humanize/flows", body)


def test_a_flow_that_is_not_an_atlas_is_not_compiled(tmp_path: Path) -> None:
    """`checked` is the reading for those, and it is what it goes on being."""
    plain = '''"""An ordinary flow."""

from hmz.flows import Agent, flow


@flow
def run(agents: tuple[Agent], task: str) -> None:
    """Does whatever it likes."""
'''
    at = written(tmp_path, "plain", plain)

    assert prophesied(at).prophecy is None
    assert [one.code for one in prophesied(at).findings] == ["not-an-atlas"]
    assert checked(at) == ()  # and the ordinary reading has nothing against it


def test_the_stricter_reading_is_the_one_an_atlas_gets(tmp_path: Path) -> None:
    """`hmz check` asks one question, and an atlas is what decides which reading answers."""
    body = '''@atlas
def run(agents: Agents, task: str) -> None:
    """Says it."""
    draft = write(agents.writer, task)
    if draft.text:
        draft = write(agents.writer, task)
'''
    at = written(tmp_path, "one", HEAD + body)

    assert "branching-mind" in {one.code for one in checked(at)}


def test_a_shipped_prophecy_that_is_no_longer_the_source_is_said(
    tmp_path: Path,
) -> None:
    """A run walks the shipped one, so a drifted flow reads as something it is not."""
    at = written(tmp_path, "one", HEAD + LOOP)
    held = prophesied(at).prophecy
    assert held is not None
    (at / PROPHECY).write_bytes(kept(held._replace(gives="Draft")))

    assert "stale-prophecy" in {one.code for one in checked(at)}


def test_a_prophecy_that_cannot_be_read_back_is_not_walked(tmp_path: Path) -> None:
    """Bytes that are not a prophecy are a file to compile again, not a graph to guess at."""
    at = written(tmp_path, "one", HEAD + LOOP)
    (at / PROPHECY).write_bytes(b"nothing here is a prophecy")

    assert "stale-prophecy" in {one.code for one in checked(at)}


def test_a_supernode_that_says_it_can_be_set_up_is_refused(tmp_path: Path) -> None:
    """What is set up is the run, so such an atlas is one to start and not one to reach."""
    body = '''class Config(BaseModel):
    """What it takes."""

    model_config = {"extra": "forbid"}

    rounds: int = Field(default=2, description="how many rounds it takes")


@atlas(name="inner")
def inner(agents: Agents, said: Draft, config: Config | None = None) -> Verdict:
    """A graph that says it can be set up."""
    verdict = judge(said)
    return verdict


@atlas
def run(agents: Agents, task: str) -> None:
    """Says it."""
    draft = write(agents.writer, task)
    verdict = inner(agents, draft)
'''
    assert "unstatic-body" in _codes(tmp_path, body)


def test_what_an_atlas_can_be_set_up_with_is_part_of_the_prophecy(
    tmp_path: Path,
) -> None:
    """A node may read the config, so what it is is what the graph is checked against."""
    body = '''class Config(BaseModel):
    """What it takes."""

    model_config = {"extra": "forbid"}

    rounds: int = Field(default=2, description="how many rounds it takes")


@logic
def bounded(said: Draft, rounds: int) -> Verdict:
    """Reads the draft against the bound the run was set up with."""
    return Verdict(done=bool(said.text) and rounds > 0)


@atlas
def run(agents: Agents, task: str, config: Config | None = None) -> None:
    """Says it."""
    draft = write(agents.writer, task)
    verdict = bounded(draft, config.rounds)
'''
    prophecy = _held(tmp_path, body).prophecy
    assert prophecy is not None

    assert prophecy.config == "Config"
    node = prophecy.node("bounded")
    assert node is not None
    assert node.takes[1].reads == "@config"
    assert node.takes[1].field == "rounds"
