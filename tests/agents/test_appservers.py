"""Tests for the backends a flow reaches through an app server rather than a command line.

Kimi Code is driven through one for every turn, because its effort, its swarm mode and its goal
are settings of a session rather than flags of a prompt; Codex is driven through one for a goal
alone. Both are exercised against a stand-in server on PATH, so what is checked is the calls a
turn is made of and the answer read back out of them.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
from pydantic import BaseModel

from hmz import backends
from hmz.agents import (
    CodexAgent,
    CodexAgentConfig,
    Event,
    KimiCodeCLIAgent,
    KimiCodeCLIAgentConfig,
)
from hmz.agents import codex as appservers

if TYPE_CHECKING:
    from collections.abc import Mapping


class _Verdict(BaseModel):
    """What a turn asked for a shape is to answer with."""

    model_config = {"extra": "forbid"}

    done: bool
    notes: str


#: A `kimi web` that says where it is listening and then serves the calls a turn is made of,
#: recording each one. A prompt of `boom` is refused, which is how a failed turn is spelled.
_KIMI = """
import json, pathlib, sys
from http.server import BaseHTTPRequestHandler, HTTPServer

LOG = pathlib.Path(sys.argv[0] + ".log")


def note(entry):
    with LOG.open("a") as stream:
        json.dump(entry, stream)
        stream.write("\\n")


note({"path": "argv", "body": sys.argv[1:], "token": None})
GOAL = []
POLLS = []
QUEUED = []
STEERED = []
# One question, put up while the turn runs and taken down once it has been answered.
ASKED = [{"question_id": "q_0", "questions": [{
    "id": "which", "header": "Which", "question": "Which way?",
    "options": [{"id": "o_l", "label": "left"}, {"id": "o_r", "label": "right"}]}]}]


class Handler(BaseHTTPRequestHandler):
    def reply(self, data, status=200):
        body = json.dumps({"code": 0, "msg": "ok", "data": data}).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        sent = json.loads(self.rfile.read(int(self.headers["Content-Length"])) or b"null")
        note({"path": self.path, "body": sent, "token": self.headers.get("Authorization")})
        if "/questions/" in self.path:
            # Answered, so the turn is no longer waiting on it and it goes down.
            ASKED.clear()
            self.reply({"resolved": True})
        elif self.path.endswith("/prompts:steer"):
            # What was queued is moved into the turn already running, which is the whole
            # difference between putting a word in and queueing a turn behind this one.
            STEERED.extend(sent["prompt_ids"])
            self.reply({"steered": True, "prompt_ids": sent["prompt_ids"]})
        elif self.path.endswith("/prompts"):
            if sent["content"][0]["text"] == "boom":
                self.reply(None, status=400)
            else:
                QUEUED.append(sent["content"][0]["text"])
                # Running while nothing else is, queued while a turn already has the session.
                self.reply({"prompt_id": "p_%d" % len(QUEUED),
                            "user_message_id": "msg_0",
                            "status": "running" if len(QUEUED) == 1 else "queued"})
        elif self.path.endswith("/profile"):
            self.reply({})
        else:
            self.reply({"id": "session_fake"})

    def do_GET(self):
        note({"path": self.path, "body": None, "token": self.headers.get("Authorization")})
        if "/status" in self.path:
            POLLS.append(None)
            if QUEUED and QUEUED[0] == "patient":
                # Working until it is told something else, which is what makes a word put in
                # mid-turn observable: the turn cannot end before it lands.
                self.reply({"busy": not STEERED})
            else:
                self.reply({"busy": len(POLLS) == 1})
        elif self.path.endswith("/questions"):
            # What the turn has stopped to ask, which is nothing unless a test says so.
            self.reply({"items": ASKED[:1]})
        elif self.path.endswith("/goal"):
            # Still being pursued the first time it is asked, as a goal is between its turns.
            GOAL.append(None)
            self.reply({"status": "active"} if len(GOAL) == 1 else None)
        elif self.path.endswith("/sessions/session_fake"):
            # The session itself, which is where the daemon keeps what it has cost so far.
            self.reply({"id": "session_fake", "usage": {
                "input_tokens": 300, "output_tokens": 100, "cache_read_tokens": 600,
                "cache_creation_tokens": 0, "turn_count": 1}})
        elif len(POLLS) < 2:
            # Readable while it is still being written: what it will say is not there yet.
            self.reply({"items": [{"id": "msg_1", "role": "assistant", "content": [
                {"type": "thinking", "thinking": "..."},
            ]}]})
        else:
            answer = " answered "
            if STEERED:
                answer = " steered:" + QUEUED[-1] + " "
            self.reply({"items": [{"id": "msg_1", "role": "assistant", "content": [
                {"type": "thinking", "thinking": "..."},
                {"type": "tool_use", "tool_name": "Write"},
                {"type": "text", "text": answer},
            ]}]})

    def log_message(self, *ignored):
        pass


server = HTTPServer(("127.0.0.1", 0), Handler)
print(f"Kimi server: http://127.0.0.1:{server.server_port}/#token=secret", flush=True)
server.serve_forever()
"""

#: A `codex app-server` that answers every call and, once a turn is started, plays the
#: notifications a goal-driven one really runs through. The thread falls idle the moment it is
#: opened, as a real one does, which a turn that has not begun must not read as its own -- and
#: again between the goal's two turns, which is where Codex continues a goal rather than ends it.
_CODEX = """
import json, pathlib, sys

LOG = pathlib.Path(sys.argv[0] + ".log")
RESULTS = {"thread/start": {"thread": {"id": "thread_fake"}}}
STUCK = []


