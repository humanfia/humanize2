"""A turn given a budget, and cut off when it is spent.

A turn is minutes long and a flow does not get to see how it is going until it is over, so
without this a turn that went wrong went wrong for as long as it took: stopping an agent
prevents its *next* turn, and a session that is one command per turn has nothing listening.
What is checked here is that a cap on what one turn writes and a cap on how long it runs are
both read off the live meter while the turn is still running, that a spent budget ends the
turn where its `when` says and leaves what its `then` says, that every turn starts with the
whole of the budget again, and that the process a cut-off turn was running in is actually
gone -- across both of the lifetimes a CLI is driven in.
"""

from __future__ import annotations

import contextlib
import os
import subprocess
import sys
import threading
import time
from typing import TYPE_CHECKING

import psutil
import pytest

from hmz.agents import (
    Budget,
    OpencodeAgent,
    OpencodeAgentConfig,
    PiAgent,
    PiAgentConfig,
    Stopped,
    Unrecoverable,
    base,
)

if TYPE_CHECKING:
    from pathlib import Path

PI = PiAgentConfig(model="m", effort="high")
OPENCODE = OpencodeAgentConfig(model="m", effort="high")

#: How many pieces a stand-in CLI answers a prompt in, and how long it waits between them.
#: Twelve at a sixth of a second is a turn that takes two seconds if nobody cuts it off and
#: a third of a second if a budget of six output tokens does.
PIECES = 12
PAUSE = 0.15

#: A `pi --mode rpc` that answers a prompt with a dozen requests to the model, saying what
#: each of them cost as it lands -- which is what a budget read off the live meter is made
#: of. It sleeps between them, so a turn that runs to the end takes visibly longer than one
#: that is cut off part way.
_PI = f"""
import json, sys, time

flags = dict(zip(sys.argv, sys.argv[1:]))
print(json.dumps({{"type": "session", "id": flags["--session-id"]}}), flush=True)
for line in sys.stdin:
    told = json.loads(line)
    if told["type"] != "prompt":
        print(json.dumps({{"type": "response", "command": told["type"],
                          "success": True}}), flush=True)
        continue
    for at in range(1, {PIECES} + 1):
        print(json.dumps({{"type": "message_update", "assistantMessageEvent":
                          {{"type": "text_end", "content": "part %d" % at}}}}), flush=True)
        print(json.dumps({{"type": "message_end", "message": {{"role": "assistant",
              "content": [{{"type": "text", "text": "part %d" % at}}],
              "usage": {{"input": 1, "output": 4}}}}}}), flush=True)
        time.sleep({PAUSE})
    print(json.dumps({{"type": "agent_settled"}}), flush=True)
"""

#: An `opencode run` whose turn is a dozen steps, each saying what it came to -- the same
#: turn as pi's, run as one command that ends with it rather than as a process spoken to.
_OPENCODE = f"""
import json, sys, time

said = sys.stdin.read()
for at in range(1, {PIECES} + 1):
    print(json.dumps({{"type": "text", "sessionID": "ses_one",
                      "part": {{"id": "prt_%d" % at, "type": "text",
                               "text": "part %d" % at}}}}), flush=True)
    print(json.dumps({{"type": "step_finish", "sessionID": "ses_one",
                      "part": {{"id": "stp_%d" % at, "type": "step-finish",
                               "tokens": {{"input": 1, "output": 4, "reasoning": 0,
                                          "cache": {{"read": 0, "write": 0}}}}}}}}),
          flush=True)
    time.sleep({PAUSE})
"""


#: The same command turn, saying nothing about what it cost -- which three of these backends
#: really do: they state a whole turn's spending once the turn is over, so a budget waiting
#: for a response to land has nothing to wait for.
_SILENT = f"""
import json, sys, time

said = sys.stdin.read()
for at in range(1, {PIECES} + 1):
    print(json.dumps({{"type": "text", "sessionID": "ses_one",
                      "part": {{"id": "prt_%d" % at, "type": "text",
                               "text": "part %d" % at}}}}), flush=True)
    time.sleep({PAUSE})
"""


