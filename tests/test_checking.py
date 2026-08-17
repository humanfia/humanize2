"""The static read of a flow's legality, held to finding what it claims and nothing else.

Two halves. A fixture or two per rule -- a flow that trips it, and a neighbour standing just
on the legal side -- so that every rule is shown to fire and shown to know where the edge is.
And a sweep over every flow humanize ships and every flow the official flowverse holds: the
rules were written against real flows, and the sweep is the alarm that goes off the day one
of them starts reading a good flow as a bad one.
"""

from __future__ import annotations

import textwrap
from typing import TYPE_CHECKING

import pytest

import hmz.flows
from hmz.flows import BUILTIN_AT, ENTRY, Agent, Driven, Person, Session, entry
from hmz.flows.checking import checked, offered, surface
from tests.stubs import written

if TYPE_CHECKING:
    from pathlib import Path

#: What each code is, so that a rule quietly changing its severity is a failing test.
SEVERITY = {
    "unread": "error",
    "not-a-flow": "error",
    "unsized-agents": "error",
    "unread-annotation": "error",
    "foreign-import": "error",
    "unknown-name": "error",
    "unknown-ask": "error",
    "dead-loop": "error",
    "sleeping-loop": "error",
    "stateless-resume": "error",
    "unbounded-loop": "warning",
    "unguarded-answer": "warning",
    "unsaid-moment": "warning",
    "loose-config": "warning",
    "unsaid-field": "warning",
    "unsaid-flow": "warning",
    "state-kept": "warning",
    "twice-named": "warning",
}

#: What a flow standing just on the legal side of a rule reads as: nothing at all.
CLEAN: set[str] = set()

#: The one line every fixture flow says about itself, so `unsaid-flow` stays out of the way
#: of every rule but its own.
DOC = '"""A flow written for one rule of the checker."""\n'