def send(message):
    sys.stdout.write(json.dumps(message) + "\\n")
    sys.stdout.flush()


for line in sys.stdin:
    call = json.loads(line)
    with LOG.open("a") as stream:
        json.dump(call, stream)
        stream.write("\\n")
    if "method" not in call:
        # An answer to something the server asked of us. The turn was waiting on it, and what
        # it answers with is what the turn goes on to say -- the answers to a question, or the
        # decision on something it asked to be allowed to do.
        result = call.get("result") or {}
        said = json.dumps(result["answers"] if "answers" in result else result)
        send({"method": "item/completed", "params": {"item": {
            "type": "agentMessage", "text": said}}})
        send({"method": "turn/completed", "params": {}})
        send({"method": "thread/status/changed", "params": {"status": {"type": "idle"}}})
        continue
    if "id" not in call:
        continue
    send({"jsonrpc": "2.0", "id": call["id"], "result": RESULTS.get(call["method"], {})})
    if call["method"] == "thread/goal/set":
        STUCK.append(call["params"]["objective"] == "stuck")
    if call["method"] == "thread/start":
        send({"method": "thread/status/changed", "params": {"status": {"type": "idle"}}})
    if call["method"] == "turn/steer":
        # The turn was left open for this: what was put in is answered inside the same turn,
        # and only then does the thread fall idle.
        send({"method": "item/completed",
              "params": {"item": {"type": "agentMessage",
                                  "text": " steered:" + call["params"]["input"][0]["text"]}}})
        send({"method": "turn/completed", "params": {}})
        send({"method": "thread/status/changed", "params": {"status": {"type": "idle"}}})
    if call["method"] == "turn/start":
        send({"method": "turn/started", "params": {"turnId": "turn_fake"}})
        if call["params"]["input"][0]["text"] == "recovering":
            send({"method": "error", "params": {"error": {
                "message": "Reconnecting... 1/5",
                "codexErrorInfo": {"responseStreamDisconnected": {
                    "httpStatusCode": None}},
            }}})
        if call["params"]["input"][0]["text"] == "asking":
            # A turn stopping to ask its user something, which the server puts to the client
            # as a request of its own and waits on.
            send({"id": "ask_1", "method": "item/tool/requestUserInput", "params": {
                "itemId": "item_0", "threadId": "thread_fake", "turnId": "turn_fake",
                "questions": [{"id": "which", "header": "Way", "question": "Which way?",
                               "options": [{"label": "left"}, {"label": "right"}]}]}})
        if call["params"]["input"][0]["text"] == "approving":
            # A turn asking to be allowed to run something, which the server puts to the
            # client as a request of its own and waits on.
            send({"id": "ok_1", "method": "item/commandExecution/requestApproval",
                  "params": {"itemId": "item_0", "threadId": "thread_fake",
                             "turnId": "turn_fake", "startedAtMs": 0,
                             "command": "rm -rf /"}})
        if call["params"]["input"][0]["text"] == "widening":
            # And one asking for the sandbox itself to be widened, whose answer is the
            # permissions rather than a decision about them.
            send({"id": "ok_2", "method": "item/permissions/requestApproval",
                  "params": {"itemId": "item_0", "threadId": "thread_fake",
                             "turnId": "turn_fake", "startedAtMs": 0, "cwd": "/w",
                             "permissions": {"network": {"enabled": True}}}})
        if call["params"]["input"][0]["text"] == "doomed":
            send({"method": "turn/completed",
                  "params": {"turn": {"id": "turn_fake", "status": "failed",
                                      "error": {"type": "usageLimitExceeded"}}}})
            continue
        send({"method": "item/agentMessage/delta", "params": {"delta": "workspace-write"}})
        send({"method": "item/completed",
              "params": {"item": {"type": "agentMessage", "text": " halfway "}}})
        if not STUCK:
            # An ordinary turn: left running, the way a real one is while the model works,
            # so that a word put in has a turn to land in.
            continue
        # Two turns of the model under one goal, which is what the objective took: Codex
        # starts the second itself, off the idle the first one left behind.
        send({"method": "turn/completed", "params": {}})
        send({"method": "thread/status/changed", "params": {"status": {"type": "idle"}}})
        send({"method": "turn/started", "params": {"turnId": "turn_fake"}})
        send({"method": "item/completed",
              "params": {"item": {"type": "agentMessage", "text": " answered "}}})
        send({"method": "turn/completed", "params": {}})
        if not STUCK[0]:
            send({"method": "thread/goal/updated",
                  "params": {"goal": {"status": "complete"}}})
        send({"method": "thread/status/changed", "params": {"status": {"type": "idle"}}})
"""


#: A `codex app-server` that runs a turn the way a working one goes: it reaches for things, it
#: thinks, it says what it spent, and only at the end does it answer. Every message is shaped as
#: `codex app-server generate-json-schema` says the real one shapes it -- the items carry what
#: that schema says they carry, and the spending is the thread's running total under
#: `tokenUsage.total`. The item nobody has heard of is there on purpose: the server grows kinds,
#: and a turn must not go quiet over one.
_CODEX_WORKING = """
import json, pathlib, sys

LOG = pathlib.Path(sys.argv[0] + ".log")
# What the thread has cost all told, which is what the server states: the rise across a turn
# is what that turn spent, and the input carries all of it but the hundred that came out.
TOTAL = [1000]


def send(message):
    sys.stdout.write(json.dumps(message) + "\\n")
    sys.stdout.flush()


