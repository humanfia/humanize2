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
from typing import Any

import pytest

from amflows.janus import (
    CodexAgent,
    CodexAgentConfig,
    KimiCodeCLIAgent,
    KimiCodeCLIAgentConfig,
)
from amflows.janus.agents import codex as appservers

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
        if self.path.endswith("/prompts:steer"):
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
        elif self.path.endswith("/goal"):
            # Still being pursued the first time it is asked, as a goal is between its turns.
            GOAL.append(None)
            self.reply({"status": "active"} if len(GOAL) == 1 else None)
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
        if call["params"]["input"][0]["text"] == "doomed":
            send({"method": "turn/completed",
                  "params": {"turn": {"id": "turn_fake", "status": "failed",
                                      "error": {"type": "usageLimitExceeded"}}}})
            send({"method": "thread/status/changed",
                  "params": {"status": {"type": "idle"}}})
            continue
        send({"method": "item/agentMessage/delta", "params": {"delta": "working"}})
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


def test_kimi_opens_then_resumes(kimi: _FakeServer) -> None:
    session = _agent().launch()
    assert session.run("hi") == "answered"
    session.run("again")

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
    assert opened[0]["body"] == {"metadata": {"cwd": os.getcwd()}}
    assert [prompt["body"]["content"][0]["text"] for prompt in prompts] == [
        "hi",
        "again",
    ]
    assert all(
        prompt["path"] == f"/api/v1/sessions/{session.id}/prompts" for prompt in prompts
    )
    assert all(call["token"] == "Bearer secret" for call in calls)


@pytest.mark.parametrize(
    ("effort", "thinking", "swarm"), [("max", "max", False), ("swarmmax", "max", True)]
)
def test_kimi_effort_says_how_hard_to_think_and_how_wide(
    kimi: _FakeServer, effort: str, thinking: str, swarm: bool
) -> None:
    """Swarm is a mode of the session, so the effort an agent runs at is where it can be said."""
    _agent(effort).launch().run("hi")

    (profile,), (prompt,) = _bodies(kimi, "/profile"), _bodies(kimi, "/prompts")
    assert profile["agent_config"]["thinking"] == thinking
    assert profile["agent_config"]["swarm_mode"] is swarm
    assert prompt["thinking"] == thinking
    assert prompt["swarm_mode"] is swarm


def test_kimi_pursues_by_setting_a_goal_on_the_session(kimi: _FakeServer) -> None:
    """The goal is the session's, not a `/goal` the model would read as a line of the prompt."""
    _agent("swarmmax").launch().pursue("the suite passes")

    (profile,), (prompt,) = _bodies(kimi, "/profile"), _bodies(kimi, "/prompts")
    assert profile["agent_config"]["goal_objective"] == "the suite passes"
    # And the objective is the turn as well: what to do, and what it is for.
    assert prompt["content"] == [{"type": "text", "text": "the suite passes"}]


def test_kimi_reads_a_message_again_until_it_has_been_finished(
    kimi: _FakeServer,
) -> None:
    """The daemon hands back a message that is still being written, so once is not enough."""
    # The stand-in has nothing to say the first time it is read, and the answer the second.
    assert _agent().launch().run("hi") == "answered"


def test_kimi_pursues_past_a_session_that_has_fallen_still(kimi: _FakeServer) -> None:
    """A goal runs on through the quiet between its turns, so that quiet must not end the turn."""
    _agent().launch().pursue("the suite passes")

    # Asked again after it answered that the goal was still being pursued, rather than the
    # session having been taken for finished the first time it fell quiet.
    assert len([call for call in kimi.calls() if call["path"].endswith("/goal")]) >= 2


def test_kimi_runs_without_setting_one(kimi: _FakeServer) -> None:
    KimiCodeCLIAgent(
        KimiCodeCLIAgentConfig(model="kimi-code/k3", effort="high")
    ).launch().run("hi")

    profiles = [call for call in kimi.calls() if call["path"].endswith("/profile")]
    assert all(
        "goal_objective" not in call["body"]["agent_config"] for call in profiles
    )


def test_a_kimi_turn_the_server_refuses_leaves_the_session_unopened(
    kimi: _FakeServer,
) -> None:
    agent = _agent()
    session = agent.launch()
    with pytest.raises(subprocess.CalledProcessError) as refused:
        session.run("boom")

    assert refused.value.returncode == 400
    assert (
        agent.opened == []
    )  # so the next call opens a session rather than resuming one
    with pytest.raises(RuntimeError):
        _ = session.id


def test_codex_pursues_by_setting_a_goal_on_the_thread(codex: _FakeServer) -> None:
    """`/goal` is `thread/goal/set`, which is the app server's rather than `codex exec`'s."""
    agent = CodexAgent(CodexAgentConfig(model="gpt-5-codex", effort="high"))
    session = agent.launch()
    # The last thing it said, not the first: an idle mid-goal is where Codex carries on.
    assert session.pursue("the suite passes") == "answered"

    called = {call["method"]: call["params"] for call in codex.calls()}
    assert called["thread/start"]["cwd"] == os.getcwd()
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
    session = CodexAgent(CodexAgentConfig(model="gpt-5-codex", effort="high")).launch()

    assert session.pursue("stuck") == "answered"  # the turn is lost, the loop is not


