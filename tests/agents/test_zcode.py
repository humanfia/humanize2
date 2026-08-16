"""ZCode, driven against a stand-in app server that speaks the protocol the real one speaks.

Every turn of this backend is a session on `zcode app-server --stdio`, because its command line
takes neither a model nor a thought level. So what is checked here is the calls a turn is made
of -- what opened the session, what was said again on the way into the next one, what came back
out of the stream -- against a server on PATH that answers the way ZCode answers.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import pytest

from hmz.agents import Failed, Moment, Occasion, Verdict, ZcodeAgent, ZcodeAgentConfig

#: A `zcode app-server --stdio` of our own. It speaks ZCode's protocol rather than JSON-RPC --
#: the frames carry no `jsonrpc`, and the real one refuses any that does -- and it asks its
#: client the two things the real one asks: what the runtime may do before it will open a
#: session at all, and, at a rung that asks, whether a high-risk tool is allowed.
#:
#: A prompt of `boom` is a turn that failed, `asking` a turn that stopped on a question and
#: `approving` one that asked to be allowed to do something. Everything else is answered the
#: way a working turn answers: it thinks, it reaches for something, it says what that request
#: cost, and only then does it end.
_ZCODE = """
import json, pathlib, sys

LOG = pathlib.Path(sys.argv[0] + ".log")
PENDING = []
SESSION = "sess_fake"


def send(message):
    sys.stdout.write(json.dumps(message) + "\\n")
    sys.stdout.flush()


def event(kind, payload):
    send({"method": "session/event", "params": {
        "sessionId": SESSION, "type": kind, "payload": payload}})


def turn(prompt):
    event("turn.started", {"input": prompt, "turnNumber": 0})
    if prompt == "boom":
        event("turn.failed", {"error": {"message": "the model refused it"}})
        return
    if prompt == "asking":
        send({"id": "server-9", "method": "interaction/requestUserInput", "params": {
            "sessionId": SESSION, "toolName": "AskUserQuestion", "toolCallId": "tu_a",
            "questions": [{"header": "Way", "question": "Which way?",
                           "options": [{"label": "left"}, {"label": "right"}]}]}})
        return
    if prompt == "approving":
        send({"id": "server-8", "method": "interaction/requestPermission", "params": {
            "sessionId": SESSION, "toolName": "Bash", "riskLevel": "high",
            "reason": "High risk tools require explicit approval", "toolCallId": "tu_b",
            "input": {"command": "rm -rf /"}}})
        return
    marked = "msg_1"
    event("model.streaming", {"assistantMessageId": marked, "kind": "reasoning_delta",
                              "delta": "thinking it over"})
    event("model.streaming", {"assistantMessageId": marked, "kind": "text_delta",
                              "delta": "Looking now."})
    event("model.streaming", {"assistantMessageId": marked, "kind": "tool_call",
                              "toolCallId": "tu_1", "toolName": "Bash",
                              "input": {"command": "ls", "description": "List the files"}})
    event("session.updated", {"content": "Looking now.", "stopReason": "tool-calls",
                              "usage": {"inputTokens": 7, "outputTokens": 3,
                                        "totalTokens": 10}})
    event("model.streaming", {"assistantMessageId": "msg_2", "kind": "text_delta",
                              "delta": prompt})
    event("session.updated", {"content": prompt, "stopReason": "stop",
                              "usage": {"inputTokens": 5, "outputTokens": 2,
                                        "totalTokens": 7}})
    event("turn.completed", {"response": prompt, "toolCallCount": 1,
                             "usage": {"inputTokens": 12, "outputTokens": 5,
                                       "totalTokens": 17, "modelRequestCount": 2}})


def opened():
    return {"session": {"sessionId": SESSION, "mode": "build",
                        "model": {"providerId": "zai", "modelId": "glm"}},
            "projection": {"turnCount": 0}, "messages": [],
            "protocol": {"name": "ZCode Protocol", "version": 1}}