for line in sys.stdin:
    with LOG.open("a") as stream:
        json.dump(json.loads(line), stream)
        stream.write("\\n")
    call = json.loads(line)
    if "id" not in call:
        continue
    send({"jsonrpc": "2.0", "id": call["id"],
          "result": {"thread": {"id": "thread_fake"}}
          if call["method"] == "thread/start" else {}})
    if call["method"] == "thread/start":
        send({"method": "thread/status/changed", "params": {"status": {"type": "idle"}}})
    if call["method"] == "turn/start":
        send({"method": "turn/started", "params": {"turnId": "turn_fake"}})
        if call["params"]["input"][0]["text"] == "asking":
            # A turn stopping to ask its user something, which the server puts to the client
            # as a request of its own and waits on.
            send({"id": "ask_1", "method": "item/tool/requestUserInput", "params": {
                "itemId": "item_0", "threadId": "thread_fake", "turnId": "turn_fake",
                "questions": [{"id": "which", "header": "Way", "question": "Which way?",
                               "options": [{"label": "left"}, {"label": "right"}]}]}})
        send({"method": "item/started", "params": {
            "threadId": "thread_fake", "turnId": "turn_fake", "startedAtMs": 0, "item": {
                "id": "item_0", "type": "userMessage", "content": "do the task"}}})
        send({"method": "item/started", "params": {
            "threadId": "thread_fake", "turnId": "turn_fake", "startedAtMs": 0, "item": {
                "id": "item_1", "type": "commandExecution", "status": "inProgress",
                "cwd": "/somewhere/else", "aggregatedOutput": "3 passed",
                "command": "pytest -q"}}})
        send({"method": "item/started", "params": {
            "threadId": "thread_fake", "turnId": "turn_fake", "startedAtMs": 0, "item": {
                "id": "item_2", "type": "flightOfFancy", "note": "something new"}}})
        send({"method": "item/completed", "params": {
            "threadId": "thread_fake", "turnId": "turn_fake", "completedAtMs": 1, "item": {
                "id": "item_1", "type": "commandExecution", "status": "completed",
                "exitCode": 0, "command": "pytest -q"}}})
        send({"method": "item/completed", "params": {
            "threadId": "thread_fake", "turnId": "turn_fake", "completedAtMs": 1, "item": {
                "id": "item_3", "type": "fileChange", "status": "completed", "changes": [
                    {"path": "src/x.py", "kind": "update", "diff": "@@ -1 +1 @@"}]}}})
        send({"method": "item/completed", "params": {
            "threadId": "thread_fake", "turnId": "turn_fake", "completedAtMs": 1, "item": {
                "type": "webSearch", "status": "completed", "query": "what a nameless one is"}}})
        send({"method": "item/completed", "params": {
            "threadId": "thread_fake", "turnId": "turn_fake", "completedAtMs": 1, "item": {
                "type": "webSearch", "status": "completed", "query": "and the one after it"}}})
        send({"method": "item/completed", "params": {
            "threadId": "thread_fake", "turnId": "turn_fake", "completedAtMs": 1, "item": {
                "id": "item_4", "type": "reasoning", "summary": [],
                "content": ["weighing it up"]}}})
        send({"method": "thread/tokenUsage/updated", "params": {
            "threadId": "thread_fake", "turnId": "turn_fake", "tokenUsage": {
                "modelContextWindow": 258400,
                "last": {"inputTokens": 900, "cachedInputTokens": 800, "outputTokens": 100,
                         "reasoningOutputTokens": 0, "totalTokens": 1000},
                "total": {"inputTokens": TOTAL[0] - 100, "cachedInputTokens": 800,
                          "outputTokens": 100, "reasoningOutputTokens": 0,
                          "totalTokens": TOTAL[0]}}}})
        send({"method": "item/completed", "params": {
            "threadId": "thread_fake", "turnId": "turn_fake", "completedAtMs": 1, "item": {
                "id": "item_5", "type": "agentMessage", "text": "done"}}})
        TOTAL[0] = 1500
        send({"method": "turn/completed", "params": {
            "threadId": "thread_fake", "turn": {"id": "turn_fake", "status": "completed",
                                                "items": []}}})
        send({"method": "thread/status/changed", "params": {"status": {"type": "idle"}}})
