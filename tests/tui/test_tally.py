"""What a run costs, read out of the logs the CLIs keep while they are still writing them.

A backend says what a turn cost once the turn is over, and a turn is minutes long. Its log has
the same numbers a request at a time, so this reads it there -- which is what makes the figure
move while the work is happening rather than in one jump at the end of it.

The rows here are the shapes the real logs have: a Claude transcript's assistant message, a
Codex rollout's `token_count`, a Kimi server event's completed step.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

from hmz.agents import (
    ClaudeCodeAgent,
    ClaudeCodeAgentConfig,
    CodexAgent,
    CodexAgentConfig,
    DshAgent,
    DshAgentConfig,
    KimiCodeCLIAgent,
    KimiCodeCLIAgentConfig,
)
from hmz.tui.monitor import Monitor
from hmz.tui.tally import Tally

if TYPE_CHECKING:
    from pathlib import Path


def _rows(path: Path, *rows: dict[str, object]) -> None:
    """Appends rows to a log, as the CLI writing it would.

    Args:
      path: The log, whose directory is made if it is not there.
      rows: What to append.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as stream:
        for row in rows:
            stream.write(json.dumps(row) + "\n")


def _said(model: str, output: int) -> dict[str, object]:
    """One assistant message of a Claude transcript, with the usage of the request behind it."""
    return {
        "type": "assistant",
        "message": {
            "model": model,
            "usage": {
                "input_tokens": 2,
                "output_tokens": output,
                "cache_read_input_tokens": 1000,
                "cache_creation_input_tokens": 0,
            },
        },
    }


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Puts every backend's home somewhere this test owns."""
    for variable in (
        "CLAUDE_CONFIG_DIR",
        "CODEX_HOME",
        "DSH_HOME",
        "KIMI_CODE_HOME",
    ):
        monkeypatch.setenv(variable, str(tmp_path / variable.lower()))
    return tmp_path


def test_a_claude_turn_is_counted_while_it_is_still_being_written(home: Path) -> None:
    """Read again as it grows, and never twice: a log is appended to, not replaced."""
    log = home / "claude_config_dir" / "projects" / "-tmp-work" / "s1.jsonl"
    _rows(log, _said("claude-opus-5", 300))
    agent = ClaudeCodeAgent(ClaudeCodeAgentConfig(model="opus", effort="high"))
    session = agent.new()
    session._adopt("s1")
    monitor = Monitor()
    tally = Tally([agent], monitor)

    tally.read()

    assert monitor.spent == {"claude-opus-5": 1302}  # named as the transcript names it

    tally.read()  # nothing new written, so nothing counted again

    assert monitor.spent == {"claude-opus-5": 1302}

    _rows(
        log, _said("claude-opus-5", 500)
    )  # the turn goes on, still inside the same turn
    tally.read()

    assert monitor.spent == {"claude-opus-5": 2804}


def test_a_sub_agent_is_counted_as_the_model_it_ran_on(home: Path) -> None:
    """A sub-agent writes a transcript of its own, and its tokens are the run's."""
    projects = home / "claude_config_dir" / "projects" / "-tmp-work"
    _rows(projects / "s1.jsonl", _said("claude-opus-5", 300))
    _rows(
        projects / "s1" / "subagents" / "agent-one.jsonl", _said("claude-haiku-4-5", 40)
    )
    agent = ClaudeCodeAgent(ClaudeCodeAgentConfig(model="opus", effort="high"))
    agent.new()._adopt("s1")
    monitor = Monitor()

    Tally([agent], monitor).read()

    assert monitor.spent == {"claude-opus-5": 1302, "claude-haiku-4-5": 1042}


