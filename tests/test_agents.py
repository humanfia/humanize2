"""Tests for the minimal agent library. The shared CLI plumbing is exercised with a `cat`-backed
fake agent; the concrete agents are checked by the command they build (no real CLI needed)."""

from __future__ import annotations

import subprocess
from typing import Any

import pytest

from flowjanus.agents import (
    AgentBase,
    ClaudeCodeAgent,
    CodexAgent,
    KimiCodeCLIAgent,
)


class _EchoAgent(AgentBase):
    """Runs `cat`, which echoes the prompt back on stdout -- a deterministic stand-in for a CLI."""

    def run(self, prompt: str) -> str:
        return self._run_cli(["cat"], prompt)


class _FailAgent(AgentBase):
    def run(self, prompt: str) -> str:
        return self._run_cli(["sh", "-c", "echo boom >&2; exit 3"], None)


def _command_of(agent: AgentBase, monkeypatch: pytest.MonkeyPatch) -> tuple[list[str], str | None]:
    """Runs the agent with the CLI call stubbed out, returning the `(argv, stdin)` it built."""
    built: list[tuple[list[str], str | None]] = []

    def fake_run_cli(self: AgentBase, argv: list[str], stdin: str | None) -> str:
        built.append((argv, stdin))
        return ""

    monkeypatch.setattr(AgentBase, "_run_cli", fake_run_cli)
    agent.run("hi")
    return built[0]


def test_run_returns_agent_text() -> None:
    assert _EchoAgent(model="m", effort="high").run("hello world") == "hello world"


def test_nonzero_exit_raises() -> None:
    with pytest.raises(subprocess.CalledProcessError) as exc:
        _FailAgent(model="m", effort="high").run("x")
    assert exc.value.returncode == 3


def test_uniform_interface_hides_backend() -> None:
    # a caller can treat any concrete agent identically
    agents: list[Any] = [
        ClaudeCodeAgent(model="m", effort="high"),
        CodexAgent(model="m", effort="high"),
        KimiCodeCLIAgent(model="m", effort="high"),
    ]
    assert all(isinstance(a, AgentBase) for a in agents)


def test_claude_command(monkeypatch: pytest.MonkeyPatch) -> None:
    argv, stdin = _command_of(ClaudeCodeAgent(model="claude-opus-4-8", effort="high"), monkeypatch)
    assert argv[:3] == ["claude", "--print", "--dangerously-skip-permissions"]
    assert "--model" in argv and "claude-opus-4-8" in argv
    assert "--effort" in argv and "high" in argv
    assert stdin == "hi"  # prompt on stdin


def test_codex_command(monkeypatch: pytest.MonkeyPatch) -> None:
    argv, stdin = _command_of(CodexAgent(model="gpt-5-codex", effort="high"), monkeypatch)
    assert argv[:2] == ["codex", "exec"]
    assert "gpt-5-codex" in argv
    assert "-c" in argv and 'model_reasoning_effort="high"' in argv
    assert stdin == "hi"


def test_kimi_command_uses_arg_not_stdin(monkeypatch: pytest.MonkeyPatch) -> None:
    argv, stdin = _command_of(KimiCodeCLIAgent(model="kimi-code/k3", effort="high"), monkeypatch)
    assert argv == ["kimi", "--prompt", "hi", "--model", "kimi-code/k3"]
    assert stdin is None  # prompt as an argument; effort is ignored for kimi
