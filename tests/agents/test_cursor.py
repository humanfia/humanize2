"""Cursor Agent, driven against a stand-in that prints what the real one prints.

What is checked is the call each turn is made of -- the bracket its parameters go in, the rung
each permission comes to, the chat it resumes -- and the turn read back out of the NDJSON it
answers in, subagents included: Cursor is one of the backends that says on the same stream
when a turn starts an agent of its own and when that one comes back.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass
from typing import TYPE_CHECKING

import pytest

from hmz import backends, models
from hmz.agents import (
    SUBAGENTS,
    CursorAgent,
    CursorAgentConfig,
    Moment,
    Occasion,
    Verdict,
)
from hmz.agents.cursor import parameterized

if TYPE_CHECKING:
    from pathlib import Path

CURSOR = CursorAgentConfig(model="composer-2.5", effort="high")

#: A `cursor-agent --print`: it writes down how it was called, names the chat, says a thing or
#: two, and ends on the result. A prompt of `fleet` sends an agent of its own out and brings it
#: back; one of `boom` is the turn that failed, which Cursor says on the line it ends on.
_CURSOR_STUB = """
import json, pathlib, sys

argv = sys.argv[1:]
log = pathlib.Path(LOG)
with log.open("a") as stream:
    json.dump({"argv": argv}, stream)
    stream.write("\\n")

flags = dict(zip(argv, argv[1:]))
resumed = next((one for one in argv if one.startswith("--resume=")), "")
chat = resumed.partition("=")[2] or "chat-0001"
prompt = argv[-1]


def say(one):
    print(json.dumps(one), flush=True)


say({"type": "system", "subtype": "init", "session_id": chat, "cwd": ".",
     "model": flags.get("--model", ""), "permissionMode": "default"})
say({"type": "user", "message": {"role": "user",
                                 "content": [{"type": "text", "text": prompt}]},
     "session_id": chat})
say({"type": "tool_call", "subtype": "started", "call_id": "call-1",
     "tool_call": {"readToolCall": {"args": {"path": "src/x.py"}}},
     "session_id": chat})
if prompt == "fleet":
    say({"type": "tool_call", "subtype": "started", "call_id": "call-2",
         "tool_call": {"taskToolCall": {"args": {"description": "read the tests"}}},
         "session_id": chat})
    say({"type": "tool_call", "subtype": "completed", "call_id": "call-2",
         "tool_call": {"taskToolCall": {"args": {"description": "read the tests"},
                                        "result": {"success": {"content": "done"}}}},
         "session_id": chat})
say({"type": "assistant",
     "message": {"role": "assistant", "content": [{"type": "text", "text": prompt}]},
     "session_id": chat})
if prompt == "boom":
    say({"type": "result", "subtype": "error", "is_error": True,
         "result": "the model refused", "session_id": chat})
else:
    say({"type": "result", "subtype": "success", "is_error": False, "duration_ms": 12,
         "result": prompt, "session_id": chat})
"""

#: What `cursor-agent --list-models` prints, colour and all.
_LISTED = """
import sys

