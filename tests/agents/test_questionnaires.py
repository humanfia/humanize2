"""The person asked for a shape, which is a questionnaire rather than a schema in a prompt.

A coding agent held to a model is handed the schema; a person is asked a question per field and
the model is built out of what they typed. The questions go the road a coding agent's own
question goes -- `AgentBase.asked`, which whatever is driving the agent shows and answers -- so
a flow gets the same thing from the person that it gets from an agent: the model, or nothing.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

import pytest
from pydantic import BaseModel, Field

from humanize.agents import HumanAgent, human

if TYPE_CHECKING:
    from humanize.agents import Question


class Settled(BaseModel):
    """What a flow wants settled before it starts, as the model it will run on."""

    model_config = {"extra": "forbid"}

    approach: Literal["fast", "careful"] = Field(
        description="Which way should this be built?"
    )
    tests: bool = Field(description="Write tests for it?")
    rounds: int = Field(default=3, description="How many rounds may it take?")
    files: list[str] = Field(default=[], description="Which files may it touch?")


def _answers(said: list[str]) -> tuple[HumanAgent, list[Question]]:
    """A person who answers each question in turn with the next thing on the list."""
    agent = HumanAgent()
    asked: list[Question] = []

    def answering(question: Question) -> str | None:
        asked.append(question)
        return said.pop(0) if said else None

    agent.ask = answering
    return agent, asked


def test_a_shape_is_asked_a_field_at_a_time_and_built_out_of_the_answers() -> None:
    agent, asked = _answers(["careful", "yes", "5", "editor.py, undo.py"])

    settled = agent("How should I do this?", schema=Settled)

    assert settled == Settled(
        approach="careful", tests=True, rounds=5, files=["editor.py", "undo.py"]
    )
    # One question per field, in the order the model declares them, and the flow's own words
    # above the first of them: a questionnaire that opened on its first field has no title.
    assert len(asked) == 4
    assert asked[0].text.startswith("How should I do this?\n\n")
    assert "Which way should this be built?" in asked[0].text
    assert asked[1].text.startswith("Write tests for it?")
    assert "How many rounds may it take?" in asked[2].text


def test_a_field_of_a_fixed_few_offers_them_and_a_switch_offers_yes_and_no() -> None:
    """Which is what an interface has to show for the question to read as one."""
    agent, asked = _answers(["fast", "no", "-", "-"])

    agent("How should I do this?", schema=Settled)

    assert asked[0].options == ("fast", "careful")
    assert asked[1].options == ("yes", "no")
    assert asked[2].options == ()  # a number is written
    assert asked[3].options == ()


def test_a_dash_at_a_field_that_has_a_default_takes_the_default() -> None:
    """A word rather than an empty answer: an empty answer is how a prompt says nobody is there."""
    agent, asked = _answers(["fast", "no", "-", "-"])

    settled = agent("How should I do this?", schema=Settled)

    assert settled == Settled(approach="fast", tests=False, rounds=3, files=[])
    # And the person is told what to type for it, and what it will take.
    assert "`-` for 3" in asked[2].text


def test_a_field_the_model_refuses_is_put_back_in_the_models_own_words() -> None:
    """The flow that declared the field is the only thing that knows what it will take."""
    agent, asked = _answers(["sideways", "yes", "3", "-", "careful"])

    settled = agent("How should I do this?", schema=Settled)

    assert settled is not None
    assert settled.approach == "careful"
    # The fifth question is the first one again, with what the model said above it.
    assert len(asked) == 5
    assert "Which way should this be built?" in asked[4].text
    assert "Input should be" in asked[4].text


def test_nobody_there_is_a_questionnaire_that_was_not_filled_in() -> None:
    """A flow run from a command line has nobody to ask, and must not wait on one."""
    agent = HumanAgent()  # nothing set `ask`, which is how a command line leaves it

    assert agent("How should I do this?", schema=Settled, suppress=True) is None
    with pytest.raises(ValueError, match="did not answer as a Settled"):
        agent("How should I do this?", schema=Settled)


def test_walking_away_halfway_through_is_the_same_as_never_starting() -> None:
    agent, asked = _answers(["careful"])  # and then nothing more

    assert agent("How should I do this?", schema=Settled, suppress=True) is None
    assert len(asked) == 2  # it stopped at the one they did not answer


@pytest.mark.timeout(30)
def test_a_person_who_keeps_typing_the_wrong_thing_is_not_asked_forever() -> None:
    """A flow that waited on somebody who will not fill this in is a flow that has stopped."""
    agent = HumanAgent()
    asked: list[Question] = []

    def sideways(question: Question) -> str:
        asked.append(question)
        return "sideways"  # never one of the answers any of these fields takes

    agent.ask = sideways

    assert agent("How should I do this?", schema=Settled, suppress=True) is None
    # The fields once, and every field again on each of the goes it gets after that.
    assert len(asked) <= len(Settled.model_fields) * (1 + human._TRIES)


def test_asked_for_nothing_in_particular_they_answer_with_what_they_typed() -> None:
    """The shape is the new thing; being said to and answering is what this always was."""
    agent = HumanAgent()
    agent.prompting = lambda: "just do it"

    assert agent("What now?") == "just do it"


def test_a_dash_means_the_same_thing_the_second_time_a_field_is_asked() -> None:
    """What was typed at a field put back means what it means anywhere else."""
    agent, asked = _answers(["careful", "yes", "later", "-", "-"])

    settled = agent("How should I do this?", schema=Settled)

    # `later` is not a number, so the field comes back -- and a dash there takes the default
    # rather than being read as the value it is not.
    assert settled == Settled(approach="careful", tests=True, rounds=3, files=[])
    assert len(asked) == 5
    assert "How many rounds may it take?" in asked[4].text
