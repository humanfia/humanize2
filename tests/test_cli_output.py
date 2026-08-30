"""Who is reading a command line, and what each of the two is handed.

What is checked here is the rule rather than the layout: that a terminal gets escapes and
nothing else does, that the three conventions are honoured in the order they settle it, that
a run written for a program is NDJSON and nothing but NDJSON however loudly a flow prints,
and that what a script reading `hmz exec` has always read off stdout is still there.
"""

from __future__ import annotations

import io
import json
import re
from typing import TYPE_CHECKING

import pytest

from hmz.agents import AgentConfig
from hmz.agents.event import Event, Usage
from hmz.cli import main
from hmz.cli.output import Out, Shown, colours, terminal
from tests.stubs import ShellAgent, written

if TYPE_CHECKING:
    from pathlib import Path

#: Anything that begins an escape sequence. A run that is piped, redirected or read by
#: anything that is not a terminal must hold none of these.
ESCAPES = re.compile(r"\x1b\[")

#: A flow that drives no agents and prints, which is what a layer under one does too. Under
#: `--json` there is nowhere for a line like this to land but stderr.
LOUD = """
from hmz.flows import flow


@flow
def run(agents: tuple[()], task: str) -> None:
    print("a flow said this")
"""


class _Tty(io.StringIO):
    """A stream that says it is a terminal, since a pipe under pytest cannot be one."""

    def isatty(self) -> bool:
        return True


@pytest.fixture(autouse=True)
def _plain(monkeypatch: pytest.MonkeyPatch) -> None:
    """Answers the colour question the same way wherever this suite runs.

    Both a developer's terminal and this project's own CI set `FORCE_COLOR`, and a test that
    reads it is a test that says something different on the two machines.
    """
    for named in ("NO_COLOR", "FORCE_COLOR", "TERM"):
        monkeypatch.delenv(named, raising=False)


def _agent() -> ShellAgent:
    """One agent to attribute events to."""
    return ShellAgent(AgentConfig(model="m", effort="high"), name="builder")


