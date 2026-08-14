"""A flow rewritten while a run is going, and read again as it is now.

A flow is a directory on disk rather than a module somebody imported, and everything that
reads one reads it by running its entry point. So a flow edited between two readings of it --
by hand, or by an agent the flow is itself driving -- is the flow that runs next, and that is
the whole reason a run can improve the thing it is being run by.

Which is easy to say and easy to lose: one `sys.modules` entry left behind, one entry point
held onto past the call that found it, and a run would go on driving the flow it read the
first time for the life of the process. Everything a flow says about itself is read the same
way, so each of them is checked here after the file under it has changed -- what it drives,
what it can be set up with, whether it can be picked up, what it says it is, what it brings,
and whether it is a flow at all.
"""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

import pytest

from hmz.agents import AgentConfig
from hmz.flows import (
    NotAFlow,
    about,
    configures,
    drives,
    find,
    held,
    load,
    loaded,
    resumes,
)
from hmz.runner import Runner
from tests.stubs import ShellAgent, written

if TYPE_CHECKING:
    from pathlib import Path

CONFIG = AgentConfig(model="m", effort="high")


def _agent() -> ShellAgent:
    """One stand-in agent, since none of these flows takes a turn worth watching."""
    return ShellAgent(CONFIG)


def _writes(said: str) -> str:
    """A flow of one line: it writes what it was told into a file and stops.

    Args:
      said: What it writes, which is what a test reads back to say which reading ran.

    Returns:
      The flow, as the source of its `__init__.py`.
    """
    return (
        '"""Says which reading of it ran."""\n\n'
        "from pathlib import Path\n\n"
        "from hmz.agents import AgentBase\n"
        "from hmz.flows import flow\n\n\n"
        "@flow\n"
        "def run(agents: tuple[AgentBase], task: str) -> None:\n"
        f'    Path("said.txt").write_text({said!r})\n'
    )


