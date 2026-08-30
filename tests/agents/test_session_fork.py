"""A conversation that has got somewhere, tried two ways.

`session.fork` is the other half of `agent.clone`, under the other word: an agent is structure,
so cloning one copies the structure and none of the history; a session is history, so forking
one copies the history and none of the structure. What comes back is a second conversation
knowing everything this one knows and nothing either of them is told afterwards -- its own id,
its own spending, its own line in the run's record.

The carrying is the CLI's own fork and never a transcript replayed, so what is checked here is
the call each backend is asked to fork with, and that a backend with no fork refuses rather
than handing back the one conversation twice.
"""

from __future__ import annotations

import json
import os
import sys
from typing import TYPE_CHECKING, Any, cast

import pytest

from hmz.agents import (
    AgentConfig,
    ClaudeCodeAgent,
    ClaudeCodeAgentConfig,
    CodexAgent,
    CodexAgentConfig,
    CommandSessionBase,
    GrokBuildAgent,
    GrokBuildAgentConfig,
    KimiCodeCLIAgent,
    KimiCodeCLIAgentConfig,
    OpencodeAgent,
    OpencodeAgentConfig,
    PiAgent,
    PiAgentConfig,
    QwenCodeAgent,
    QwenCodeAgentConfig,
    SessionBase,
    StreamSessionBase,
)
from hmz.agents.skills import Loaded
from hmz.epic import Epic, sessions
from tests.stubs import ShellAgent

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

CONFIG = AgentConfig(model="m", effort="high")
OPENCODE = OpencodeAgentConfig(model="opencode/big-pickle", effort="high")

#: An `opencode run` that answers in the events of one turn, and mints a session of its own
#: when it is told to fork -- which is what the real one does, and the whole of what a forked
#: session is made of. Everything it was called with goes in the log, so a test reads the call. Set
#: `STUBBORN` and it takes the flag and goes on writing into the session it was given, which
#: is the one way a fork can go wrong without anything looking wrong.
_OPENCODE = """
import json, os, pathlib, sys, uuid

log = pathlib.Path(LOG)
said = sys.stdin.read()
argv = sys.argv[1:]
with log.open("a") as stream:
    json.dump({"argv": argv, "stdin": said}, stream)
    stream.write("\\n")

flags = dict(zip(sys.argv, sys.argv[1:]))
session = flags.get("--session", "")
forks = "--fork" in argv and not os.environ.get("STUBBORN")
if not session or forks:
    session = "ses_" + uuid.uuid4().hex[:8]


def out(kind, part):
    print(json.dumps({"type": kind, "sessionID": session, "part": part}), flush=True)


out("text", {"id": "prt_text", "type": "text", "text": said})
out("step_finish", {"id": "prt_done", "type": "step-finish", "reason": "stop",
                    "tokens": {"total": 3, "input": 2, "output": 1, "reasoning": 0,
                               "cache": {"read": 0, "write": 0}}})
"""


