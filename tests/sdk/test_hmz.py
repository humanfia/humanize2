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

import pytest

from hmz.kept import Runs
from hmz.sdk import Hmz, Taken

if TYPE_CHECKING:
    import pathlib

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
    """A line that lists the agents kept under a name must not pay for the interface."""
    probe = (
        "import sys\n"
        "from hmz.sdk import Hmz\n"
        "held = Hmz()\n"
        "print(' '.join(sorted(m for m in sys.modules if m.startswith('hmz.'))))\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", probe], capture_output=True, text=True, check=True
    )

    reached = {name.split(".")[1] for name in result.stdout.split()}
    assert reached == {"sdk"}


def test_the_agents_written_down_are_the_ones_a_command_line_wrote() -> None:
    """One store, reached one way, so that what a menu saved a line reads back."""
    held = Hmz()
    held.agents.add("mine", "claude/claude-opus-5:high")

    kept = held.agents.find("mine")

    assert kept is not None
    assert kept.runs.spec == "claude/claude-opus-5:high"
    assert [one.name for one in held.agents.all()] == ["mine"]


def test_a_name_already_written_down_is_its_own_refusal() -> None:
    """So that a command line can say which flag writes over one and a menu need not."""
    held = Hmz()
    held.agents.add("mine", "claude/claude-opus-5:high")

    with pytest.raises(Taken, match="already an agent called mine"):
        held.agents.add("mine", "codex/gpt-5.6:high")

    written = held.agents.add("mine", "codex/gpt-5.6:high", force=True)
    assert written.runs.spec == "codex/gpt-5.6:high"
    assert len(held.agents.all()) == 1


def test_one_written_over_keeps_its_place_in_the_list() -> None:
    """However it was written: a menu and a command line write down the same thing."""
    held = Hmz()
    held.agents.add("one", "claude/a:high")
    held.agents.add("two", "claude/b:high")

    held.agents.write("one", Runs("codex/c:high"))

    assert [each.name for each in held.agents.all()] == ["one", "two"]


def test_an_agent_that_is_not_one_says_which_spelling_was_refused() -> None:
    held = Hmz()

    with pytest.raises(ValueError, match="nosuchcli/model:high"):
        held.agents.add("mine", "nosuchcli/model:high")


def test_taking_one_away_says_whether_there_was_one() -> None:
    held = Hmz()
    held.agents.add("mine", "claude/a:high")

    assert held.agents.remove("mine")
    assert not held.agents.remove("mine")


def test_the_places_flows_come_from_are_the_four_that_are_always_there() -> None:
    assert [one.name for one in Hmz().verses.all()] == [
        "builtin",
        "official",
        "local",
        "user",
    ]


def test_where_a_place_came_from_is_asked_of_which_place_it_is() -> None:
    """An empty URL means three different things, and one of them is humanize's own."""
    verses = Hmz().verses
    by_name = {one.name: one for one in verses.all()}

    assert verses.whence(by_name["builtin"]) == "the flows humanize ships"
    assert "your own flows" in verses.whence(by_name["local"])
    # And humanize's own flowverse is where it is fetched from, whether or not it has been.
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
    flow, agents, task, config, container = held.read(
        ["-f", str(written), "-a", "claude/model:high", "go"]
    )
    running = held.run(flow, agents, task, config, container=container)

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

    runs = held.cycles.all()

    assert len(runs) == 1
    ran = held.cycles.read(runs[0])
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

    assert Hmz(tmp_path).cycles.all()
    assert Hmz(elsewhere).cycles.all() == []


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
