"""Branching a conversation in place, preserving its prefix for the backend's cache.

Only Claude and Codex have a native history operation for it -- `--fork-session` and
`thread/fork` -- so a flow built on `Session.fork` declares the place with `Annotated[Agent,
Forks]` and is refused an unfit backend before the first turn. Both drivers are exercised
against stand-ins, so what is checked is the exact call a fork is made of, the boundary it
honours, and the isolation of the child from whatever the parent becomes afterwards.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from hmz.agents import (
    ClaudeCodeAgent,
    ClaudeCodeAgentConfig,
    ClaudeCodeSession,
    CodexAgent,
    CodexAgentConfig,
    CodexSession,
    OpencodeAgent,
    OpencodeAgentConfig,
    PiAgent,
    PiAgentConfig,
)
from hmz.flows import NotAFlow, wanted
from hmz.runner import Runner

#: A `claude --print`: it names the session it was given, forks without a prompt when asked,
#: and otherwise answers each `user` message written to it as one turn. A prompt of `boom` is
#: refused, which is how a child whose first turn fails is spelled.
_CLAUDE = """
import json, pathlib, sys

LOG = pathlib.Path(sys.argv[0] + ".log")


def note(entry):
    with LOG.open("a") as stream:
        json.dump(entry, stream)
        stream.write("\\n")


def out(said):
    print(json.dumps(said), flush=True)


argv = sys.argv[1:]
note({"argv": argv})
flags = {}
for i, one in enumerate(argv):
    if one.startswith("--") and i + 1 < len(argv) and not argv[i + 1].startswith("--"):
        flags[one] = argv[i + 1]
    elif one.startswith("--"):
        flags[one] = True
sid = flags.get("--session-id") or flags.get("--resume")
out({"type": "system", "session_id": sid})
if flags.get("--fork-session"):
    sys.exit(0)  # the fork is made by the flags alone; no prompt is owed
for line in sys.stdin:
    said = json.loads(line)
    if said.get("type") != "user":
        continue
    text = said["message"]["content"][0]["text"]
    if text == "boom":
        out({"type": "result", "subtype": "error_during_execution", "is_error": True,
             "result": ""})
        continue
    out({"type": "assistant", "message": {"id": "msg_1", "role": "assistant",
         "content": [{"type": "text", "text": text}]}})
    out({"type": "result", "subtype": "success", "is_error": False, "result": text})
"""

#: A `codex app-server`: it answers `thread/start` with one thread, `thread/fork` with another,
#: and completes whatever turn is started on either. Both the parent's server and the forked
#: child's dedicated server run this same stand-in, so what a test reads is the calls each was
#: made of and how many servers there were.
_CODEX = """
import json, pathlib, sys

LOG = pathlib.Path(sys.argv[0] + ".log")


def send(message):
    print(json.dumps(message), flush=True)


for line in sys.stdin:
    call = json.loads(line)
    with LOG.open("a") as stream:
        json.dump(call, stream)
        stream.write("\\n")
    if "id" not in call:
        continue
    method = call.get("method")
    result = {}
    if method == "thread/start":
        result = {"thread": {"id": "parent_thread"}}
    elif method == "thread/fork":
        result = {"thread": {"id": "child_thread"}}
        send({"method": "thread/status/changed",
              "params": {"threadId": "other_thread", "status": {"type": "idle"}}})
    send({"jsonrpc": "2.0", "id": call["id"], "result": result})
    if method == "thread/start":
        send({"method": "thread/status/changed",
              "params": {"status": {"type": "idle"}}})
    if method == "turn/start":
        tid = call["params"].get("threadId", "parent_thread")
        send({"method": "turn/started",
              "params": {"turnId": "turn_fake", "threadId": tid}})
        send({"method": "item/completed",
              "params": {"item": {"type": "agentMessage", "text": "answered"},
                         "threadId": tid}})
        send({"method": "turn/completed",
              "params": {"threadId": tid,
                         "turn": {"id": "turn_fake", "status": "completed"}}})
        send({"method": "thread/status/changed",
              "params": {"status": {"type": "idle"}, "threadId": tid}})
