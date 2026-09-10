"""A backend that stops saying anything, and what the watchdog does about it.

The one thing a read loop cannot see for itself: a CLI still holding its stdout open and
never writing to it again is neither an answer nor an exit, and every loop in the agents
layer waits on one of those. So the turns here are wedged on purpose -- a process told to
sleep, a process sent SIGSTOP -- and what is asserted is that the turn ends anyway, that it
ends saying what happened, and that nothing is left running afterwards.
"""

from __future__ import annotations

import contextlib
import os
import subprocess
import sys
import time
from typing import TYPE_CHECKING

import psutil
import pytest

from hmz import backends
from hmz.agents import (
    AgentBase,
    AgentConfig,
    CommandSessionBase,
    Event,
    SessionBase,
    StreamSessionBase,
)
from hmz.agents.watchdog import WATCHDOG, Watchdog, held, silence

if TYPE_CHECKING:
    from collections.abc import Iterable

CONFIG = AgentConfig(model="m", effort="high")

#: A process that takes the turn and then says nothing at all, for as long as it is left. It
#: reads its stdin so that the line a stream session writes lands rather than breaking the
#: pipe, and it never exits: this is the wedge, not a crash.
WEDGED = "import sys, time; sys.stdin.readline(); time.sleep(600)"

#: The same, plus a child holding the same pipes: a CLI wedged on something it started is the
#: usual shape of one, and killing the parent alone leaves the pipe held by the child.
NESTED = (
    "import subprocess, sys, time; "
    "sys.stdin.readline(); "
    "subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(600)']); "
    "time.sleep(600)"
)

#: A process that talks the whole way through a turn and then ends it. Nothing about this is
#: quick: the point is that a turn longer than the window is not touched while it is talking.
CHATTY = (
    "import sys, time; "
    "sys.stdin.readline(); "
    "[ (print('thinking', flush=True), time.sleep(0.2)) for _ in range(12) ]; "
    "print('done', flush=True)"
)


