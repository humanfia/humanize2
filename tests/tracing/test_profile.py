"""What else was running while the agents were, and how it reaches the same trace.

An agent's turn is mostly other programs: it runs the tests, it builds the thing, it greps
the repository. None of that is in the backend's own log, which records the tool call and not
the process -- so a run may be profiled as well as traced, and what it saw is drawn the way
the agents are: one process per program, one track per thread.
"""

from __future__ import annotations

import subprocess
import sys
import time
from typing import TYPE_CHECKING

import pytest

from hmz.tracing import chrome
from hmz.tracing.profile import PROFILE, Process, Profiler, Thread, read

if TYPE_CHECKING:
    import pathlib


def _ran(at: pathlib.Path, *said: str) -> list[Process]:
    """Profiles one shell command, and answers with what the sampler saw.

    Args:
      at: Where to write the profile.
      said: The command to run.

    Returns:
      What was seen, oldest first.
    """
    one = Profiler(at / PROFILE, every=0.01)
    one.start()
    try:
        subprocess.run(said, check=False, capture_output=True)
    finally:
        one.stop()
    return read(at)


@pytest.mark.timeout(60)
def test_the_programs_a_run_starts_are_written_down(tmp_path: pathlib.Path) -> None:
    """Which is the whole of it: what ran, what started it, and how long it took.

    Found by what it was started with rather than by its name: a profiler watches everything
    under this process, and a suite that runs flows on threads of its own has other shells
    of its own going at the same time.
    """
    said = "sleep 0.4"
    held = _ran(tmp_path, "sh", "-c", said)

    shell = next(one for one in held if one.argv == ("sh", "-c", said))
    # Timed against the clock the rest of a trace is timed by, rather than against the
    # machine's idea of when it booted -- which is out by half a second on an ordinary one.
    assert 0.2 <= shell.ended - shell.began <= 5.0
    assert shell.began <= time.time()
    # And what started it, which is how the tree is rebuilt.
    assert [one.name for one in held if one.ppid == shell.pid] == ["sleep"]


@pytest.mark.timeout(60)
def test_a_program_is_written_down_as_it_goes_rather_than_at_the_end(
    tmp_path: pathlib.Path,
) -> None:
    """A run that died is a run whose profile has to say what it got to."""
    one = Profiler(tmp_path / PROFILE, every=0.01)
    one.start()
    try:
        subprocess.run(["sh", "-c", "sleep 0.1"], check=False, capture_output=True)
        time.sleep(0.1)
        # Nothing has stopped it, and the program it saw is already written down.
        assert any(each.name == "sh" for each in read(tmp_path))
    finally:
        one.stop()


@pytest.mark.timeout(60)
def test_a_profile_holds_the_threads_of_what_it_saw(tmp_path: pathlib.Path) -> None:
    """A track is a thread, so a program with two of them is a process with two tracks."""
    held = _ran(
        tmp_path,
        sys.executable,
        "-c",
        "import threading, time\n"
        "held = threading.Thread(target=lambda: time.sleep(0.3))\n"
        "held.start()\n"
        "held.join()\n",
    )

    one = next(each for each in held if each.threads)
    assert len(one.threads) >= 1
    assert one.threads[0].tid == one.pid  # the one that ran main


@pytest.mark.timeout(60)
def test_a_profile_nothing_was_written_to_is_nothing(tmp_path: pathlib.Path) -> None:
    """A run that was not profiled is a trace of its sessions, which is what it always was."""
    assert read(tmp_path) == []
    assert read(tmp_path / "nothing.jsonl") == []


def test_the_programs_are_drawn_as_processes_with_a_track_apiece() -> None:
    """The same shape as an agent and its sub-agents, which is what one document is for."""
    document = chrome.build(
        [],
        None,
        None,
        [
            Process(
                pid=41,
                ppid=1,
                name="pytest",
                argv=("pytest", "-q"),
                began=1000.0,
                ended=1002.0,
                threads=(
                    Thread(41, 1000.0, 1002.0, 1.5),
                    Thread(99, 1000.5, 1002.0, 0.5),
                ),
            )
        ],
    )

    events = document["traceEvents"]
    assert [one["args"]["name"] for one in events if one["name"] == "process_name"] == [
        "pytest · 41"
    ]
    assert [one["args"]["name"] for one in events if one["name"] == "thread_name"] == [
        "main",
        "thread 99",
    ]
    slices = [one for one in events if one["ph"] == "X"]
    assert [one["dur"] for one in slices] == [2_000_000, 1_500_000]
    assert slices[0]["args"]["argv"] == "pytest -q"
    assert slices[0]["args"]["cpu"] == 1.5
    assert document["otherData"]["programs"] == "1"


def test_a_trace_of_sessions_alone_says_nothing_about_programs() -> None:
    """One more field to read past on every trace that was never profiled is one too many."""
    from hmz.tracing.session import Action, Session

    session = Session(
        key="claude:one",
        backend="claude",
        ident="one",
        label="main",
        title="one",
        agent="claude",
        actions=[Action("a turn", "turn", 1000.0, 1001.0)],
    )

    document = chrome.build([session], None, None, [])

    assert "programs" not in document["otherData"]
