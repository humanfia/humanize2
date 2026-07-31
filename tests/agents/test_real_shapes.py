"""End-to-end tests that a shape asked for is the backend's own rather than a word in a prompt.

Each is written against the thing only a real backend can show: an answer that is the object
and nothing else, from a turn that was never told in words to write JSON.

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
