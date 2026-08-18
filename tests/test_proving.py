"""A flow driven by stubs against a clock, held to ending every proof and saying why.

The scenarios are the questions: a budget loop walks to the end of its budget when the
reviewer never says done, a loop whose only exit is that verdict is caught by the turn cap,
a flow that takes no turns at all is killed by the clock, and the silent world -- every turn
answering nothing -- is every guard tried at once. Each proof is a subprocess, so these
tests are also the test that the child half answers the parent at all.
"""

from __future__ import annotations

import textwrap
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, Field

from hmz.flows.proving import (
    ALWAYS_DONE,
    NEVER_DONE,
    SILENT,
    Scenario,
    _made,
    _said,
    proved,
)
from tests.stubs import written

if TYPE_CHECKING:
    from pathlib import Path

#: A world that says no quickly: few turns allowed, and a short clock, so a flow that
#: cannot end is caught in test time rather than in a minute apiece.
QUICKLY = Scenario(
    "never-done", verdict=False, answer="did some of it", turns=6, seconds=20.0
)

#: A budget loop in miniature: each stub turn climbs 100k output tokens, so three turns
#: spend the 250k this flow holds itself to.
BUDGETED = '''
"""A loop held to a budget of its own."""

import time

from hmz.flows import Agent, flow


@flow
def run(agents: tuple[Agent], task: str) -> None:
    (agent,) = agents
    while True:
        agent(task, suppress=True)
        if agent.spent().output >= 250_000:
            return
        time.sleep(5)
'''

#: A loop whose one way out is the reviewer's verdict, which is rlar's shape.
VERDICT_ONLY = '''
"""A loop only its reviewer can end."""

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
'''


def test_a_budget_loop_ends_when_the_reviewer_never_says_done(tmp_path: Path) -> None:
    """The point of the whole module: bounded flows end in the worst world there is."""
    at = written(tmp_path, "one", textwrap.dedent(BUDGETED))
    proof = proved(at, scenarios=(NEVER_DONE,))
    assert proof.findings == ()
    (outcome,) = proof.outcomes
    assert outcome.finished
    assert outcome.turns == 3
    assert outcome.said == ""


def test_a_verdict_only_loop_is_caught_by_the_turn_cap(tmp_path: Path) -> None:
    at = written(tmp_path, "one", textwrap.dedent(VERDICT_ONLY))
    proof = proved(at, scenarios=(QUICKLY, ALWAYS_DONE))
    never, always = proof.outcomes
    assert not never.finished
    assert never.turns == QUICKLY.turns
    assert f"{QUICKLY.turns} turns" in never.said
    # The same loop under a reviewer that says yes ends the way it means to.
    assert always.finished
    assert always.turns == 2


def test_a_flow_that_takes_no_turns_is_killed_by_the_clock(tmp_path: Path) -> None:
    at = written(
        tmp_path,
        "one",
        textwrap.dedent(
            '''
            """A loop with no turns for the cap to count."""

            from hmz.flows import Agent, flow


            @flow
            def run(agents: tuple[Agent], task: str) -> None:
                held = 0
                while True:
                    held += 1
            '''
        ),
    )
    proof = proved(at, scenarios=(Scenario("spin", None, "", seconds=3.0),))
    (outcome,) = proof.outcomes
    assert not outcome.finished
    assert "still running after 3s" in outcome.said


def test_a_crash_is_the_outcome_with_its_last_words(tmp_path: Path) -> None:
    at = written(
        tmp_path,
        "one",
        textwrap.dedent(
            '''
            """A flow that falls over."""

            from hmz.flows import Agent, flow


            @flow
            def run(agents: tuple[Agent], task: str) -> None:
                raise RuntimeError("the kettle is on fire")
            '''
        ),
    )
    proof = proved(at, scenarios=(ALWAYS_DONE,))
    (outcome,) = proof.outcomes
    assert not outcome.finished
    assert "the kettle is on fire" in outcome.said


