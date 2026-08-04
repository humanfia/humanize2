"""The skills a flow brings, and the sessions they are mounted onto.

A flow is a directory, and `skills/` inside it is what that flow works by. Every session its
agents open is given them -- copied where that backend reads a project's own skills, for as
long as the session lives, and taken away again after -- so a flow carries what it needs
rather than expecting it to be installed on whoever's machine runs it. A flow may also name
skills that live in somebody else's repository, which are fetched and then mounted the same
way.
"""

from __future__ import annotations

import gc
import subprocess
from typing import TYPE_CHECKING

import pytest

from hmz.agents import AgentConfig
from hmz.agents.skills import Loaded
from hmz.flows.skills import brought, cached
from hmz.runner import NotAFlow, Runner
from tests.stubs import ShellAgent, written

if TYPE_CHECKING:
    from pathlib import Path

CONFIG = AgentConfig(model="m", effort="high")


class ClaudeAgent(ShellAgent):
    """A stand-in whose backend is one that reads a project's own skills.

    The mount is a fact about the CLI -- which directory it reads skills out of -- and a
    stand-in agent named after nothing has no such directory, so there would be nothing to
    watch. Named for the backend, which is how every agent here says which one it drives.
    """


#: A flow that does what it is told, in a session of its own: what the turn is is the shell
#: line the test hands it, so a test can have it look at what was mounted beside it.
DOES = '''"""Does the one thing it is told."""

from hmz.agents import AgentBase
from hmz.flows import flow


@flow
def run(agents: tuple[AgentBase], task: str) -> None:
    (agent,) = agents
    agent(task)
'''

#: The same, holding one session across two turns, so that two of them are open at once.
TWICE = '''"""Opens two sessions and does the thing in both."""

from hmz.agents import AgentBase
from hmz.flows import flow


@flow
def run(agents: tuple[AgentBase], task: str) -> None:
    (agent,) = agents
    one, other = agent.new(), agent.new()
    one(task)
    other(task)
    one.close()
    # The other is still open, so what they share is still there for it.
    other("ls .claude/skills > while-one-is-shut.txt")
    other.close()
'''


def skill(name: str, says: str = "Do the thing.") -> str:
    """One `SKILL.md`, as every one of these CLIs lays one out."""
    return f"---\nname: {name}\ndescription: does a thing\n---\n\n{says}\n"


def _repository(at: Path, *names: str) -> Path:
    """Somebody else's repository of skills, to be named by a flow and fetched from."""
    for name in names:
        (at / "skills" / name).mkdir(parents=True)
        (at / "skills" / name / "SKILL.md").write_text(skill(name))
    for said in (
        ["init", "-b", "main"],
        ["config", "user.email", "t@example.com"],
        ["config", "user.name", "t"],
        ["add", "-A"],
        ["commit", "-m", "skills"],
    ):
        subprocess.run(["git", "-C", str(at), *said], check=True, capture_output=True)
    return at


def test_a_flows_own_skills_are_the_ones_in_its_skills_directory(
    tmp_path: Path,
) -> None:
    """Found by looking, since they are in it: a flow does not declare what it holds."""
    at = written(
        tmp_path, "mine", DOES, {"note-taking": skill("note-taking"), "b": skill("b")}
    )

    assert [(one.name, one.whose) for one in brought(at)] == [
        ("b", "this flow"),
        ("note-taking", "this flow"),
    ]
    # And a flow that brings none says so rather than raising about a directory it has not.
    assert brought(written(tmp_path, "bare", DOES)) == []


def test_a_skill_in_somebody_elses_repository_is_named_and_fetched(
    tmp_path: Path,
) -> None:
    """A git URL and, after the `#`, which of that repository's skills is wanted."""
    theirs = _repository(tmp_path / "theirs", "deep-research", "shallow-research")
    at = written(tmp_path / "flows", "mine", DOES)

    (one,) = brought(at, [f"{theirs}#deep-research"])

    assert one.name == "deep-research"
    assert one.at == cached(str(theirs)) / "skills" / "deep-research"
    assert one.whose.endswith("#deep-research")
    # Named without one, every skill in it is brought.
    assert [one.name for one in brought(at, [str(theirs)])] == [
        "deep-research",
        "shallow-research",
    ]


def test_the_flows_own_wins_a_name_a_repository_also_uses(tmp_path: Path) -> None:
    """A fork that edited a skill meant the edited one."""
    theirs = _repository(tmp_path / "theirs", "deep-research")
    at = written(
        tmp_path / "flows",
        "mine",
        DOES,
        {"deep-research": skill("deep-research", says="Mine, not theirs.")},
    )

    (one,) = brought(at, [str(theirs)])

    assert one.whose == "this flow"
    assert "Mine, not theirs" in (one.at / "SKILL.md").read_text()