"""

#: A flow that branches a conversation, which only some backends can.
FORKING = '''"""A loop that hands the work to a forked child rather than the agent itself."""

from typing import Annotated, NamedTuple

from hmz.agents import AgentBase, Forks
from hmz.flows import flow


class Agents(NamedTuple):
    """The one it drives, which has to have a native fork."""

    worker: Annotated[AgentBase, Forks]


@flow
def run(agents: Agents, task: str) -> None:
    agents.worker.new().fork()
'''


@dataclass(frozen=True)
class _Fake:
    """A stand-in backend on PATH, and everything it was asked for."""

    log: Path

    def calls(self) -> list[dict[str, Any]]:
        return [json.loads(line) for line in self.log.read_text().splitlines()]


def _install(
    name: str, script: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> _Fake:
    """Puts one stand-in CLI on PATH under the name the backend calls it."""
    binaries = tmp_path / "bin"
    binaries.mkdir(exist_ok=True)
    fake = binaries / name
    fake.write_text(f"#!{sys.executable}\n{script}")
    fake.chmod(0o755)
    monkeypatch.setenv("PATH", f"{binaries}{os.pathsep}{os.environ['PATH']}")
    return _Fake(Path(f"{fake}.log"))


@pytest.fixture
def claude(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> _Fake:
    return _install("claude", _CLAUDE, tmp_path, monkeypatch)


@pytest.fixture
def codex(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> _Fake:
    return _install("codex", _CODEX, tmp_path, monkeypatch)


def _written(tmp_path: Path, source: str, name: str = "forking") -> str:
    """Writes a flow out and answers with its path."""
    where = tmp_path / f"{name}.py"
    where.write_text(source)
    return str(where)


# --- The capability a fork is built on -------------------------------------------------------


def test_only_claude_and_codex_say_a_fork_is_available() -> None:
    """The one thing that gates the `Forks` declaration, read off the session class."""
    assert ClaudeCodeSession.forks is True
    assert CodexSession.forks is True
    assert (
        OpencodeAgent(OpencodeAgentConfig(model="m", effort="low")).new().forks is False
    )


def test_an_unsupported_backend_refuses_a_fork_before_a_child_is_made() -> None:
    """No child is created and nothing is sent to the backend: the refusal is up front."""
    for agent in (
        PiAgent(PiAgentConfig(model="m", effort="low")),
        OpencodeAgent(OpencodeAgentConfig(model="m", effort="low")),
    ):
        with pytest.raises(NotImplementedError, match="no native fork"):
            agent.new().fork()


def test_a_fork_needs_an_opened_parent() -> None:
    """Eager and prompt-free, but only once there is a conversation to branch."""
    session = ClaudeCodeAgent(ClaudeCodeAgentConfig(model="m", effort="low")).new()
    with pytest.raises(RuntimeError, match="has not run a turn yet"):
        session.fork()


def test_a_fork_refuses_a_parent_whose_turn_is_still_running() -> None:
    """A fork while a turn is running would branch a conversation mid-answer."""
    session = ClaudeCodeAgent(ClaudeCodeAgentConfig(model="m", effort="low")).new()
    session._id = "parent"
    session._working = True
    with pytest.raises(RuntimeError, match="while a turn is running"):
        session.fork()


def test_a_fork_refuses_a_closed_parent() -> None:
    session = ClaudeCodeAgent(ClaudeCodeAgentConfig(model="m", effort="low")).new()
    session._id = "parent"
    session._ended = True
    with pytest.raises(RuntimeError, match="closed"):
        session.fork()


def test_a_fork_refuses_a_parent_that_moved_backends() -> None:
    agent = ClaudeCodeAgent(ClaudeCodeAgentConfig(model="m", effort="low"))
    session = agent.new()
    session._id = "parent"
    session._moved_to = agent.new()
    with pytest.raises(RuntimeError, match="moved"):
        session.fork()


def test_a_fork_refuses_an_unknown_permission(claude: _Fake) -> None:
    agent = ClaudeCodeAgent(ClaudeCodeAgentConfig(model="m", effort="low"))
    session = agent.new()
    assert session("hi") == "hi"
    with pytest.raises(ValueError, match="permission must be one of"):
        session.fork(permission="everything")


# --- The Forks declaration, checked before the first turn ------------------------------------


def test_a_place_that_forks_says_so(tmp_path: Path) -> None:
    (place,) = wanted(_written(tmp_path, FORKING))

    assert place.forks is True
    assert place.name == "worker"


def test_an_agent_without_a_native_fork_is_refused(tmp_path: Path) -> None:
    where = _written(tmp_path, FORKING)

    with pytest.raises(NotAFlow, match="has no native fork for"):
        Runner(where, [PiAgent(PiAgentConfig(model="m", effort="low"))])


@pytest.mark.parametrize(
    "agent",
    [
        ClaudeCodeAgent(ClaudeCodeAgentConfig(model="m", effort="low")),
        CodexAgent(CodexAgentConfig(model="m", effort="low")),
    ],
)
def test_an_agent_whose_backend_forks_is_taken(agent: object, tmp_path: Path) -> None:
    runner = Runner(_written(tmp_path, FORKING), [agent])  # pyright: ignore[reportArgumentType]

    assert len(runner.agents) == 1


def test_the_catalogue_says_which_backends_fork() -> None:
    from hmz.flows import catalogue

    (forks,) = [one for one in catalogue() if one.name == "forks"]

    assert forks.backends == frozenset({"claude", "codex"})


# --- Claude: `--resume --fork-session --session-id` ------------------------------------------


def test_claude_forks_eagerly_and_the_child_resumes_itself(claude: _Fake) -> None:
    """The branch is made by the flags alone, and the child carries on under its own id."""
    agent = ClaudeCodeAgent(ClaudeCodeAgentConfig(model="m", effort="low"))
    parent = agent.new()
    assert parent("hi") == "hi"

    child = parent.fork()

    assert child("research") == "research"
    assert parent("next") == "next"  # the parent goes on, unchanged

    calls = claude.calls()
    forked = next(call for call in calls if "--fork-session" in call["argv"])
    assert forked["argv"][forked["argv"].index("--resume") + 1] == parent.id
    assert forked["argv"][forked["argv"].index("--session-id") + 1] == child.id
    # The child's own turn resumes the child, never the parent.
    child_opened = next(
        call
        for call in calls
        if "--resume" in call["argv"]
        and call["argv"][call["argv"].index("--resume") + 1] == child.id
    )
    assert "--fork-session" not in child_opened["argv"]
    assert parent.id != child.id


def test_claude_refuses_an_intermediate_boundary(claude: _Fake) -> None:
    """Claude forks the whole conversation, so a non-None boundary is not silently ignored."""
    session = ClaudeCodeAgent(ClaudeCodeAgentConfig(model="m", effort="low")).new()
    assert session("hi") == "hi"

    with pytest.raises(NotImplementedError, match="whole conversation"):
        session.fork(last_turn_id="some-turn")


def test_a_claude_child_does_not_see_tools_added_to_the_parent_after_fork(
    claude: _Fake,
) -> None:
    """The child bridge is private, so a later parent offer cannot leak into its turn."""
    from hmz.agents import Tool

    agent = ClaudeCodeAgent(ClaudeCodeAgentConfig(model="m", effort="low"))
    parent = agent.new()
    assert parent("hi") == "hi"
    child = parent.fork()
    parent.offers([Tool(name="later", about="a later callback", call=lambda: "later")])
    child.offers([])

    assert child("research") == "research"
    child_call = next(
        call
        for call in claude.calls()
        if "--resume" in call["argv"]
        and call["argv"][call["argv"].index("--resume") + 1] == child.id
    )
    assert "--mcp-config" not in child_call["argv"]


def test_a_claude_child_whose_first_turn_fails_is_still_the_child(
    claude: _Fake,
) -> None:
    """The child id was adopted by the fork, so a failed turn is its own failure, not the fork."""
    session = ClaudeCodeAgent(ClaudeCodeAgentConfig(model="m", effort="low")).new()
    assert session("hi") == "hi"
    child = session.fork()

    with pytest.raises(subprocess.CalledProcessError):
        child("boom")

    assert child.id != session.id  # the child exists even though the turn failed


def test_reconfiguring_the_parent_does_not_change_a_claude_child(claude: _Fake) -> None:
    """The fork context froze the boundary: a later reconfiguration is the parent's own."""
    from dataclasses import replace

    agent = ClaudeCodeAgent(ClaudeCodeAgentConfig(model="m", effort="low"))
    parent = agent.new()
    assert parent("hi") == "hi"
    child = parent.fork()

    agent.reconfigure(replace(agent.config, model="changed", effort="max"))
    assert child("research") == "research"

    child_opened = next(
        call
        for call in claude.calls()
        if "--resume" in call["argv"]
        and call["argv"][call["argv"].index("--resume") + 1] == child.id
    )
    assert child_opened["argv"][child_opened["argv"].index("--model") + 1] == "m"
    assert child_opened["argv"][child_opened["argv"].index("--effort") + 1] == "low"


