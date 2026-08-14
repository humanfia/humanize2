"""Which of a flow's skills one conversation carries, and changing it while it runs.

A flow brings the skills it works by and every session its agents open is given them. Which of
them is the session's own answer: an agent is what it was made as, and a conversation is a
thing that gets somewhere -- one that has finished reading the codebase and started writing the
tests wants the skill about writing them and no longer wants the eight about reading it.

So a session says which it carries, and may say it again: what is put where the backend reads
it is settled as each turn opens, so a session told between two turns is carrying what it was
told about on the turn after. What the flow brought is not changed by any of it -- that is the
flow's, and the same flow is driving every one of these conversations.
"""

from __future__ import annotations

import gc
from typing import TYPE_CHECKING

from hmz.agents import AgentConfig
from hmz.runner import Runner
from tests.stubs import ShellAgent, written

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

CONFIG = AgentConfig(model="m", effort="high")


class ClaudeAgent(ShellAgent):
    """A stand-in whose backend reads a project's own skills out of `.claude/skills`."""


def skill(name: str) -> str:
    """One `SKILL.md`, as every one of these CLIs reads a skill."""
    return f"---\nname: {name}\ndescription: does {name}\n---\n\n# {name}\n"


#: Three skills, so that carrying some of them is a thing that can be told apart from
#: carrying all of them and from carrying none.
BROUGHT = {one: skill(one) for one in ("reading", "writing", "reviewing")}

#: What each flow below is written into: a header naming what it drives, and a body.
HEAD = '''"""A flow that says what its sessions are carrying."""

from pathlib import Path

from hmz.agents import AgentBase
from hmz.flows import flow


@flow
def run(agents: tuple[AgentBase], task: str) -> None:
    (agent,) = agents
'''


def _flow(tmp_path: Path, body: str) -> None:
    """Writes the flow out, with the three skills beside it."""
    written(tmp_path / ".humanize/flows", "mine", HEAD + body, BROUGHT)


def _ran(tmp_path: Path, body: str) -> ShellAgent:
    """Runs that flow over one stand-in agent, and answers with the agent it drove."""
    _flow(tmp_path, body)
    agent = ClaudeAgent(CONFIG)
    Runner("mine", [agent]).run("go")
    gc.collect()  # whatever sessions the flow let go of
    return agent


def _listed(tmp_path: Path, name: str) -> list[str]:
    """What was in the mount directory when the turn that wrote that file ran."""
    return sorted((tmp_path / name).read_text().split())


