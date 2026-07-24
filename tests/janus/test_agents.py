"""Tests for the minimal agent library.

The shared process plumbing is exercised with `sh`-backed fake sessions, which take their script
as the prompt. The concrete backends are driven through `run()` against fake CLIs on PATH, so what
is checked is the command they build and the session they resume, not how they build it.
"""

from __future__ import annotations

import errno
import io
import json
import os
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

import pytest

from amflows.janus import (
    AgentBase,
    AgentConfig,
    ClaudeCodeAgent,
    ClaudeCodeAgentConfig,
    CodexAgent,
    CodexAgentConfig,
    KimiCodeCLIAgent,
    KimiCodeCLIAgentConfig,
    SessionBase,
)
from tests.janus.conftest import HereAnchor, ShellAgent

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
CODEX_ID = "019fa62b-d9e1-7b73-be84-bd70260e1cf6"
KIMI_ID = "session_d227710c-06ae-4935-a3d3-412abc707af9"

CONFIG = AgentConfig(model="m", effort="high")


class _EchoSession(SessionBase):
    """Runs `cat`, echoing the prompt back on stdout -- the only fake on the stdin path."""

    def _turn(self, prompt: str) -> tuple[list[str], str | None]:
        return (["cat"], prompt)

    def _read_session_id(self, transcript: str) -> str:
        return "echo"


class _EchoAgent(AgentBase):
    def launch(self) -> _EchoSession:
        return _EchoSession(self)


class _StubbornSession(SessionBase):
    """Fills its own stdout before reading a byte of the prompt, which a pipe cannot hold."""

    def _turn(self, prompt: str) -> tuple[list[str], str | None]:
        return (["sh", "-c", "yes answer | head -c 150000; cat > /dev/null"], prompt)

    def _read_session_id(self, transcript: str) -> str:
        return "stubborn"


class _StubbornAgent(AgentBase):
    def launch(self) -> _StubbornSession:
        return _StubbornSession(self)


class _QuitterSession(SessionBase):
    """Rejects the call and exits before reading a byte of the prompt still being written."""

    def _turn(self, prompt: str) -> tuple[list[str], str | None]:
        return (["sh", "-c", "echo 'bad flag' >&2; exit 4"], prompt)

    def _read_session_id(self, transcript: str) -> str:
        raise AssertionError("a failed turn must never be asked for a session id")


class _QuitterAgent(AgentBase):
    def launch(self) -> _QuitterSession:
        return _QuitterSession(self)


@dataclass(frozen=True)
class _Call:
    """One invocation of a fake CLI: what it was asked for, and what it was fed."""

    argv: list[str]
    stdin: str


@dataclass(frozen=True)
class _FakeCLIs:
    """Fake `claude`, `codex` and `kimi` on PATH, each recording the calls it was made with."""

    log: Path

    def calls(self) -> list[_Call]:
        return [_Call(**json.loads(line)) for line in self.log.read_text().splitlines()]