"""


@dataclass(frozen=True)
class _FakeServer:
    """A stand-in backend on PATH, and everything it was asked for."""

    log: Path

    def calls(self) -> list[dict[str, Any]]:
        return [json.loads(line) for line in self.log.read_text().splitlines()]


def _install(
    name: str, script: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> _FakeServer:
    """Puts one stand-in backend on PATH.

    Args:
      name: The command to answer to.
      script: What it does when run.
      tmp_path: Where to put it.
      monkeypatch: What to change PATH with.

    Returns:
      The server, and the log it will write.
    """
    binaries = tmp_path / "bin"
    binaries.mkdir(exist_ok=True)
    fake = binaries / name
    fake.write_text(f"#!{sys.executable}\n{script}")
    fake.chmod(0o755)
    monkeypatch.setenv("PATH", f"{binaries}{os.pathsep}{os.environ['PATH']}")
    return _FakeServer(Path(f"{fake}.log"))


def _agent(effort: str = "high") -> KimiCodeCLIAgent:
    """A Kimi Code agent at the one model the stand-in daemon answers for."""
    return KimiCodeCLIAgent(KimiCodeCLIAgentConfig(model="kimi-code/k3", effort=effort))


def _named(argv: list[str]) -> list[str]:
    """One command, with the program written as the name its CLI is installed under.

    Args:
      argv: The command as it would be spawned, whose program is the path this machine has
        that CLI at.

    Returns:
      The same command, said the way it is written down, so that what a test reads is the
      arguments a turn is made of rather than where this machine keeps its coding agents.
    """
    return [Path(argv[0]).name, *argv[1:]]


def _bodies(server: _FakeServer, path: str) -> list[dict[str, Any]]:
    """What was sent to each call on one of the daemon's paths, oldest first.

    Args:
      server: The stand-in daemon that recorded them.
      path: The tail of the path to keep.

    Returns:
      One body per matching call, so that a test unpacking them fails on a path that stopped
      being called rather than passing over an empty list.
    """
    return [call["body"] for call in server.calls() if call["path"].endswith(path)]


@pytest.fixture
def kimi(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> _FakeServer:
    return _install("kimi", _KIMI, tmp_path, monkeypatch)


@pytest.fixture
def codex(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> _FakeServer:
    return _install("codex", _CODEX, tmp_path, monkeypatch)


@pytest.fixture
def working(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> _FakeServer:
    return _install("codex", _CODEX_WORKING, tmp_path, monkeypatch)


def test_kimi_opens_then_resumes(kimi: _FakeServer) -> None:
    session = _agent().new()
    assert session("hi") == "answered"
    session("again")

    started, *calls = kimi.calls()
    # A port of its own, so that two flows on one machine cannot collide over the default one.
    assert started["body"] == [
        "web",
        "--no-open",
        "--port",
        "0",
        "--log-level",
        "error",
    ]
    opened = [call for call in calls if call["path"] == "/api/v1/sessions"]
    prompts = [call for call in calls if call["path"].endswith("/prompts")]
    assert len(opened) == 1  # one session, resumed rather than reopened
    assert opened[0]["body"] == {"metadata": {"cwd": str(Path.cwd())}}
    assert [prompt["body"]["content"][0]["text"] for prompt in prompts] == [
        "hi",
        "again",
    ]
    assert all(
        prompt["path"] == f"/api/v1/sessions/{session.id}/prompts" for prompt in prompts
    )
    assert all(call["token"] == "Bearer secret" for call in calls)


def test_a_kimi_turn_says_what_it_is_doing_and_what_it_came_to(
    kimi: _FakeServer,
) -> None:
    """A turn is read back as it is written, rather than kept until it has an answer.

    And what it cost is asked of the session it ran in, which is the only place the daemon
    says: a flow that cannot see what it is spending is a flow nobody can stop in time.
    """
    session = _agent().new()

    shown = [(event.kind, event.text) for event in session.stream("hi")]

    assert ("reasoning", "...") in shown  # thought
    assert ("tool", "Write") in shown  # reached for something
    assert ("text", " answered ") in shown  # and said so, before the turn was over
    assert shown[-1] == ("result", "answered")


def test_what_a_kimi_turn_spent_is_charged_to_the_turn_that_spent_it(
    kimi: _FakeServer,
) -> None:
    """The daemon counts the session, which is every turn of it, so take the rise."""
    session = _agent().new()

    spent = [event.tokens for event in session.stream("hi") if event.kind == "result"]

    assert spent == [{"kimi-code/k3": 1000}]  # every kind of token, in and out alike


@pytest.mark.parametrize(
    ("effort", "thinking", "swarm"), [("max", "max", False), ("swarmmax", "max", True)]
)
def test_kimi_effort_says_how_hard_to_think_and_how_wide(
    kimi: _FakeServer, effort: str, thinking: str, swarm: bool
) -> None:
    """Swarm is a mode of the session, so the effort an agent runs at is where it can be said."""
    _agent(effort).new()("hi")

    (profile,), (prompt,) = _bodies(kimi, "/profile"), _bodies(kimi, "/prompts")
    assert profile["agent_config"]["thinking"] == thinking
    assert profile["agent_config"]["swarm_mode"] is swarm
    assert prompt["thinking"] == thinking
    assert prompt["swarm_mode"] is swarm


def test_kimi_pursues_by_setting_a_goal_on_the_session(kimi: _FakeServer) -> None:
    """The goal is the session's, not a `/goal` the model would read as a line of the prompt."""
    _agent("swarmmax").new().pursue("the suite passes")

    (profile,), (prompt,) = _bodies(kimi, "/profile"), _bodies(kimi, "/prompts")
    assert profile["agent_config"]["goal_objective"] == "the suite passes"
    # And the objective is the turn as well: what to do, and what it is for.
    assert prompt["content"] == [{"type": "text", "text": "the suite passes"}]


def test_kimi_reads_a_message_again_until_it_has_been_finished(
    kimi: _FakeServer,
) -> None:
    """The daemon hands back a message that is still being written, so once is not enough."""
    # The stand-in has nothing to say the first time it is read, and the answer the second.
    assert _agent().new()("hi") == "answered"


def test_kimi_pursues_past_a_session_that_has_fallen_still(kimi: _FakeServer) -> None:
    """A goal runs on through the quiet between its turns, so that quiet must not end the turn."""
    _agent().new().pursue("the suite passes")

    # Asked again after it answered that the goal was still being pursued, rather than the
    # session having been taken for finished the first time it fell quiet.
    assert len([call for call in kimi.calls() if call["path"].endswith("/goal")]) >= 2


def test_kimi_runs_without_setting_one(kimi: _FakeServer) -> None:
    KimiCodeCLIAgent(KimiCodeCLIAgentConfig(model="kimi-code/k3", effort="high")).new()(
        "hi"
    )

    profiles = [call for call in kimi.calls() if call["path"].endswith("/profile")]
    assert all(
        "goal_objective" not in call["body"]["agent_config"] for call in profiles
    )


