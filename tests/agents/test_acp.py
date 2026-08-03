"""A CLI of your own, driven over the Agent Client Protocol.

The protocol is the whole of what is known about such a backend, so what is checked here is
the conversation: the handshake, the session it opens, the turn it takes on that session, and
the tool call it is asked to permit -- against a stand-in agent that speaks the protocol back.
"""

from __future__ import annotations

import os
import subprocess
import sys
from typing import TYPE_CHECKING

import pytest

from hmz import backends
from hmz.agents import AcpAgent, AcpAgentConfig, driver

if TYPE_CHECKING:
    from pathlib import Path

#: An agent that speaks ACP: it answers the handshake, opens a session, and takes a turn --
#: saying a thought, a tool call it asks permission for, and the answer it ends on. A prompt
#: of `boom` ends the turn on a refusal, which is a turn that did not land.
_AGENT = """
import json, sys

granted = []


def out(message):
    print(json.dumps(message), flush=True)


def answer(at, result):
    out({"jsonrpc": "2.0", "id": at, "result": result})


def update(session, said):
    out({"jsonrpc": "2.0", "method": "session/update",
         "params": {"sessionId": session, "update": said}})


for line in sys.stdin:
    if not line.strip():
        continue
    told = json.loads(line)
    method, at = told.get("method"), told.get("id")
    params = told.get("params") or {}
    if method == "initialize":
        answer(at, {"protocolVersion": 1, "agentCapabilities": {"loadSession": False},
                    "authMethods": []})
    elif method == "session/new":
        answer(at, {"sessionId": "ses-acp-1", "_cwd": params.get("cwd")})
    elif method == "session/prompt":
        said = params["prompt"][0]["text"]
        session = params["sessionId"]
        update(session, {"sessionUpdate": "agent_thought_chunk",
                         "content": {"type": "text", "text": "thinking about " + said}})
        if said != "boom":
            update(session, {"sessionUpdate": "tool_call", "toolCallId": "call_1",
                             "title": "echo " + said, "kind": "execute",
                             "status": "pending"})
            # The client is asked to permit it, and its answer decides what happens next.
            out({"jsonrpc": "2.0", "id": 9001, "method": "session/request_permission",
                 "params": {"sessionId": session, "toolCall": {"toolCallId": "call_1"},
                            "options": [
                                {"optionId": "no-thanks", "name": "no", "kind": "reject_once"},
                                {"optionId": "go-on", "name": "yes", "kind": "allow_once"}]}})
            while True:
                back = json.loads(sys.stdin.readline())
                if back.get("id") == 9001:
                    granted.append(back.get("result", {}).get("outcome", {}))
                    break
            # Only a grant carries the turn on: a client that picked the first option on
            # offer would have refused it, and the turn says so.
            if granted[-1].get("optionId") != "go-on":
                answer(at, {"stopReason": "refusal"})
                continue
            update(session, {"sessionUpdate": "agent_message_chunk",
                             "content": {"type": "text", "text": said}})
            answer(at, {"stopReason": "end_turn"})
        else:
            answer(at, {"stopReason": "refusal"})
    elif at is not None:
        out({"jsonrpc": "2.0", "id": at,
             "error": {"code": -32601, "message": "no"}})
"""


@pytest.fixture
def added(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    """Puts a stand-in ACP agent on PATH and writes it down as a CLI of your own."""
    monkeypatch.setenv("HUMANIZE_HOME", str(tmp_path / "home"))
    binaries = tmp_path / "bin"
    binaries.mkdir()
    fake = binaries / "my-agent"
    fake.write_text(f"#!{sys.executable}\n{_AGENT}")
    fake.chmod(0o755)
    monkeypatch.setenv("PATH", f"{binaries}{os.pathsep}{os.environ['PATH']}")
    backends.remember("my-agent", ["my-agent", "--acp"])
    return "my-agent"


def _agent(added: str) -> AcpAgent:
    """An agent configured to run the CLI that was added."""
    return AcpAgent(
        AcpAgentConfig(cli=added, model="as configured", effort="as configured")
    )


def test_an_added_cli_is_written_down_and_read_back(added: str) -> None:
    """It outlives the run: a CLI is installed on a machine, not in one directory."""
    assert backends.speaking()[added] == ("my-agent", "--acp")
    profile = backends.named(added)
    assert profile is not None
    assert profile.name == added
    assert profile in backends.profiles()


def test_an_added_cli_is_driven_over_the_protocol(added: str) -> None:
    """One class drives every CLI anybody adds, since the protocol is all that is known."""
    assert driver(added)[0] is AcpAgent
    assert _agent(added).backend == added


def test_a_name_a_backend_already_answers_to_is_refused(added: str) -> None:
    """Two backends answering to one name is a name nobody can resolve."""
    with pytest.raises(ValueError, match="already a backend"):
        backends.remember("claude", ["claude", "--acp"])


def test_an_added_cli_can_be_taken_away_again(added: str) -> None:
    assert backends.forget(added) is True
    assert backends.speaking() == {}
    assert backends.named(added) is None
    assert backends.forget(added) is False


def test_a_turn_opens_a_session_and_says_what_the_agent_said(added: str) -> None:
    """The handshake, the session, and the turn taken on it, in that order."""
    session = _agent(added).new()
    said = list(session.stream("hi"))

    kinds = [event.kind for event in said]
    assert kinds == ["reasoning", "tool", "text", "result"]
    assert said[1].text == "echo hi"
    assert said[-1].text == "hi"
    assert session.id == "ses-acp-1"


def test_the_session_is_held_open_across_turns(added: str) -> None:
    """ACP opens a conversation once and prompts it many times."""
    session = _agent(added).new()
    assert session("hi") == "hi"
    assert session("again") == "again"
    assert session.id == "ses-acp-1"


def test_a_tool_call_is_permitted_by_the_kind_of_the_option(added: str) -> None:
    """Never by its id: one agent calls it `proceed_once` and another `allow-once`.

    The stand-in offers the refusal first and carries the turn on only for the grant, so a
    client that picked whichever option came first would end this turn on a refusal.
    """
    assert _agent(added).new()("hi") == "hi"


def test_a_turn_that_ended_on_a_refusal_is_a_failed_turn(added: str) -> None:
    """A stop reason that is not an answer must not come back as one."""
    with pytest.raises(subprocess.CalledProcessError) as raised:
        _agent(added).new()("boom")
    assert "refusal" in str(raised.value.stderr)


def test_an_added_cli_cannot_be_steered_mid_turn(added: str) -> None:
    """Steering is an extension each agent spells its own way."""
    with pytest.raises(NotImplementedError):
        _agent(added).new().interject("hello?")


def test_an_agent_with_no_command_says_so(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A CLI that was never added is a name nothing knows how to start."""
    monkeypatch.setenv("HUMANIZE_HOME", str(tmp_path / "home"))
    with pytest.raises(ValueError, match="no command to start it with"):
        _ = AcpAgent(AcpAgentConfig(cli="nobody", model="m", effort="e")).command
