"""What a session and an agent have spent, and how fast they are spending it.

A backend says what a request cost as the request lands, not once the turn is over -- a turn is
minutes long, and a rate that only moved at the end of one would stand still for all of them.
What is checked here is that each backend's own counting arrives as the same kinds, that
`input` and `output` are among them whatever else that CLI counts, and that a rate is tokens a
second over seconds on the clock.
"""

from __future__ import annotations

import json
import os
import sys
from typing import TYPE_CHECKING

import pytest

from humanize.agents import (
    WINDOW,
    ClaudeCodeAgent,
    ClaudeCodeAgentConfig,
    Meter,
    OpencodeAgent,
    OpencodeAgentConfig,
    PiAgent,
    PiAgentConfig,
    Usage,
)

if TYPE_CHECKING:
    from pathlib import Path

PI = PiAgentConfig(model="m", effort="high")
OPENCODE = OpencodeAgentConfig(model="m", effort="high")

#: A `pi --mode rpc` that answers each prompt with two requests to the model, each of which
#: says what it cost -- which is what makes a rate readable while the turn is still running.
_PI = """
import json, sys

flags = dict(zip(sys.argv, sys.argv[1:]))
print(json.dumps({"type": "session", "id": flags["--session-id"]}), flush=True)
for line in sys.stdin:
    told = json.loads(line)
    if told["type"] != "prompt":
        print(json.dumps({"type": "response", "command": told["type"],
                          "success": True}), flush=True)
        continue
    for half in ("thinking", told["message"]):
        print(json.dumps({"type": "message_end", "message": {"role": "assistant",
              "content": [{"type": "text", "text": half}],
              "usage": {"input": 10, "output": 5, "cacheRead": 2,
                        "cacheWrite": 1}}}), flush=True)
    print(json.dumps({"type": "agent_settled"}), flush=True)
"""

#: An `opencode run` whose turn is two steps, each saying what it came to.
_OPENCODE = """
import json, sys

said = sys.stdin.read()
print(json.dumps({"type": "text", "sessionID": "ses_one",
                  "part": {"id": "prt_1", "type": "text", "text": said}}), flush=True)
for at in (2, 3):
    print(json.dumps({"type": "step_finish", "sessionID": "ses_one",
                      "part": {"id": "prt_%d" % at, "type": "step-finish",
                               "tokens": {"input": 5, "output": 2, "reasoning": 1,
                                          "cache": {"read": 4, "write": 0}}}}), flush=True)
"""


#: A `claude --print` that says the same message twice -- as it really does, once for the
#: thinking in it and once for the words -- and then states a turn total larger than either.
_CLAUDE = """
import json, sys

flags = dict(zip(sys.argv, sys.argv[1:]))
print(json.dumps({"type": "system",
                  "session_id": flags.get("--session-id") or flags["--resume"]}), flush=True)
USED = {"input_tokens": 10, "output_tokens": 4,
        "cache_read_input_tokens": 100, "cache_creation_input_tokens": 20}
TURNS = 0
for line in sys.stdin:
    said = json.loads(line)["message"]["content"][0]["text"]
    TURNS += 1
    for part in ("thinking", "text"):
        print(json.dumps({"type": "assistant", "message": {
            "id": "msg_%d" % TURNS, "usage": USED,
            "content": [{"type": part, part: said}]}}), flush=True)
    # The session's running total, which is what Claude states at the end of every turn: it
    # counts more input than the message did, and it counts every turn so far.
    print(json.dumps({"type": "result", "result": said, "modelUsage": {"m": {
        "inputTokens": 500 * TURNS, "outputTokens": 4 * TURNS,
        "cacheReadInputTokens": 100 * TURNS,
        "cacheCreationInputTokens": 20 * TURNS}}}), flush=True)
"""