@pytest.fixture
def clis(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> _FakeCLIs:
    """Installs a fake CLI per backend, printing the transcript that backend really prints."""
    log = tmp_path / "calls.jsonl"
    binaries = tmp_path / "bin"
    binaries.mkdir()
    for name, transcript in (
        ("claude", ""),  # Claude prints no id: it takes the one it is given
        ("codex", CODEX_TRANSCRIPT),
        ("kimi", KIMI_TRANSCRIPT),
    ):
        fake = binaries / name
        fake.write_text(
            f"#!{sys.executable}\n"
            "import json, pathlib, sys\n"
            f"with pathlib.Path({str(log)!r}).open('a') as stream:\n"
            "    json.dump({'argv': sys.argv[1:], 'stdin': sys.stdin.read()}, stream)\n"
            "    stream.write('\\n')\n"
            f"sys.stdout.write({transcript!r})\n"
        )
        fake.chmod(0o755)
    monkeypatch.setenv("PATH", f"{binaries}{os.pathsep}{os.environ['PATH']}")
    return _FakeCLIs(log)


def test_run_returns_agent_text() -> None:
    assert _EchoAgent(CONFIG).launch().run("hello world") == "hello world"


def test_both_streams_are_teed_and_captured(capsys: pytest.CaptureFixture[str]) -> None:
    session = ShellAgent(CONFIG).launch()
    assert (
        session.run("echo progress >&2; echo answer") == "answer"
    )  # only stdout is the response
    assert (
        session.id == "answer\n\nprogress"
    )  # but the id parser sees both streams, kept apart

    streams = capsys.readouterr()
    assert streams.out == "answer\n"
    assert streams.err == "progress\n"


def test_failed_turn_raises_and_leaves_the_session_unopened() -> None:
    session = ShellAgent(CONFIG).launch()
    with pytest.raises(subprocess.CalledProcessError) as exc:
        session.run("echo boom >&2; exit 3")
    assert exc.value.returncode == 3
    assert exc.value.stderr == "boom\n"  # stderr reaches the caller as a diagnostic
    assert session.reads == 0  # a failed turn is never asked for a session id
    with pytest.raises(
        RuntimeError
    ):  # so the next turn opens the session instead of resuming
        _ = session.id


def test_a_session_spans_its_turns() -> None:
    session = ShellAgent(CONFIG).launch()
    with pytest.raises(RuntimeError):  # not opened until a turn lands
        _ = session.id
    session.run("echo one")
    session.run("echo two")
    assert session.id == "one"
    assert (
        session.reads == 1
    )  # the id names the session, so it is read only as it opens


def test_an_agent_is_one_agent_apart_from_its_configuration() -> None:
    # The rlar shape: an actor and the reviewer reading its work, at one model and one effort.
    actor, reviewer = _EchoAgent(CONFIG), _EchoAgent(CONFIG)
    assert actor.id != reviewer.id
    assert actor.config == reviewer.config
    # A flow that names its agents keeps those names across restarts; one left unnamed is
    # named after its class, so a trace of two of them still reads as two.
    assert _EchoAgent(CONFIG, name="actor").id == "actor"
    assert actor.id.startswith("_EchoAgent#")


def test_an_agent_remembers_every_session_it_opened() -> None:
    agent = ShellAgent(CONFIG)
    assert agent.opened == []  # nothing has been opened yet
    kept = agent.launch()
    kept.run("echo one")
    kept.run("echo two")  # the same session: noted as it opened, and only then
    for turn in range(3):  # a Ralph loop, whose sessions nobody holds on to
        agent.launch().run(f"echo loop-{turn}")

    assert agent.opened == ["one", "loop-0", "loop-1", "loop-2"]
    assert agent.sessions == [
        kept
    ]  # what the weak list cannot say, this one still does
    agent.opened.clear()  # a copy, so a reader cannot lose the agent its history
    assert len(agent.opened) == 4


def test_a_failed_turn_leaves_nothing_behind_to_remember() -> None:
    agent = ShellAgent(CONFIG)
    with pytest.raises(subprocess.CalledProcessError):
        agent.launch().run("exit 3")

    assert agent.opened == []


def test_an_agent_keeps_the_sessions_it_launched() -> None:
    agent = _EchoAgent(CONFIG)
    first, second = agent.launch(), agent.launch()
    assert agent.sessions == [first, second]  # oldest first
    assert agent.config is CONFIG

    agent.sessions.clear()  # the list is a copy, so a caller cannot lose the agent its sessions
    assert agent.sessions == [first, second]


def test_an_agent_does_not_grow_by_the_sessions_a_flow_dropped() -> None:
    agent = _EchoAgent(CONFIG)
    kept = agent.launch()
    for _ in range(100):  # a Ralph loop: a session per turn, none of them kept
        agent.launch().run("x")
    assert agent.sessions == [kept]
    assert len(agent._sessions) == 1  # not even the bookkeeping is left behind


def test_launching_while_another_thread_reads_loses_no_session() -> None:
    agent = _EchoAgent(CONFIG)
    stop = threading.Event()

    def read() -> None:
        while not stop.is_set():
            len(agent.sessions)

    with ThreadPoolExecutor(max_workers=1) as pool:
        reader = pool.submit(read)
        held = [agent.launch() for _ in range(2000)]
        stop.set()
        reader.result()
    assert agent.sessions == held


def test_turns_of_one_session_do_not_overlap(tmp_path: Path) -> None:
    session = ShellAgent(CONFIG).launch()
    # `set -C` makes the redirection fail rather than truncate, so a turn that overlapped another
    # would exit nonzero instead of quietly sharing the marker.
    script = f'set -Ce; : > "{tmp_path}/turn"; sleep 0.05; rm "{tmp_path}/turn"'
    with ThreadPoolExecutor(max_workers=4) as pool:
        turns = [pool.submit(session.run, script) for _ in range(4)]
    for turn in turns:
        turn.result()  # one conversation, so its turns are a sequence


def test_a_turn_that_takes_no_prompt_on_stdin_cannot_read_ours(tmp_path: Path) -> None:
    """A backend taking its prompt in argv must not be handed the terminal we are watched from."""
    typed = tmp_path / "typed"
    typed.write_text("what the user is typing\n")
    ours = os.dup(0)
    try:
        with typed.open() as stdin:
            os.dup2(stdin.fileno(), 0)
        assert (
            ShellAgent(CONFIG).launch().run("cat") == ""
        )  # nothing to read, rather than ours
    finally:
        os.dup2(ours, 0)
        os.close(ours)


@pytest.mark.timeout(
    60, method="thread"
)  # a regression hangs rather than fails: bound it
def test_a_turn_outlives_our_own_output_going_away(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A flow piped into something that has exited must not leave its agent blocked on a write."""

    class _Closed(io.StringIO):
        def write(self, text: str) -> int:
            raise BrokenPipeError(errno.EPIPE, "Broken pipe")

    monkeypatch.setattr(sys, "stdout", _Closed())
    session = ShellAgent(CONFIG).launch()
    turn = session.run(
        "yes answer | head -c 150000"
    )  # more than a pipe holds, nowhere to tee it
    assert (
        len(turn) == 150_000
    )  # nothing can be shown, but the flow still gets its answer
    assert session.run("echo again") == "again"


@pytest.mark.timeout(
    60, method="thread"
)  # a regression hangs rather than fails: bound it
def test_output_the_encoding_cannot_decode_is_kept_and_does_not_wedge_the_session() -> (
    None
):
    session = ShellAgent(CONFIG).launch()
    # A byte the encoding cannot decode used to kill the reader; with the pipe then unread the
    # agent blocked on its next write and the turn hung, holding the session's lock forever.
    script = "printf 'thinking \\377\\n' >&2; yes noise | head -c 150000 >&2; exit 3"
    with pytest.raises(subprocess.CalledProcessError) as exc:
        session.run(script)
    assert exc.value.stderr.startswith("thinking")  # replaced, rather than fatal
    assert (
        len(exc.value.stderr) > 150_000
    )  # and the rest of the diagnostic still arrived
    assert session.run("echo again") == "again"  # the session is still usable


def test_an_agent_that_exits_mid_prompt_is_reported_by_its_exit_status() -> None:
    # The prompt is larger than a pipe holds, so the write breaks; what the caller needs is the
    # agent's own complaint, not our broken pipe -- which the flows do not catch.
    with pytest.raises(subprocess.CalledProcessError) as exc:
        _QuitterAgent(CONFIG).launch().run("P" * 300_000)
    assert exc.value.returncode == 4
    assert exc.value.stderr == "bad flag\n"


def test_a_prompt_larger_than_the_pipe_buffer_does_not_deadlock() -> None:
    # Deadlocks unless every pipe drains while the prompt is being written, which is the shape of
    # a long task file sent to an agent that reports progress before it has read all of it.
    assert len(_StubbornAgent(CONFIG).launch().run("P" * 300_000)) == 150_000


def test_claude_opens_then_resumes(clis: _FakeCLIs) -> None:
    session = ClaudeCodeAgent(
        ClaudeCodeAgentConfig(model="claude-opus-4-8", effort="high")
    ).launch()
    session.run("hi")
    session.run("again")

    opened, resumed = clis.calls()
    assert opened.argv[:2] == ["--print", "--session-id"]
    assert opened.argv[2] == session.id  # the id is pinned before the session exists
    assert "--dangerously-skip-permissions" in opened.argv
    assert opened.argv[-4:] == ["--model", "claude-opus-4-8", "--effort", "high"]
    assert opened.stdin == "hi"  # prompt on stdin
    assert resumed.argv[:3] == ["--print", "--resume", session.id]
    assert resumed.stdin == "again"


def test_codex_opens_then_resumes(clis: _FakeCLIs) -> None:
    session = CodexAgent(CodexAgentConfig(model="gpt-5-codex", effort="high")).launch()
    session.run("hi")
    session.run("again")

    opened, resumed = clis.calls()
    assert opened.argv[0] == "exec" and "resume" not in opened.argv
    assert "--dangerously-bypass-approvals-and-sandbox" in opened.argv
    assert "gpt-5-codex" in opened.argv
    assert 'model_reasoning_effort="high"' in opened.argv
    assert opened.argv[-1] == "-" and opened.stdin == "hi"  # prompt on stdin
    assert session.id == CODEX_ID  # read back out of the header the first turn printed
    assert resumed.argv[:3] == ["exec", "resume", CODEX_ID]


def test_kimi_opens_then_resumes(clis: _FakeCLIs) -> None:
    session = KimiCodeCLIAgent(
        KimiCodeCLIAgentConfig(model="kimi-code/k3", effort="high")
    ).launch()
    session.run("hi")
    session.run("again")

    opened, resumed = clis.calls()
    # prompt as an argument, not on stdin; effort is ignored for kimi
    assert opened.argv == ["--prompt", "hi", "--model", "kimi-code/k3"]
    assert opened.stdin == ""
    assert (
        session.id == KIMI_ID
    )  # read back out of the resume hint the first turn printed
    assert resumed.argv == [
        "--session",
        KIMI_ID,
        "--prompt",
        "again",
        "--model",
        "kimi-code/k3",
    ]


def test_an_anchored_agent_hands_its_whole_turn_to_the_anchor(clis: _FakeCLIs) -> None:
    """The agent still runs here, so the session it opens is still ours to resume."""
    anchor = HereAnchor(target="ssh://build-box", workspace="/srv/project")
    session = ClaudeCodeAgent(
        ClaudeCodeAgentConfig(model="claude-opus-4-8", effort="high", anchor=anchor)
    ).launch()
    session.run("hi")
    session.run("again")

    # What coganchor is given is the backend's own call, resumed session id and all.
    tail = [
        "--dangerously-skip-permissions",
        "--model",
        "claude-opus-4-8",
        "--effort",
        "high",
    ]
    assert anchor.seen == [
        ["claude", "--print", "--session-id", session.id, *tail],
        ["claude", "--print", "--resume", session.id, *tail],
    ]
    assert [call.stdin for call in clis.calls()] == ["hi", "again"]


@pytest.mark.parametrize("agent", [CodexAgent, KimiCodeCLIAgent])
def test_unreadable_session_id_raises(agent: type[AgentBase]) -> None:
    session = agent(CONFIG).launch()
    with pytest.raises(RuntimeError):
        session._read_session_id("no session id here")