def test_a_fork_child_does_not_copy_pending_agent_waiting_prompts(
    claude: _Fake,
) -> None:
    agent = ClaudeCodeAgent(ClaudeCodeAgentConfig(model="m", effort="low"))
    parent = agent.new()
    assert parent("hi") == "hi"
    child = parent.fork()
    agent.waiting = lambda: ["a pending parent answer"]

    assert child("research") == "research"

    # The stand-in echoes the complete prompt, so the return value proves no parent waiting
    # prompt was appended to the child turn.


def test_a_second_fork_inherits_the_first_childs_frozen_context(claude: _Fake) -> None:
    from dataclasses import replace

    agent = ClaudeCodeAgent(ClaudeCodeAgentConfig(model="original", effort="low"))
    parent = agent.new()
    assert parent("hi") == "hi"
    child = parent.fork()
    agent.reconfigure(replace(agent.config, model="changed", effort="max"))

    grandchild = child.fork()
    assert grandchild("research") == "research"

    grandchild_call = next(
        call
        for call in claude.calls()
        if "--resume" in call["argv"]
        and call["argv"][call["argv"].index("--resume") + 1] == grandchild.id
    )
    assert (
        grandchild_call["argv"][grandchild_call["argv"].index("--model") + 1]
        == "original"
    )
    assert (
        grandchild_call["argv"][grandchild_call["argv"].index("--effort") + 1] == "low"
    )