def test_a_repository_that_cannot_be_reached_stops_the_run_before_it_starts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A flow that works by a skill it has not got is not one to start and find out later."""
    monkeypatch.chdir(tmp_path)
    written(
        tmp_path / ".humanize/flows",
        "mine",
        DOES.replace("@flow\n", '@flow(skills=("/nowhere/at/all",))\n'),
    )

    with pytest.raises(NotAFlow):
        Runner("mine", [ClaudeAgent(CONFIG)])


def test_a_session_is_given_them_where_its_backend_reads_a_projects_own(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Mounted as the session opens, and gone once the session it was for has ended."""
    monkeypatch.chdir(tmp_path)
    written(
        tmp_path / ".humanize/flows",
        "mine",
        DOES,
        {"note-taking": skill("note-taking")},
    )

    Runner("mine", [ClaudeAgent(CONFIG)]).run(
        "ls .claude/skills > listed.txt; cat .claude/skills/note-taking/SKILL.md > read.txt"
    )
    gc.collect()  # the session the turn ran in, let go of by the flow

    assert (tmp_path / "listed.txt").read_text().split() == ["note-taking"]
    assert "does a thing" in (tmp_path / "read.txt").read_text()
    # Mounted rather than installed: what the flow brought is not left on the machine.
    assert not (tmp_path / ".claude").exists()


def test_a_projects_own_skill_of_that_name_is_left_alone(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """What the project keeps is the project's, and a flow does not write over it."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".claude" / "skills" / "note-taking").mkdir(parents=True)
    (tmp_path / ".claude" / "skills" / "note-taking" / "SKILL.md").write_text(
        skill("note-taking", says="The project's own.")
    )
    written(
        tmp_path / ".humanize/flows",
        "mine",
        DOES,
        {"note-taking": skill("note-taking")},
    )

    Runner("mine", [ClaudeAgent(CONFIG)]).run(
        "cat .claude/skills/note-taking/SKILL.md > read.txt"
    )
    gc.collect()

    assert "The project's own" in (tmp_path / "read.txt").read_text()
    # And it is still there afterwards: nothing of the project's was taken away with the mount.
    assert (tmp_path / ".claude" / "skills" / "note-taking" / "SKILL.md").is_file()


def test_two_sessions_of_one_flow_share_the_mount_until_the_last_is_done(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One closing must not take out from under the other what both were given."""
    monkeypatch.chdir(tmp_path)
    written(
        tmp_path / ".humanize/flows",
        "twice",
        TWICE,
        {"note-taking": skill("note-taking")},
    )

    Runner("twice", [ClaudeAgent(CONFIG)]).run("ls .claude/skills > listed.txt")
    gc.collect()

    assert (tmp_path / "while-one-is-shut.txt").read_text().split() == ["note-taking"]
    assert not (tmp_path / ".claude").exists()


def test_a_backend_that_reads_no_such_directory_carries_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A flow that brings skills brings that backend none, rather than failing to start."""
    monkeypatch.chdir(tmp_path)
    written(
        tmp_path / ".humanize/flows",
        "mine",
        DOES,
        {"note-taking": skill("note-taking")},
    )
    agent = ShellAgent(CONFIG)  # a backend with nowhere a skill of a flow's could go

    Runner("mine", [agent]).run("ls -a > listed.txt")

    assert agent.loaded == (
        Loaded(
            name="note-taking",
            at=tmp_path / ".humanize/flows/mine/skills/note-taking",
            whose="this flow",
        ),
    )
    assert ".claude" not in (tmp_path / "listed.txt").read_text().split()


def test_a_flow_is_copied_whole_into_this_projects_own(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Which is what a flow being a directory buys: a copy of one is a flow, skills and all."""
    from hmz.flows import find, fork

    monkeypatch.chdir(tmp_path)
    (tmp_path / "theirs").mkdir()
    written(tmp_path / "theirs", "mine", DOES, {"note-taking": skill("note-taking")})

    at = fork(str(tmp_path / "theirs" / "mine"))

    assert (tmp_path / at / "__init__.py").read_text() == DOES
    assert (tmp_path / at / "skills" / "note-taking" / "SKILL.md").is_file()
    # And your own are looked in first, so the name now means the copy.
    assert find("mine") == str(tmp_path / ".humanize/flows/mine/__init__.py")
    # One already copied is one to edit rather than one to write over.
    with pytest.raises(ValueError, match="already a flow of your own"):
        fork(str(tmp_path / "theirs" / "mine"))


def test_a_copy_is_yours_to_change_and_is_what_then_runs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A fetched flowverse is fetched over, so an edit that is to keep is an edit to a copy."""
    from hmz.flows import fork

    monkeypatch.chdir(tmp_path)
    (tmp_path / "theirs").mkdir()
    written(tmp_path / "theirs", "mine", DOES, {"note-taking": skill("note-taking")})
    fork(str(tmp_path / "theirs" / "mine"))
    at = tmp_path / ".humanize/flows/mine/skills/note-taking/SKILL.md"
    at.write_text(skill("note-taking", says="Changed, and mine."))

    Runner("mine", [ClaudeAgent(CONFIG)]).run(
        "cat .claude/skills/note-taking/SKILL.md > read.txt"
    )
    gc.collect()

    assert "Changed, and mine" in (tmp_path / "read.txt").read_text()
