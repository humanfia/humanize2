"""A turn asked to answer in a shape, which is what a flow reads a decision off.

Two halves: what every backend does with a schema -- ask for it, read the answer back as the
model, and say nothing at all when the answer is not one -- and what a backend that can be held
to the shape puts on the call it makes. The second is checked as the command built rather than
as a turn run, for the same reason the rest of the suite checks commands.
"""

from __future__ import annotations

import json
import subprocess
from typing import TYPE_CHECKING

import pytest
from pydantic import BaseModel

from hmz.agents import (
    AgentBase,
    AgentConfig,
    ClaudeCodeAgent,
    ClaudeCodeAgentConfig,
    CommandSessionBase,
)

if TYPE_CHECKING:
    import os

CONFIG = AgentConfig(model="m", effort="high")


class Verdict(BaseModel):
    """What a review comes to, as a flow that ends on one would declare it."""

    model_config = {"extra": "forbid"}

    done: bool
    notes: str


class _SaysSession(CommandSessionBase):
    """Answers with what its agent was made to say, whatever it was asked.

    Not the shell-backed stub the rest of the suite uses: the prompt is the script there, and
    a prompt with a JSON Schema in it is not a script.
    """

    def _turn(self, prompt: str) -> tuple[list[str], str | None]:
        agent = self._agent
        assert isinstance(agent, _SaysAgent)
        agent.heard.append(prompt)
        if agent.said is None:
            return (["sh", "-c", "echo boom >&2; exit 3"], None)
        return (["cat"], agent.said)

    def _read_session_id(self, transcript: str) -> str:
        return "one"


class _SaysAgent(AgentBase):
    """An agent whose every turn answers with the one thing, or fails."""

    def __init__(self, said: str | None) -> None:
        super().__init__(CONFIG)
        self.said = said
        self.heard: list[str] = []

    def new(self, cwd: str | os.PathLike[str] | None = None) -> _SaysSession:
        return _SaysSession(self, cwd)


def test_a_backend_that_cannot_be_held_to_a_shape_is_asked_for_it() -> None:
    """The schema itself is the instruction, and it goes into the prompt it is asked with."""
    agent = _SaysAgent('{"done": true, "notes": "all of it"}')
    agent.new()("how did it go?", schema=Verdict)

    asked = agent.heard[0]
    assert asked.startswith("how did it go?")
    assert "JSON" in asked
    assert '"done"' in asked  # the fields, as the model will be given them


def test_an_answer_is_read_back_as_the_model_it_was_asked_for() -> None:
    agent = _SaysAgent('{"done": false, "notes": "AC-2 is not done"}')
    assert agent.new()("how did it go?", schema=Verdict) == Verdict(
        done=False, notes="AC-2 is not done"
    )


def test_an_answer_with_talking_around_it_is_still_read() -> None:
    """A backend that was asked rather than held may answer with the object inside a fence."""
    agent = _SaysAgent(
        'Here is my review:\n\n```json\n{"done": true, "notes": "ok"}\n```\n'
    )
    assert agent.new()("how did it go?", schema=Verdict) == Verdict(
        done=True, notes="ok"
    )


def test_an_answer_that_is_not_the_shape_is_a_turn_that_did_not_answer() -> None:
    agent = _SaysAgent("I think it looks fine.")
    with pytest.raises(ValueError, match="did not answer as a Verdict"):
        agent.new()("how did it go?", schema=Verdict)
    # `|| true` covers it, as it covers a turn that failed: both are a flow's next round.
    assert agent.new()("how did it go?", schema=Verdict, suppress=True) is None


def test_a_turn_that_failed_answers_with_nothing_rather_than_an_empty_model() -> None:
    agent = _SaysAgent(None)
    with pytest.raises(subprocess.CalledProcessError):
        agent.new()("how did it go?", schema=Verdict)
    assert agent.new()("how did it go?", schema=Verdict, suppress=True) is None


def test_a_reviewer_that_never_ran_is_not_a_reviewer_that_agreed() -> None:
    """The rlar shape, where None is the answer to two questions at once.

    A flow reads `done` off a shape and goes round again on anything else, so a reviewer whose
    CLI is not signed in and a reviewer that had nothing to add are the same None -- and the
    loop that is held to the reviewer's judgement rather than to a budget runs on. Which of
    the two it was is the turn's to say, and it says it here.
    """
    agent = _SaysAgent(None)
    heard: list[tuple[str, str]] = []
    agent.watch(lambda _agent, _session, event: heard.append((event.kind, event.text)))

    assert agent.new()("how did it go?", schema=Verdict, suppress=True) is None

    assert [kind for kind, _text in heard].count("failed") == 1


def test_a_turn_asked_for_nothing_in_particular_is_asked_for_nothing() -> None:
    agent = _SaysAgent("looks fine")
    assert agent.new()("how did it go?") == "looks fine"
    assert agent.heard == ["how did it go?"]


def test_an_agent_asked_for_a_shape_asks_in_a_session_of_its_own() -> None:
    agent = _SaysAgent('{"done": true, "notes": "done"}')
    assert agent("how did it go?", schema=Verdict) == Verdict(done=True, notes="done")
    assert len(agent.opened) == 1


def test_claude_is_held_to_the_shape_rather_than_asked_for_it() -> None:
    """`--json-schema` is Claude's own, so the prompt says nothing about the shape."""
    session = ClaudeCodeAgent(ClaudeCodeAgentConfig(model="m", effort="high")).new()
    assert "--json-schema" not in session._command()
    session._shaping = Verdict
    argv = session._command()
    given = json.loads(argv[argv.index("--json-schema") + 1])
    assert given == Verdict.model_json_schema()
    # The whole of what is asked: the fields, their types, and that there are no others.
    assert given["required"] == ["done", "notes"]
    assert given["additionalProperties"] is False


def test_an_agent_whose_goals_are_off_is_refused_what_would_outlive_the_turn() -> None:
    """One deterministic argument, and only where the goals were actually switched off.

    Whose precedence is not the CLI's to decide: what humanize refuses is written once, in
    the order it is written here, so that a command read back off a trace is the same command
    every time.
    """
    agent = ClaudeCodeAgent(ClaudeCodeAgentConfig(model="m", effort="high"))
    session = agent.new()

    assert "--disallowedTools" not in session._command()  # goals on: nothing is refused

    agent.disable_goals()
    argv = session._command()

    assert argv.count("--disallowedTools") == 1
    assert argv[argv.index("--disallowedTools") + 1] == (
        "Agent,ScheduleWakeup,CronCreate,CronDelete,CronList"
    )