# --- Codex: `thread/fork` on a dedicated server ----------------------------------------------


def test_codex_forks_a_thread_and_the_child_runs_on_its_own_server(
    codex: _Fake,
) -> None:
    agent = CodexAgent(CodexAgentConfig(model="gpt-5-codex", effort="high"))
    parent = agent.new()
    assert parent("first") == "answered"

    child = parent.fork()

    assert child("research") == "answered"
    assert parent("next") == "answered"  # the parent goes on, unchanged

    calls = codex.calls()
    forked = next(call for call in calls if call.get("method") == "thread/fork")
    assert forked["params"]["threadId"] == parent.id
    assert (
        "lastTurnId" not in forked["params"]
    )  # forking through the latest completed turn
    assert child.id == "child_thread"
    assert parent.id == "parent_thread"
    # Two servers: the parent's, and the child's dedicated one it overlaps on.
    assert [call.get("method") for call in calls].count("initialize") == 2
    # The child's turn went to the child thread, not the parent's.
    assert any(
        call.get("method") == "turn/start"
        and call["params"]["threadId"] == "child_thread"
        for call in calls
    )


def test_codex_forks_through_an_earlier_completed_turn(codex: _Fake) -> None:
    """An inclusive boundary: naming a completed turn forks through exactly that one."""
    agent = CodexAgent(CodexAgentConfig(model="gpt-5-codex", effort="high"))
    parent = agent.new()
    assert parent("first") == "answered"
    assert parent("second") == "answered"

    assert parent.last_turn_id == "turn_fake"
    child = parent.fork(last_turn_id=parent.last_turn_id)

    forked = next(call for call in codex.calls() if call.get("method") == "thread/fork")
    assert forked["params"]["lastTurnId"] == "turn_fake"
    assert child.id == "child_thread"