def test_what_is_not_a_flow_is_a_refused_load(tmp_path: Path) -> None:
    at = written(tmp_path, "one", '"""Not a flow."""\n\nx = 1\n')
    proof = proved(at, scenarios=(ALWAYS_DONE,))
    assert [one.code for one in proof.findings] == ["refused-load"]
    assert proof.findings[0].severity == "error"
    assert "marked @flow()" in proof.findings[0].said
    (outcome,) = proof.outcomes
    assert not outcome.finished


#: A flow whose bound is its config, for proving the config reaches it.
CONFIGURED = '''
"""A loop held to whatever budget it is set up with."""

from hmz.flows import Agent, flow
from pydantic import BaseModel, Field


class Config(BaseModel):
    model_config = {"extra": "forbid"}

    budget: float = Field(default=1.0, ge=0, description="millions of output tokens")


@flow
def run(agents: tuple[Agent], task: str, config: Config | None = None) -> None:
    (agent,) = agents
    held = config or Config()
    while True:
        agent(task, suppress=True)
        if agent.spent().output >= held.budget * 1_000_000:
            return
'''


def test_a_config_is_read_back_through_the_flows_own_model(tmp_path: Path) -> None:
    at = written(tmp_path, "one", textwrap.dedent(CONFIGURED))
    # 0.3 million at 100k a turn is three turns: the setting reached the loop.
    proof = proved(at, config={"budget": 0.3}, scenarios=(NEVER_DONE,))
    assert proof.findings == ()
    assert proof.outcomes[0].finished
    assert proof.outcomes[0].turns == 3
    # And one the model refuses is refused before anything runs.
    refused = proved(at, config={"budget": "a lot"}, scenarios=(NEVER_DONE,))
    assert [one.code for one in refused.findings] == ["refused-load"]
    assert not refused.outcomes[0].finished


def test_an_empty_proof_only_loads_and_reads_the_live_config(tmp_path: Path) -> None:
    at = written(tmp_path, "one", textwrap.dedent(CONFIGURED))
    proof = proved(at, scenarios=())
    assert proof == ((), ())
    # A config the static reading cannot see is still read here, off the model itself.
    loose = written(
        tmp_path,
        "loose",
        textwrap.dedent(
            '''
            """A flow with a config that says nothing about itself."""

            from hmz.flows import Agent, flow
            from pydantic import BaseModel


            class Config(BaseModel):
                budget: float = 1.0


            @flow
            def run(agents: tuple[Agent], task: str, config: Config | None = None) -> None:
                agents[0](task)
            '''
        ),
    )
    told = proved(loose, scenarios=())
    assert [one.code for one in told.findings] == ["loose-config", "unsaid-field"]
    assert {one.severity for one in told.findings} == {"warning"}


#: A flow reading a shaped answer: one guarded, one not, for the silent world to tell apart.
GUARDED = '''
"""A flow that guards what a turn answered."""

from hmz.flows import Agent, flow
from pydantic import BaseModel, Field


class Review(BaseModel):
    model_config = {"extra": "forbid"}

    done: bool = Field(description="whether it is over")


@flow
def run(agents: tuple[Agent], task: str) -> None:
    (agent,) = agents
    while True:
        review = agent(task, suppress=True, schema=Review)
        if review is not None and review.done:
            return
        if agent.spent().output >= 200_000:
            return
'''

UNGUARDED = '''
"""A flow that reads a field off whatever came back."""

from hmz.flows import Agent, flow
from pydantic import BaseModel, Field


class Review(BaseModel):
    model_config = {"extra": "forbid"}

    done: bool = Field(description="whether it is over")


@flow
def run(agents: tuple[Agent], task: str) -> None:
    review = agents[0](task, suppress=True, schema=Review)
    print(review.done)
'''