def test_a_kimi_turn_the_server_refuses_leaves_the_session_unopened(
    kimi: _FakeServer,
) -> None:
    agent = _agent()
    session = agent.new()
    with pytest.raises(subprocess.CalledProcessError) as refused:
        session("boom")

    assert refused.value.returncode == 400
    assert (
        agent.opened == []
    )  # so the next call opens a session rather than resuming one
    with pytest.raises(RuntimeError):
        _ = session.id


def test_codex_pursues_by_setting_a_goal_on_the_thread(codex: _FakeServer) -> None:
    """`/goal` is `thread/goal/set`, which is the app server's rather than `codex exec`'s."""
    agent = CodexAgent(CodexAgentConfig(model="gpt-5-codex", effort="high"))
    session = agent.new()
    # The last thing it said, not the first: an idle mid-goal is where Codex carries on.
    assert session.pursue("the suite passes") == "answered"

    called = {call["method"]: call["params"] for call in codex.calls()}
    assert called["thread/start"]["cwd"] == str(Path.cwd())
    assert called["thread/start"]["model"] == "gpt-5-codex"
    assert called["thread/goal/set"] == {
        "threadId": "thread_fake",
        "objective": "the suite passes",
    }
    assert called["turn/start"]["input"] == [
        {"type": "text", "text": "the suite passes"}
    ]
    assert called["turn/start"]["effort"] == "high"
    # The thread is the session, so `codex exec resume` goes on with the one a goal opened.
    assert session.id == "thread_fake"
    assert agent.opened == ["thread_fake"]


