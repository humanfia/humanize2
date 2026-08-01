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

from humanize.agents import (
    AgentBase,
    AgentConfig,
    ClaudeCodeAgent,
    ClaudeCodeAgentConfig,
    CommandSessionBase,
)

if TYPE_CHECKING:
    import os
    from pathlib import Path

CONFIG = AgentConfig(model="m", effort="high")

SKILL = """---
name: {name}
description: does a thing
---

Do the thing.
"""


@pytest.fixture
def installed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Two skills of your own and one this project keeps, where the CLI looks for them."""
    for named in ("writing", "hf-cli"):
        where = tmp_path / "claude-home" / "skills" / named
        where.mkdir(parents=True)
        (where / "SKILL.md").write_text(SKILL.format(name=named))
    where = tmp_path / "project" / ".claude" / "skills" / "housekeeping"
    where.mkdir(parents=True)
    (where / "SKILL.md").write_text(SKILL.format(name="housekeeping"))
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "claude-home"))
    monkeypatch.chdir(tmp_path / "project")
    return tmp_path


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


def test_claude_is_refused_every_skill_this_agent_was_not_given(
    installed: Path,
) -> None:
    """An agent says which skills it has; a CLI has to be told which it may not use.

    So what goes on the command line is the rest of them, worked out from what is actually
    installed -- one rule per skill, as the tool call it would be: a skill is a tool here.
    """
    plain = ClaudeCodeAgent(ClaudeCodeAgentConfig(model="m", effort="high")).new()
    assert (
        "--disallowedTools" not in plain._command()
    )  # never asked: the CLI as it comes

    session = ClaudeCodeAgent(
        ClaudeCodeAgentConfig(model="m", effort="high", skills=("writing",))
    ).new()
    argv = session._command()
    assert (
        argv[argv.index("--disallowedTools") + 1] == "Skill(hf-cli),Skill(housekeeping)"
    )

    # An agent given none is refused all of them, which is not the same as never being asked.
    none = ClaudeCodeAgent(
        ClaudeCodeAgentConfig(model="m", effort="high", skills=())
    ).new()
    argv = none._command()
    assert (
        argv[argv.index("--disallowedTools") + 1]
        == "Skill(hf-cli),Skill(writing),Skill(housekeeping)"
    )
