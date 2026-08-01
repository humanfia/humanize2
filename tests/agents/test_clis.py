"""Tests for the backends driven through their own command line rather than a server.

pi holds one process for the whole session and takes its turns as commands on stdin; opencode
and mimocode are one run apiece and answer in events. Both are exercised against stand-ins on
PATH that print what the real ones print, so what is checked is the call each turn is made of
and the turn read back out of what it answered.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass
from typing import TYPE_CHECKING

import pytest

from hmz.agents import (
    MimoCodeAgent,
    MimoCodeAgentConfig,
    OpencodeAgent,
    OpencodeAgentConfig,
    PiAgent,
    PiAgentConfig,
)
from hmz.machines import AnchoredConfig
from tests.stubs import HereAnchor

if TYPE_CHECKING:
    from pathlib import Path

PI = PiAgentConfig(model="openai-codex/gpt-5.5", effort="high")
OPENCODE = OpencodeAgentConfig(model="opencode/big-pickle", effort="high")
MIMO = MimoCodeAgentConfig(model="xiaomi/mimo-v2.5", effort="low")

#: A `pi --mode rpc`: it names the session it was given, then answers each command written to
#: it with the events one agent run is made of. A prompt of `boom` is refused outright and one
#: of `wrong` comes back as a request that errored, which are the two ways a turn fails here.
_PI = """
import json, pathlib, queue, sys, threading

log = pathlib.Path(LOG)
lines = queue.Queue()
held = []


def reading():
    for line in sys.stdin:
        lines.put(line)
    lines.put(None)


def take(waiting=None):
    # A command already read and not for the turn it arrived during comes first.
    if held:
        return held.pop(0)
    try:
        line = lines.get(timeout=waiting) if waiting else lines.get()
    except queue.Empty:
        return None
    return None if line is None else json.loads(line)


def note(argv, said):
    with log.open("a") as stream:
        json.dump({"argv": argv, "stdin": said}, stream)
        stream.write("\\n")


def out(said):
    print(json.dumps(said), flush=True)


def steered(said):
    note([], "steer " + said)
    out({"type": "message_start", "message": {"role": "user",
         "content": [{"type": "text", "text": said}]}})


note(sys.argv[1:], "")
flags = dict(zip(sys.argv, sys.argv[1:]))
threading.Thread(target=reading, daemon=True).start()
out({"type": "session", "id": flags["--session-id"]})
while True:
    told = take()
    if told is None:
        break
    if told["type"] == "steer":
        steered(told["message"])
        continue
    if told["type"] != "prompt":
        note([], told["type"])
        out({"type": "response", "command": told["type"], "success": True})
        continue
    said = told["message"]
    note([], said)
    if said == "boom":
        out({"type": "response", "command": "prompt", "success": False,
             "error": "pi would not take it"})
        continue
    out({"type": "response", "command": "prompt", "success": True})
    out({"type": "agent_start"})
    # The turn's own prompt comes back as a user message too, and is not a word put in.
    out({"type": "message_start", "message": {"role": "user",
         "content": [{"type": "text", "text": said}]}})
    out({"type": "message_update", "assistantMessageEvent":
         {"type": "text_delta", "delta": "half"}})
    out({"type": "message_update", "assistantMessageEvent":
         {"type": "thinking_end", "content": "thinking about " + said}})
    out({"type": "message_update", "assistantMessageEvent": {"type": "toolcall_end",
         "toolCall": {"name": "bash", "arguments": {"command": "echo " + said}}}})
    out({"type": "message_update", "assistantMessageEvent":
         {"type": "text_end", "content": said}})
    out({"type": "message_end", "message": {"role": "assistant",
         "content": ([] if said == "wrong" else [{"type": "text", "text": said}]),
         "usage": {"input": 10, "output": 5, "cacheRead": 2, "cacheWrite": 1},
         **({"errorMessage": "the model refused"} if said == "wrong" else {})}})
    out({"type": "agent_end"})
    # A word steered in while the run was going is part of it: the run settles once, after
    # everything it was told, which is the whole reason a steer is not a turn of its own.
    while (more := take(0.25)) is not None:
        if more["type"] != "steer":
            held.append(more)
            break
        steered(more["message"])
    out({"type": "agent_settled"})
"""

#: An `opencode run`: it takes the prompt on stdin and answers in the events of one turn. A
#: prompt of `boom` comes back as an error event with the exit status still zero, which is how
#: this backend reports a turn it could not finish; one of `quiet` says nothing at all.
_OPENCODE = """
import json, os, pathlib, sys

