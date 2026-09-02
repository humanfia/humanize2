"""humanize as one object, which is what every way in holds.

What is checked here is that it is the same store and the same run whichever way it was
reached, that a workspace it was given is the one it is about, and that holding one costs
nothing until something is asked of it -- which is what lets `hmz exec` reach it without
paying for the tracer, the sandbox and every coding agent driver there is.
"""

from __future__ import annotations

import subprocess
import sys
from typing import TYPE_CHECKING

from hmz.sdk import Hmz

if TYPE_CHECKING:
    import pathlib

    import pytest

FLOW = """
from hmz.flows import Agent, flow


@flow()
def run(agents: tuple[Agent], task: str) -> None:
    (one,) = agents
    print(f"ran {task}")
"""


def test_the_workspace_is_the_one_it_was_given(tmp_path: pathlib.Path) -> None:
    assert Hmz(tmp_path).workspace == tmp_path


def test_the_workspace_is_wherever_humanize_is_run_when_none_was_given(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Kept as nothing rather than filled in: a flow may change directory under a run."""
    monkeypatch.chdir(tmp_path)

    assert Hmz().workspace == tmp_path


def test_what_it_is_asked_for_is_what_it_loads() -> None:
    """A line that lists the places flows come from must not pay for the interface."""
    probe = (
        "import sys\n"
        "from hmz.sdk import Hmz\n"
        "held = Hmz()\n"
        "print(' '.join(sorted(m for m in sys.modules if m.startswith('hmz.'))))\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", probe], capture_output=True, text=True, check=True
    )

    # By the whole name of each and not by the directory it is in: what must not be loaded
    # is now under the same directory as what must -- a tracer, an exporter and every layer
    # they name all sit beside the module `Hmz` is written in, and a set of directories
    # would say `runtime` either way.
    assert set(result.stdout.split()) == {
        # What was named, which hands through rather than keeping a copy of its own.
        "hmz.sdk",
        # The runtime's front door, which is where `Hmz` is written.
        "hmz.runtime",
        "hmz.runtime.doing",
        "hmz.runtime.doing.core",
    }


def test_the_places_flows_come_from_are_the_three_that_are_always_there() -> None:
    assert [one.name for one in Hmz().verses.all()] == ["official", "local", "user"]


def test_where_a_place_came_from_is_asked_of_which_place_it_is() -> None:
    """An empty URL means two different things, and neither is humanize's own."""
    verses = Hmz().verses
    by_name = {one.name: one for one in verses.all()}

    assert "your own flows" in verses.whence(by_name["local"])
    # And humanize's own flowverse is where it is fetched from, whether or not it has been --
    # the handful it keeps in the package are under that name too, and came from there.
    assert verses.whence(by_name["official"]).startswith("https://")


def test_a_flow_is_run_and_says_it_ran(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Which is the whole of what the SDK is for: one object, and a run of a flow from it."""
    monkeypatch.chdir(tmp_path)
    written = tmp_path / "one.py"
    written.write_text(FLOW, encoding="utf-8")
    held = Hmz()

    held.exec(["-f", str(written), "-a", "claude/model:high", "go"])

    assert "ran go" in capsys.readouterr().out


def test_a_run_is_started_and_waited_for(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Making one starts nothing: whoever made it says which of the two they are holding."""
    monkeypatch.chdir(tmp_path)
    written = tmp_path / "one.py"
    written.write_text(FLOW, encoding="utf-8")
    held = Hmz()
    flow, agents, task, config, _ = held.read(
        ["-f", str(written), "-a", "claude/model:high", "go"]
    )
    running = held.run(flow, agents, task, config)

    assert not running.running
    running.start()

    assert running.wait(timeout=30)
    assert running.raised is None
    # The person the flow talks to is among them where it talks to one, and the agents it
    # was given are the rest.
    assert len(running.agents) == 1


def test_the_runs_of_a_workspace_are_the_ones_run_there(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    written = tmp_path / "one.py"
    written.write_text(FLOW, encoding="utf-8")
    held = Hmz()
    held.exec(["-f", str(written), "-a", "claude/model:high", "go"])

    runs = held.epics.all()

    assert len(runs) == 1
    ran = held.epics.read(runs[0])
    assert ran is not None
    assert ran.task == "go"


def test_a_workspace_that_was_named_is_the_one_the_runs_are_read_from(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(tmp_path)
    written = tmp_path / "one.py"
    written.write_text(FLOW, encoding="utf-8")
    Hmz().exec(["-f", str(written), "-a", "claude/model:high", "go"])

    assert Hmz(tmp_path).epics.all()
    assert Hmz(elsewhere).epics.all() == []


def test_a_directory_that_is_a_clone_of_nothing_reads_as_whoever_shows_it_says(
    tmp_path: pathlib.Path,
) -> None:
    """A listing has a column of them and a sheet has a sentence, so it is theirs to say."""
    from hmz.flows.verses import Flowverse

    verses = Hmz().verses
    stray = Flowverse(name="stray", url="", at=tmp_path, fetched=True, fixed=False)

    assert verses.whence(stray) == "-"
    assert verses.whence(stray, "not a clone of anything") == "not a clone of anything"


def test_a_step_between_two_places_is_the_same_store_a_command_line_walks() -> None:
    held = Hmz()

    held.fallbacks.points("claude/opus", "codex/gpt")

    assert held.fallbacks.chain("claude/opus") == ["claude/opus", "codex/gpt"]
    assert [one.spec for one in held.fallbacks.all()] == ["claude/opus"]
    assert held.fallbacks.clear("claude/opus")
    assert held.fallbacks.chain("claude/opus") == ["claude/opus"]
