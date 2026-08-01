"""Moving how hard an agent thinks while it is already running.

A config is frozen, because a session resumes under the settings it opened with. The effort is
the one of them a flow may move as it goes -- a loop watching what it is costing turns the
whole agent down, and one nursing a conversation through a hard patch turns that session up --
so it is asked of the agent and the session rather than read off the config, and each backend
carries it to the CLI the way that CLI takes it.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import pytest

from hmz.agents import (
    ClaudeCodeAgent,
    ClaudeCodeAgentConfig,
    OpencodeAgent,
    OpencodeAgentConfig,
    PiAgent,
    PiAgentConfig,
)

if TYPE_CHECKING:
    from pathlib import Path

CLAUDE = ClaudeCodeAgentConfig(model="m", effort="high")
PI = PiAgentConfig(model="m", effort="high")
OPENCODE = OpencodeAgentConfig(model="m", effort="high")

#: A `claude` that writes down each launch and answers each thing it is told.
_CLAUDE = """
import json, pathlib, sys

log = pathlib.Path(LOG)


def note(entry):
    with log.open("a") as stream:
        json.dump(entry, stream)
        stream.write("\\n")


note({"argv": sys.argv[1:], "said": None})
flags = dict(zip(sys.argv, sys.argv[1:]))
print(json.dumps({"type": "system",
                  "session_id": flags.get("--session-id") or flags["--resume"]}), flush=True)
for line in sys.stdin:
    said = json.loads(line)["message"]["content"][0]["text"]
    note({"argv": None, "said": said})
    print(json.dumps({"type": "result", "result": said}), flush=True)
"""

#: A `pi --mode rpc` that writes down its launch and every command written to it.
_PI = """
import json, pathlib, sys

log = pathlib.Path(LOG)


def note(entry):
    with log.open("a") as stream:
        json.dump(entry, stream)
        stream.write("\\n")


note({"argv": sys.argv[1:], "said": None})
flags = dict(zip(sys.argv, sys.argv[1:]))
print(json.dumps({"type": "session", "id": flags["--session-id"]}), flush=True)
for line in sys.stdin:
    told = json.loads(line)
    note({"argv": None, "said": json.dumps(told)})
    if told["type"] != "prompt":
        print(json.dumps({"type": "response", "command": told["type"],
                          "success": True}), flush=True)
        continue
    print(json.dumps({"type": "message_end", "message": {"role": "assistant",
          "content": [{"type": "text", "text": told["message"]}],
          "usage": {"input": 1, "output": 1}}}), flush=True)
    print(json.dumps({"type": "agent_settled"}), flush=True)
"""

#: An `opencode run` that writes down the run it was and answers with what it was fed.
_OPENCODE = """
import json, pathlib, sys

said = sys.stdin.read()
with pathlib.Path(LOG).open("a") as stream:
    json.dump({"argv": sys.argv[1:], "said": said}, stream)
    stream.write("\\n")

print(json.dumps({"type": "text", "sessionID": "ses_one",
                  "part": {"id": "prt_1", "type": "text", "text": said}}), flush=True)
print(json.dumps({"type": "step_finish", "sessionID": "ses_one",
                  "part": {"id": "prt_2", "type": "step-finish",
                           "tokens": {"input": 1, "output": 1, "reasoning": 0,
                                      "cache": {"read": 0, "write": 0}}}}), flush=True)
