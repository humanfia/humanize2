"""End-to-end tests that a shape is the backend's own, and that a skill can be kept from one.

Each is written against the thing only a real backend can show: an answer that is the object
and nothing else, from a turn that was never told in words to write JSON, and a skill the CLI
would have loaded that the agent then says it may not use.

These cost tokens and need network access, so they only run with ``pytest --run-agents``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from pydantic import BaseModel, Field

from humanize.agents import (
    ClaudeCodeAgent,
    ClaudeCodeAgentConfig,
    CodexAgent,
    CodexAgentConfig,
)

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = pytest.mark.agent


class Answer(BaseModel):
    """One question, answered in a shape a flow could branch on."""

    model_config = {"extra": "forbid"}

    capital: str = Field(description="The city, as one word.")
    landlocked: bool = Field(description="Whether the country has no coastline.")


#: Asked as prose, with nothing in it about JSON or fields: what holds the answer to the shape
#: has to be the backend's own setting, or this is a test of the prompt.
ASKED = "What is the capital of Switzerland, and does the country have a coastline?"

#: A skill nothing would have but this test, so that finding it is finding this one.
SKILL = """---
name: banana-notes
description: Write notes about bananas. Use whenever the user mentions bananas.
---

Say BANANA and nothing else.
"""


def test_claude_answers_in_the_shape_it_was_held_to() -> None:
    session = ClaudeCodeAgent(
        ClaudeCodeAgentConfig(model="claude-haiku-4-5", effort="low")
    ).new()

    said = session(ASKED, schema=Answer)

    assert said is not None
    assert "bern" in said.capital.lower()
    assert said.landlocked is True
    # And the session is still a session: the process was started for the shape, and the turn
    # after it resumes the same conversation.
    assert "bern" in session("Which city did you just name?").lower()


def test_codex_answers_in_the_shape_it_was_held_to(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    session = CodexAgent(CodexAgentConfig(model="gpt-5.5", effort="low")).new()

    said = session(ASKED, schema=Answer)

    assert said is not None
    assert "bern" in said.capital.lower()
    assert said.landlocked is True


def test_a_claude_agent_is_refused_a_skill_it_was_not_given(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The rule reaches the agent: what it may not use, it says it may not use."""
    where = tmp_path / ".claude" / "skills" / "banana-notes"
    where.mkdir(parents=True)
    (where / "SKILL.md").write_text(SKILL)
    monkeypatch.chdir(tmp_path)

    asked = (
        "Use the banana-notes skill now, then tell me in one sentence whether you were "
        "able to use it or were refused permission."
    )
    # Given no skills at all, which is every one of them switched off.
    without = ClaudeCodeAgent(
        ClaudeCodeAgentConfig(model="claude-haiku-4-5", effort="low", skills=())
    )

    assert "refus" in without(asked).lower() or "denied" in without(asked).lower()


def test_a_codex_agent_is_not_given_a_skill_it_was_not_given(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Codex is told which are off before it lists any, so this one is not there to be used."""
    where = tmp_path / ".agents" / "skills" / "banana-notes"
    where.mkdir(parents=True)
    (where / "SKILL.md").write_text(SKILL)
    monkeypatch.chdir(tmp_path)

    with_it = CodexAgent(CodexAgentConfig(model="gpt-5.5", effort="low"))
    listed = with_it.server.call("skills/list", {"cwds": [str(tmp_path)]})
    assert any(
        skill["name"] == "banana-notes" and skill["enabled"]
        for entry in listed["data"]
        for skill in entry["skills"]
    )

    without = CodexAgent(CodexAgentConfig(model="gpt-5.5", effort="low", skills=()))
    listed = without.server.call("skills/list", {"cwds": [str(tmp_path)]})
    assert not any(
        skill["name"] == "banana-notes" and skill["enabled"]
        for entry in listed["data"]
        for skill in entry["skills"]
    )
