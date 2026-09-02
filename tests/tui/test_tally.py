"""What a run costs, read out of the logs the CLIs keep while they are still writing them.

A backend says what a turn cost once the turn is over, and a turn is minutes long. Its log has
the same numbers a request at a time, so this reads it there -- which is what makes the figure
move while the work is happening rather than in one jump at the end of it.

The rows here are the shapes the real logs have: a Claude transcript's assistant message, a
Codex rollout's `token_count`, a Kimi server event's completed step, a ZCode rollout's
whole model request.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from hmz.coganchor.agents import (
    ClaudeCodeAgent,
    ClaudeCodeAgentConfig,
    CodexAgent,
    CodexAgentConfig,
    DshAgent,
    DshAgentConfig,
    KimiCodeCLIAgent,
    KimiCodeCLIAgentConfig,
    ZcodeAgent,
    ZcodeAgentConfig,
)
from hmz.tui.monitor import Monitor
from hmz.tui.tally import Tally


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


def test_a_zcode_session_is_counted_from_the_requests_it_rolls_out(
    home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One row per model request, and the model it names is the one that request ran on.

    ZCode has no home variable of its own, so what puts its home where a test owns it is the
    home itself.
    """
    monkeypatch.setattr(Path, "home", lambda: home / "zcode_home")
    log = home / "zcode_home" / ".zcode" / "cli" / "rollout" / "model-io-sess_z1.jsonl"
    _rows(
        log,
        {
            "sessionId": "sess_z1",
            "model": {"providerId": "zai", "modelId": "glm-nine", "role": "main"},
            "request": {"body": {"model": "glm-nine"}},
            "response": {
                "usage": {
                    "inputTokens": 900,
                    "outputTokens": 100,
                    "totalTokens": 1000,
                    "cacheReadTokens": 0,
                    "cacheWriteTokens": 0,
                }
            },
        },
    )
    agent = ZcodeAgent(ZcodeAgentConfig(model="zai/glm-nine", effort="high"))
    agent.new()._adopt("sess_z1")
    monitor = Monitor()
    tally = Tally([agent], monitor)

    tally.read()

    assert monitor.spent == {"zai/glm-nine": 1000}

    _rows(
        log,
        {
            "sessionId": "sess_z1",
            # The lite model a sub-agent ran on is counted as itself.
            "model": {"providerId": "zai", "modelId": "glm-quick", "role": "lite"},
            "response": {"usage": {"inputTokens": 40, "outputTokens": 10}},
        },
    )
    tally.read()

    assert monitor.spent == {"zai/glm-nine": 1000, "zai/glm-quick": 50}


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


def test_what_was_read_is_reported_kind_by_kind(home: Path) -> None:
    """The count is a lump; the bill is not. Only the kinds can be put a price against."""
    log = home / "claude_config_dir" / "projects" / "-tmp-work" / "s1.jsonl"
    _rows(log, _said("claude-opus-5", 300))
    agent = ClaudeCodeAgent(ClaudeCodeAgentConfig(model="opus", effort="high"))
    agent.new()._adopt("s1")
    monitor = Monitor()

    Tally([agent], monitor).read()

    assert monitor.kinds[("read", "claude-opus-5")] == {
        "input": 2,
        "output": 300,
        "cache_read": 1000,
    }  # and no cache write, which this request did not make


def test_a_log_that_says_only_a_total_is_counted_and_not_priced(home: Path) -> None:
    """Codex's rollout may name a total and no kinds. That is tokens, and no bill."""
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
                "info": {"last_token_usage": {"total_tokens": 1000}},
            },
        },
    )
    agent = CodexAgent(CodexAgentConfig(model="gpt-5.6-sol", effort="low"))
    agent.new()._adopt("t1")
    monitor = Monitor()

    Tally([agent], monitor).read()

    assert monitor.spent == {"gpt-5.6-sol": 1000}
    # Counted under no kind at all, which is what cannot be priced -- rather than guessed
    # at as input, which would be a bill nobody can stand behind.
    assert monitor.kinds[("read", "gpt-5.6-sol")] == {"": 1000}
    assert monitor.spending()[0].dollars is None


def test_a_cached_read_codex_counted_inside_the_input_is_not_billed_twice(
    home: Path,
) -> None:
    """Codex's `input_tokens` has the cached reads inside it, at a tenth of the price."""
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
                    "last_token_usage": {
                        "input_tokens": 900,
                        "cached_input_tokens": 800,
                        "output_tokens": 100,
                        "total_tokens": 1000,
                    }
                },
            },
        },
    )
    agent = CodexAgent(CodexAgentConfig(model="gpt-5.6-sol", effort="low"))
    agent.new()._adopt("t1")
    monitor = Monitor()

    Tally([agent], monitor).read()

    assert monitor.kinds[("read", "gpt-5.6-sol")] == {
        "input": 100,
        "cache_read": 800,
        "output": 100,
    }


def test_a_prompt_that_was_wholly_cached_has_no_plain_input_rather_than_none_of_it(
    home: Path,
) -> None:
    """Taking the cached reads back out can leave nothing, and nothing is not a kind."""
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
                    "last_token_usage": {
                        "input_tokens": 800,
                        "cached_input_tokens": 800,
                        "output_tokens": 100,
                        "total_tokens": 900,
                    }
                },
            },
        },
    )
    agent = CodexAgent(CodexAgentConfig(model="gpt-5.6-sol", effort="low"))
    agent.new()._adopt("t1")
    monitor = Monitor()

    Tally([agent], monitor).read()

    assert monitor.kinds[("read", "gpt-5.6-sol")] == {"cache_read": 800, "output": 100}


def test_a_backend_reports_what_its_log_says_once_that_log_has_been_read(
    home: Path,
) -> None:
    """Not before: a rollout written on another machine is one nothing here reads.

    Codex's own server counts its cached reads inside the input and never names one, while
    the rollout it writes does name them. So what the interface can show of a Codex run is
    wider than what its driver reports -- but only where the rollout is in fact on this
    machine, and a kind claimed off a log nobody read would be a nought drawn as a fact.
    """
    agent = CodexAgent(CodexAgentConfig(model="gpt-5.6-sol", effort="low"))
    agent.new()._adopt("t1")
    monitor = Monitor()
    tally = Tally([agent], monitor)

    tally.read()  # nothing written yet, so nothing claimed

    assert monitor.reports == {}

    _rows(
        home
        / "codex_home"
        / "sessions"
        / "2026"
        / "08"
        / "rollout-2026-08-06T07-14-14-t1.jsonl",
        {
            "type": "event_msg",
            "payload": {
                "type": "token_count",
                "info": {
                    "last_token_usage": {
                        "input_tokens": 900,
                        "output_tokens": 40,
                        "cached_input_tokens": 400,
                        "total_tokens": 940,
                    },
                    "total_token_usage": {"total_tokens": 940},
                },
            },
        },
    )
    tally.read()

    # The driver's two, and the cached read only the rollout names.
    assert monitor.reports[agent.id] == frozenset({"input", "output", "cache_read"})