log = pathlib.Path(LOG)
said = sys.stdin.read()
allowed = os.environ.get("OPENCODE_PERMISSION") or os.environ.get("MIMOCODE_PERMISSION")
with log.open("a") as stream:
    json.dump({"argv": sys.argv[1:], "stdin": said, "allowed": allowed,
               "inherited": os.environ.get("A_THING_THE_FLOW_HAS")}, stream)
    stream.write("\\n")

flags = dict(zip(sys.argv, sys.argv[1:]))
session = flags.get("--session", "ses_stub")


def out(kind, part):
    print(json.dumps({"type": kind, "sessionID": session, "part": part}), flush=True)


if said == "quiet":
    sys.exit(0)
if said == "boom":
    print(json.dumps({"type": "error", "sessionID": session,
                      "error": {"name": "APIError"}}), flush=True)
    sys.exit(0)
out("step_start", {"id": "prt_start", "type": "step-start"})
out("tool_use", {"id": "prt_tool", "type": "tool", "tool": "bash",
                 "state": {"status": "completed", "input": {"command": "echo " + said},
                           "title": "echo " + said}})
out("reasoning", {"id": "prt_think", "type": "reasoning", "text": "thinking about " + said})
out("step_finish", {"id": "prt_one", "type": "step-finish", "reason": "tool-calls",
                    "tokens": {"total": 9, "input": 5, "output": 2, "reasoning": 1,
                               "cache": {"read": 1, "write": 0}}})
out("text", {"id": "prt_text", "type": "text", "text": said})
out("step_finish", {"id": "prt_two", "type": "step-finish", "reason": "stop",
                    "tokens": {"total": 3, "input": 2, "output": 1, "reasoning": 0,
                               "cache": {"read": 0, "write": 0}}})
