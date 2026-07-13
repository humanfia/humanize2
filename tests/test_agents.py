"""Tests for the minimal agent library. The base is exercised with a `cat`-backed fake agent;
the concrete agents are checked by the command they build (no real CLI needed)."""

from __future__ import annotations

import pytest

from flowjanus import (
    AgentBase,
    AgentError,
    ClaudeCodeAgent,
    CodexAgent,
    KimiCodeCLIAgent,
)


class _EchoAgent(AgentBase):
    """Runs `cat`, which echoes the prompt back on stdout -- a deterministic stand-in for a CLI."""

    def _command(self, prompt):
        return ["cat"], prompt


class _FailAgent(AgentBase):
    def _command(self, prompt):
        return ["sh", "-c", "echo boom >&2; exit 3"], None


def test_run_returns_agent_text():
    assert _EchoAgent().run("hello world") == "hello world"


def test_nonzero_exit_raises_agent_error():
    with pytest.raises(AgentError) as exc:
        _FailAgent().run("x")
    assert "exited 3" in str(exc.value) and "boom" in str(exc.value)


def test_uniform_interface_hides_backend():
    # a caller can treat any concrete agent identically
    agents = [
        ClaudeCodeAgent(model="m"),
        CodexAgent(model="m"),
        KimiCodeCLIAgent(model="m"),
    ]
    assert all(hasattr(a, "run") and isinstance(a, AgentBase) for a in agents)


def test_claude_command():
    argv, stdin = ClaudeCodeAgent(model="claude-opus-4-8", effort="high")._command("hi")
    assert argv[:3] == ["claude", "--print", "--dangerously-skip-permissions"]
    assert "--model" in argv and "claude-opus-4-8" in argv
    assert "--effort" in argv and "high" in argv
    assert stdin == "hi"  # prompt on stdin


def test_codex_command():
    argv, stdin = CodexAgent(model="gpt-5-codex", effort="high")._command("hi")
    assert argv[:2] == ["codex", "exec"]
    assert "gpt-5-codex" in argv
    assert "-c" in argv and 'model_reasoning_effort="high"' in argv
    assert stdin == "hi"


def test_kimi_command_uses_arg_not_stdin():
    argv, stdin = KimiCodeCLIAgent(model="kimi-code/k3", effort="high")._command("hi")
    assert argv == ["kimi", "--prompt", "hi", "--model", "kimi-code/k3"]
    assert stdin is None  # prompt as an argument; effort is ignored for kimi
