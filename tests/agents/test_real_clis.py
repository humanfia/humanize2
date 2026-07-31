"""The three command-line backends against the real binaries.

The stand-ins elsewhere print a protocol; this is the protocol. What it pins is what only the
real thing can confirm: that pi resumes the session it was pinned to and takes a word put into
a running turn, and that opencode and mimocode carry a conversation across two runs and say
what each of them cost.

Each runs in a directory of its own, so an agent that decides to tidy up tidies up nothing of
this project's.
"""

from __future__ import annotations

import shutil
from typing import TYPE_CHECKING

import pytest

from humanize.agents import (
    Event,
    MimoCodeAgent,
    MimoCodeAgentConfig,
    OpencodeAgent,
    OpencodeAgentConfig,
    PiAgent,
    PiAgentConfig,
)

if TYPE_CHECKING:
    from pathlib import Path

#: Small and quick: what is being tested is the plumbing, not the model.
PI = PiAgentConfig(model="openai-codex/gpt-5.4-mini", effort="low")
OPENCODE = OpencodeAgentConfig(model="opencode/nemotron-3-ultra-free", effort="low")
MIMO = MimoCodeAgentConfig(model="openai/gpt-5.4-mini", effort="low")


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A directory of its own for the turn to work in, which is where it is run from."""
    monkeypatch.chdir(tmp_path)
    return tmp_path


@pytest.mark.agent
@pytest.mark.timeout(600)
def test_pi_carries_a_conversation_and_says_what_it_cost(workspace: Path) -> None:
    if shutil.which("pi") is None:
        pytest.skip("pi is not installed here")
    session = PiAgent(PI).new()
    said = list(session.stream("Remember the number 4711. Reply with exactly: OK"))

    assert said[-1].kind == "result"
    assert "OK" in said[-1].text
    assert sum(said[-1].tokens.values()) > 0  # it says what the turn cost
    assert session.id  # and names the session the turn landed in
    # The same conversation, resumed: the second turn has the first one in context.
    assert "4711" in session("What number did I ask you to remember? Digits only.")


@pytest.mark.agent
@pytest.mark.timeout(600)
def test_pi_takes_a_word_put_into_the_turn_it_is_running(workspace: Path) -> None:
    if shutil.which("pi") is None:
        pytest.skip("pi is not installed here")
    session = PiAgent(PI).new()

    # Put in at the first thing the agent says rather than after a wait: the turn is provably
    # under way by then, however fast the model happens to be today.
    said: list[Event] = []
    for event in session.stream("Count from 1 to 40, one number per line. No tools."):
        if not said:
            session.interject("STOP. Ignore the counting. Reply with exactly: STEERED")
        said.append(event)

    assert said[-1].kind == "result"
    assert (
        sum(event.kind == "result" for event in said) == 1
    )  # one turn, two things said
    assert "STEERED" in said[-1].text
    # And nothing of it was left behind for the next turn to pick up as its own.
    assert "SECOND" in session("Reply with exactly: SECOND")


@pytest.mark.agent
@pytest.mark.timeout(600)
def test_pi_runs_a_tool_where_the_turn_lands(workspace: Path) -> None:
    if shutil.which("pi") is None:
        pytest.skip("pi is not installed here")
    session = PiAgent(PI).new()
    said = list(session.stream("Use the bash tool to run `echo hi`, then reply: DONE"))

    assert any(event.kind == "tool" for event in said)
    assert said[-1].kind == "result"


@pytest.mark.agent
@pytest.mark.timeout(600)
def test_opencode_carries_a_conversation_across_two_runs(workspace: Path) -> None:
    if shutil.which("opencode") is None:
        pytest.skip("opencode is not installed here")
    session = OpencodeAgent(OPENCODE).new()
    said = list(session.stream("Remember the number 4711. Reply with exactly: OK"))

    assert said[-1].kind == "result"
    assert "OK" in said[-1].text
    assert sum(said[-1].tokens.values()) > 0
    assert session.id.startswith("ses_")
    # A run of its own, resuming the session the first one opened.
    assert "4711" in session("What number did I ask you to remember? Digits only.")


@pytest.mark.agent
@pytest.mark.timeout(600)
def test_mimo_is_the_same_program_under_its_own_name(workspace: Path) -> None:
    if shutil.which("mimo") is None:
        pytest.skip("mimocode is not installed here")
    session = MimoCodeAgent(MIMO).new()
    said = list(session.stream("Reply with exactly: OK"))

    assert said[-1].kind == "result"
    assert "OK" in said[-1].text
    assert session.id.startswith("ses_")