"""


@dataclass(frozen=True)
class _Noted:
    """What the stand-in was launched as, and what was written to it."""

    log: Path

    def rows(self) -> list[dict[str, Any]]:
        return [json.loads(line) for line in self.log.read_text().splitlines()]

    def launches(self) -> list[list[str]]:
        return [row["argv"] for row in self.rows() if row["argv"] is not None]

    def said(self) -> list[str]:
        return [row["said"] for row in self.rows() if row["said"] is not None]


def _install(
    named: str, script: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> _Noted:
    """Puts one stand-in CLI on PATH and says where it writes down what it was asked."""
    log = tmp_path / f"{named}.jsonl"
    binaries = tmp_path / "bin"
    binaries.mkdir(exist_ok=True)
    fake = binaries / named
    fake.write_text(f"#!{sys.executable}\n{script.replace('LOG', repr(str(log)))}")
    fake.chmod(0o755)
    monkeypatch.setenv("PATH", f"{binaries}{os.pathsep}{os.environ['PATH']}")
    return _Noted(log)


@pytest.fixture
def claude(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> _Noted:
    return _install("claude", _CLAUDE, tmp_path, monkeypatch)


@pytest.fixture
def pi(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> _Noted:
    return _install("pi", _PI, tmp_path, monkeypatch)


@pytest.fixture
def opencode(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> _Noted:
    return _install("opencode", _OPENCODE, tmp_path, monkeypatch)


def test_an_agent_runs_at_what_it_was_configured_with_until_it_is_told_otherwise() -> (
    None
):
    agent = ClaudeCodeAgent(CLAUDE)
    session = agent.new()

    assert agent.effort == "high"
    assert session.effort == "high"
    assert agent.config.effort == "high"  # which is not moved by moving the other


def test_moving_an_agents_effort_moves_every_session_of_it() -> None:
    agent = ClaudeCodeAgent(CLAUDE)
    first, second = agent.new(), agent.new()

    agent.effort = "low"

    assert [first.effort, second.effort] == ["low", "low"]
    assert agent.config.effort == "high"  # the config is what it was configured with


def test_a_session_told_something_of_its_own_keeps_it() -> None:
    """A flow nursing one conversation through a hard patch turns that session up."""
    agent = ClaudeCodeAgent(CLAUDE)
    nursed, ordinary = agent.new(), agent.new()

    nursed.effort = "max"
    agent.effort = "low"

    assert nursed.effort == "max"
    assert ordinary.effort == "low"

    nursed.effort = ""  # and giving it back leaves it on the agent's again
    assert nursed.effort == "low"


def test_claude_resumes_the_conversation_in_a_process_that_thinks_at_the_new_one(
    claude: _Noted,
) -> None:
    """`--effort` is an argument of the process, so moving it restarts one.

    The conversation is not restarted with it: the new process resumes the session, which is
    what an anchored session does between every pair of turns anyway.
    """
    agent = ClaudeCodeAgent(CLAUDE)
    session = agent.new()
    assert session("one") == "one"
    assert session("two") == "two"  # nothing moved, so nothing restarted

    agent.effort = "low"
    assert session("three") == "three"
    assert session("four") == "four"  # and it stays there

    opened, again = claude.launches()
    assert opened[opened.index("--effort") + 1] == "high"
    assert again[again.index("--effort") + 1] == "low"
    assert again[again.index("--resume") + 1] == session.id
    assert claude.said() == ["one", "two", "three", "four"]


def test_pi_is_told_the_new_effort_rather_than_started_again(pi: _Noted) -> None:
    """It takes the thinking level on the session it is already holding, so it is told."""
    agent = PiAgent(PI)
    session = agent.new()
    assert session("one") == "one"

    session.effort = "low"
    assert session("two") == "two"

    (launch,) = pi.launches()  # one process throughout
    assert launch[launch.index("--thinking") + 1] == "high"
    told = [json.loads(said) for said in pi.said()]
    assert [one["type"] for one in told] == ["prompt", "set_thinking_level", "prompt"]
    assert told[1]["level"] == "low"


def test_pi_is_told_once_rather_than_before_every_turn(pi: _Noted) -> None:
    agent = PiAgent(PI)
    session = agent.new()
    session("one")
    session.effort = "low"
    session("two")
    session("three")

    told = [json.loads(said)["type"] for said in pi.said()]
    assert told == ["prompt", "set_thinking_level", "prompt", "prompt"]


def test_an_effort_moved_before_the_first_turn_is_what_the_process_starts_at(
    pi: _Noted,
) -> None:
    """There is nothing up to be told, so it goes on the command line like any other."""
    agent = PiAgent(PI)
    agent.effort = "low"
    agent("one")

    (launch,) = pi.launches()
    assert launch[launch.index("--thinking") + 1] == "low"
    assert [json.loads(said)["type"] for said in pi.said()] == ["prompt"]


def test_opencode_runs_the_next_turn_at_the_new_variant(opencode: _Noted) -> None:
    """A run per turn, so the next run is where a new effort shows up."""
    agent = OpencodeAgent(OPENCODE)
    session = agent.new()
    session("one")
    agent.effort = "minimal"
    session("two")

    first, second = opencode.launches()
    assert first[first.index("--variant") + 1] == "high"
    assert second[second.index("--variant") + 1] == "minimal"


def test_what_a_flow_moves_is_read_back_off_the_agent_and_the_session() -> None:
    """Which is the whole of the interface: a property, read and written."""
    agent = OpencodeAgent(OPENCODE)
    session = agent.new()

    agent.effort = "low"
    assert (agent.effort, session.effort) == ("low", "low")

    agent.effort = ""
    assert (agent.effort, session.effort) == ("high", "high")