CASES = [
    pytest.param(
        DOC
        + """
from hmz.flows import Agent, flow

@flow
def run(agents: tuple[Agent], task: str) -> None:
    (agent,) = agents
    while True:
        agent(task, suppress=True)
""",
        {"dead-loop"},
        id="dead-loop",
    ),
    pytest.param(
        DOC
        + """
from hmz.flows import Agent, flow

@flow
def run(agents: tuple[Agent], task: str) -> None:
    (agent,) = agents
    while True:
        worked = agent(task, suppress=True)
        if not worked:
            break
""",
        CLEAN,
        id="dead-loop-edge-a-break-inside",
    ),
    pytest.param(
        DOC
        + """
import time

from hmz.flows import Agent, flow

@flow
def run(agents: tuple[Agent], task: str) -> None:
    while True:
        time.sleep(5)
""",
        {"sleeping-loop"},
        id="sleeping-loop",
    ),
    pytest.param(
        DOC
        + """
import time

from hmz.flows import Agent, flow

@flow
def run(agents: tuple[Agent], task: str) -> None:
    while True:
        time.sleep(5)
        break
""",
        CLEAN,
        id="sleeping-loop-edge-it-can-end",
    ),
    pytest.param(
        DOC
        + """
from hmz.flows import Agent, flow

@flow
def run(agents: tuple[Agent], task: str) -> None:
    (agent,) = agents
    agent.launch(task)
""",
        {"unknown-ask"},
        id="unknown-ask",
    ),
    pytest.param(
        DOC
        + """
from hmz.flows import Agent, flow

@flow
def run(agents: tuple[Agent], task: str) -> None:
    (agent,) = agents
    print(agent.spent().output)
    session = agent.new()
    session(task, suppress=True)
    session.close()
""",
        CLEAN,
        id="unknown-ask-edge-the-interface",
    ),
    pytest.param(
        DOC
        + """
from typing import NamedTuple

from hmz.flows import Agent, Person, flow

class Crew(NamedTuple):
    actor: Agent
    human: Person

@flow
def run(agents: Crew, task: str) -> None:
    agents.reviewer(task)
""",
        {"unknown-ask"},
        id="unknown-ask-a-place-not-declared",
    ),
    pytest.param(
        DOC
        + """
from typing import NamedTuple

from hmz.flows import Agent, Person, flow

class Crew(NamedTuple):
    actor: Agent
    human: Person

@flow
def run(agents: Crew, task: str) -> None:
    agents.actor(task, suppress=True)
    agents.human.board.put("doing", task)
""",
        CLEAN,
        id="unknown-ask-edge-the-places-declared",
    ),
    pytest.param(
        DOC
        + """
from hmz.flows import Agent, flow

@flow
def run(agents: tuple[Agent], task: str) -> None:
    session = agents[0].new()
    session.rewind()
""",
        {"unknown-ask"},
        id="unknown-ask-of-a-session",
    ),
    pytest.param(
        DOC
        + """
from hmz.agents import Moment

from hmz.flows import Agent, flow

@flow
def run(agents: tuple[Agent], task: str) -> None:
    agents[0](task)
""",
        {"foreign-import"},
        id="foreign-import",
    ),
    pytest.param(
        DOC
        + """
import hmz.backends

from hmz.flows import Agent, flow

@flow
def run(agents: tuple[Agent], task: str) -> None:
    agents[0](task)
""",
        {"foreign-import"},
        id="foreign-import-a-module",
    ),
    pytest.param(
        DOC
        + """
from hmz.flows import Agent, Moment, Usage, backends, flow, home

@flow
def run(agents: tuple[Agent], task: str) -> None:
    agents[0](task)
""",
        CLEAN,
        id="foreign-import-edge-the-one-import",
    ),
    pytest.param(
        DOC
        + """
from hmz.flows import Agent, flow, teleport

@flow
def run(agents: tuple[Agent], task: str) -> None:
    agents[0](task)
""",
        {"unknown-name"},
        id="unknown-name",
    ),
    pytest.param(
        DOC
        + """
from hmz.flows import flow

@flow
def run(agents, task):
    agents[0](task)
""",
        {"unsized-agents"},
        id="unsized-agents-nothing-said",
    ),
    pytest.param(
        DOC
        + """
from hmz.flows import Agent, flow

@flow
def run(agents: tuple, task: str) -> None:
    agents[0](task)
""",
        {"unsized-agents"},
        id="unsized-agents-a-bare-tuple",
    ),
    pytest.param(
        DOC
        + """
from hmz.flows import Agent, flow

@flow
def run(agents: tuple[Agent, ...], task: str) -> None:
    agents[0](task)
""",
        {"unsized-agents"},
        id="unsized-agents-any-number",
    ),
    pytest.param(
        DOC
        + """
from hmz.flows import Agent, flow

@flow
def run(agents: tuple[Agent, Agent], task: str) -> None:
    agents[0](task)
    agents[1](task)
""",
        CLEAN,
        id="unsized-agents-edge-a-fixed-length",
    ),
    pytest.param(
        DOC
        + """
from typing import TYPE_CHECKING

from hmz.flows import flow

if TYPE_CHECKING:
    from hmz.flows import Agent

@flow
def run(agents: "tuple[Agent]", task: str) -> None:
    agents[0](task)
""",
        {"unread-annotation"},
        id="unread-annotation",
    ),
    pytest.param(
        DOC
        + """
from typing import TYPE_CHECKING

from hmz.flows import Agent, flow

if TYPE_CHECKING:
    from hmz.flows import Agent

@flow
def run(agents: "tuple[Agent]", task: str) -> None:
    agents[0](task)
""",
        CLEAN,
        id="unread-annotation-edge-also-at-runtime",
    ),
    pytest.param(
        DOC
        + """
from hmz.flows import Agent, flow

@flow(resumable=True)
def run(agents: tuple[Agent], task: str) -> None:
    agents[0](task)
""",
        {"stateless-resume"},
        id="stateless-resume",
    ),
    pytest.param(
        DOC
        + """
from hmz.flows import Agent, flow
from pydantic import BaseModel, Field

class Config(BaseModel):
    model_config = {"extra": "forbid"}

    budget: float = Field(default=1.0, description="the bound")

@flow(resumable=True)
def run(agents: tuple[Agent], task: str, config: Config | None = None) -> None:
    agents[0](task)
""",
        {"stateless-resume"},
        id="stateless-resume-a-config-in-the-way",
    ),
    pytest.param(
        DOC
        + """
from typing import Any

from hmz.flows import Agent, flow

@flow(resumable=True)
def run(agents: tuple[Agent], task: str, state: dict[str, Any]) -> None:
    agents[0](task)
""",
        CLEAN,
        id="stateless-resume-edge-the-state-third",
    ),
    pytest.param(
        DOC
        + """
import time

from hmz.flows import Agent, flow
from pydantic import BaseModel, Field

class Review(BaseModel):
    model_config = {"extra": "forbid"}

    done: bool = Field(description="whether it is over")

@flow
def run(agents: tuple[Agent, Agent], task: str) -> None:
    working = agents[0].new()
    prompt = task
    while True:
        worked = working(prompt, suppress=True)
        if worked:
            review = agents[1](task, suppress=True, schema=Review)
            if review is not None and review.done:
                return
        time.sleep(5)
""",
        {"unbounded-loop"},
        id="unbounded-loop",
    ),
    pytest.param(
        DOC
        + """
import time

from hmz.flows import Agent, flow
from pydantic import BaseModel, Field

class Review(BaseModel):
    model_config = {"extra": "forbid"}

    done: bool = Field(description="whether it is over")

@flow
def run(agents: tuple[Agent, Agent], task: str) -> None:
    working = agents[0].new()
    while True:
        working(task, suppress=True)
        review = agents[1](task, suppress=True, schema=Review)
        if review is not None and review.done:
            return
        if agents[0].spent().output > 1_000_000:
            return
        time.sleep(5)
""",
        CLEAN,
        id="unbounded-loop-edge-a-budget-bound",
    ),
    pytest.param(
        DOC
        + """
import time

from hmz.flows import Agent, flow

@flow
def run(agents: tuple[Agent], task: str) -> None:
    (agent,) = agents
    while True:
        said = agent(task, suppress=True)
        if said:
            return
        time.sleep(5)
""",
        CLEAN,
        id="unbounded-loop-edge-a-turn-merely-landing",
    ),
    pytest.param(
        DOC
        + """
from hmz.flows import Agent, flow
from pydantic import BaseModel, Field

class Review(BaseModel):
    model_config = {"extra": "forbid"}

    done: bool = Field(description="whether it is over")

@flow
def run(agents: tuple[Agent], task: str) -> None:
    review = agents[0](task, suppress=True, schema=Review)
    print(review.done)
""",
        {"unguarded-answer"},
        id="unguarded-answer",
    ),
    pytest.param(
        DOC
        + """
from hmz.flows import Agent, flow
from pydantic import BaseModel, Field

class Review(BaseModel):
    model_config = {"extra": "forbid"}

    done: bool = Field(description="whether it is over")

@flow
def run(agents: tuple[Agent], task: str) -> None:
    review = agents[0](task, suppress=True, schema=Review)
    if review is not None and review.done:
        print("done")
""",
        CLEAN,
        id="unguarded-answer-edge-guarded",
    ),
    pytest.param(
        DOC
        + """
from hmz.flows import Agent, Moment, flow

@flow
def run(agents: tuple[Agent], task: str) -> None:
    agents[0].hooks.on(Moment.PERMISSION_REQUEST, print)
""",
        {"unsaid-moment"},
        id="unsaid-moment",
    ),
    pytest.param(
        DOC
        + """
from typing import Annotated, NamedTuple

from hmz.flows import Agent, Moment, flow

class Crew(NamedTuple):
    builder: Annotated[Agent, Moment.PERMISSION_REQUEST]

@flow
def run(agents: Crew, task: str) -> None:
    agents.builder.hooks.on(Moment.PERMISSION_REQUEST, print)
""",
        CLEAN,
        id="unsaid-moment-edge-the-place-declares-it",
    ),
    pytest.param(
        DOC
        + """
from hmz.flows import Agent, Moment, flow

@flow
def run(agents: tuple[Agent], task: str) -> None:
    agents[0].hooks.on(Moment.STOP, print)
""",
        CLEAN,
        id="unsaid-moment-edge-a-moment-every-backend-runs",
    ),
    pytest.param(
        DOC
        + """
from hmz.flows import Agent, flow
from pydantic import BaseModel, Field

class Config(BaseModel):
    budget: float = Field(default=1.0, description="the bound")

@flow
def run(agents: tuple[Agent], task: str, config: Config | None = None) -> None:
    agents[0](task)
""",
        {"loose-config"},
        id="loose-config",
    ),
    pytest.param(
        DOC
        + """
from hmz.flows import Agent, flow
from pydantic import BaseModel, Field

class Config(BaseModel):
    model_config = {"frozen": True}

    budget: float = Field(default=1.0, description="the bound")

@flow
def run(agents: tuple[Agent], task: str, config: Config | None = None) -> None:
    agents[0](task)
""",
        CLEAN,
        id="loose-config-edge-frozen",
    ),
    pytest.param(
        DOC
        + """
from hmz.flows import Agent, flow
from pydantic import BaseModel

class Config(BaseModel):
    model_config = {"extra": "forbid"}

    budget: float

@flow
def run(agents: tuple[Agent], task: str, config: Config | None = None) -> None:
    agents[0](task)
""",
        {"unsaid-field"},
        id="unsaid-field",
    ),
    pytest.param(
        DOC
        + """
from hmz.flows import Agent, flow
from pydantic import BaseModel

class Answer(BaseModel):
    said: str

@flow
def run(agents: tuple[Agent], task: str) -> None:
    agents[0](task, suppress=True, schema=Answer)
""",
        CLEAN,
        id="unsaid-field-edge-a-schema-is-not-a-config",
    ),
    pytest.param(
        """
from hmz.flows import Agent, flow

@flow
def run(agents: tuple[Agent], task: str) -> None:
    agents[0](task)
""",
        {"unsaid-flow"},
        id="unsaid-flow",
    ),
    pytest.param(
        DOC
        + """
from typing import Any

from hmz.flows import Agent, flow

@flow(resumable=True)
def run(agents: tuple[Agent], task: str, state: dict[str, Any]) -> None:
    kept = state
    kept["rounds"] = kept.get("rounds", 0) + 1
    agents[0](task)
""",
        {"state-kept"},
        id="state-kept",
    ),
    pytest.param(
        DOC
        + """
from typing import Any

from hmz.flows import Agent, flow

@flow(resumable=True)
def run(agents: tuple[Agent], task: str, state: dict[str, Any]) -> None:
    kept = state
    kept["rounds"] = kept.get("rounds", 0) + 1
    agents[0](task)
    kept.clear()
""",
        CLEAN,
        id="state-kept-edge-cleared",
    ),
    pytest.param(
        DOC
        + """
from hmz.flows import Agent, flow

@flow(name="draft")
def one(agents: tuple[Agent], task: str) -> None:
    agents[0](task)

@flow(name="draft")
def two(agents: tuple[Agent], task: str) -> None:
    agents[0](task)
""",
        {"twice-named"},
        id="twice-named",
    ),
    pytest.param(
        DOC
        + """
from hmz.flows import Agent, flow

@flow(name="draft")
def one(agents: tuple[Agent], task: str) -> None:
    agents[0](task)

@flow(name="check")
def two(agents: tuple[Agent], task: str) -> None:
    agents[0](task)
""",
        CLEAN,
        id="twice-named-edge-two-names",
    ),
    pytest.param(
        DOC
        + """
def run(agents, task):
    return None
""",
        {"not-a-flow"},
        id="not-a-flow",
    ),
    pytest.param(
        "def run(:\n",
        {"unread"},
        id="unread",
    ),
]