def test_reconfiguring_the_parent_does_not_change_a_codex_child(codex: _Fake) -> None:
    """The first child turn carries the frozen values, not whatever the parent became."""
    from dataclasses import replace

    agent = CodexAgent(CodexAgentConfig(model="gpt-5-codex", effort="high"))
    parent = agent.new()
    assert parent("first") == "answered"
    child = parent.fork()

    agent.reconfigure(replace(agent.config, model="changed", effort="max"))
    assert child("research") == "answered"

    child_turn = next(
        call
        for call in codex.calls()
        if call.get("method") == "turn/start"
        and call["params"]["threadId"] == "child_thread"
    )
    assert child_turn["params"]["model"] == "gpt-5-codex"
    assert child_turn["params"]["effort"] == "high"


def test_a_codex_permission_override_is_sent_to_the_native_fork(codex: _Fake) -> None:
    agent = CodexAgent(CodexAgentConfig(model="gpt-5-codex", effort="high"))
    parent = agent.new()
    assert parent("first") == "answered"

    child = parent.fork(permission="read-only")

    forked = next(call for call in codex.calls() if call.get("method") == "thread/fork")
    assert forked["params"]["sandbox"] == "read-only"
    assert forked["params"]["approvalPolicy"] == "never"
    assert child._fork_context is not None
    assert child._fork_context.cache_equivalent is False


def test_a_codex_fork_rejects_an_unknown_completed_boundary(codex: _Fake) -> None:
    agent = CodexAgent(CodexAgentConfig(model="gpt-5-codex", effort="high"))
    parent = agent.new()
    assert parent("first") == "answered"

    with pytest.raises(RuntimeError, match="not a completed turn"):
        parent.fork(last_turn_id="missing-turn")

    assert not [call for call in codex.calls() if call.get("method") == "thread/fork"]


def test_a_fork_child_error_is_not_hidden_by_suppress(claude: _Fake) -> None:
    parent = ClaudeCodeAgent(ClaudeCodeAgentConfig(model="m", effort="low")).new()
    assert parent("hi") == "hi"
    child = parent.fork()

    with pytest.raises(subprocess.CalledProcessError):
        child("boom", suppress=True)


def test_a_fork_child_does_not_enter_the_parent_fallback_chain(
    claude: _Fake, monkeypatch: pytest.MonkeyPatch
) -> None:
    from hmz.agents import Failed

    agent = ClaudeCodeAgent(ClaudeCodeAgentConfig(model="m", effort="low"))
    parent = agent.new()
    assert parent("hi") == "hi"
    child = parent.fork()

    def fail(_prompt: str, *, schema: object = None) -> Any:
        del schema
        raise Failed(1, ["claude"], "", "child failed")

    monkeypatch.setattr(child, "_stream", fail)
    monkeypatch.setattr(
        agent,
        "stands_in",
        lambda: (_ for _ in ()).throw(AssertionError("fork child used fallback")),
    )

    with pytest.raises(Failed):
        child("research")