def test_a_terminal_gets_escapes_and_a_pipe_does_not(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Which is the whole question, asked of the stream rather than of the command."""
    assert colours(_Tty()) is True
    assert colours(io.StringIO()) is False


@pytest.mark.parametrize(
    ("named", "value", "wanted"),
    [
        # Unconditional, and over everything: that is what the convention says it is.
        ("NO_COLOR", "1", False),
        # A terminal saying it could not read them.
        ("TERM", "dumb", False),
        # And somebody saying to write them into something that is not a terminal at all,
        # which is what a CI log wants and what this project's own CI sets.
        ("FORCE_COLOR", "1", True),
        ("FORCE_COLOR", "0", False),
    ],
)
def test_the_three_conventions_answer_before_the_stream_does(
    monkeypatch: pytest.MonkeyPatch, named: str, value: str, wanted: bool
) -> None:
    """`NO_COLOR`, `TERM=dumb` and `FORCE_COLOR`, in the order they settle it."""
    monkeypatch.setenv(named, value)

    assert colours(_Tty() if named != "FORCE_COLOR" else io.StringIO()) is wanted


def test_no_colour_wins_over_forcing_it(monkeypatch: pytest.MonkeyPatch) -> None:
    """A machine that says never means never, whatever else is also set."""
    monkeypatch.setenv("FORCE_COLOR", "1")
    monkeypatch.setenv("NO_COLOR", "1")

    assert colours(_Tty()) is False


def test_forcing_colour_does_not_invent_a_terminal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Escapes in a log file are one thing; a piped run believing it is watched is another."""
    monkeypatch.setenv("FORCE_COLOR", "1")

    assert colours(io.StringIO()) is True
    assert terminal(io.StringIO()) is False


def test_a_listing_is_a_line_for_a_person_and_an_object_for_a_program(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """One call apiece, so that the two readings cannot drift into two listings."""
    with Out() as out:
        out.row("claude/mine  key", cli="claude", name="mine", way="key")
        out.note("try `hmz providers add claude/mine`")
    said = capsys.readouterr().out.splitlines()

    assert said == ["claude/mine  key", "try `hmz providers add claude/mine`"]

    with Out(as_json=True) as out:
        out.row("claude/mine  key", cli="claude", name="mine", way="key")
        # A hint is a thing to say to a person: an empty list is already the answer.
        out.note("try `hmz providers add claude/mine`")
    written_out = capsys.readouterr().out.splitlines()

    assert [json.loads(one) for one in written_out] == [
        {"cli": "claude", "name": "mine", "way": "key"}
    ]


def test_a_run_written_for_a_program_cannot_have_a_stray_line_put_in_it(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """One line that is not JSON is a stream that will not parse, so there is nowhere for
    one to land but stderr."""
    with Out(as_json=True) as out:
        print("a flow said this")
        out.record(kind="text", text="the agent said this")
    said = capsys.readouterr()

    assert [json.loads(one) for one in said.out.splitlines()] == [
        {"kind": "text", "text": "the agent said this"}
    ]
    assert "a flow said this" in said.err


def test_a_run_nobody_is_watching_is_written_without_an_escape_in_it(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Which is what keeps a redirected run readable rather than a file of escapes."""
    agent = _agent()
    with Out() as out, Shown(out) as shown:
        shown.heard(agent, None, Event(kind="begins", text=""))
        shown.heard(agent, None, Event(kind="text", text="fixing the checker"))
        shown.heard(agent, None, Event(kind="tool", text="Bash ls -la"))
        shown.heard(agent, None, Event(kind="ends", text=""))
    said = capsys.readouterr()

    assert not ESCAPES.search(said.err)
    assert "builder is working" in said.err
    assert "fixing the checker" in said.err
    assert "Bash(ls -la)" in said.err
    assert "Worked for" in said.err


def test_a_clock_is_drawn_only_where_escapes_are_wanted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A clock is written in escapes, cursor and all, so `NO_COLOR` means no clock."""
    monkeypatch.setattr("sys.stderr", _Tty())
    with Out() as out:
        out.spins(lambda: "builder is working")
        assert out._region is not None
        out.spins(None)

    plain = _Tty()
    monkeypatch.setattr("sys.stderr", plain)
    monkeypatch.setenv("NO_COLOR", "1")
    with Out() as out:
        out.spins(lambda: "builder is working")

        assert out._region is None
    # And nothing of `rich`'s reached the stream: what the run is doing is still said a line
    # at a time, as it is for anything that is not a terminal.
    assert not ESCAPES.search(plain.getvalue())


def test_two_turns_of_one_agent_are_two_turns(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """An agent runs several conversations at once, and each turn is timed against its own."""
    agent = _agent()
    first, second = agent.new(), agent.new()
    with Out() as out, Shown(out) as shown:
        shown.heard(agent, first, Event(kind="begins", text=""))
        shown.heard(agent, second, Event(kind="begins", text=""))

        assert shown._working().startswith("2 turns working")

        shown.heard(agent, first, Event(kind="ends", text=""))
        # The one still going keeps the clock up, which is the whole point of having one.
        assert shown._working().startswith("builder is working")

        shown.heard(agent, second, Event(kind="ends", text=""))
        assert shown._working() == ""
    said = capsys.readouterr().err

    assert said.count("Worked for") == 2


def test_what_a_turn_answered_is_still_on_stdout_for_a_script(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Every script written against `hmz exec` reads the answer there, and goes on doing so."""
    agent = _agent()
    with Out() as out, Shown(out) as shown:
        shown.heard(
            agent,
            None,
            Event(
                kind="result",
                text="done",
                tokens={"m": 30},
                spent=Usage(input=20, output=10),
            ),
        )
    said = capsys.readouterr()

    assert said.out.splitlines() == ["done"]
    # And what it cost, under the turn, where the person reading it is looking.
    assert "input 20" in said.err
    assert "output 10" in said.err

    # A turn that answered nothing writes nothing: a blank line is not an answer, and a
    # script reading this stream would have to know to drop it.
    with Out() as out, Shown(out) as shown:
        shown.heard(agent, None, Event(kind="result", text=""))

    assert capsys.readouterr().out == ""


def test_a_run_written_for_a_program_is_one_object_per_thing_that_was_said(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Every key every time: a schema a program has to guess at is not one it can read."""
    agent = _agent()
    with Out(as_json=True) as out, Shown(out) as shown:
        shown.heard(agent, None, Event(kind="begins", text=""))
        shown.heard(
            agent,
            None,
            Event(kind="result", text="done", tokens={"m": 30}, spent=Usage(input=30)),
        )
    said = capsys.readouterr()

    objects = [json.loads(one) for one in said.out.splitlines()]
    assert [one["kind"] for one in objects] == ["begins", "result"]
    for one in objects:
        assert set(one) == {
            "at",
            "agent",
            "cli",
            "model",
            "session",
            "kind",
            "text",
            "whose",
            "tokens",
            "spent",
        }
        assert one["agent"] == "builder"
        assert one["cli"] == "shell"
    assert objects[-1]["tokens"] == {"m": 30}
    assert objects[-1]["spent"] == {"input": 30}
    # Nothing that is not an object: the answer is one of them rather than a line beside them.
    assert said.out.count("\n") == 2


def test_the_exec_line_says_who_is_reading_the_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`--json` is read by the same parser as the rest of the line: one grammar, one line."""
    monkeypatch.chdir(tmp_path)
    flow = str(written(tmp_path, "loud", LOUD))

    assert main(["exec", "-f", flow, "--json", "go"]) == 0
    said = capsys.readouterr()

    # A flow that drives no agents says nothing, so there is nothing to write down -- and
    # what the flow itself printed is on stderr, where it cannot spoil the stream.
    assert said.out == ""
    assert "a flow said this" in said.err

    assert main(["exec", "-f", flow, "go"]) == 0
    assert "a flow said this" in capsys.readouterr().out