@pytest.mark.parametrize(("source", "expected"), CASES)
def test_each_rule_fires_and_knows_the_edge(
    tmp_path: Path, source: str, expected: set[str]
) -> None:
    at = written(tmp_path, "one", textwrap.dedent(source))
    found = checked(at)
    assert {one.code for one in found} == expected, found
    for one in found:
        assert one.severity == SEVERITY[one.code]
        assert one.line >= 0


def test_a_flow_that_is_not_there_is_not_a_flow(tmp_path: Path) -> None:
    found = checked(tmp_path / "nowhere")
    assert [one.code for one in found] == ["not-a-flow"]


def test_a_single_file_flow_is_read_as_one(tmp_path: Path) -> None:
    at = tmp_path / "alone.py"
    at.write_text(
        textwrap.dedent(
            '''
            """A flow that is one file."""

            from hmz.flows import Agent, flow

            @flow
            def run(agents: tuple[Agent], task: str) -> None:
                while True:
                    agents[0](task, suppress=True)
            '''
        )
    )
    assert [one.code for one in checked(at)] == ["dead-loop"]


def test_what_is_under_skills_is_not_read(tmp_path: Path) -> None:
    """A skill may ship a helper script, and it is the agents' content, not the flow's."""
    at = written(
        tmp_path,
        "one",
        DOC
        + textwrap.dedent(
            """
            from hmz.flows import Agent, flow

            @flow
            def run(agents: tuple[Agent], task: str) -> None:
                agents[0](task)
            """
        ),
        skills={"helping": "# How to help\n"},
    )
    beside = at / "skills" / "helping" / "helper.py"
    beside.write_text("import hmz.backends\nwhile True:\n    pass\n")
    assert checked(at) == ()