for line in sys.stdin:
    call = json.loads(line)
    with LOG.open("a") as stream:
        json.dump(call, stream)
        stream.write("\\n")
    if "method" not in call:
        # An answer to something the server asked of us. A session is only opened once the
        # client has said what the runtime may do, and a turn that stopped on an approval or
        # a question goes on with whatever the answer was.
        if PENDING:
            send({"id": PENDING.pop()["id"], "result": opened()})
            continue
        said = json.dumps(call.get("result") or {})
        event("session.updated", {"content": said, "stopReason": "stop",
                                  "usage": {"inputTokens": 1, "outputTokens": 1,
                                            "totalTokens": 2}})
        event("turn.completed", {"response": said, "toolCallCount": 0,
                                 "usage": {"inputTokens": 1, "outputTokens": 1,
                                           "totalTokens": 2, "modelRequestCount": 1}})
        continue
    if "id" not in call:
        continue
    if call["method"] == "session/create":
        # The real one will not open a session until the client has answered this, and gives
        # up on it after fifteen seconds.
        PENDING.append(call)
        send({"id": "server-1", "method": "session/requestRuntimePreferences",
              "params": {"sessionId": SESSION, "scope": "runtime-materialization"}})
        continue
    if call["method"] == "session/resume":
        send({"id": call["id"], "result": opened()})
        continue
    if call["method"] == "session/goal":
        send({"id": call["id"], "result": {"response": "Goal complete",
                                           "startedTurn": True, "snapshot": {}}})
        turn("under a goal: " + call["params"].get("objective", ""))
        continue
    if call["method"] == "session/send":
        send({"id": call["id"], "result": {"sessionId": SESSION, "accepted": True,
                                           "stateRevision": 1}})
        turn(call["params"]["content"])
        continue
    send({"id": call["id"], "result": {}})