def test_a_codex_thread_is_counted_from_the_rollout_it_writes(home: Path) -> None:
    """`last_token_usage` is the request that just came back, and they add up to the thread."""
    log = (
        home
        / "codex_home"
        / "sessions"
        / "2026"
        / "08"
        / "rollout-2026-08-06T07-14-14-t1.jsonl"
    )
    _rows(
        log,
        {
            "type": "event_msg",
            "payload": {
                "type": "token_count",
                "info": {
                    "last_token_usage": {"input_tokens": 900, "total_tokens": 1000},
                    "total_token_usage": {"total_tokens": 1000},
                },
            },
        },
    )
    agent = CodexAgent(CodexAgentConfig(model="gpt-5.6-sol", effort="low"))
    agent.new()._adopt("t1")
    monitor = Monitor()
    tally = Tally([agent], monitor)

    tally.read()

    assert monitor.spent == {"gpt-5.6-sol": 1000}  # the model the agent runs at

    _rows(
        log,
        {
            "type": "event_msg",
            "payload": {
                "type": "token_count",
                "info": {
                    "last_token_usage": {"total_tokens": 500},
                    "total_token_usage": {"total_tokens": 1500},
                },
            },
        },
    )
    tally.read()

    assert monitor.spent == {"gpt-5.6-sol": 1500}


def test_a_dsh_session_is_counted_from_its_assistant_messages(home: Path) -> None:
    log = (
        home / "dsh_home" / "sessions" / "--tmp-work--" / "session-d1" / "session.jsonl"
    )
    _rows(
        log,
        {
            "type": "assistant/message",
            "data": {
                "message": {
                    "source": {
                        "kind": "model",
                        "provider": "deepseek-official",
                        "model": "deepseek-v4-pro",
                    }
                },
                "usage": {
                    "inputTokens": 11,
                    "outputTokens": 7,
                    "cacheReadTokens": 3,
                    "cacheWriteTokens": 2,
                    "reasoningTokens": 5,
                },
            },
        },
    )
    agent = DshAgent(DshAgentConfig(model="deepseek-v4-flash", effort="high"))
    agent.new()._adopt("session-d1")
    monitor = Monitor()

    Tally([agent], monitor).read()

    # The log names the actual model, and reasoning is already part of output.
    assert monitor.spent == {"deepseek-v4-pro": 23}


def test_a_kimi_session_is_counted_from_the_steps_its_daemon_writes(home: Path) -> None:
    log = home / "kimi_code_home" / "server" / "events" / "session_k1.jsonl"
    _rows(
        log,
        {
            "kind": "event",
            "envelope": {
                "type": "turn.step.completed",
                "payload": {
                    "type": "turn.step.completed",
                    "usage": {
                        "inputOther": 2847,
                        "output": 39,
                        "inputCacheRead": 19200,
                        "inputCacheCreation": 0,
                    },
                },
            },
        },
    )
    agent = KimiCodeCLIAgent(KimiCodeCLIAgentConfig(model="kimi-code/k3", effort="max"))
    agent.new()._adopt("session_k1")
    monitor = Monitor()

    Tally([agent], monitor).read()

    assert monitor.spent == {"kimi-code/k3": 22086}


def test_a_row_that_is_only_half_written_is_left_for_the_next_read(home: Path) -> None:
    """A log is read while it is being written, so the last line of it may not be a line."""
    log = home / "claude_config_dir" / "projects" / "-tmp-work" / "s1.jsonl"
    _rows(log, _said("claude-opus-5", 300))
    with log.open("a") as stream:
        stream.write(
            json.dumps(_said("claude-opus-5", 500))[:40]
        )  # still being written
    agent = ClaudeCodeAgent(ClaudeCodeAgentConfig(model="opus", effort="high"))
    agent.new()._adopt("s1")
    monitor = Monitor()
    tally = Tally([agent], monitor)

    tally.read()

    assert monitor.spent == {
        "claude-opus-5": 1302
    }  # the whole row, and only the whole row

    with log.open("a") as stream:  # the rest of it lands
        stream.write(json.dumps(_said("claude-opus-5", 500))[40:] + "\n")
    tally.read()

    assert monitor.spent == {"claude-opus-5": 2804}


def test_a_session_with_no_log_to_read_is_left_to_its_backend(home: Path) -> None:
    """An agent working on another machine keeps its log there, and says so itself."""
    agent = ClaudeCodeAgent(ClaudeCodeAgentConfig(model="opus", effort="high"))
    agent.new()._adopt("nowhere")
    monitor = Monitor()

    Tally([agent], monitor).read()
    monitor.spend(agent.id, 4000, model="opus")  # what the turn itself reported

    assert monitor.spent == {"opus": 4000}