class _Fake:
    """A codex app server that answers the two calls a thread is opened by."""

    def __init__(self) -> None:
        self.called: list[tuple[str, dict[str, Any]]] = []

    def permitted(self, permission: str, tier: str) -> dict[str, Any]:
        return {"approvalPolicy": permission, "serviceTier": tier}

    def call(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        self.called.append((method, params))
        return {"thread": {"id": "thread-forked"}}


#: A `kimi fork`: it says which session it cut on the one line it prints, which is the whole
#: of what the driver reads back out of it.
_KIMI = """
import json, pathlib, sys

with pathlib.Path(LOG).open("a") as stream:
    json.dump({"argv": sys.argv[1:], "stdin": ""}, stream)
    stream.write("\\n")
print('Forked to session_cut ("Fork: hello") in 12ms')
"""


def _install(binaries: Path, named: str, script: str, log: Path) -> None:
    """Puts one stand-in CLI on PATH under the name the backend calls it."""
    fake = binaries / named
    fake.write_text(f"#!{sys.executable}\n{script.replace('LOG', repr(str(log)))}")
    fake.chmod(0o755)


@pytest.fixture
def calls(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Puts the stand-ins on PATH, and answers with the log they write."""
    log = tmp_path / "calls.jsonl"
    binaries = tmp_path / "bin"
    binaries.mkdir()
    _install(binaries, "opencode", _OPENCODE, log)
    _install(binaries, "kimi", _KIMI, log)
    monkeypatch.setenv("PATH", f"{binaries}{os.pathsep}{os.environ['PATH']}")
    return log


def _argv(log: Path) -> list[list[str]]:
    """What each run of the stand-in was called with, in order."""
    return [json.loads(line)["argv"] for line in log.read_text().splitlines()]


def test_a_fork_is_a_second_conversation_cut_from_this_one(calls: Path) -> None:
    """The backend forks what it is holding, so the child opens knowing what this one knows."""
    session = OpencodeAgent(OPENCODE).new()
    session("the marker word is beluga")

    other = session.fork()
    other("what was the marker word")

    first, second = _argv(calls)
    assert (
        "--fork" not in first
    )  # the conversation this one was cut from opened normally
    assert second[second.index("--session") + 1] == session.id
    assert "--fork" in second
    assert other.id != session.id


def test_a_child_that_has_opened_goes_on_in_its_own_conversation(calls: Path) -> None:
    """The fork is the first turn and nothing after it: two turns of a child are one branch."""
    session = OpencodeAgent(OPENCODE).new()
    session("hello")
    other = session.fork()
    other("first")

    other("second")

    _, forked, again = _argv(calls)
    assert forked[forked.index("--session") + 1] == session.id
    assert again[again.index("--session") + 1] == other.id
    assert "--fork" not in again


def test_a_fork_nobody_uses_costs_nothing(calls: Path) -> None:
    """The fork happens where the first turn does, so eight branches are eight objects."""
    session = OpencodeAgent(OPENCODE).new()
    session("hello")

    held = [session.fork() for _ in range(8)]

    assert len(_argv(calls)) == 1
    assert all(one.named is None for one in held)


def test_nothing_spent_on_the_one_it_came_from_is_counted_twice(calls: Path) -> None:
    """Two branches of one conversation are two conversations to whatever reads the bill."""
    agent = OpencodeAgent(OPENCODE)
    session = agent.new()
    session("hello")
    spent = session.spent().total

    other = session.fork()
    other("again")

    assert other.spent().total == spent  # what it spent itself, not what it inherited
    assert session.spent().total == spent
    assert agent.spent().total == spent * 2


def test_the_child_is_one_of_the_agents_conversations(calls: Path) -> None:
    """A trace of the run is gathered by what the agent opened, and the child is one of them."""
    agent = OpencodeAgent(OPENCODE)
    session = agent.new()
    session("hello")

    other = session.fork()
    other("again")

    assert agent.opened == [session.id, other.id]
    assert {one.id for one in agent.sessions} == {session.id, other.id}


def test_the_run_says_which_conversation_a_child_was_cut_from(
    calls: Path, tmp_path: Path
) -> None:
    """The backend's log shows a session that opened knowing things and never says whence."""
    agent = OpencodeAgent(OPENCODE, name="builder")
    epic = Epic("branching", [agent], "go", tmp_path)
    agent.epic = epic
    session = agent.new()
    session("hello")

    session.fork()("again")

    held = {one.ident: one for one in sessions(epic.path)}
    assert held[session.id].parent == ""
    (branch,) = [one for one in held.values() if one.ident != session.id]
    assert branch.parent == session.id


def test_what_the_conversation_is_running_by_comes_across(
    calls: Path, tmp_path: Path
) -> None:
    """A child continues this conversation, so it continues at what this one had got to."""
    agent = OpencodeAgent(OPENCODE)
    # Each skill a directory of its own, and none of them the one the session works in: a
    # turn mounts what it carries under the workspace, and a skill that *is* the workspace
    # is a directory being copied into itself.
    brought = [tmp_path / "skills" / one for one in ("reading", "writing")]
    for one in brought:
        one.mkdir(parents=True)
        (one / "SKILL.md").write_text(f"# {one.name}\n")
    agent.loads([Loaded(name=one.name, at=one) for one in brought])
    session = agent.new()
    session.effort = "low"
    session.loads(["writing"])
    session("hello")

    other = session.fork()

    assert other.effort == "low"
    assert other.skills == ("writing",)


def test_a_backend_with_no_fork_refuses_rather_than_sharing_one_conversation() -> None:
    """Two loops each continuing what they take to be their own explains nothing later."""
    session = ShellAgent(CONFIG).new()
    session("echo landed")

    assert session.forks is False
    with pytest.raises(NotImplementedError, match="second"):
        session.fork()


def test_a_fork_that_landed_back_in_its_parent_is_said_rather_than_lived_with(
    calls: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A CLI that takes the flag and does not fork is the one failure nothing could explain."""
    monkeypatch.setenv("STUBBORN", "1")
    session = OpencodeAgent(OPENCODE).new()
    session("hello")

    with pytest.raises(RuntimeError, match="the conversation this one was cut from"):
        session.fork()("again")


def test_a_conversation_that_has_got_nowhere_is_one_to_open_rather_than_fork() -> None:
    """There is nothing to carry, so the answer is a session rather than a branch of one."""
    session = OpencodeAgent(OPENCODE).new()

    with pytest.raises(RuntimeError, match="has not run a turn"):
        session.fork()


def test_a_fork_whose_parent_has_moved_on_is_refused_rather_than_cut_elsewhere(
    calls: Path,
) -> None:
    """The branch point is where it was asked for, or it is a branch nobody chose."""
    session = OpencodeAgent(OPENCODE).new()
    session("hello")
    child = session.fork()

    session("carry on here")

    with pytest.raises(RuntimeError, match="taken a turn since"):
        child("and here")


def test_driving_one_child_does_not_move_the_conversation_they_came_from(
    calls: Path,
) -> None:
    """Which is what makes two branches of one conversation the ordinary thing to write."""
    session = OpencodeAgent(OPENCODE).new()
    session("hello")

    careful, quick = session.fork(), session.fork()
    careful("one way")
    quick("the other")

    assert len({session.id, careful.id, quick.id}) == 3


def _claude() -> SessionBase:
    return ClaudeCodeAgent(ClaudeCodeAgentConfig(model="m", effort="high")).new()


def _qwen() -> SessionBase:
    return QwenCodeAgent(QwenCodeAgentConfig(model="m", effort="high")).new()


def _grok() -> SessionBase:
    return GrokBuildAgent(GrokBuildAgentConfig(model="m", effort="xhigh")).new()


def _pi() -> SessionBase:
    return PiAgent(PiAgentConfig(model="m", effort="high")).new()


def _built(session: SessionBase) -> list[str]:
    """The command line one turn of this session would be, however it is built."""
    if isinstance(session, StreamSessionBase):
        return session._command()
    return cast("CommandSessionBase", session)._turn("hi")[0]


@pytest.mark.parametrize(
    ("opens", "wanted"),
    [
        (_claude, ["--resume", "parent-session", "--fork-session"]),
        (_qwen, ["--resume", "parent-session", "--fork-session"]),
        (_grok, ["--resume", "parent-session", "--fork-session"]),
        (_pi, ["--fork", "parent-session"]),
    ],
)
def test_each_backend_asks_its_own_cli_to_fork(
    opens: Callable[[], SessionBase], wanted: list[str]
) -> None:
    """The CLI's own fork does the carrying: nothing here replays a conversation."""
    session = opens()
    session._forked_from = "parent-session"

    argv = _built(session)

    assert [one for one in argv if one in wanted] == wanted
    assert session.forks is True


def test_kimi_cuts_its_fork_with_the_command_its_cli_has_for_it(calls: Path) -> None:
    """Its daemon's own route for the same thing refuses every session it is holding."""
    session = KimiCodeCLIAgent(KimiCodeCLIAgentConfig(model="m", effort="low")).new()

    cut = session._fork("session-parent")

    (argv,) = _argv(calls)
    assert argv[:4] == ["fork", "session-parent", "--yes", "--cwd"]
    assert cut == "session_cut"


def test_codex_forks_the_thread_rather_than_starting_one() -> None:
    """Its app server answers with a thread of its own holding what that one had got to."""
    session = CodexAgent(CodexAgentConfig(model="m", effort="high")).new()
    session._forked_from = "thread-parent"
    server = _Fake()

    thread = session._thread(cast("Any", server))

    (method, params) = server.called[0]
    assert method == "thread/fork"
    assert params["threadId"] == "thread-parent"
    assert thread == "thread-forked"