"""


@dataclass(frozen=True)
class _FakeServer:
    """What the stand-in wrote down: every frame its client sent it, in order."""

    log: Path

    def calls(self) -> list[dict[str, Any]]:
        """Every frame, as read."""
        if not self.log.exists():
            return []
        return [json.loads(line) for line in self.log.read_text().splitlines()]

    def named(self, method: str) -> list[dict[str, Any]]:
        """The params of every call of one method, in the order they were made."""
        return [
            one.get("params") or {}
            for one in self.calls()
            if one.get("method") == method
        ]


@pytest.fixture
def server(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> _FakeServer:
    """Puts a stand-in `zcode` on PATH, and says where it writes what it was sent."""
    binaries = tmp_path / "bin"
    binaries.mkdir(exist_ok=True)
    fake = binaries / "zcode"
    fake.write_text(f"#!{sys.executable}\n{_ZCODE}")
    fake.chmod(0o755)
    monkeypatch.setenv("PATH", f"{binaries}{os.pathsep}{os.environ['PATH']}")
    return _FakeServer(Path(f"{fake}.log"))


def _agent(**settings: Any) -> ZcodeAgent:
    """An agent of this backend, at whatever this test is about."""
    return ZcodeAgent(ZcodeAgentConfig(model="zai/glm-5.3", effort="high", **settings))


def test_a_turn_opens_a_session_naming_what_it_is_to_run(
    server: _FakeServer, tmp_path: Path
) -> None:
    """The model, the thought level and the rung are what the command line cannot be told."""
    agent = _agent()
    session = agent.new(tmp_path)

    assert session("hello") == "hello"

    (opened,) = server.named("session/create")
    assert opened["model"] == {"providerId": "zai", "modelId": "glm-5.3"}
    assert opened["thoughtLevel"] == "high"
    assert opened["mode"] == "yolo"
    assert opened["workspace"]["workspacePath"] == str(tmp_path)
    # A title is a turn of its own on the lite model, and nothing here reads one.
    assert opened["titleGenerationEnabled"] is False
    agent.stop()


def test_the_frames_it_sends_are_the_protocols_own_rather_than_json_rpc(
    server: _FakeServer, tmp_path: Path
) -> None:
    """The real server refuses a frame carrying `jsonrpc`, so none of ours may."""
    agent = _agent()
    agent.new(tmp_path)("hello")

    sent = server.calls()

    assert sent
    assert not any("jsonrpc" in one for one in sent)
    agent.stop()


def test_a_turn_says_what_the_agent_said_in_the_order_it_said_it(
    server: _FakeServer, tmp_path: Path
) -> None:
    """The words that led up to a tool call are said before it, which is why it was made."""
    agent = _agent()
    said = list(agent.new(tmp_path).stream("hello"))

    assert [one.kind for one in said] == [
        "reasoning",
        "text",
        "tool",
        "text",
        "result",
    ]
    assert said[0].text == "thinking it over"
    assert said[2].text == "Bash List the files"
    assert said[-1].text == "hello"
    agent.stop()


def test_what_a_turn_cost_is_counted_as_each_request_of_it_lands(
    server: _FakeServer, tmp_path: Path
) -> None:
    """A turn is minutes long, and a rate that only moved at the end would stand still."""
    agent = _agent()
    session = agent.new(tmp_path)
    said = list(session.stream("hello"))

    assert dict(said[-1].tokens) == {"zai/glm-5.3": 17}
    assert dict(said[-1].spent) == {"input": 12.0, "output": 5.0}
    assert dict(session.spent()) == {"input": 12.0, "output": 5.0}
    assert dict(agent.spent()) == {"input": 12.0, "output": 5.0}
    agent.stop()


def test_the_session_it_opened_is_the_one_the_next_turn_carries_on(
    server: _FakeServer, tmp_path: Path
) -> None:
    """A conversation is one conversation, and the settings it opened with are not said twice."""
    agent = _agent()
    session = agent.new(tmp_path)
    session("first")
    session("second")

    assert session.id == "sess_fake"
    assert session.id in agent.opened
    assert len(server.named("session/create")) == 1
    assert [one["content"] for one in server.named("session/send")] == [
        "first",
        "second",
    ]
    # Nothing moved between the two, so nothing was said again.
    assert server.named("session/setModel") == []
    assert server.named("session/setThoughtLevel") == []
    assert server.named("session/setMode") == []
    agent.stop()


def test_an_effort_changed_between_turns_is_said_again(
    server: _FakeServer, tmp_path: Path
) -> None:
    """It is a setting of the session rather than of the turn, so it is set on the session."""
    agent = _agent()
    session = agent.new(tmp_path)
    session("first")
    session.effort = "low"
    session("second")

    (told,) = server.named("session/setThoughtLevel")

    assert told["thoughtLevel"] == "low"
    # One flow's choice is not the default of whatever the person at this machine opens next.
    assert told["persistAsWorkspaceLastUsed"] is False
    agent.stop()


@pytest.mark.parametrize(
    ("rung", "mode"),
    [
        ("read-only", "plan"),
        ("workspace-write", "edit"),
        ("auto", "build"),
        ("bypass", "yolo"),
    ],
)
def test_every_rung_is_a_mode_zcode_is_run_in(
    server: _FakeServer, tmp_path: Path, rung: str, mode: str
) -> None:
    """Four of its five, and never its own `auto`.

    In that mode its permission service refuses every tool, saying the mode is reserved and
    not implemented yet.
    """
    agent = _agent(permission=rung)
    agent.new(tmp_path)("hello")

    (opened,) = server.named("session/create")

    assert opened["mode"] == mode
    agent.stop()


def test_an_agent_that_may_not_search_the_web_is_denied_the_tools_that_reach_it(
    server: _FakeServer, tmp_path: Path
) -> None:
    """At the session rather than in anybody's settings file: two agents may be told two things."""
    agent = _agent()
    agent.new(tmp_path)("hello")

    (searching,) = server.named("session/create")

    assert "toolDenylist" not in searching
    agent.stop()

    agent = ZcodeAgent(replace(agent.config, web_search=False))
    agent.new(tmp_path)("hello")

    denied = server.named("session/create")[-1]

    assert denied["toolDenylist"] == ["WebFetch", "WebSearch"]
    agent.stop()


def test_a_failed_turn_says_what_zcode_said_about_it(
    server: _FakeServer, tmp_path: Path
) -> None:
    """A turn that failed must say why, and an exit status alone says nothing."""
    agent = _agent()
    session = agent.new(tmp_path)

    with pytest.raises(subprocess.CalledProcessError) as refused:
        session("boom")

    assert isinstance(refused.value, Failed)
    assert "the model refused it" in str(refused.value)
    # A turn that failed never opened the session, so the next one retries rather than
    # carrying on a conversation nobody can find.
    with pytest.raises(RuntimeError, match="has not run a turn yet"):
        _ = session.id
    agent.stop()


def test_a_turn_that_failed_is_nothing_at_all_where_it_is_suppressed(
    server: _FakeServer, tmp_path: Path
) -> None:
    """Which is how a flow that would rather go on than stop asks for one."""
    agent = _agent()

    assert agent.new(tmp_path)("boom", suppress=True) == ""
    agent.stop()