"""


@dataclass(frozen=True)
class _Call:
    """One invocation of a stand-in CLI: what it was asked for, and what it was fed."""

    argv: list[str]
    stdin: str
    #: What its environment said the agent may do, for the backend that is told there.
    allowed: str | None = None
    #: Something the flow itself had in its environment, which a turn is run with too.
    inherited: str | None = None


@dataclass(frozen=True)
class _Stubs:
    """The stand-in CLIs on PATH, and the calls they were made with."""

    log: Path

    def calls(self) -> list[_Call]:
        return [_Call(**json.loads(line)) for line in self.log.read_text().splitlines()]


def _install(binaries: Path, named: str, script: str, log: Path) -> None:
    """Puts one stand-in CLI on PATH under the name the backend calls it."""
    fake = binaries / named
    fake.write_text(f"#!{sys.executable}\n{script.replace('LOG', repr(str(log)))}")
    fake.chmod(0o755)


@pytest.fixture
def stubs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> _Stubs:
    """Installs a stand-in for each of the three, printing what the real ones print."""
    log = tmp_path / "calls.jsonl"
    binaries = tmp_path / "bin"
    binaries.mkdir()
    _install(binaries, "pi", _PI, log)
    _install(binaries, "opencode", _OPENCODE, log)
    _install(binaries, "mimo", _OPENCODE, log)
    monkeypatch.setenv("PATH", f"{binaries}{os.pathsep}{os.environ['PATH']}")
    return _Stubs(log)


def test_pi_holds_one_process_for_the_whole_session(stubs: _Stubs) -> None:
    """Two turns are two commands written to one pi, rather than two runs of it."""
    session = PiAgent(PI).new()
    assert session("hi") == "hi"
    assert session("again") == "again"

    launch, first, second = stubs.calls()
    assert launch.argv[:3] == ["--mode", "rpc", "--model"]
    assert launch.argv[launch.argv.index("--model") + 1] == "openai-codex/gpt-5.5"
    assert launch.argv[launch.argv.index("--thinking") + 1] == "high"
    assert launch.argv[launch.argv.index("--session-id") + 1] == session.id
    assert [first.stdin, second.stdin] == ["hi", "again"]


def test_pi_says_what_the_turn_did_and_what_it_cost(stubs: _Stubs) -> None:
    """A message is a list of parts, and only the finished ones carry any words."""
    session = PiAgent(PI).new()
    said = list(session.stream("hi"))

    assert [event.kind for event in said] == ["reasoning", "tool", "text", "result"]
    assert said[1].text == "bash echo hi"
    assert said[-1].text == "hi"
    # Every kind of token: what a rate measures is the traffic, and a cache read is traffic.
    assert dict(said[-1].tokens) == {"openai-codex/gpt-5.5": 18}
    assert stubs.log.exists()


def test_pi_can_be_talked_to_while_a_turn_is_running(stubs: _Stubs) -> None:
    """The point of holding the process open: a word put in reaches the turn under way."""
    session = PiAgent(PI).new()
    said: list[str] = []
    for event in session.stream("start"):
        if (
            event.kind == "reasoning" and not said
        ):  # the turn is running and pi is listening
            session.interject("actually, stop")
        said.append(event.kind)

    # One turn, however many things were said in it: pi answers a whole run once, so a word
    # put in is not an answer owed and the turn still ends on one result.
    assert said.count("result") == 1
    assert said[-1] == "result"
    assert "took" in said
    assert [call.stdin for call in stubs.calls() if call.stdin] == [
        "start",
        "steer actually, stop",
    ]
    assert session("after") == "after"  # the stream is still in step for the next turn


def test_pi_that_never_opened_cannot_be_talked_to() -> None:
    with pytest.raises(RuntimeError, match="no turn is running"):
        PiAgent(PI).new().interject("hello?")


def test_pi_reports_a_refused_prompt_as_a_failed_turn(stubs: _Stubs) -> None:
    session = PiAgent(PI).new()
    with pytest.raises(subprocess.CalledProcessError):
        session("boom")
    assert session.named is not None
    with pytest.raises(RuntimeError, match="has not run a turn yet"):
        _ = session.id  # a turn that failed leaves the session unopened


def test_pi_reports_a_request_that_errored_as_a_failed_turn(stubs: _Stubs) -> None:
    """A run whose last request came back an error and left nothing to say did not land."""
    session = PiAgent(PI).new()
    with pytest.raises(subprocess.CalledProcessError):
        session("wrong")
    # And the session is still usable: the next turn opens it.
    assert session("hi") == "hi"


def test_an_anchored_pi_hands_its_whole_turn_to_the_anchor(stubs: _Stubs) -> None:
    anchor = HereAnchor(target="ssh://build-box", workspace="/srv/project")
    session = PiAgent(
        PiAgentConfig(
            model="openai-codex/gpt-5.5",
            effort="high",
            machine=AnchoredConfig(anchor=anchor),
        )
    ).new()
    session("hi")
    session("again")

    # An anchored turn ends with its process, so the next one resumes the session it named.
    opened, resumed = anchor.seen
    assert opened[opened.index("--session-id") + 1] == session.id
    assert resumed[resumed.index("--session-id") + 1] == session.id


def test_opencode_is_one_run_per_turn_resuming_the_session_it_opened(
    stubs: _Stubs,
) -> None:
    session = OpencodeAgent(OPENCODE).new()
    assert session("hi") == "hi"
    assert session("again") == "again"

    first, second = stubs.calls()
    assert first.argv[:4] == ["run", "--format", "json", "--dir"]
    assert first.argv[first.argv.index("--model") + 1] == "opencode/big-pickle"
    assert first.argv[first.argv.index("--variant") + 1] == "high"
    assert "--auto" in first.argv
    assert "--session" not in first.argv  # nothing to carry on yet
    assert second.argv[second.argv.index("--session") + 1] == session.id
    assert [first.stdin, second.stdin] == ["hi", "again"]


def test_opencode_says_what_the_turn_did_and_what_it_cost(stubs: _Stubs) -> None:
    session = OpencodeAgent(OPENCODE).new()
    said = list(session.stream("hi"))

    assert [event.kind for event in said] == ["tool", "reasoning", "text", "result"]
    assert said[0].text == "bash echo hi"
    assert said[-1].text == "hi"
    # Both steps, every kind of token: reasoning is counted beside the output here.
    assert dict(said[-1].tokens) == {"opencode/big-pickle": 12}


def test_opencode_does_not_put_its_protocol_on_the_terminal(
    stubs: _Stubs, capsys: pytest.CaptureFixture[str]
) -> None:
    """What it writes on stdout is the turn as events, not the agent talking."""
    assert OpencodeAgent(OPENCODE).new()("hi") == "hi"

    streams = capsys.readouterr()
    assert "sessionID" not in streams.out
    assert streams.out.strip() == "hi"  # the answer, where the CLI would have put it


def test_opencode_reports_an_error_event_as_a_failed_turn(stubs: _Stubs) -> None:
    """It exits zero and says what went wrong in its events, so the events are read."""
    session = OpencodeAgent(OPENCODE).new()
    with pytest.raises(subprocess.CalledProcessError):
        session("boom")
    with pytest.raises(RuntimeError, match="has not run a turn yet"):
        _ = session.id


def test_opencode_that_said_nothing_at_all_is_a_failed_turn(stubs: _Stubs) -> None:
    with pytest.raises(subprocess.CalledProcessError):
        OpencodeAgent(OPENCODE).new()("quiet")


def test_a_suppressed_opencode_turn_answers_with_nothing(stubs: _Stubs) -> None:
    assert OpencodeAgent(OPENCODE).new()("boom", suppress=True) == ""


def test_mimo_is_opencode_under_its_own_name(stubs: _Stubs) -> None:
    session = MimoCodeAgent(MIMO).new()
    assert session("hi") == "hi"

    (call,) = stubs.calls()
    assert call.argv[:3] == ["run", "--format", "json"]
    assert call.argv[call.argv.index("--model") + 1] == "xiaomi/mimo-v2.5"
    assert call.argv[call.argv.index("--variant") + 1] == "low"
    # Its own spelling of `--auto`, which is the one thing that differs on the way in.
    assert "--dangerously-skip-permissions" in call.argv
    assert "--auto" not in call.argv


def test_the_new_backends_name_themselves_as_a_command_line_names_them() -> None:
    """`AgentBase.backend` is read off the class, so a mismatch is a backend nobody finds."""
    from hmz import backends

    for agent, config in (
        (PiAgent, PI),
        (OpencodeAgent, OPENCODE),
        (MimoCodeAgent, MIMO),
    ):
        named = agent(config).backend
        assert backends.named(named) is not None, named


def test_a_backend_that_cannot_be_talked_to_mid_turn_says_so(stubs: _Stubs) -> None:
    with pytest.raises(NotImplementedError):
        OpencodeAgent(OPENCODE).new().interject("hello?")


def test_neither_opencode_nor_mimo_has_a_goal_feature(stubs: _Stubs) -> None:
    with pytest.raises(NotImplementedError):
        OpencodeAgent(OPENCODE).new().pursue("the suite passes")
    with pytest.raises(NotImplementedError):
        PiAgent(PI).new().pursue("the suite passes")


def test_pi_is_given_no_tools_that_change_anything_when_it_may_change_nothing(
    stubs: _Stubs,
) -> None:
    """Pi has no permission gate and no sandbox: what it takes is which tools to load."""
    reading = PiAgent(
        PiAgentConfig(model="m", effort="high", permission="read-only")
    ).new()
    assert reading("hi") == "hi"
    (launch, _) = stubs.calls()
    assert launch.argv[launch.argv.index("--exclude-tools") + 1] == "bash,edit,write"


@pytest.mark.parametrize("permission", ["workspace-write", "auto", "bypass"])
def test_pi_above_that_rung_is_the_same_agent(stubs: _Stubs, permission: str) -> None:
    """Nothing here can tell the three apart, and it says so rather than pretending."""
    session = PiAgent(
        PiAgentConfig(model="m", effort="high", permission=permission)
    ).new()
    assert session("hi") == "hi"
    (launch, _) = stubs.calls()
    assert "--exclude-tools" not in launch.argv


@pytest.mark.parametrize(
    ("permission", "edit", "bash", "webfetch"),
    [
        ("read-only", "deny", "deny", "allow"),
        ("workspace-write", "allow", "allow", "deny"),
        ("auto", "allow", "allow", "allow"),
        ("bypass", "allow", "allow", "allow"),
    ],
)
def test_opencode_is_told_what_the_agent_may_do_in_its_own_variable(
    stubs: _Stubs, permission: str, edit: str, bash: str, webfetch: str
) -> None:
    """Set for the turn and for nothing else: the user's own settings are left alone."""
    session = OpencodeAgent(
        OpencodeAgentConfig(model="m", effort="high", permission=permission)
    ).new()
    assert session("hi") == "hi"

    (call,) = stubs.calls()
    assert call.allowed is not None
    assert json.loads(call.allowed) == {
        "edit": edit,
        "bash": bash,
        "webfetch": webfetch,
    }
    # And the flag that answers everything not refused outright is still on: what the rung
    # narrows is said as refusals, and the flag is what carries the rest.
    assert "--auto" in call.argv


def test_mimo_is_told_the_same_thing_under_its_own_name(stubs: _Stubs) -> None:
    session = MimoCodeAgent(
        MimoCodeAgentConfig(model="m", effort="low", permission="read-only")
    ).new()
    assert session("hi") == "hi"

    (call,) = stubs.calls()
    assert call.allowed is not None
    assert json.loads(call.allowed)["bash"] == "deny"


def test_a_turn_runs_in_the_flows_own_environment_and_what_it_is_told(
    stubs: _Stubs, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Adding a variable must not take away the rest: an agent logs in as it already does."""
    monkeypatch.setenv("A_THING_THE_FLOW_HAS", "kept")
    assert OpencodeAgent(OPENCODE).new()("hi") == "hi"

    (call,) = stubs.calls()
    assert call.inherited == "kept"
    assert call.allowed is not None
