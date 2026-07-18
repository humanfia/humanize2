"""Tests for the minimal agent library. The shared process plumbing is exercised with `sh`-backed
fake sessions; the concrete backends are checked by the commands they build and the session ids
they read back, so no real CLI is needed."""

from __future__ import annotations

import subprocess
import uuid

import pytest

from flowjanus.agents import (
    AgentBase,
    ClaudeCodeAgent,
    CodexAgent,
    KimiCodeCLIAgent,
    SessionBase,
)

# Verbatim from `codex exec` and `kimi --prompt`, which is where the session ids come from.
CODEX_TRANSCRIPT = """OpenAI Codex v0.144.4
--------
workdir: /tmp/probe
model: gpt-5.6-sol
session id: 019fa62b-d9e1-7b73-be84-bd70260e1cf6
--------
"""
KIMI_TRANSCRIPT = """• Replying as asked.

To resume this session: kimi -r session_d227710c-06ae-4935-a3d3-412abc707af9
"""


class _EchoSession(SessionBase):
    """Runs `cat`, echoing the prompt back on stdout -- a deterministic stand-in for a CLI."""

    def __init__(self, agent: AgentBase):
        super().__init__(agent)
        self.reads = 0

    def _turn(self, prompt: str) -> tuple[list[str], str | None]:
        return (["cat"], prompt)

    def _read_session_id(self, transcript: str) -> str:
        self.reads += 1
        return "echo"


class _EchoAgent(AgentBase):
    """An agent that records every session it opens, so a test can count them."""

    def __init__(self, *, model: str, effort: str):
        super().__init__(model=model, effort=effort)
        self.started: list[_EchoSession] = []

    def start(self) -> _EchoSession:
        self.started.append(_EchoSession(self))
        return self.started[-1]


class _NoisySession(SessionBase):
    """Writes to both streams like the real CLIs do: progress on stderr, the answer on stdout."""

    def _turn(self, prompt: str) -> tuple[list[str], str | None]:
        return (["sh", "-c", "echo progress >&2; echo answer"], None)

    def _read_session_id(self, transcript: str) -> str:
        return transcript.strip()  # so a test can see exactly what the parser was given


class _NoisyAgent(AgentBase):
    def start(self) -> _NoisySession:
        return _NoisySession(self)


class _FailSession(SessionBase):
    def _turn(self, prompt: str) -> tuple[list[str], str | None]:
        return (["sh", "-c", "echo boom >&2; exit 3"], None)

    def _read_session_id(self, transcript: str) -> str:
        raise AssertionError("a failed turn must never be asked for a session id")


class _FailAgent(AgentBase):
    def start(self) -> _FailSession:
        return _FailSession(self)


def test_run_returns_agent_text() -> None:
    assert _EchoAgent(model="m", effort="high").run("hello world") == "hello world"


def test_both_streams_are_teed_and_captured(capsys: pytest.CaptureFixture[str]) -> None:
    session = _NoisyAgent(model="m", effort="high").start()
    assert session.run("x") == "answer"  # only stdout is the response
    assert session.session_id == "answer\nprogress"  # but the id parser sees both streams

    streams = capsys.readouterr()
    assert streams.out == "answer\n"
    assert streams.err == "progress\n"


def test_failed_turn_raises_and_leaves_the_session_unopened() -> None:
    session = _FailAgent(model="m", effort="high").start()
    with pytest.raises(subprocess.CalledProcessError) as exc:
        session.run("x")
    assert exc.value.returncode == 3
    assert exc.value.stderr == "boom\n"  # stderr reaches the caller as a diagnostic
    assert session.session_id is None  # so the next turn opens the session instead of resuming


def test_agent_run_uses_a_throwaway_session() -> None:
    agent = _EchoAgent(model="m", effort="high")
    agent.run("one")
    agent.run("two")
    assert len(agent.started) == 2  # a fresh session per turn: nothing carries over


def test_a_session_spans_its_turns() -> None:
    agent = _EchoAgent(model="m", effort="high")
    session = agent.start()
    assert session.session_id is None  # not opened until a turn lands
    session.run("one")
    session.run("two")
    assert session.session_id == "echo"
    assert session.reads == 1  # the id names the session, so it is read only as it opens
    assert len(agent.started) == 1  # one conversation, two turns


def test_uniform_interface_hides_backend() -> None:
    # a caller can treat any concrete agent identically
    agents: list[AgentBase] = [
        ClaudeCodeAgent(model="m", effort="high"),
        CodexAgent(model="m", effort="high"),
        KimiCodeCLIAgent(model="m", effort="high"),
    ]
    assert all(isinstance(agent.start(), SessionBase) for agent in agents)


def test_claude_opens_then_resumes() -> None:
    session = ClaudeCodeAgent(model="claude-opus-4-8", effort="high").start()

    argv, stdin = session._turn("hi")
    assert argv[:3] == ["claude", "--print", "--session-id"]
    assert uuid.UUID(argv[3])  # the id is pinned before the session exists
    assert "--dangerously-skip-permissions" in argv
    assert "--model" in argv and "claude-opus-4-8" in argv
    assert "--effort" in argv and "high" in argv
    assert stdin == "hi"  # prompt on stdin

    assert session._turn("hi")[0][3] != argv[3]  # a failed opening turn must not reuse its id

    session.session_id = session._read_session_id("")  # Claude prints nothing to read back
    assert session._turn("hi")[0][:4] == ["claude", "--print", "--resume", session.session_id]


def test_codex_opens_then_resumes() -> None:
    session = CodexAgent(model="gpt-5-codex", effort="high").start()

    argv, stdin = session._turn("hi")
    assert argv[:2] == ["codex", "exec"]
    assert "resume" not in argv
    assert "--dangerously-bypass-approvals-and-sandbox" in argv
    assert "gpt-5-codex" in argv
    assert "-c" in argv and 'model_reasoning_effort="high"' in argv
    assert argv[-1] == "-" and stdin == "hi"  # prompt on stdin

    session.session_id = session._read_session_id(CODEX_TRANSCRIPT)
    assert session.session_id == "019fa62b-d9e1-7b73-be84-bd70260e1cf6"
    assert session._turn("hi")[0][:4] == ["codex", "exec", "resume", session.session_id]


def test_kimi_opens_then_resumes() -> None:
    session = KimiCodeCLIAgent(model="kimi-code/k3", effort="high").start()

    argv, stdin = session._turn("hi")
    assert argv == ["kimi", "--prompt", "hi", "--model", "kimi-code/k3"]
    assert stdin is None  # prompt as an argument; effort is ignored for kimi

    session.session_id = session._read_session_id(KIMI_TRANSCRIPT)
    assert session.session_id == "session_d227710c-06ae-4935-a3d3-412abc707af9"
    assert session._turn("hi")[0][:3] == ["kimi", "--session", session.session_id]


@pytest.mark.parametrize("agent", [CodexAgent, KimiCodeCLIAgent])
def test_unreadable_session_id_raises(agent: type[AgentBase]) -> None:
    with pytest.raises(RuntimeError):
        agent(model="m", effort="high").start()._read_session_id("no session id here")