@pytest.fixture(autouse=True)
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A project with flows of its own, and a home nothing has written to."""
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    where = tmp_path / "project"
    (where / ".humanize/flows").mkdir(parents=True)
    monkeypatch.chdir(where)
    return where


def test_a_flow_rewritten_between_two_calls_of_one_handle_is_read_again(
    project: Path,
) -> None:
    """`load` holds the name rather than the entry point it found under it.

    Which is the whole of the promise: the handle is taken once, and each call of it runs the
    file as it stands rather than as it stood when somebody asked for it.
    """
    flows = project / ".humanize/flows"
    written(flows, "one", _writes("first"))
    calling = load("one")

    calling([_agent()], "go")
    assert (project / "said.txt").read_text() == "first"

    written(flows, "one", _writes("second"))
    calling([_agent()], "go")

    assert (project / "said.txt").read_text() == "second"


def test_a_flow_that_grows_a_setting_between_calls_is_set_up_by_the_model_it_has_now(
    project: Path,
) -> None:
    """A config is read back through the model this reading declared, and not the last one.

    Two readings of one file are two classes, and what survives that is the fields. So a
    field added to a flow between two calls of it is a field the second call takes -- and a
    setting the flow no longer has is one it refuses, which is the same rule read the other
    way.
    """
    flows = project / ".humanize/flows"
    settable = (
        '"""Takes a setting, and writes down what it was set up with."""\n\n'
        "import json\n"
        "from pathlib import Path\n\n"
        "from hmz.agents import AgentBase\n"
        "from hmz.flows import flow\n"
        "from pydantic import BaseModel\n\n\n"
        "class Config(BaseModel):\n"
        '    model_config = {{"extra": "forbid"}}\n\n'
        "{fields}\n\n"
        "@flow\n"
        "def run(\n"
        "    agents: tuple[AgentBase], task: str, config: Config | None = None\n"
        ") -> None:\n"
        '    Path("set_up.json").write_text(\n'
        "        json.dumps({{}} if config is None else config.model_dump())\n"
        "    )\n"
    )
    written(flows, "settable", settable.format(fields="    rounds: int = 3"))
    calling = load("settable")

    calling([_agent()], "go", {"rounds": 9})
    assert (project / "set_up.json").read_text() == '{"rounds": 9}'

    # A field the flow did not have when the handle was taken.
    written(
        flows,
        "settable",
        settable.format(fields="    rounds: int = 3\n    loud: bool = False"),
    )
    calling([_agent()], "go", {"rounds": 9, "loud": True})

    assert (project / "set_up.json").read_text() == '{"rounds": 9, "loud": true}'
    assert configures("local/settable") is not None

    # And rewritten to take nothing at all, the same call is one to correct.
    written(flows, "settable", _writes("plain"))
    with pytest.raises(NotAFlow, match="takes no config"):
        calling([_agent()], "go", {"rounds": 9})
    assert configures("local/settable") is None


def test_a_flow_that_changes_how_many_agents_it_drives_is_held_to_the_count_it_has_now(
    project: Path,
) -> None:
    """The count is read at the call, so a flow that grew a place is short of an agent."""
    flows = project / ".humanize/flows"
    written(flows, "pair", _writes("one agent"))
    calling = load("pair")

    calling([_agent()], "go")
    assert (project / "said.txt").read_text() == "one agent"

    written(
        flows,
        "pair",
        '"""Two agents now."""\n\n'
        "from hmz.agents import AgentBase\n"
        "from hmz.flows import flow\n\n\n"
        "@flow\n"
        "def run(agents: tuple[AgentBase, AgentBase], task: str) -> None:\n"
        "    pass\n",
    )

    with pytest.raises(NotAFlow, match="drives 2 agents, 1 given"):
        calling([_agent()], "go")
    assert drives("local/pair") == ("", "")


def test_a_flow_rewritten_into_something_that_is_no_longer_one_says_so_at_the_call(
    project: Path,
) -> None:
    """Refused where it is asked for, and again at each call: the file may have moved on.

    A name that was never a flow is refused at `load`, which is the line to correct. One that
    was a flow and has stopped being one is refused at the call it stopped being one before,
    since that is when it happened.
    """
    flows = project / ".humanize/flows"
    written(flows, "was", _writes("a flow"))
    calling = load("was")
    calling([_agent()], "go")

    written(
        flows,
        "was",
        '"""Nothing in here is marked."""\n\n\ndef run() -> None:\n    pass\n',
    )

    with pytest.raises(NotAFlow, match="nothing in it is marked"):
        calling([_agent()], "go")

    # And back again, without the handle being taken a second time.
    written(flows, "was", _writes("a flow again"))
    calling([_agent()], "go")

    assert (project / "said.txt").read_text() == "a flow again"


def test_a_file_that_will_not_run_holds_no_flows_and_holds_them_again_once_it_does(
    project: Path,
) -> None:
    """A list of flows is drawn while a file is being edited, and must not end on one."""
    flows = project / ".humanize/flows"
    at = written(flows, "broken", _writes("fine"))
    assert [one.about for one in held(at)] == ["Says which reading of it ran."]

    written(flows, "broken", "this is not python at all(\n")
    assert held(at) == []

    written(flows, "broken", _writes("fine again"))
    assert [one.about for one in held(at)] == ["Says which reading of it ran."]


def test_a_flow_that_becomes_resumable_between_two_runs_is_handed_state_at_the_next(
    project: Path,
) -> None:
    """What can happen next is what the flow says today, and not what a run of it recorded."""
    flows = project / ".humanize/flows"
    written(flows, "counts", _writes("no state"))
    assert not resumes("local/counts")

    written(
        flows,
        "counts",
        '"""Counts its runs."""\n\n'
        "from pathlib import Path\n"
        "from typing import Any\n\n"
        "from hmz.agents import AgentBase\n"
        "from hmz.flows import flow\n\n\n"
        "@flow(resumable=True)\n"
        "def run(\n"
        "    agents: tuple[AgentBase], task: str, state: dict[str, Any]\n"
        ") -> None:\n"
        '    state["rounds"] = state.get("rounds", 0) + 1\n'
        '    Path("rounds.txt").write_text(str(state["rounds"]))\n',
    )

    assert resumes("local/counts")
    Runner("local/counts", [_agent()]).run("go")
    assert (project / "rounds.txt").read_text() == "1"
    Runner("local/counts", [_agent()]).run("go")

    assert (project / "rounds.txt").read_text() == "2"


def test_what_a_flow_says_about_itself_is_read_as_it_says_it_now(project: Path) -> None:
    """The one line a picker shows is read by running the file, like everything else."""
    flows = project / ".humanize/flows"
    written(flows, "says", _writes("first"))
    assert about("local/says") == "Says which reading of it ran."

    written(
        flows,
        "says",
        '"""It says something else now."""\n\n'
        "from hmz.agents import AgentBase\n"
        "from hmz.flows import flow\n\n\n"
        "@flow\n"
        "def run(agents: tuple[AgentBase], task: str) -> None:\n"
        "    pass\n",
    )

    assert about("local/says") == "It says something else now."


def test_a_module_beside_a_flow_rewritten_between_two_calls_is_read_again(
    project: Path,
) -> None:
    """A flow is its directory, so what it imports out of it is read again with it.

    The flow file itself is run rather than imported and so was never cached; the module
    beside it is imported, and is the half that would be left in `sys.modules` for the life
    of the process. A loop that improves its own prompts improves the file they are in.
    """
    flows = project / ".humanize/flows"
    at = written(
        flows,
        "reads",
        '"""Writes down what the module beside it says."""\n\n'
        "from pathlib import Path\n\n"
        "from hmz.agents import AgentBase\n"
        "from hmz.flows import flow\n\n"
        "import beside\n\n\n"
        "@flow\n"
        "def run(agents: tuple[AgentBase], task: str) -> None:\n"
        "    Path('said.txt').write_text(beside.SAID)\n",
    )
    (at / "beside.py").write_text('SAID = "first"\n')
    calling = load("reads")

    calling([_agent()], "go")
    assert (project / "said.txt").read_text() == "first"

    (at / "beside.py").write_text('SAID = "second"\n')
    calling([_agent()], "go")

    assert (project / "said.txt").read_text() == "second"


def test_a_module_beside_a_flow_is_forgotten_so_the_next_flow_reads_its_own(
    project: Path,
) -> None:
    """Two flows may each keep a `prompts.py`, and the first read must not own the name."""
    flows = project / ".humanize/flows"
    for name, said in (("alpha", "alpha"), ("beta", "beta")):
        at = written(
            flows,
            name,
            '"""Writes down what the module beside it says."""\n\n'
            "from pathlib import Path\n\n"
            "from hmz.agents import AgentBase\n"
            "from hmz.flows import flow\n\n"
            "import beside\n\n\n"
            "@flow\n"
            "def run(agents: tuple[AgentBase], task: str) -> None:\n"
            "    Path('said.txt').write_text(beside.SAID)\n",
        )
        (at / "beside.py").write_text(f'SAID = "{said}"\n')

    load("alpha")([_agent()], "go")
    assert (project / "said.txt").read_text() == "alpha"
    load("beta")([_agent()], "go")
    assert (project / "said.txt").read_text() == "beta"
    load("alpha")([_agent()], "go")

    assert (project / "said.txt").read_text() == "alpha"
    assert "beside" not in sys.modules


def test_reading_a_flow_leaves_nothing_of_it_behind(project: Path) -> None:
    """Neither the flow nor what it imports, and neither in `sys.modules` nor on the path."""
    flows = project / ".humanize/flows"
    at = written(
        flows,
        "leaves",
        '"""Imports the module beside it."""\n\n'
        "from hmz.agents import AgentBase\n"
        "from hmz.flows import flow\n\n"
        "import beside\n\n\n"
        "@flow\n"
        "def run(agents: tuple[AgentBase], task: str) -> None:\n"
        "    pass\n",
    )
    (at / "beside.py").write_text("SAID = 1\n")
    path = list(sys.path)

    assert loaded(find("local/leaves"))["beside"].SAID == 1

    assert "beside" not in sys.modules
    assert sys.path == path
    # And humanize's own is untouched: a flow kept inside this tree would otherwise unload
    # the package that is running it.
    assert "hmz.flows" in sys.modules


def test_a_flow_rewritten_by_the_run_it_is_driving_is_the_one_that_runs_next(
    project: Path,
) -> None:
    """Which is what a run that improves its own flow comes to.

    The flow rewrites its own file mid-run and then calls itself by name. The call reads what
    is on disk now, so the second reading is the rewritten one -- and the run going on is
    still the first reading, which is what the entry point that is running has to be.
    """
    flows = project / ".humanize/flows"
    written(flows, "target", _writes("as it was"))
    written(
        flows,
        "improves",
        '"""Rewrites the flow it is about to call."""\n\n'
        "from pathlib import Path\n\n"
        "from hmz.agents import AgentBase\n"
        "from hmz.flows import flow, load\n\n\n"
        "@flow\n"
        "def run(agents: tuple[AgentBase], task: str) -> None:\n"
        '    calling = load("target")\n'
        "    calling(agents, task)\n"
        '    Path("was.txt").write_text(Path("said.txt").read_text())\n'
        '    at = Path(".humanize/flows/target/__init__.py")\n'
        "    at.write_text(at.read_text().replace('as it was', 'as it became'))\n"
        "    calling(agents, task)\n",
    )

    Runner("local/improves", [_agent()]).run("go")

    assert (project / "was.txt").read_text() == "as it was"
    assert (project / "said.txt").read_text() == "as it became"


def test_a_flow_a_run_is_driving_is_read_again_by_the_run_after_it(
    project: Path,
) -> None:
    """A `Runner` is one run and holds the entry point it started; the next one reads again."""
    flows = project / ".humanize/flows"
    written(flows, "twice", _writes("first run"))

    Runner("local/twice", [_agent()]).run("go")
    assert (project / "said.txt").read_text() == "first run"

    written(flows, "twice", _writes("second run"))
    Runner("local/twice", [_agent()]).run("go")

    assert (project / "said.txt").read_text() == "second run"


def test_a_flow_that_writes_itself_a_skill_carries_it_at_the_next_call(
    project: Path,
) -> None:
    """The skills are worked out afresh at each call, being as much the flow as the file is."""
    flows = project / ".humanize/flows"
    written(
        flows,
        "brings",
        '"""Writes down what it is carrying."""\n\n'
        "from pathlib import Path\n\n"
        "from hmz.agents import AgentBase\n"
        "from hmz.flows import flow\n\n\n"
        "@flow\n"
        "def run(agents: tuple[AgentBase], task: str) -> None:\n"
        "    (agent,) = agents\n"
        "    Path('carried.txt').write_text(\n"
        "        ','.join(one.name for one in agent.loaded)\n"
        "    )\n",
        skills={"note-taking": "---\nname: note-taking\n---\n"},
    )
    calling = load("brings")

    calling([_agent()], "go")
    assert (project / "carried.txt").read_text() == "note-taking"

    written(
        flows,
        "brings",
        (flows / "brings/__init__.py").read_text(),
        skills={
            "note-taking": "---\nname: note-taking\n---\n",
            "reviewing": "---\n---\n",
        },
    )
    calling([_agent()], "go")

    assert (project / "carried.txt").read_text() == "note-taking,reviewing"


def test_a_flow_read_again_within_one_second_is_read_as_it_is_now(
    project: Path,
) -> None:
    """Nothing here is mtime-keyed, so two readings a moment apart are two readings.

    A flow rewritten by the agent it is driving is rewritten in the middle of a loop, which is
    where two edits within a second of each other actually happen. A cache keyed on when the
    file changed would run the first of them twice.
    """
    flows = project / ".humanize/flows"
    calling = None
    for said in ("a", "b", "c", "d"):
        written(flows, "quick", _writes(said))
        calling = calling or load("quick")
        calling([_agent()], "go")
        assert (project / "said.txt").read_text() == said


def test_a_flow_deleted_and_written_again_is_found_again(project: Path) -> None:
    """A handle survives the file going: the name is what it holds, and the name came back."""
    import shutil

    flows = project / ".humanize/flows"
    written(flows, "gone", _writes("here"))
    calling = load("gone")
    calling([_agent()], "go")

    shutil.rmtree(flows / "gone")
    with pytest.raises(NotAFlow):
        calling([_agent()], "go")

    written(flows, "gone", _writes("back"))
    calling([_agent()], "go")

    assert (project / "said.txt").read_text() == "back"