def _install(
    named: str, script: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Path:
    """Puts one stand-in CLI on PATH, and says where it went."""
    binaries = tmp_path / "bin"
    binaries.mkdir(exist_ok=True)
    fake = binaries / named
    fake.write_text(f"#!{sys.executable}\n{script}")
    fake.chmod(0o755)
    monkeypatch.setenv("PATH", f"{binaries}{os.pathsep}{os.environ['PATH']}")
    return fake


@pytest.fixture
def pi(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    return _install("pi", _PI, tmp_path, monkeypatch)


@pytest.fixture
def opencode(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    return _install("opencode", _OPENCODE, tmp_path, monkeypatch)


@pytest.fixture
def silent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    return _install("opencode", _SILENT, tmp_path, monkeypatch)


def _left(fake: Path) -> list[psutil.Process]:
    """Every run of this stand-in CLI still going, which after a cut-off should be none.

    Named by the file it was started from rather than by taking whatever this process has
    below it: the suite is one process, and another module's leftovers are not this one's.
    """
    left: list[psutil.Process] = []
    for one in psutil.Process().children(recursive=True):
        with contextlib.suppress(psutil.Error):
            if one.status() != psutil.STATUS_ZOMBIE and str(fake) in " ".join(
                one.cmdline()
            ):
                left.append(one)
    return left


def test_a_budget_says_which_cap_a_turn_has_run_through() -> None:
    """One place a reading is compared with a cap, so a new dimension is a line there."""
    budget = Budget(output=500, seconds=90)

    assert budget.over(output=499, seconds=89) == ""
    assert budget.over(output=500, seconds=1) == "500 output tokens"
    assert budget.over(output=1, seconds=90) == "90s"


def test_a_budget_with_nothing_named_in_it_caps_nothing() -> None:
    """Which is how one conversation opts out of the budget its agent carries."""
    assert not Budget().bounded
    assert Budget().over(output=1e9, seconds=1e9) == ""
    assert Budget(output=1).bounded
    assert Budget(seconds=1).bounded


def test_a_cut_off_nothing_answers_to_is_refused_where_it_is_written() -> None:
    """Minutes into the turn it was meant to hold is the wrong place to find out."""
    with pytest.raises(ValueError, match="when"):
        Budget(when="sometime")


def test_an_outcome_nothing_answers_to_is_refused_where_it_is_written() -> None:
    with pytest.raises(ValueError, match="then"):
        Budget(then="explode")


def test_a_budget_cannot_be_less_than_nothing() -> None:
    with pytest.raises(ValueError, match="less than nothing"):
        Budget(output=-1)


def test_a_turn_that_writes_its_budget_is_cut_off_where_it_stands(pi: Path) -> None:
    """Six tokens of a turn that would have written forty-eight, and the process is gone."""
    session = PiAgent(PI).new()
    session.budget = Budget(output=6, when="immediately")

    began = time.monotonic()
    said = session("write me something long")

    assert time.monotonic() - began < PIECES * PAUSE
    assert "part 1" in said
    assert f"part {PIECES}" not in said
    assert not _left(pi)


def test_a_turn_cut_off_still_ends_on_one_answer(pi: Path) -> None:
    """`stream` ends on exactly one `result`, or whatever is reading it waits forever."""
    session = PiAgent(PI).new()
    session.budget = Budget(output=6, when="immediately")

    kinds = [event.kind for event in session.stream("write me something long")]

    assert kinds.count("result") == 1
    assert "failed" not in kinds


def test_a_turn_cut_off_still_opens_the_conversation(pi: Path) -> None:
    """A cap is not a kill: the round is short, and the next one carries the same session on.

    What the agent did before it was cut off is on disk and the conversation is open to the
    next turn, so a short turn that left the session unopened would have the round after it
    start from nothing and lose the work the short one did.
    """
    agent = PiAgent(PI)
    session = agent.new()
    session.budget = Budget(output=6, when="immediately")

    session("write me something long")

    assert session.named is not None
    assert session.id == session.named
    assert agent.opened == [session.id]


def test_a_turn_its_budget_failed_is_not_opened_by_the_cut_off(pi: Path) -> None:
    """`fail` is the flow saying it cannot use a short round, and a failed turn opens nothing."""
    agent = PiAgent(PI)
    session = agent.new()
    session.budget = Budget(output=6, when="immediately", then="fail")

    with pytest.raises(Unrecoverable):
        session("write me something long")

    assert agent.opened == []


def test_a_turn_that_runs_out_of_clock_is_cut_off(pi: Path) -> None:
    """Seconds on the clock: a turn wedged on a tool is a turn taking that long."""
    session = PiAgent(PI).new()
    session.budget = Budget(seconds=PIECES * PAUSE / 4, when="immediately")

    began = time.monotonic()
    said = session("write me something long")

    assert time.monotonic() - began < PIECES * PAUSE
    assert "part 1" in said
    assert f"part {PIECES}" not in said


def test_a_budget_spent_next_response_keeps_the_answer_that_crossed_it(
    pi: Path,
) -> None:
    """The response in flight lands, and the turn stops on it rather than mid-sentence."""
    session = PiAgent(PI).new()
    session.budget = Budget(output=6, when="next-response")

    said = session("write me something long")

    assert "part 2" in said  # four tokens took it to eight, and those words are kept
    assert f"part {PIECES}" not in said


def test_a_clock_that_runs_out_next_response_still_ends_the_turn(pi: Path) -> None:
    """It waits for an answer to land rather than for the turn, or it would never bite."""
    session = PiAgent(PI).new()
    session.budget = Budget(seconds=PIECES * PAUSE / 4, when="next-response")

    began = time.monotonic()
    said = session("write me something long")

    assert time.monotonic() - began < PIECES * PAUSE
    assert f"part {PIECES}" not in said


def test_a_spent_budget_may_fail_the_turn_instead_of_ending_it(pi: Path) -> None:
    """And it is `Unrecoverable`: the same budget is spent again on the next try."""
    session = PiAgent(PI).new()
    session.budget = Budget(output=6, when="immediately", then="fail")

    with pytest.raises(Unrecoverable, match="cut off"):
        session("write me something long")


def test_a_turn_failed_for_its_budget_is_not_quietly_suppressed(pi: Path) -> None:
    """`suppress` is `|| true` for a turn that failed, not for a loop that must stop."""
    session = PiAgent(PI).new()
    session.budget = Budget(output=6, when="immediately", then="fail")

    with pytest.raises(Unrecoverable):
        session("write me something long", suppress=True)


def test_every_turn_starts_with_the_whole_budget_again(pi: Path) -> None:
    """Or a tenth round would be cut off for what the first round wrote."""
    session = PiAgent(PI).new()
    session.budget = Budget(output=6, when="immediately")

    first = session("write me something long")
    second = session("and again")

    assert "part 1" in first
    assert "part 1" in second  # not cut off before it had said anything
    assert session.spent().output > 6  # both turns wrote, and the meter kept both


def test_a_conversation_runs_under_its_agents_budget_until_it_is_told_otherwise(
    pi: Path,
) -> None:
    """A budget is a setting of the agent, and a setting of one conversation of it."""
    agent = PiAgent(PiAgentConfig(model="m", effort="high", budget=Budget(output=6)))
    session = agent.new()

    assert session.budget == Budget(output=6)

    said = session("write me something long")

    assert f"part {PIECES}" not in said

    session.budget = Budget()  # nothing named is nothing capped
    whole = session("and again, all of it")

    assert f"part {PIECES}" in whole


def test_a_clock_bites_on_a_backend_that_says_nothing_about_what_it_spent(
    silent: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`next-response` waits for an answer to land, and not forever: none is coming here."""
    monkeypatch.setattr(base, "_LANDING", PAUSE)
    session = OpencodeAgent(OPENCODE).new()
    session.budget = Budget(seconds=PAUSE * 2, when="next-response")

    began = time.monotonic()
    said = session("write me something long")

    assert time.monotonic() - began < PIECES * PAUSE
    assert "part 1" in said
    assert f"part {PIECES}" not in said
    assert not _left(silent)


def test_a_budget_said_mid_turn_is_the_next_turns(opencode: Path) -> None:
    """A turn runs under the budget it opened with, or it is cut off for what it was allowed.

    Read live, the caps would be measured against a baseline no turn ever took: every token
    the conversation has ever spent, and every second since the machine started.
    """
    session = OpencodeAgent(OPENCODE).new()
    told: list[str] = []

    def shorten(_agent: object, _session: object, event: object) -> None:
        kind = getattr(event, "kind", "")
        if kind == "text" and not told:
            told.append("said")
            session.budget = Budget(output=1, when="immediately")

    session._agent.watch(shorten)
    said = session("write me something long")

    assert told  # the budget really was set while the turn was running
    assert f"part {PIECES}" in said  # and this turn ran to the end all the same


def test_a_command_turn_is_cut_off_and_its_process_ended(opencode: Path) -> None:
    """The lifetime that had nowhere to be reached: one run of a command line per turn."""
    session = OpencodeAgent(OPENCODE).new()
    session.budget = Budget(output=6, when="immediately")

    began = time.monotonic()
    said = session("write me something long")

    assert time.monotonic() - began < PIECES * PAUSE
    assert "part 1" in said
    assert f"part {PIECES}" not in said
    assert not _left(opencode)


def test_a_command_turn_is_interrupted_by_hand(opencode: Path) -> None:
    """What a watchdog reaches for, and what it is handed: one turn, ended where it is."""
    session = OpencodeAgent(OPENCODE).new()
    answered: list[str] = []

    turn = threading.Thread(target=lambda: answered.append(session("write something")))
    turn.start()
    while session._underway is None:  # the turn has to have started to be cut off
        time.sleep(0.01)
    time.sleep(PAUSE * 2)
    session.interrupt(why="the watchdog says so")
    turn.join(timeout=PIECES * PAUSE)

    assert not turn.is_alive()
    assert answered
    assert "part 1" in answered[0]
    assert not _left(opencode)


def test_a_session_with_no_turn_running_is_left_alone(opencode: Path) -> None:
    """A reason left standing would end the next turn before it had said anything."""
    session = OpencodeAgent(OPENCODE).new()
    session.interrupt(why="nothing is running")

    said = session("write something")

    assert f"part {PIECES}" in said


def test_stopping_an_agent_ends_the_command_turn_it_is_taking(opencode: Path) -> None:
    """`stop` says it ends the turn under way, and on these backends it now does."""
    agent = OpencodeAgent(OPENCODE)
    session = agent.new()
    raised: list[BaseException] = []

    def turn() -> None:
        try:
            session("write something")
        except BaseException as why:  # noqa: BLE001 -- whichever end it comes to
            raised.append(why)

    running = threading.Thread(target=turn)
    running.start()
    while session._underway is None:
        time.sleep(0.01)
    agent.stop()
    running.join(timeout=PIECES * PAUSE)

    assert not running.is_alive()
    assert raised
    assert isinstance(raised[0], Stopped | subprocess.CalledProcessError)
    assert not _left(opencode)