def test_codex_resumes_the_thread_a_later_goal_is_set_on(codex: _FakeServer) -> None:
    """A goal is set on a thread the server holds, and one it opened earlier it has let go."""
    session = CodexAgent(CodexAgentConfig(model="gpt-5-codex", effort="high")).launch()
    session.pursue("the suite passes")
    session.pursue("and stays passing")

    methods = [call["method"] for call in codex.calls()]
    assert (
        methods.count("thread/start") == 1
    )  # one thread, resumed rather than reopened
    assert methods.count("thread/resume") == 1


def test_codex_starts_no_app_server_until_a_turn_needs_one(
    codex: _FakeServer,
) -> None:
    CodexAgent(CodexAgentConfig(model="gpt-5-codex", effort="high")).launch()

    assert not codex.log.exists()


def test_codex_runs_an_ordinary_turn_on_the_thread(codex: _FakeServer) -> None:
    """Not `codex exec`: the turn goes to the server, which is what leaves it steerable."""
    agent = CodexAgent(CodexAgentConfig(model="gpt-5-codex", effort="high"))
    session = agent.launch()

    # The turn stays open the way a real one does, so it is ended by putting a word in.
    def finish() -> None:
        for _ in range(200):
            if session._running.turn is not None:
                session.interject("go on")
                return
            time.sleep(0.02)

    threading.Thread(target=finish, daemon=True).start()
    assert session.run("do the task") == "steered:go on"

    called = {call["method"]: call["params"] for call in codex.calls()}
    assert called["thread/start"]["cwd"] == os.getcwd()
    assert called["turn/start"]["input"] == [{"type": "text", "text": "do the task"}]
    assert called["turn/start"]["effort"] == "high"
    assert "thread/goal/set" not in called  # an ordinary turn sets no goal
    assert session.id == "thread_fake"
    assert agent.opened == ["thread_fake"]


def test_codex_can_be_talked_to_while_a_turn_is_running(codex: _FakeServer) -> None:
    """The point of running the turn on the server: a word put in reaches the turn under way."""
    session = CodexAgent(CodexAgentConfig(model="gpt-5-codex", effort="high")).launch()

    said = []
    for event in session.stream("count to sixty"):
        if event.kind == "text" and not said:
            session.interject("actually, stop")
        said.append(event)

    steered = next(call for call in codex.calls() if call["method"] == "turn/steer")
    assert steered["params"] == {
        "threadId": "thread_fake",
        "input": [{"type": "text", "text": "actually, stop"}],
        # Named, so the server refuses to steer a turn that has already moved on.
        "expectedTurnId": "turn_fake",
    }
    assert "steered:actually, stop" in said[-1].text


def test_a_codex_session_with_no_turn_running_cannot_be_talked_to() -> None:
    session = CodexAgent(CodexAgentConfig(model="gpt-5-codex", effort="high")).launch()

    with pytest.raises(RuntimeError, match="no turn is running"):
        session.interject("hello?")


def test_a_codex_turn_that_failed_does_not_answer_as_if_it_landed(
    codex: _FakeServer,
) -> None:
    """The thread goes idle either way, so a turn that failed must say so rather than "".

    Otherwise a loop feeds an empty answer forward as the work of the turn before it.
    """
    agent = CodexAgent(CodexAgentConfig(model="gpt-5-codex", effort="high"))
    session = agent.launch()

    with pytest.raises(subprocess.CalledProcessError) as failed:
        session.run("doomed")

    assert "usageLimitExceeded" in str(failed.value.stderr)
    assert agent.opened == []  # a turn that failed opened nothing
    with pytest.raises(RuntimeError):
        _ = session.id


def test_a_codex_turn_ignores_what_another_thread_is_saying(codex: _FakeServer) -> None:
    """One server holds every session of the agent, and each turn is only its own thread's."""
    session = CodexAgent(CodexAgentConfig(model="gpt-5-codex", effort="high")).launch()
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
    assert session.run("do the task") == "steered:go on"


def test_kimi_steers_a_word_into_the_turn_already_running(kimi: _FakeServer) -> None:
    """A prompt sent to a working session is queued; steering moves it into this turn.

    Without the steer it would be answered as a turn of its own once this one ended, which is
    a turn queued behind rather than a word put in.
    """
    session = KimiCodeCLIAgent(
        KimiCodeCLIAgentConfig(model="kimi-code/k3", effort="high")
    ).launch()

    def put_in() -> None:
        for _ in range(300):
            if session._running.session is not None:
                session.interject("actually, stop")
                return
            time.sleep(0.02)

    threading.Thread(target=put_in, daemon=True).start()
    answered = session.run("patient")

    sent = [call for call in kimi.calls() if call["path"].endswith("/prompts:steer")]
    assert [call["body"] for call in sent] == [{"prompt_ids": ["p_2"]}]
    # The word went in as a prompt of its own and was then moved into the running turn, so
    # the turn's answer is the answer to it.
    assert answered == "steered:actually, stop"


def test_a_kimi_session_with_no_turn_running_cannot_be_talked_to() -> None:
    session = KimiCodeCLIAgent(
        KimiCodeCLIAgentConfig(model="kimi-code/k3", effort="high")
    ).launch()

    with pytest.raises(RuntimeError, match="no turn is running"):
        session.interject("hello?")