def test_the_silent_world_is_every_guard_tried_at_once(tmp_path: Path) -> None:
    guarded = written(tmp_path, "guarded", textwrap.dedent(GUARDED))
    proof = proved(guarded, scenarios=(SILENT,))
    assert proof.outcomes[0].finished  # None answers taken again, until the budget
    unguarded = written(tmp_path, "unguarded", textwrap.dedent(UNGUARDED))
    told = proved(unguarded, scenarios=(SILENT,))
    assert not told.outcomes[0].finished
    assert "AttributeError" in told.outcomes[0].said


def test_the_person_answers_what_the_scenario_says(tmp_path: Path) -> None:
    at = written(
        tmp_path,
        "one",
        textwrap.dedent(
            '''
            """A conversation, over when the person says nothing."""

            from typing import NamedTuple

            from hmz.flows import Agent, Person, flow


            class Chat(NamedTuple):
                assistant: Agent
                human: Person


            @flow
            def run(agents: Chat, task: str) -> None:
                conversation = agents.assistant.new()
                said = task
                while said:
                    answered = conversation(said, suppress=True)
                    said = agents.human(answered)
            '''
        ),
    )
    # Nobody at the prompt: the flow does the one thing it was given and stops.
    silent = proved(at, scenarios=(SILENT,))
    assert silent.outcomes[0].finished
    assert silent.outcomes[0].turns == 2  # the assistant's turn, and the person's ""
    # A person who never stops talking is a conversation that never ends: the cap's.
    chatty = proved(at, scenarios=(Scenario("chatty", True, "go on", turns=9),))
    assert not chatty.outcomes[0].finished


def test_an_async_flow_is_awaited(tmp_path: Path) -> None:
    at = written(
        tmp_path,
        "one",
        textwrap.dedent(
            '''
            """A flow written as a coroutine."""

            from hmz.flows import Agent, flow


            @flow
            async def run(agents: tuple[Agent], task: str) -> None:
                await agents[0].aturn(task, suppress=True)
            '''
        ),
    )
    proof = proved(at, scenarios=(ALWAYS_DONE,))
    (outcome,) = proof.outcomes
    assert outcome.finished, outcome
    assert outcome.turns == 1


class Nested(BaseModel):
    said: str
    fine: bool


class Shaped(BaseModel):
    done: bool
    notes: str
    stage: Literal["draft", "final"]
    rounds: int = 4
    weight: float
    parts: list[str]
    inner: Nested
    extra: str | None = None


def test_a_shaped_answer_is_fabricated_field_by_field() -> None:
    made = _made(Shaped, NEVER_DONE)
    held = Shaped.model_validate(made)
    assert held.done is False  # the verdict, whatever the field is called
    assert held.notes == NEVER_DONE.answer
    assert held.stage == "draft"  # the first of a literal's few
    assert held.rounds == 4  # the default, where the field has one
    assert held.weight == 0
    assert held.parts == []
    assert held.inner == Nested(said=NEVER_DONE.answer, fine=False)
    assert held.extra == NEVER_DONE.answer  # a string, even behind a union


def test_a_shape_nothing_can_be_fabricated_for_answers_nothing() -> None:
    class Impossible(BaseModel):
        count: int = Field(ge=5)  # fabricated as 0, which the model then refuses

    assert _said(Impossible, ALWAYS_DONE) == ""
    # And the silent world answers nothing whatever the shape.
    assert _said(Shaped, SILENT) == ""
    assert _said(None, SILENT) == ""
    assert _said(None, ALWAYS_DONE) == ALWAYS_DONE.answer


def test_a_list_that_takes_at_least_some_is_answered_with_that_many() -> None:
    from typing import Annotated

    class Planned(BaseModel):
        lanes: list[Nested] = Field(min_length=3)
        tags: list[Annotated[str, Field(min_length=1)]] = Field(min_length=1)
        loose: list[str]

    made = _made(Planned, NEVER_DONE)
    held = Planned.model_validate(made)
    assert len(held.lanes) == 3
    assert held.lanes[0] == Nested(said=NEVER_DONE.answer, fine=False)
    assert held.tags == [NEVER_DONE.answer]
    assert held.loose == []