def test_a_finding_says_which_file_beside_the_entry_it_is_in(tmp_path: Path) -> None:
    at = written(
        tmp_path,
        "one",
        DOC
        + textwrap.dedent(
            """
            from hmz.flows import Agent, flow

            @flow
            def run(agents: tuple[Agent], task: str) -> None:
                agents[0](task)
            """
        ),
    )
    (at / "helper.py").write_text(
        textwrap.dedent(
            '''
            """What the flow imports beside itself."""

            def churn() -> None:
                while True:
                    print("round and round")
            '''
        )
    )
    found = checked(at)
    assert [(one.code, one.where.name) for one in found] == [("dead-loop", "helper.py")]


def test_the_surface_is_the_interfaces_themselves() -> None:
    """What an agent may be asked is read off `agent.py`, not kept as a second list."""
    assert {"new", "clone", "spent", "hooks", "cycle", "__call__"} <= surface(Agent)
    assert "board" not in surface(Agent)
    assert "board" in surface(Person)
    assert {"loads", "close", "stream"} <= surface(Session)
    assert "rename" not in surface(Agent)
    assert "rename" in surface(Driven)


def test_everything_offered_is_reachable() -> None:
    """`offered` is what `unknown-name` trusts, so a name in it nothing answers is a lie."""
    said = offered()
    assert {"flow", "Agent", "Moment", "home", "models", "backends"} <= said
    assert "ClaudeCodeAgent" not in said
    for name in sorted(said):
        assert getattr(hmz.flows, name, None) is not None, name