@pytest.fixture(autouse=True)
def _brief(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every window in this file is a second: a quarter of an hour is not a test."""
    monkeypatch.setenv(WATCHDOG, "1")


class _Stream(StreamSessionBase):
    """A session whose one process is whatever the test asked for."""

    program = WEDGED

    def __init__(
        self, agent: AgentBase, cwd: str | os.PathLike[str] | None = None
    ) -> None:
        super().__init__(agent, cwd)
        #: Every process this session has started, so a test can ask what became of them
        #: after the session has let go of them.
        self.started: list[subprocess.Popen[str]] = []

    def _command(self) -> list[str]:
        return [sys.executable, "-u", "-c", self.program]

    def _start(self, argv: list[str]) -> subprocess.Popen[str]:
        proc = super()._start(argv)
        if proc not in self.started:
            self.started.append(proc)
        return proc

    def _write(self, text: str, ticket: str = "") -> str:
        return text + "\n"

    def _read(self, line: str) -> Iterable[Event]:
        if line.startswith("done"):
            return (Event(kind="result", text="ok"),)
        return (Event(kind="text", text=line.rstrip("\n")),)


class _Asked(_Stream):
    """The same, but with somewhere for the watchdog to ask the turn to stop."""

    def __init__(
        self, agent: AgentBase, cwd: str | os.PathLike[str] | None = None
    ) -> None:
        super().__init__(agent, cwd)
        self.asked: list[str] = []

    def interrupt(self, *, why: str) -> None:
        self.asked.append(why)


class _Command(CommandSessionBase):
    """A session whose turn is one run of a command that never says anything."""

    program = WEDGED

    def _turn(self, prompt: str) -> tuple[list[str], str | None]:
        return [sys.executable, "-u", "-c", self.program], prompt + "\n"

    def _read_session_id(self, transcript: str) -> str:
        return "a-session"


class _Agent(AgentBase):
    """An agent of no backend anyone has written down, holding sessions of one class."""

    session: type[SessionBase] = _Stream

    def new(self, cwd: str | os.PathLike[str] | None = None) -> SessionBase:
        return type(self).session(self, cwd)


def _agent(session: type[SessionBase]) -> _Agent:
    """An agent whose sessions are of one class, made for one test."""
    return type("_Agent", (_Agent,), {"session": session})(CONFIG)


def _watched(agent: AgentBase) -> list[Event]:
    """Everything the agent says, collected as it says it."""
    said: list[Event] = []
    agent.watch(lambda _agent, _session, event: said.append(event))
    return said


def _steps(said: list[Event]) -> str:
    """Everything the agent said, as one string to look for the ladder in."""
    return "\n".join(event.text for event in said)


def test_a_stream_session_wedged_mid_turn_is_ended_and_says_why() -> None:
    """The turn cannot end itself: the process is up, silent, and going nowhere."""
    agent = _agent(_Stream)
    said = _watched(agent)
    session = agent.new()
    assert isinstance(session, _Stream)

    with pytest.raises(subprocess.CalledProcessError) as failed:
        list(session._stream("go"))

    # What the turn failed with is what happened, not what the killing looked like: an
    # `exit status -15` here would be the watchdog describing its own footprints.
    assert "watchdog" in str(failed.value)
    assert "has said nothing" in str(failed.value)
    # And every rung said so as it was taken, where a flow watching the agent can act on it.
    assert "has said nothing" in _steps(said)
    assert session.started
    assert all(proc.returncode is not None for proc in session.started)


def test_a_wedged_turn_fails_as_a_turn_rather_than_as_a_stop() -> None:
    """A flow catches turns; a watchdog kill that read as a deliberate stop would end a run.

    `Stopped` is deliberately not a `CalledProcessError` so that a loop carrying on past a
    failed turn does not carry on past a stop. A wedge is the other thing: worth another go,
    against the same conversation, which is what the retry ladder above this does with a
    `Failed` and does not do with anything else.
    """
    from hmz.agents import Failed, Stopped, Unrecoverable

    session = _agent(_Stream).new()
    with pytest.raises(Failed) as failed:
        list(session._stream("go"))
    assert not isinstance(failed.value, Stopped)
    # Nor unrecoverable: the same prompt to a fresh transport is exactly what should be tried.
    assert not isinstance(failed.value, Unrecoverable)


def test_a_command_session_wedged_mid_turn_is_ended_and_says_why() -> None:
    """The other read loop: a queue nobody will ever put the last None on."""
    agent = _agent(_Command)
    said = _watched(agent)
    session = agent.new()

    with pytest.raises(subprocess.CalledProcessError) as failed:
        list(session._stream("go"))

    assert "watchdog" in str(failed.value)
    assert "has said nothing" in _steps(said)


def test_a_turn_that_keeps_talking_is_left_alone() -> None:
    """A turn longer than the window is not a wedged turn, and must survive being long.

    Two and a half seconds against a window of one, which is the same shape as twenty
    minutes against a quarter of an hour: what says the turn is alive is that it is saying
    things, not that it is finishing quickly.
    """
    agent = _agent(_Stream)
    said = _watched(agent)
    session = agent.new()
    assert isinstance(session, _Stream)
    session.program = CHATTY

    started = time.monotonic()
    events = list(session._stream("go"))

    assert time.monotonic() - started > 2.0  # longer than the window, on purpose
    assert events[-1].kind == "result"
    assert events[-1].text == "ok"
    assert "watchdog" not in _steps(said)


def test_the_turn_is_asked_to_stop_before_anything_is_taken_from_it() -> None:
    """The gentlest rung first: a backend that can be told is told before it is signalled."""
    agent = _agent(_Asked)
    said = _watched(agent)
    session = agent.new()
    assert isinstance(session, _Asked)

    with pytest.raises(subprocess.CalledProcessError):
        list(session._stream("go"))

    assert session.asked, "the session was never asked to stop"
    assert "no output for" in session.asked[0]
    assert "was asked to stop" in _steps(said)


@pytest.mark.skipif(os.name == "nt", reason="SIGSTOP is not a thing on Windows")
def test_a_process_that_was_stopped_is_named_as_stopped() -> None:
    """The one wedge the machine can be certain about, and the one it must not mistake."""
    agent = _agent(_Stream)
    said = _watched(agent)
    session = agent.new()
    assert isinstance(session, _Stream)
    proc = session._start(session._command())
    psutil.Process(proc.pid).suspend()
    watch = Watchdog(session, riding=lambda: proc, window=0.2)
    try:
        with watch:
            # Long enough for every rung: a suspended process ignores the polite signal --
            # it is not running to receive it -- so this is the one wedge that always ends
            # at the last rung.
            time.sleep(4.0)
    finally:
        with contextlib.suppress(OSError):
            proc.kill()
        with contextlib.suppress(OSError):
            proc.wait()
    assert "is stopped" in _steps(said)
    assert watch.wedged() is not None
    assert proc.returncode is not None


def test_a_wedged_process_takes_what_it_started_with_it() -> None:
    """A CLI wedged on something it spawned: the pipe is held by the child, so the child goes."""
    agent = _agent(_Stream)
    session = agent.new()
    assert isinstance(session, _Stream)
    session.program = NESTED

    with pytest.raises(subprocess.CalledProcessError):
        list(session._stream("go"))

    proc = session.started[0]
    assert proc.returncode is not None
    assert not psutil.pid_exists(proc.pid) or psutil.Process(proc.pid).status() in (
        psutil.STATUS_ZOMBIE,
        psutil.STATUS_DEAD,
    )


def test_a_watchdog_turned_off_never_starts_a_thread(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Zero seconds is the watchdog humanize had before there was one: none at all."""
    monkeypatch.setenv(WATCHDOG, "0")
    session = _agent(_Stream).new()
    with Watchdog(session) as watch:
        assert watch._thread is None
    assert watch.wedged() is None


def test_the_window_is_the_backend_s_own_and_the_environment_outranks_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A number chosen per CLI, in the one file that says what is true of each of them."""
    monkeypatch.delenv(WATCHDOG, raising=False)
    # dsh's own SDK bounds every request, so its turns are given less rope than the rest.
    assert silence("dsh") < silence("claude")
    assert silence("claude") == backends.PROFILES[0].silence
    # A backend nobody has written down still gets a window: an unknown CLI can wedge too.
    assert silence("nothing-answers-to-this") > 0
    monkeypatch.setenv(WATCHDOG, "12.5")
    assert silence("dsh") == 12.5


def test_what_survives_a_transport_going_down_is_written_where_the_facts_are() -> None:
    """Which backends resume, said in `hmz.backends` rather than guessed at by a watchdog."""
    assert all(one.resumes for one in backends.PROFILES)
    assert all(one.restarts for one in backends.PROFILES)
    # An app server is one per agent: putting it down for one wedged turn ends its siblings,
    # which is what the watchdog has to say before it does it.
    assert {one.name for one in backends.PROFILES if one.shares} == {
        "codex",
        "kimi",
        "zcode",
    }
    # And a CLI known only by the protocol it speaks does not resume: the protocol's only way
    # to open a session opens a new one.
    assert not backends.UNKNOWN.resumes


def test_a_session_that_cannot_be_asked_to_stop_says_so_rather_than_pretending() -> (
    None
):
    """The default, which is what a backend taking its whole prompt up front has to do."""
    session = _agent(_Stream).new()
    with pytest.raises(NotImplementedError, match="cannot be interrupted"):
        session.interrupt(why="the budget is spent")


def test_a_turn_waiting_on_a_person_is_not_a_turn_waiting_on_its_backend() -> None:
    """A permission prompt somebody takes a long time over must not cost the CLI its life.

    The clock is stopped for as long as an agent has a question outstanding: the CLI is
    sitting there with nothing being asked of it, which is not silence it is answerable for.
    """
    agent = _agent(_Stream)
    said = _watched(agent)
    session = agent.new()
    assert isinstance(session, _Stream)
    proc = session._start(session._command())
    watch = Watchdog(session, riding=lambda: proc, window=0.5)
    try:
        with watch, held(agent):
            time.sleep(
                3.0
            )  # six windows, every one of them the person's rather than the CLI's
    finally:
        with contextlib.suppress(OSError):
            proc.kill()
        with contextlib.suppress(OSError):
            proc.wait()
    assert watch.wedged() is None
    assert _steps(said) == ""


def test_a_backend_that_crashed_keeps_the_reason_it_crashed() -> None:
    """The watchdog says what it saw, and takes the blame only for what it did.

    A process already gone when the clock ran out has a diagnostic of its own on the way --
    an exit status, a line of stderr -- and replacing that with "the watchdog stopped this
    turn" would be this taking the credit for somebody else's failure.
    """
    agent = _agent(_Stream)
    said = _watched(agent)
    session = agent.new()
    assert isinstance(session, _Stream)
    proc = session._start(session._command())
    proc.kill()
    proc.wait()
    watch = Watchdog(session, riding=lambda: proc, window=0.5)
    with watch:
        time.sleep(2.0)
    assert "is gone" in _steps(said)  # seen, and said at the moment it was seen
    assert watch.wedged() is None  # but nothing was done to it, so nothing is claimed


def test_a_turn_that_ends_on_its_own_is_never_given_the_watchdog_s_verdict() -> None:
    """The verdict replaces a failure only where the watchdog caused one."""
    session = _agent(_Stream).new()
    watch = Watchdog(session, window=1000.0)
    with watch:
        pass
    assert watch.wedged() is None

    # And a turn that failed for its own reasons, under a watchdog that never fired, keeps
    # the reason it failed.
    own = subprocess.CalledProcessError(3, ["something"], "", "it fell over")
    with (
        pytest.raises(subprocess.CalledProcessError) as failed,
        Watchdog(session, window=1000.0),
    ):
        raise own
    assert failed.value is own