print("\\x1b[1mAvailable models\\x1b[0m")
print()
print("\\x1b[36mcomposer-2.5\\x1b[0m \\x1b[2m- Composer 2.5\\x1b[0m \\x1b[2m(default)\\x1b[0m")
print("gpt-5 - GPT-5")
print("gpt-5-high - GPT-5 (high)")
print("gpt-5-fast - GPT-5 (fast)")
print("gpt-5-low-fast - GPT-5 (low, fast)")
print("gpt-5-high-fast - GPT-5 (high, fast)")
print("claude-opus-4-8 (current)")
print("sonnet-4.5-thinking - Claude Sonnet 4.5 (thinking)")
print("grok-code-fast-1")
print("cheetah")
print("auto")
print()
print("Tip: use $ agent --model <id>")
"""


@dataclass(frozen=True)
class _Calls:
    """The stand-in on PATH, and how it was called."""

    log: Path

    def argv(self) -> list[list[str]]:
        return [json.loads(line)["argv"] for line in self.log.read_text().splitlines()]


def _install(binaries: Path, script: str, log: Path) -> None:
    """Puts a stand-in `cursor-agent` on PATH."""
    fake = binaries / "cursor-agent"
    fake.write_text(f"#!{sys.executable}\n{script.replace('LOG', repr(str(log)))}")
    fake.chmod(0o755)


@pytest.fixture
def cursor(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> _Calls:
    """A stand-in `cursor-agent` on PATH, printing what the real one prints."""
    log = tmp_path / "calls.jsonl"
    binaries = tmp_path / "bin"
    binaries.mkdir()
    _install(binaries, _CURSOR_STUB, log)
    monkeypatch.setenv("PATH", f"{binaries}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.chdir(tmp_path)
    return _Calls(log)


def test_the_cli_is_named_by_what_it_is_installed_as() -> None:
    """`agent` is a name anything could have taken; `cursor-agent` can only be this one."""
    profile = backends.named("cursor")
    assert profile is not None
    assert profile.name == "cursor"
    assert profile.runs() == "cursor-agent"
    # And both spellings of it name the same backend.
    assert backends.named("cursor-agent") is profile


def test_how_hard_it_thinks_is_written_into_the_model() -> None:
    """Cursor has no flag for a rung: its models are parameterized and take it in brackets."""
    assert parameterized("gpt-5", "high", fast=False) == "gpt-5[effort=high,fast=false]"
    assert parameterized("gpt-5", "low", fast=True) == "gpt-5[effort=low,fast=true]"
    # A model spelled with its own bracket meant what it said, and a second would be refused.
    assert (
        parameterized("claude-opus-4-8[context=1m]", "high", fast=True)
        == "claude-opus-4-8[context=1m]"
    )


def test_a_turn_is_one_run_of_its_command_line(cursor: _Calls) -> None:
    """The model with its bracket, the workspace, and the prompt after a `--`."""
    session = CursorAgent(CURSOR).new()

    assert session("hello") == "hello"

    (argv,) = cursor.argv()
    assert argv[argv.index("--model") + 1] == "composer-2.5[effort=high,fast=false]"
    assert argv[:4] == ["--print", "--output-format", "stream-json", "--model"]
    assert argv[-2:] == ["--", "hello"]
    assert "--trust" in argv
    assert session.id == "chat-0001"


def test_the_second_turn_resumes_the_chat_the_first_one_opened(cursor: _Calls) -> None:
    """Written onto the flag: its own argument is optional, so a separate one is the prompt."""
    session = CursorAgent(CURSOR).new()
    session("hello")

    session("again")

    _first, second = cursor.argv()
    assert "--resume=chat-0001" in second


#: What each rung comes to on Cursor's own command line.
_RUNGS = (
    ("read-only", ["--mode", "plan"]),
    ("workspace-write", ["--force", "--sandbox", "enabled"]),
    ("auto", ["--auto-review"]),
    ("bypass", ["--force", "--sandbox", "disabled"]),
)


def test_a_rung_is_the_mode_or_the_sandbox_cursor_has_for_it(cursor: _Calls) -> None:
    """Each of the four does something of its own rather than reading as the same turn."""
    from dataclasses import replace

    for rung, _expected in _RUNGS:
        CursorAgent(replace(CURSOR, permission=rung)).new()("hello")

    for argv, (_rung, expected) in zip(cursor.argv(), _RUNGS, strict=True):
        for one in expected:
            assert one in argv


def test_asking_for_the_faster_service_is_the_same_bracket(cursor: _Calls) -> None:
    """Which is why this backend can express a tier at all."""
    from dataclasses import replace

    CursorAgent(replace(CURSOR, service_tier="fast")).new()("hello")

    (argv,) = cursor.argv()
    assert argv[argv.index("--model") + 1] == "composer-2.5[effort=high,fast=true]"


def test_a_turn_says_what_it_did_as_it_does_it(cursor: _Calls) -> None:
    """A tool call once, as it starts: a row per status is a transcript of statuses."""
    session = CursorAgent(CURSOR).new()

    said = list(session.stream("hello"))

    assert [event.kind for event in said] == ["tool", "text", "result"]
    assert said[0].text == "read src/x.py"
    assert said[-1].text == "hello"


def test_an_agent_of_its_own_is_said_as_one_rather_than_as_a_tool(
    cursor: _Calls,
) -> None:
    """A fleet under a turn is agents, and whatever is watching draws them as agents."""
    session = CursorAgent(CURSOR).new()

    said = list(session.stream("fleet"))

    fleet = [event for event in said if event.kind.startswith("subagent")]
    assert [event.kind for event in fleet] == ["subagent", "subagent-ends"]
    # One agent rather than two lines: the id the call was made under is what pairs them.
    assert {event.whose for event in fleet} == {"call-2"}
    assert fleet[0].text == "task read the tests"


def test_the_moments_about_a_fleet_are_fired_where_one_runs(cursor: _Calls) -> None:
    """Which is what makes a hook a thing a flow can hang on the agents under its agent."""
    agent = CursorAgent(CURSOR)
    seen: list[Occasion] = []

    def note(occasion: Occasion) -> Verdict | None:
        seen.append(occasion)
        return None

    assert CursorAgent.moments >= SUBAGENTS
    agent.hooks.on(Moment.SUBAGENT_START, note)
    agent.hooks.on(Moment.SUBAGENT_STOP, note)

    agent.new()("fleet")

    assert [one.moment for one in seen] == [
        Moment.SUBAGENT_START,
        Moment.SUBAGENT_STOP,
    ]
    assert seen[0].tool == "task"
    assert seen[0].about == "read the tests"
    assert {one.under for one in seen} == {"call-2"}


def test_a_turn_that_failed_says_so_rather_than_answering_with_it(
    cursor: _Calls,
) -> None:
    """A loop fed that as an answer would be running on it as the work of the turn."""
    session = CursorAgent(CURSOR).new()

    with pytest.raises(subprocess.CalledProcessError) as raised:
        session("boom")

    assert "the model refused" in str(raised.value)


@pytest.fixture
def listing(asking: None, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A stand-in `cursor-agent` with a catalogue on it, and a home to keep the answer in."""
    binaries = tmp_path / "bin"
    binaries.mkdir()
    _install(binaries, _LISTED, tmp_path / "listed.jsonl")
    monkeypatch.setenv("PATH", f"{binaries}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("HUMANIZE_HOME", str(tmp_path / "home"))


def test_what_it_runs_is_read_off_its_own_listing(listing: None) -> None:
    """The heading above the list and the tip below it are sentences, not models."""
    found = models.ask("cursor")

    assert [one.name for one in found] == [
        "composer-2.5",
        "gpt-5",
        "gpt-5-high",
        "gpt-5-fast",
        "gpt-5-low-fast",
        "gpt-5-high-fast",
        "claude-opus-4-8",
        "sonnet-4.5-thinking",
        "grok-code-fast-1",
        "cheetah",
        "auto",
    ]


#: Cursor's whole ladder, which is what a model is offered at when its own name says nothing
#: about how hard it thinks: the rung is a parameter of the model rather than a property of it.
_LADDER = ("high", "medium", "low")

#: What each model in that listing is offered at, and why it is that rather than the other.
_OFFERED = {
    "composer-2.5": _LADDER,
    "gpt-5": _LADDER,
    "gpt-5-high": ("high",),
    # `fast` is the service a turn runs on and not a rung, so the first of these two is still
    # the whole ladder and the second is `low` with that service written behind it.
    "gpt-5-fast": _LADDER,
    "gpt-5-low-fast": ("low",),
    "gpt-5-high-fast": ("high",),
    "claude-opus-4-8": _LADDER,
    # `thinking` is what the model is, `1` is which one it is, and `auto` is Cursor choosing:
    # a name is only pinned by a word that is one of Cursor's own three rungs.
    "sonnet-4.5-thinking": _LADDER,
    "grok-code-fast-1": _LADDER,
    "cheetah": _LADDER,
    "auto": _LADDER,
}


def test_a_model_is_offered_at_the_rung_its_own_name_carries(listing: None) -> None:
    """A rung is a word of the name wherever it falls in it: `gpt-5-low-fast` runs at `low`."""
    found = models.ask("cursor")

    assert {one.name: one.efforts for one in found} == _OFFERED


def test_web_search_cannot_be_switched_off_and_is_refused_rather_than_ignored() -> None:
    """Its own command line takes no tool away, and a setting that lies is worse than none."""
    from dataclasses import replace

    with pytest.raises(ValueError, match="no way of being told"):
        CursorAgent(replace(CURSOR, web_search=False))
