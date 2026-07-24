"""End-to-end tests that the goal a session is given is the backend's own, not a prompt.

Each one is written against the thing only a real backend can show: a command line that answers
`/goal` itself rather than passing it to the model, a runtime that reaches for its goal tools, a
thread that has a goal set on it afterwards. A backend that quietly read the objective as an
ordinary prompt would pass none of them.

These cost tokens and need network access, so they only run with ``pytest --run-agents``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from amflows.janus import (
    ClaudeCodeAgent,
    ClaudeCodeAgentConfig,
    CodexAgent,
    CodexAgentConfig,
    KimiCodeCLIAgent,
    KimiCodeCLIAgentConfig,
)

pytestmark = pytest.mark.agent

#: Small enough to be met in one turn, and checkable without reading the answer.
OBJECTIVE = (
    "Create a file named DONE.txt in the working directory whose only content is done."
)


def test_claude_answers_the_goal_command_itself() -> None:
    """Print mode expands `/goal`: an unanswerable one is answered by Claude, not by the model."""
    session = ClaudeCodeAgent(
        ClaudeCodeAgentConfig(model="claude-opus-4-8", effort="low")
    ).launch()

    assert "no goal set" in session.run("/goal").lower()


def test_kimi_reaches_for_its_goal_tools(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capfd: pytest.CaptureFixture[str]
) -> None:
    """Only a session the runtime holds a goal for calls a goal tool, and only it can finish one."""
    monkeypatch.chdir(tmp_path)
    KimiCodeCLIAgent(
        KimiCodeCLIAgentConfig(model="kimi-code/k3", effort="high")
    ).launch().pursue(OBJECTIVE)

    assert (
        "Goal" in capfd.readouterr().err
    )  # UpdateGoal, which no ordinary turn is given
    assert (tmp_path / "DONE.txt").read_text().strip() == "done"


def test_kimi_answers_with_the_last_turn_a_goal_took(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capfd: pytest.CaptureFixture[str]
) -> None:
    """An objective no single turn can meet, so the answer is one only the runtime reaches."""
    monkeypatch.chdir(tmp_path)
    answer = (
        KimiCodeCLIAgent(KimiCodeCLIAgentConfig(model="kimi-code/k3", effort="off"))
        .launch()
        .pursue(
            "Write the word BANANA in two separate assistant messages. Use no tools. "
            "The goal is met only after the second such message."
        )
    )

    # The first turn says BANANA and nothing else, so an answer that is anything more is one
    # from a turn the runtime started itself -- and an empty one is a message read back before
    # the agent had finished writing it.
    assert "BANANA" in capfd.readouterr().err
    assert answer and answer != "BANANA"


def test_kimi_runs_a_swarm_when_the_effort_says_to(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Swarm is a mode the session is in, so the session is what is asked whether it is in it."""
    monkeypatch.chdir(tmp_path)
    agent = KimiCodeCLIAgent(
        KimiCodeCLIAgentConfig(model="kimi-code/k3", effort="swarmmax")
    )
    session = agent.launch()
    session.run("Reply with the word ready and do nothing else.")

    status = agent.server.call("GET", f"/sessions/{session.id}/status")
    assert status["swarm_mode"] is True
    assert status["thinking_level"] == "max"


def test_codex_answers_with_the_last_turn_a_goal_took(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capfd: pytest.CaptureFixture[str]
) -> None:
    """An objective no single turn can meet, so the answer is one only the runtime reaches."""
    monkeypatch.chdir(tmp_path)
    answer = (
        CodexAgent(CodexAgentConfig(model="gpt-5.6-sol", effort="low"))
        .launch()
        .pursue(
            "Write the word BANANA in two separate assistant messages. Use no tools. "
            "The goal is met only after the second such message."
        )
    )

    # The first turn says BANANA and nothing else, so an answer that is anything more is one
    # from a turn the runtime started itself rather than the first it was given.
    assert "BANANA" in capfd.readouterr().err
    assert answer and answer != "BANANA"


def test_codex_leaves_the_goal_on_the_thread(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A goal is thread state, so the thread is what is asked afterwards whether it had one."""
    monkeypatch.chdir(tmp_path)
    agent = CodexAgent(CodexAgentConfig(model="gpt-5.6-sol", effort="low"))
    session = agent.launch()
    session.pursue(OBJECTIVE)

    server = agent.server
    goal = server.call("thread/goal/get", {"threadId": session.id})
    assert goal["goal"]["objective"] == OBJECTIVE
    assert (tmp_path / "DONE.txt").read_text().strip() == "done"