def test_a_rung_below_the_one_that_grants_it_refuses_what_it_is_asked(
    server: _FakeServer, tmp_path: Path
) -> None:
    """ZCode asks at `edit` too, and an agent allowed its workspace is not allowed more."""
    agent = _agent(permission="workspace-write")

    assert agent.new(tmp_path)("approving") == json.dumps(
        {"decision": "deny", "reason": "the agent is allowed no more than edit mode"}
    )
    agent.stop()


def test_a_high_risk_tool_is_allowed_and_a_hook_may_say_no(
    server: _FakeServer, tmp_path: Path
) -> None:
    """The moment the backend waits on is the one place a refusal stops it doing something."""
    agent = _agent(permission="auto")
    assert agent.new(tmp_path)("approving") == json.dumps(
        {"decision": "allow", "reason": "run unattended"}
    )
    agent.stop()

    refusing = _agent(permission="auto")
    seen: list[Occasion] = []

    def refuse(occasion: Occasion) -> Verdict:
        seen.append(occasion)
        return Verdict(refused=True, because="not that one")

    refusing.hooks.on(Moment.PERMISSION_REQUEST, refuse)

    assert refusing.new(tmp_path)("approving") == json.dumps(
        {"decision": "deny", "reason": "not that one"}
    )
    assert [one.tool for one in seen] == ["Bash"]
    refusing.stop()


def test_a_question_nobody_is_there_to_answer_lets_the_turn_go_on(
    server: _FakeServer, tmp_path: Path
) -> None:
    """A turn waiting for a reply that is not coming is a flow that has stopped."""
    agent = _agent()

    assert agent.new(tmp_path)("asking") == json.dumps(
        {"decision": "deny", "reason": "nobody is here to answer"}
    )
    agent.stop()


def test_a_question_somebody_answers_carries_their_words_back(
    server: _FakeServer, tmp_path: Path
) -> None:
    """ZCode takes an answer over a channel its own terminal holds, so this is the reason."""
    agent = _agent()
    asked: list[str] = []

    def answer(question: Any) -> str:
        asked.append(question.text)
        return "left"

    agent.ask = answer

    assert agent.new(tmp_path)("asking") == json.dumps(
        {"decision": "deny", "reason": "Which way? left"}
    )
    assert asked == ["Which way?"]
    agent.stop()


def test_a_goal_is_zcodes_own_and_the_turn_it_starts_runs_to_the_end(
    server: _FakeServer, tmp_path: Path
) -> None:
    """`pursue` is the agent keeping itself going, which ZCode has a feature for."""
    agent = _agent()
    session = agent.new(tmp_path)

    assert session.pursue("make it green") == "under a goal: make it green"

    (told,) = server.named("session/goal")

    assert told["action"] == "set"
    assert told["objective"] == "make it green"
    assert session.id == "sess_fake"
    agent.stop()


def test_nothing_can_be_said_to_a_turn_that_is_already_running(
    server: _FakeServer, tmp_path: Path
) -> None:
    """Nowhere to put a word, because the server refuses one.

    A second prompt while one is running is refused, and what its own terminal steers with is
    a channel that terminal holds.
    """
    agent = _agent()

    with pytest.raises(NotImplementedError):
        agent.new(tmp_path).interject("also mind the gap")
    agent.stop()


def test_the_protocol_does_not_reach_the_terminal(
    server: _FakeServer, tmp_path: Path, capfd: pytest.CaptureFixture[str]
) -> None:
    """What a person watching sees is the turn, not the frames it was carried in."""
    agent = _agent()
    agent.new(tmp_path)("hello")
    streams = capfd.readouterr()

    assert "session/event" not in streams.out
    assert "sessionId" not in streams.out
    assert streams.out.strip().endswith("hello")
    agent.stop()


def test_a_turn_runs_in_the_flows_own_environment(
    server: _FakeServer, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An agent with no provider is left exactly as it was found."""
    monkeypatch.setenv("A_THING_THE_FLOW_HAS", "kept")
    agent = _agent()

    assert agent.new(tmp_path)("hello") == "hello"
    assert os.environ["A_THING_THE_FLOW_HAS"] == "kept"
    agent.stop()


def test_two_sessions_of_one_agent_share_the_server_it_started(
    server: _FakeServer, tmp_path: Path
) -> None:
    """One per agent rather than one per session, so dropping a session drops no server."""
    agent = _agent()
    first, second = agent.new(tmp_path), agent.new(tmp_path)
    first("one")
    second("two")

    assert agent.server is agent.server
    assert len(server.named("session/create")) == 2
    agent.stop()