def test_a_session_nobody_has_said_anything_about_carries_all_of_them(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Which is what every session of every flow has always carried."""
    monkeypatch.chdir(tmp_path)

    agent = _ran(
        tmp_path,
        "    session = agent.new()\n"
        "    session('ls .claude/skills > listed.txt')\n"
        "    Path('said.txt').write_text(','.join(session.skills))\n",
    )

    assert _listed(tmp_path, "listed.txt") == ["reading", "reviewing", "writing"]
    # In the flow's own order, which is the order they are on disk.
    assert (tmp_path / "said.txt").read_text() == "reading,reviewing,writing"
    assert [one.name for one in agent.loaded] == ["reading", "reviewing", "writing"]


def test_a_session_told_which_to_carry_carries_those_and_no_others(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The rest are not in the workspace at all: what is not carried is not there to read."""
    monkeypatch.chdir(tmp_path)

    _ran(
        tmp_path,
        "    session = agent.new()\n"
        "    session.loads(['writing'])\n"
        "    session('ls .claude/skills > listed.txt')\n",
    )

    assert _listed(tmp_path, "listed.txt") == ["writing"]


def test_a_session_told_between_two_turns_carries_it_on_the_turn_after(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Which is the whole of what makes this the session's rather than the agent's.

    The turn already running is not touched: what a turn is working by is not moved
    underneath it. The next one opens carrying what it was told about.
    """
    monkeypatch.chdir(tmp_path)

    _ran(
        tmp_path,
        "    session = agent.new()\n"
        "    session.loads(['reading'])\n"
        "    session('ls .claude/skills > first.txt')\n"
        "    session.loads(['writing'])\n"
        "    session('ls .claude/skills > second.txt')\n"
        "    session.loads(None)\n"
        "    session('ls .claude/skills > third.txt')\n",
    )

    assert _listed(tmp_path, "first.txt") == ["reading"]
    # The one it was carrying goes, and the one it was told about arrives.
    assert _listed(tmp_path, "second.txt") == ["writing"]
    # And nothing is every one of them again, which is where a session starts.
    assert _listed(tmp_path, "third.txt") == ["reading", "reviewing", "writing"]


def test_two_conversations_of_one_agent_carry_different_ones_at_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One agent, two conversations, and each is somewhere different in the work.

    They work in directories of their own here, since two sessions in one workspace share the
    one directory the backend reads: what is checked is that each carries its own answer.
    """
    monkeypatch.chdir(tmp_path)
    (tmp_path / "one").mkdir()
    (tmp_path / "two").mkdir()

    _ran(
        tmp_path,
        "    first = agent.new(cwd='one')\n"
        "    first.loads(['reading'])\n"
        "    second = agent.new(cwd='two')\n"
        "    second.loads(['writing', 'reviewing'])\n"
        "    first('ls .claude/skills > ../first.txt')\n"
        "    second('ls .claude/skills > ../second.txt')\n"
        "    Path('said.txt').write_text(\n"
        "        ';'.join([','.join(first.skills), ','.join(second.skills)])\n"
        "    )\n",
    )

    assert _listed(tmp_path, "first.txt") == ["reading"]
    assert _listed(tmp_path, "second.txt") == ["reviewing", "writing"]
    assert (tmp_path / "said.txt").read_text() == "reading;reviewing,writing"


def test_a_name_the_flow_does_not_bring_is_not_a_skill_to_invent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """What a session may carry is the flow's to say, so the rest is carried and it is not.

    A fork of a flow that dropped a skill is the case: a session asking for it by name is a
    session carrying what there is rather than a turn that will not run.
    """
    monkeypatch.chdir(tmp_path)

    _ran(
        tmp_path,
        "    session = agent.new()\n"
        "    session.loads(['writing', 'nothing-called-this'])\n"
        "    session('ls .claude/skills > listed.txt')\n"
        "    Path('said.txt').write_text(','.join(session.skills))\n",
    )

    assert _listed(tmp_path, "listed.txt") == ["writing"]
    assert (tmp_path / "said.txt").read_text() == "writing"


def test_a_session_carrying_none_of_them_has_nothing_in_the_workspace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An empty list is an answer: this conversation works by what the CLI already has."""
    monkeypatch.chdir(tmp_path)

    _ran(
        tmp_path,
        "    session = agent.new()\n"
        "    session.loads([])\n"
        "    session('ls .claude 2>/dev/null > listed.txt; true')\n"
        "    Path('said.txt').write_text(','.join(session.skills))\n",
    )

    assert _listed(tmp_path, "listed.txt") == []
    assert (tmp_path / "said.txt").read_text() == ""
    assert not (tmp_path / ".claude").exists()


def test_what_a_session_carries_is_gone_when_the_session_is(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Mounted rather than installed, whichever of them it was carrying."""
    monkeypatch.chdir(tmp_path)

    _ran(
        tmp_path,
        "    session = agent.new()\n"
        "    session.loads(['reading'])\n"
        "    session('ls .claude/skills > listed.txt')\n"
        "    session.close()\n",
    )

    assert _listed(tmp_path, "listed.txt") == ["reading"]
    assert not (tmp_path / ".claude").exists()


def test_a_session_closed_and_spoken_to_again_carries_what_it_was_told(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A stopped flow that carries on is the case, and what it carries is its own answer."""
    monkeypatch.chdir(tmp_path)

    _ran(
        tmp_path,
        "    session = agent.new()\n"
        "    session.loads(['reviewing'])\n"
        "    session('ls .claude/skills > first.txt')\n"
        "    session.close()\n"
        "    session('ls .claude/skills > second.txt')\n",
    )

    assert _listed(tmp_path, "first.txt") == ["reviewing"]
    assert _listed(tmp_path, "second.txt") == ["reviewing"]