#: Every warning a flow humanize ships or the official flowverse holds is allowed to keep.
#: rlar's loop is ended by its reviewer alone, which is the flow's own documented shape --
#: and exactly the shape the checker exists to point at, so the warning stands.
ALLOWED_WARNINGS = {"rlar": {"unbounded-loop"}}


def _swept() -> list[object]:
    """One parameter per flow humanize ships or the official flowverse holds now."""
    places = [("builtin", BUILTIN_AT)]
    places.extend(
        (verse.name, hmz.flows.holds(verse))
        for verse in hmz.flows.flowverses()
        if verse.name == hmz.flows.OFFICIAL and verse.fetched
    )
    held: list[object] = []
    seen_official = False
    for whose, under in places:
        seen_official = seen_official or whose == hmz.flows.OFFICIAL
        for name in hmz.flows.offered(under):
            at = entry(under, name)
            if at is None:
                continue
            target = at.parent if at.name == ENTRY else at
            held.append(pytest.param(target, name, id=f"{whose}/{name}"))
    if not seen_official:
        held.append(
            pytest.param(
                None,
                "official",
                id="official/unfetched",
                marks=pytest.mark.skip(
                    reason="the official flowverse has not been fetched here"
                ),
            )
        )
    return held


@pytest.mark.parametrize(("at", "name"), _swept())
def test_every_flow_humanize_offers_reads_clean(at: Path, name: str) -> None:
    """The false-positive alarm: real flows, and exactly the warnings they are allowed."""
    found = checked(at)
    errors = [one for one in found if one.severity == "error"]
    assert not errors, errors
    warned = {one.code for one in found if one.severity == "warning"}
    assert warned == ALLOWED_WARNINGS.get(name, set()), found