def _install(
    named: str, script: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Puts one stand-in CLI on PATH."""
    binaries = tmp_path / "bin"
    binaries.mkdir(exist_ok=True)
    fake = binaries / named
    fake.write_text(f"#!{sys.executable}\n{script}")
    fake.chmod(0o755)
    monkeypatch.setenv("PATH", f"{binaries}{os.pathsep}{os.environ['PATH']}")


@pytest.fixture
def pi(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _install("pi", _PI, tmp_path, monkeypatch)


@pytest.fixture
def opencode(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _install("opencode", _OPENCODE, tmp_path, monkeypatch)


def test_a_reckoning_is_a_mapping_of_the_kinds_it_holds() -> None:
    """A kind that is not in one is one the backend does not count, not one it counts as 0."""
    usage = Usage(input=10, output=4, cache_read=2)

    assert usage.input == 10
    assert usage.output == 4
    assert usage["cache_read"] == 2
    assert usage.total == 16
    assert dict(usage) == {"input": 10, "output": 4, "cache_read": 2}
    assert "cache_write" not in usage
    assert usage.get("cache_write", 0) == 0
    with pytest.raises(KeyError):
        _ = usage["cache_write"]


def test_two_reckonings_add_kind_by_kind() -> None:
    assert dict(Usage(input=1, output=2) + Usage(output=3, reasoning=4)) == {
        "input": 1,
        "output": 5,
        "reasoning": 4,
    }


def test_a_reckoning_over_seconds_is_a_rate() -> None:
    assert dict(Usage(input=10, output=4) / 2) == {"input": 5.0, "output": 2.0}
    # Nothing has happened over no time, which is a rate of nothing rather than an error.
    assert dict(Usage(input=10) / 0) == {"input": 0.0}


def test_a_meter_says_what_it_has_seen_and_how_fast_it_saw_it() -> None:
    """Seconds on the clock: the gaps a flow leaves are time the tokens were spent over."""
    meter = Meter()
    began = meter._began

    meter.spend(Usage(input=100, output=20), now=began + 1)
    meter.spend(Usage(input=100, output=20), now=began + 2)

    assert dict(meter.spent()) == {"input": 200, "output": 40}
    # Ten seconds in, over a window of ten: 240 tokens over ten seconds.
    rate = meter.rate(over=10, now=began + 10)
    assert rate.output == pytest.approx(4.0)
    assert rate.input == pytest.approx(20.0)


def test_a_run_younger_than_the_window_is_measured_over_the_run() -> None:
    """Or a rate read a second in would be a fifth of what that second came to."""
    meter = Meter()
    began = meter._began

    meter.spend(Usage(output=60), now=began + 0.5)

    assert meter.rate(over=WINDOW, now=began + 1).output == pytest.approx(60.0)


def test_what_falls_out_of_the_window_stops_counting() -> None:
    """A flow that has gone quiet reads as quiet rather than as what it once averaged."""
    meter = Meter()
    began = meter._began

    meter.spend(Usage(output=100), now=began + 1)

    assert meter.rate(over=10, now=began + 5).output == pytest.approx(20.0)
    assert meter.rate(over=10, now=began + 60).output == pytest.approx(0.0)
    assert dict(meter.spent()) == {
        "input": 0.0,
        "output": 100,
    }  # but it was still spent


def test_a_meter_always_has_the_two_kinds_every_backend_counts() -> None:
    meter = Meter()

    assert dict(meter.spent()) == {"input": 0.0, "output": 0.0}
    assert dict(meter.rate()) == {"input": 0.0, "output": 0.0}


def test_a_session_says_what_it_has_spent_by_kind(pi: None) -> None:
    """Two requests to the model in one turn, and the session has both of them."""
    session = PiAgent(PI).new()
    assert session("hi") == "hi"

    spent = session.spent()
    assert spent.input == 20
    assert spent.output == 10
    assert spent["cache_read"] == 4
    assert spent["cache_write"] == 2
    assert spent.total == 36


def test_what_the_turn_answers_with_carries_the_same_reckoning(pi: None) -> None:
    """The `result` says what the turn cost, per model and by kind, and they agree."""
    session = PiAgent(PI).new()
    (answered,) = [event for event in session.stream("hi") if event.kind == "result"]

    assert answered.spent.total == sum(answered.tokens.values())
    assert answered.spent.output == 10


def test_an_agent_has_spent_what_every_session_of_it_spent(pi: None) -> None:
    """A Ralph loop drops a session a turn, and what it spent is still what it spent."""
    agent = PiAgent(PI)
    agent("one")  # a session of its own, kept by nobody
    agent("two")

    assert agent.spent().total == 72
    assert not agent.sessions  # both were let go of, and the spending was not


def test_a_backend_counts_what_it_counts_and_says_so(opencode: None) -> None:
    """The kinds differ from CLI to CLI, which is why they are a mapping rather than a shape."""
    session = OpencodeAgent(OPENCODE).new()
    session("hi")

    spent = session.spent()
    # opencode counts its reasoning beside the output rather than inside it, so it is a kind.
    assert dict(spent) == {
        "input": 10,
        "output": 4,
        "reasoning": 2,
        "cache_read": 8,
    }
    assert spent.total == 24


def test_a_rate_is_read_off_the_session_or_the_agent(opencode: None) -> None:
    agent = OpencodeAgent(OPENCODE)
    session = agent.new()
    session("hi")

    # Everything spent is inside any window worth asking about, and the run is younger than
    # the window, so both are the spending over the seconds the run has lasted.
    assert session.rate(over=WINDOW).output > 0
    # The agent's clock started a moment before the session's, so the two divide the same
    # spending by all but the same seconds.
    assert agent.rate(over=WINDOW).output == pytest.approx(
        session.rate(over=WINDOW).output, rel=0.05
    )
    assert set(session.rate()) >= {"input", "output"}


def test_a_session_that_has_run_nothing_has_spent_nothing() -> None:
    session = OpencodeAgent(OPENCODE).new()

    assert session.spent().total == 0
    assert session.rate().total == 0
    assert json.dumps(dict(session.spent()))  # and it is a plain mapping, so it says so


@pytest.mark.agent
@pytest.mark.timeout(600)
def test_claude_says_what_it_spent_by_kind_for_real() -> None:
    """The kinds are read off two spellings of the same usage, so a real turn settles both."""
    from humanize.agents import ClaudeCodeAgent, ClaudeCodeAgentConfig

    session = ClaudeCodeAgent(
        ClaudeCodeAgentConfig(model="claude-haiku-4-5-20251001", effort="low")
    ).new()
    (answered,) = [
        event
        for event in session.stream("Reply with exactly: OK")
        if event.kind == "result"
    ]

    assert "OK" in answered.text
    # What the turn states and what its messages said add up to the same spending.
    assert answered.spent.total == sum(answered.tokens.values())
    assert session.spent().total == answered.spent.total
    assert session.spent().output > 0
    assert session.rate(over=60).output > 0


@pytest.mark.agent
@pytest.mark.timeout(600)
def test_codex_says_what_it_spent_by_kind_for_real() -> None:
    from humanize.agents import CodexAgent, CodexAgentConfig

    session = CodexAgent(CodexAgentConfig(model="gpt-5.5", effort="low")).new()
    (answered,) = [
        event
        for event in session.stream("Reply with exactly: OK")
        if event.kind == "result"
    ]

    assert "OK" in answered.text
    assert answered.spent.total == sum(answered.tokens.values())
    assert session.spent().input > 0
    assert session.spent().output > 0


@pytest.fixture
def claude(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _install("claude", _CLAUDE, tmp_path, monkeypatch)


def test_a_message_said_twice_is_one_request_counted_once(claude: None) -> None:
    """Claude states the whole of what a request cost on every telling of its message.

    So what one of them adds is the rise on the message it names, and what the turn states at
    the end adds only the rest -- 500 in where the message said 10 is 490 more, not another
    124 of everything.
    """
    session = ClaudeCodeAgent(ClaudeCodeAgentConfig(model="m", effort="high")).new()
    (answered,) = [event for event in session.stream("hi") if event.kind == "result"]

    assert dict(answered.spent) == {
        "input": 500,
        "output": 4,
        "cache_read": 100,
        "cache_write": 20,
    }
    assert dict(session.spent()) == dict(answered.spent)
    assert session.spent().total == sum(answered.tokens.values())


def test_the_next_turn_is_counted_from_where_the_last_one_left_off(
    claude: None,
) -> None:
    """Claude counts the session, so a turn is the rise across it and never the whole."""
    session = ClaudeCodeAgent(ClaudeCodeAgentConfig(model="m", effort="high")).new()
    session("one")
    (answered,) = [event for event in session.stream("two") if event.kind == "result"]

    assert answered.spent.total == 624  # the rise across the second turn, not the whole
    assert session.spent().total == 1248  # which is what the two of them come to