def test_codex_gives_up_on_a_goal_that_has_gone_quiet(
    codex: _FakeServer, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A turn that ends saying nothing about the goal must not leave a flow waiting forever."""
    monkeypatch.setattr(appservers, "_QUIET_SECONDS", 0.2)
    session = CodexAgent(CodexAgentConfig(model="gpt-5-codex", effort="high")).new()

    assert session.pursue("stuck") == "answered"  # the turn is lost, the loop is not


def test_codex_resumes_the_thread_a_later_goal_is_set_on(codex: _FakeServer) -> None:
    """A goal is set on a thread the server holds, and one it opened earlier it has let go."""
    session = CodexAgent(CodexAgentConfig(model="gpt-5-codex", effort="high")).new()
    session.pursue("the suite passes")
    session.pursue("and stays passing")

    methods = [call["method"] for call in codex.calls()]
    assert (
        methods.count("thread/start") == 1
    )  # one thread, resumed rather than reopened
    assert methods.count("thread/resume") == 1


def test_codex_runs_where_the_path_it_was_started_with_does_not_name_it(
    codex: _FakeServer, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A flow is not always started from a shell somebody set up.

    A notebook kernel, a service and a runtime platform's launcher each hand their child the
    PATH they were given, and an agent installed on this machine is installed either way: it
    is run by the path it is installed at rather than by a name that PATH has to resolve.
    """
    monkeypatch.setattr(backends, "_INSTALLED_AT", (str(tmp_path / "bin"),))
    monkeypatch.setenv("PATH", str(tmp_path / "nothing"))
    session = CodexAgent(CodexAgentConfig(model="gpt-5-codex", effort="high")).new()

    assert session.pursue("the suite passes") == "answered"
    assert next(call["method"] for call in codex.calls()) == "initialize"


def test_codex_starts_no_app_server_until_a_turn_needs_one(
    codex: _FakeServer,
) -> None:
    CodexAgent(CodexAgentConfig(model="gpt-5-codex", effort="high")).new()

    assert not codex.log.exists()


def test_codex_runs_an_ordinary_turn_on_the_thread(codex: _FakeServer) -> None:
    """Not `codex exec`: the turn goes to the server, which is what leaves it steerable."""
    agent = CodexAgent(CodexAgentConfig(model="gpt-5-codex", effort="high"))
    session = agent.new()

    # The turn stays open the way a real one does, so it is ended by putting a word in.
    def finish() -> None:
        for _ in range(200):
            if session._running.turn is not None:
                session.interject("go on")
                return
            time.sleep(0.02)

    threading.Thread(target=finish, daemon=True).start()
    assert session("do the task") == "steered:go on"

    called = {call["method"]: call["params"] for call in codex.calls()}
    assert called["thread/start"]["cwd"] == str(Path.cwd())
    assert called["turn/start"]["input"] == [{"type": "text", "text": "do the task"}]
    assert called["turn/start"]["effort"] == "high"
    assert "thread/goal/set" not in called  # an ordinary turn sets no goal
    assert session.id == "thread_fake"
    assert agent.opened == ["thread_fake"]


def test_codex_can_be_talked_to_while_a_turn_is_running(codex: _FakeServer) -> None:
    """The point of running the turn on the server: a word put in reaches the turn under way."""
    session = CodexAgent(CodexAgentConfig(model="gpt-5-codex", effort="high")).new()

    said: list[Event] = []
    for event in session.stream("count to sixty"):
        if event.kind == "text" and not said:
            session.interject("actually, stop")
        said.append(event)

    steered = next(call for call in codex.calls() if call["method"] == "turn/steer")
    named = steered["params"].pop("clientUserMessageId")
    assert steered["params"] == {
        "threadId": "thread_fake",
        "input": [{"type": "text", "text": "actually, stop"}],
        # Named, so the server refuses to steer a turn that has already moved on.
        "expectedTurnId": "turn_fake",
    }
    # And named again, this time so that the server can say which word it has taken in: it
    # plays a steered word back as a `userMessage` item carrying this id, and that item is
    # the only thing that says the model has it rather than the server.
    assert named
    assert "steered:actually, stop" in said[-1].text


def test_a_codex_turn_says_what_it_is_doing_while_it_is_doing_it(
    working: _FakeServer,
) -> None:
    """A turn is minutes of work and one answer, and the minutes are what is watched.

    Every item the server reports is shown, including a kind of item this has never heard
    of: the alternative is a turn that reads as a hang until it answers.
    """
    session = CodexAgent(CodexAgentConfig(model="gpt-5-codex", effort="high")).new()

    shown = [(event.kind, event.text) for event in session.stream("do the task")]

    assert ("tool", "Bash pytest -q") in shown  # named as every other backend names it
    assert (
        "tool",
        "flightOfFancy something new",
    ) in shown  # and one nobody has heard of
    assert (
        "tool",
        "Edit src/x.py",
    ) in shown  # and one only ever completed, never started
    assert ("reasoning", "weighing it up") in shown
    assert shown[-1] == ("result", "done")
    # What it ran, rather than the directory or the output the server sends beside it.
    assert not [
        row for row in shown if "somewhere/else" in row[1] or "3 passed" in row[1]
    ]
    assert not [row for row in shown if "do the task" in row[1]]  # nor the prompt, back
    # Started and then completed is one thing done, and reads as one row rather than two.
    assert shown.count(("tool", "Bash pytest -q")) == 1
    # An item naming itself with nothing is not the nameless one before it: two of them are
    # two things done, and the second is not swallowed as one already seen.
    assert ("tool", "WebSearch what a nameless one is") in shown
    assert ("tool", "WebSearch and the one after it") in shown


def test_a_codex_turn_that_reconnects_can_still_complete(
    working: _FakeServer,
) -> None:
    """A transient error is superseded when Codex completes the same turn."""
    session = CodexAgent(CodexAgentConfig(model="gpt-5-codex", effort="high")).new()

    assert session("recovering") == "done"


def test_what_a_codex_turn_spent_is_charged_to_the_turn_that_spent_it(
    working: _FakeServer,
) -> None:
    """The server counts the thread, which is every turn of the session, so take the rise."""
    session = CodexAgent(CodexAgentConfig(model="gpt-5-codex", effort="high")).new()

    first = [event for event in session.stream("do the task") if event.kind == "result"]
    second = [event for event in session.stream("and again") if event.kind == "result"]

    assert first[-1].tokens == {"gpt-5-codex": 1000}
    assert second[-1].tokens == {"gpt-5-codex": 500}  # 1500 all told, 1000 of it before


def test_a_codex_session_with_no_turn_running_cannot_be_talked_to() -> None:
    session = CodexAgent(CodexAgentConfig(model="gpt-5-codex", effort="high")).new()

    with pytest.raises(RuntimeError, match="no turn is running"):
        session.interject("hello?")


@pytest.mark.timeout(5)
def test_a_codex_turn_that_failed_does_not_wait_for_the_thread_to_idle(
    codex: _FakeServer,
) -> None:
    """A completed turn is terminal even when Codex never says its thread is idle.

    A failed turn must say so rather than leave the flow waiting forever for another event.
    """
    agent = CodexAgent(CodexAgentConfig(model="gpt-5-codex", effort="high"))
    session = agent.new()

    with pytest.raises(subprocess.CalledProcessError) as failed:
        session("doomed")

    assert "usageLimitExceeded" in str(failed.value.stderr)
    assert agent.opened == []  # a turn that failed opened nothing
    with pytest.raises(RuntimeError):
        _ = session.id


def test_a_codex_turn_ignores_what_another_thread_is_saying(codex: _FakeServer) -> None:
    """One server holds every session of the agent, and each turn is only its own thread's."""
    session = CodexAgent(CodexAgentConfig(model="gpt-5-codex", effort="high")).new()
    server = session._agent.server

    # A straggler from a thread this turn is not on, of the kind that would otherwise end it.
    server._messages.put(
        {
            "method": "thread/status/changed",
            "params": {"status": {"type": "idle"}, "threadId": "somebody_else"},
        }
    )

    def finish() -> None:
        for _ in range(300):
            if session._running.turn is not None:
                session.interject("go on")
                return
            time.sleep(0.02)

    threading.Thread(target=finish, daemon=True).start()
    assert session("do the task") == "steered:go on"


def test_kimi_steers_a_word_into_the_turn_already_running(kimi: _FakeServer) -> None:
    """A prompt sent to a working session is queued; steering moves it into this turn.

    Without the steer it would be answered as a turn of its own once this one ended, which is
    a turn queued behind rather than a word put in.
    """
    session = KimiCodeCLIAgent(
        KimiCodeCLIAgentConfig(model="kimi-code/k3", effort="high")
    ).new()

    def put_in() -> None:
        for _ in range(300):
            if session._running.session is not None:
                session.interject("actually, stop")
                return
            time.sleep(0.02)

    threading.Thread(target=put_in, daemon=True).start()
    answered = session("patient")

    sent = [call for call in kimi.calls() if call["path"].endswith("/prompts:steer")]
    assert [call["body"] for call in sent] == [{"prompt_ids": ["p_2"]}]
    # The word went in as a prompt of its own and was then moved into the running turn, so
    # the turn's answer is the answer to it.
    assert answered == "steered:actually, stop"


def test_a_kimi_session_with_no_turn_running_cannot_be_talked_to() -> None:
    session = KimiCodeCLIAgent(
        KimiCodeCLIAgentConfig(model="kimi-code/k3", effort="high")
    ).new()

    with pytest.raises(RuntimeError, match="no turn is running"):
        session.interject("hello?")


def test_codex_puts_a_question_to_whoever_is_driving_the_agent(
    codex: _FakeServer,
) -> None:
    """A turn that stopped to ask waits on the answer, so the server has to be given one."""
    agent = CodexAgent(CodexAgentConfig(model="gpt-5.6-sol", effort="high"))
    asked: list[str] = []

    def answer(question: Any) -> str:
        asked.append(question.text)
        return "right"

    agent.ask = answer

    # What the turn answered is what the server was told, keyed by the id it gave the
    # question and given as a list, since a question may take more than one of its options.
    assert agent("asking") == json.dumps({"which": {"answers": ["right"]}})
    assert asked == ["Which way?"]


def test_codex_is_told_nobody_answered_rather_than_left_waiting(
    codex: _FakeServer,
) -> None:
    """A turn waiting on an answer that is not coming is a flow that has stopped."""
    agent = CodexAgent(CodexAgentConfig(model="gpt-5.6-sol", effort="high"))

    assert agent("asking") == json.dumps({"which": {"answers": []}})


def test_kimi_answers_a_question_the_turn_stopped_on(kimi: _FakeServer) -> None:
    """The daemon holds the question and the turn waits on it.

    A poll that only read the messages would be reading a session that has stopped moving.
    """
    agent = _agent()
    agent.ask = lambda question: "right"

    assert agent("hi") == "answered"

    # Answered by the option it names, since a question that offered options need not take
    # anything else.
    assert _bodies(kimi, "/questions/q_0") == [
        {"answers": {"which": {"kind": "single", "option_id": "o_r"}}}
    ]


def test_a_codex_turn_is_held_to_the_shape_it_was_asked_for(codex: _FakeServer) -> None:
    """`outputSchema` is a setting of the turn, so the prompt says nothing about the shape."""
    session = CodexAgent(CodexAgentConfig(model="gpt-5.6-sol", effort="high")).new()

    def finish() -> None:
        for _ in range(200):
            if session._running.turn is not None:
                session.interject("go on")
                return
            time.sleep(0.02)

    threading.Thread(target=finish, daemon=True).start()
    session("do the task", schema=_Verdict, suppress=True)

    called = {call["method"]: call["params"] for call in codex.calls()}
    # What was asked is the schema itself, and the prompt is the prompt.
    assert called["turn/start"]["outputSchema"] == _Verdict.model_json_schema()
    assert called["turn/start"]["input"] == [{"type": "text", "text": "do the task"}]


def test_codex_can_disable_goals_before_its_server_starts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The per-agent policy also removes Codex's goal feature from its app server."""
    started: list[list[str]] = []

    class _Recording:
        def __init__(
            self, argv: list[str], env: Mapping[str, str] | None = None
        ) -> None:
            del env
            started.append(argv)
            self._held: list[Any] = []

        def stop(self) -> None:
            """Nothing was started, so there is nothing to take down."""

    monkeypatch.setattr(appservers, "_AppServer", _Recording)
    agent = CodexAgent(CodexAgentConfig(model="gpt-5.6-sol", effort="high"))
    agent.disable_goals()

    assert not agent.goals_enabled
    assert agent.server is not None
    # By the path this machine has Codex installed at, which is a name only where it is not
    # installed at all: what is being read here is the arguments it is started with.
    assert [_named(argv) for argv in started] == [
        [
            "codex",
            "app-server",
            "--disable",
            "goals",
            "-c",
            "tools.web_search=true",
            "--stdio",
        ]
    ]
    with pytest.raises(RuntimeError, match="goals are disabled"):
        agent.new().pursue("the suite passes", suppress=True)


def test_codex_passes_allowlisted_overrides_to_its_app_server(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A window asked for on this agent is this server's `-c`, not the user's config.toml."""
    started: list[list[str]] = []

    class _Recording:
        def __init__(
            self, argv: list[str], env: Mapping[str, str] | None = None
        ) -> None:
            del env
            started.append(argv)
            self._held: list[Any] = []

        def stop(self) -> None:
            """Nothing was started, so there is nothing to take down."""

    monkeypatch.setattr(appservers, "_AppServer", _Recording)
    agent = CodexAgent(
        CodexAgentConfig(
            model="gpt-5.6-sol",
            effort="high",
            overrides=(
                ("model_context_window", "1000000"),
                ("model_auto_compact_token_limit", "900000"),
            ),
        )
    )

    assert agent.server is not None
    assert [_named(argv) for argv in started] == [
        [
            "codex",
            "app-server",
            "-c",
            "tools.web_search=true",
            "--stdio",
            "-c",
            "model_context_window=1000000",
            "-c",
            "model_auto_compact_token_limit=900000",
        ]
    ]


def test_codex_refuses_an_override_that_is_already_a_setting_of_the_agent() -> None:
    """model, effort and permission have one place; a second would be two answers."""
    with pytest.raises(ValueError, match="not a Codex override"):
        CodexAgentConfig(
            model="gpt-5.6-sol",
            effort="high",
            overrides=(("model", "gpt-5.6-sol"),),
        )
    with pytest.raises(ValueError, match="positive integer"):
        CodexAgentConfig(
            model="gpt-5.6-sol",
            effort="high",
            overrides=(("model_context_window", "1m"),),
        )
    with pytest.raises(ValueError, match="below model_context_window"):
        CodexAgentConfig(
            model="gpt-5.6-sol",
            effort="high",
            overrides=(
                ("model_context_window", "1000000"),
                ("model_auto_compact_token_limit", "1000000"),
            ),
        )


def test_codex_refuses_to_disable_goals_after_its_server_starts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A server's feature set cannot be changed underneath threads it already holds."""

    class _Recording:
        def __init__(
            self, argv: list[str], env: Mapping[str, str] | None = None
        ) -> None:
            del argv, env
            self._held: list[Any] = []

        def stop(self) -> None:
            """Nothing was started, so there is nothing to take down."""

    monkeypatch.setattr(appservers, "_AppServer", _Recording)
    agent = CodexAgent(CodexAgentConfig(model="gpt-5.6-sol", effort="high"))
    assert agent.server is not None

    with pytest.raises(RuntimeError, match="before its first turn"):
        agent.disable_goals()


def test_codex_grants_what_a_turn_asks_to_be_allowed_to_do(codex: _FakeServer) -> None:
    """At the rung that means the asking is granted, the answer is yes.

    The server waits on it, so this is the one moment a refusal here actually stops the agent
    doing something -- which is why it is the one a hook can reach.
    """
    agent = CodexAgent(
        CodexAgentConfig(model="gpt-5.6-sol", effort="high", permission="auto")
    )

    assert agent("approving") == json.dumps({"decision": "accept"})


def test_a_hook_may_refuse_what_codex_asked_to_be_allowed_to_do(
    codex: _FakeServer,
) -> None:
    from hmz.agents import Moment, Verdict

    agent = CodexAgent(
        CodexAgentConfig(model="gpt-5.6-sol", effort="high", permission="auto")
    )
    with agent.hooks.on(Moment.PERMISSION_REQUEST, lambda _: Verdict(refused=True)):
        assert agent("approving") == json.dumps({"decision": "decline"})


def test_codex_is_widened_by_handing_back_the_permissions_it_asked_for(
    codex: _FakeServer,
) -> None:
    """That request takes the permissions as its answer rather than a yes or a no."""
    agent = CodexAgent(
        CodexAgentConfig(model="gpt-5.6-sol", effort="high", permission="auto")
    )

    assert agent("widening") == json.dumps(
        {"permissions": {"network": {"enabled": True}}, "scope": "turn"}
    )


def test_a_widening_a_hook_refuses_is_granted_nothing(codex: _FakeServer) -> None:
    from hmz.agents import Moment, Verdict

    agent = CodexAgent(
        CodexAgentConfig(model="gpt-5.6-sol", effort="high", permission="auto")
    )
    with agent.hooks.on(Moment.PERMISSION_REQUEST, lambda _: Verdict(refused=True)):
        assert agent("widening") == json.dumps({"permissions": {}})


@pytest.mark.parametrize(
    ("permission", "sandbox"),
    [
        ("read-only", "read-only"),
        ("workspace-write", "workspace-write"),
        ("bypass", "danger-full-access"),
    ],
)
def test_a_codex_turn_carries_the_rung_it_runs_at(
    working: _FakeServer, permission: str, sandbox: str
) -> None:
    """A thread picked back up does not carry the settings it was started with."""
    agent = CodexAgent(
        CodexAgentConfig(model="gpt-5.6-sol", effort="high", permission=permission)
    )
    agent("hi")

    started = [call for call in working.calls() if call.get("method") == "turn/start"]
    assert [call["params"]["sandbox"] for call in started] == [sandbox]
    assert [call["params"]["approvalPolicy"] for call in started] == ["never"]


@pytest.mark.parametrize(
    ("permission", "mode", "planning"),
    [("read-only", "auto", True), ("bypass", "yolo", False)],
)
def test_a_kimi_turn_carries_the_rung_it_runs_at(
    kimi: _FakeServer, permission: str, mode: str, planning: bool
) -> None:
    agent = KimiCodeCLIAgent(
        KimiCodeCLIAgentConfig(
            model="kimi-code/k3", effort="high", permission=permission
        )
    )
    agent("hi")

    (profile,) = _bodies(kimi, "/profile")
    assert profile["agent_config"]["permission_mode"] == mode
    assert profile["agent_config"]["plan_mode"] is planning


def test_a_codex_turn_runs_at_the_effort_the_flow_moved_it_to(
    working: _FakeServer,
) -> None:
    """A setting of the turn here, so the next turn simply carries the new one."""
    agent = CodexAgent(CodexAgentConfig(model="gpt-5.6-sol", effort="high"))
    session = agent.new()
    session("one")
    session.effort = "low"
    session("two")

    started = [call for call in working.calls() if call.get("method") == "turn/start"]
    assert [call["params"]["effort"] for call in started] == ["high", "low"]


def test_a_kimi_turn_runs_at_the_effort_the_flow_moved_it_to(kimi: _FakeServer) -> None:
    """The profile is sent with every turn, so the next one carries the new one."""
    agent = _agent()
    agent.effort = "low"
    agent("hi")

    (profile,) = _bodies(kimi, "/profile")
    assert profile["agent_config"]["thinking"] == "low"


def test_a_kimi_turn_moved_to_a_swarm_runs_wide_from_the_next_turn(
    kimi: _FakeServer,
) -> None:
    """Kimi's effort says how wide as well as how hard, so moving it moves both."""
    agent = _agent()
    agent.effort = "swarmmax"
    agent("hi")

    (profile,) = _bodies(kimi, "/profile")
    assert profile["agent_config"]["thinking"] == "max"
    assert profile["agent_config"]["swarm_mode"] is True