def test_a_failed_fork_child_turn_is_recorded_without_transcript_content(
    claude: _Fake, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from hmz.cycle import Cycle

    monkeypatch.chdir(tmp_path)
    agent = ClaudeCodeAgent(ClaudeCodeAgentConfig(model="m", effort="low"))
    cycle = Cycle("forking", [agent], "task", tmp_path)
    agent.cycle = cycle
    parent = agent.new()
    assert parent("hi") == "hi"
    child = parent.fork()

    with pytest.raises(subprocess.CalledProcessError):
        child("boom", suppress=True)

    failures = [
        event for event in _events(cycle) if event.get("event") == "fork-failed"
    ]
    assert len(failures) == 1
    assert failures[0]["session_id"] == child.id
    assert "boom" not in str(failures[0])


# --- The run writes the fork down as a branch -------------------------------------------------


def test_a_fork_is_written_down_as_a_branch_not_an_open(
    claude: _Fake, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from hmz.cycle import Cycle, called, forks

    monkeypatch.chdir(tmp_path)
    agent = ClaudeCodeAgent(ClaudeCodeAgentConfig(model="m", effort="low"))
    cycle = Cycle("forking", [agent], "task", tmp_path)
    agent.cycle = cycle
    session = agent.new()
    assert session("hi") == "hi"

    child = session.fork()

    forked = [event for event in _events(cycle) if event.get("event") == "forked"]
    assert len(forked) == 1
    (said,) = forked
    assert said["parent_session_id"] == session.id
    assert said["session_id"] == child.id
    assert said["parent_key"] == called(agent.id, "claude", "", session.id)
    assert said["session_key"] == called(agent.id, "claude", "", child.id)
    # And a trace can read the branch back: the child id maps to its parent id.
    assert forks(cycle.path) == {child.id: session.id}


def test_permission_override_and_cache_equivalence_are_recorded(
    claude: _Fake, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from hmz.cycle import Cycle

    monkeypatch.chdir(tmp_path)
    agent = ClaudeCodeAgent(ClaudeCodeAgentConfig(model="m", effort="low"))
    cycle = Cycle("forking", [agent], "task", tmp_path)
    agent.cycle = cycle
    parent = agent.new()
    assert parent("hi") == "hi"

    child = parent.fork(permission="read-only")

    forked = [event for event in _events(cycle) if event.get("event") == "forked"]
    assert forked[0]["session_id"] == child.id
    assert forked[0]["permission"] == "read-only"
    assert forked[0]["cache_equivalent"] is False


def _events(cycle: Any) -> list[dict[str, Any]]:
    """Every line one cycle's own record wrote, in the order it wrote them."""
    from hmz.cycle import JOURNAL

    at = cycle.path / JOURNAL
    return [json.loads(line) for line in at.read_text().splitlines()]


# --- The failure and retry probe: a response lost after the child was made -------------------


#: A `claude` whose fork makes the child and exits without ever naming it back, which is how a
#: response lost after the backend created the branch is spelled. Every other turn behaves as
#: `_CLAUDE` does, so the parent can be opened and driven on.
_CLAUDE_LOST = """
import json, pathlib, sys

LOG = pathlib.Path(sys.argv[0] + ".log")


def note(entry):
    with LOG.open("a") as stream:
        json.dump(entry, stream)
        stream.write("\\n")


def out(said):
    print(json.dumps(said), flush=True)


argv = sys.argv[1:]
note({"argv": argv})
flags = {}
for i, one in enumerate(argv):
    if one.startswith("--") and i + 1 < len(argv) and not argv[i + 1].startswith("--"):
        flags[one] = argv[i + 1]
    elif one.startswith("--"):
        flags[one] = True
if flags.get("--fork-session"):
    sys.exit(0)  # the child is made, but its name never comes back
sid = flags.get("--session-id") or flags.get("--resume")
out({"type": "system", "session_id": sid})
for line in sys.stdin:
    said = json.loads(line)
    if said.get("type") != "user":
        continue
    text = said["message"]["content"][0]["text"]
    out({"type": "assistant", "message": {"id": "msg_1", "role": "assistant",
         "content": [{"type": "text", "text": text}]}})
    out({"type": "result", "subtype": "success", "is_error": False, "result": text})
"""

#: A `codex app-server` whose `thread/fork` fails after the branch was made, so the child id is
#: lost with the response. It is asked once, and the driver must not ask again.
_CODEX_FORK_LOST = """
import json, pathlib, sys

LOG = pathlib.Path(sys.argv[0] + ".log")


def send(message):
    print(json.dumps(message), flush=True)


for line in sys.stdin:
    call = json.loads(line)
    with LOG.open("a") as stream:
        json.dump(call, stream)
        stream.write("\\n")
    if "id" not in call:
        continue
    method = call.get("method")
    result = {}
    if method == "thread/start":
        result = {"thread": {"id": "parent_thread"}}
    elif method == "thread/fork":
        send({"jsonrpc": "2.0", "id": call["id"],
              "error": {"code": -32000, "message": "the child was made, then the stream broke"}})
        continue
    send({"jsonrpc": "2.0", "id": call["id"], "result": result})
    if method == "thread/start":
        send({"method": "thread/status/changed",
              "params": {"status": {"type": "idle"}}})
    if method == "turn/start":
        tid = call["params"].get("threadId", "parent_thread")
        send({"method": "turn/started",
              "params": {"turnId": "turn_fake", "threadId": tid}})
        send({"method": "item/completed",
              "params": {"item": {"type": "agentMessage", "text": "answered"},
                         "threadId": tid}})
        send({"method": "turn/completed",
              "params": {"threadId": tid,
                         "turn": {"id": "turn_fake", "status": "completed"}}})
        send({"method": "thread/status/changed",
              "params": {"status": {"type": "idle"}, "threadId": tid}})
"""


def test_a_claude_fork_whose_response_is_lost_is_reconciled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The child id is chosen up front, so a response lost with the process reconciles to it."""
    _install("claude", _CLAUDE_LOST, tmp_path, monkeypatch)
    agent = ClaudeCodeAgent(ClaudeCodeAgentConfig(model="m", effort="low"))
    parent = agent.new()
    assert parent("hi") == "hi"

    child = parent.fork()  # does not raise, though the fork never named itself

    assert child.id != parent.id  # the id chosen up front, adopted regardless


def test_a_codex_fork_whose_response_is_lost_is_recorded_as_an_orphan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The fork is asked once and never retried; the orphan is written down to reconcile."""
    from hmz.cycle import Cycle

    monkeypatch.chdir(tmp_path)
    _install("codex", _CODEX_FORK_LOST, tmp_path, monkeypatch)
    agent = CodexAgent(CodexAgentConfig(model="gpt-5-codex", effort="high"))
    cycle = Cycle("forking", [agent], "task", tmp_path)
    agent.cycle = cycle
    parent = agent.new()
    assert parent("first") == "answered"

    with pytest.raises(subprocess.CalledProcessError):
        parent.fork()

    # Asked once, so a blind retry could not have made a second branch.
    asked = [
        call
        for call in _install_call_log(tmp_path, "codex")
        if call.get("method") == "thread/fork"
    ]
    assert len(asked) == 1
    lost = [event for event in _events(cycle) if event.get("event") == "fork-lost"]
    assert len(lost) == 1
    assert lost[0]["parent_session_id"] == parent.id


def _install_call_log(tmp_path: Path, name: str) -> list[dict[str, Any]]:
    """Every call the stand-in `name` was made of."""
    return [
        json.loads(line)
        for line in (tmp_path / "bin" / f"{name}.log").read_text().splitlines()
    ]
