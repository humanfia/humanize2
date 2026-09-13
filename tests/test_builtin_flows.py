"""The one flow humanize keeps in the package: what a run of it is, and what it leaves.

`chat` is one agent talking, and it is here rather than in the official flowverse because it is
what humanize does before anything has been fetched. Everything else humanize offers is in that
repository, and what those flows do is tested where they live.

Nothing here starts a coding agent. What a turn comes to is the stand-in's shell command, so a
task that exits non-zero is a turn that could not be taken -- which is the one thing this flow
has to tell apart from a conversation that is over.
"""

from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING

import pytest

from hmz.coganchor.agents import AgentConfig
from hmz.flows import resumes
from hmz.flows.builtin import chat
from hmz.runtime.epic import STATE, epics
from hmz.runtime.runner import Runner
from tests.stubs import ShellAgent

if TYPE_CHECKING:
    from pathlib import Path

CONFIG = AgentConfig(model="m", effort="high")

#: What the agent is set to do, which the stand-in runs as the shell command it is.
TASK = "echo working"

#: The conversation, by the name `-f` takes. Imported above rather than written out here: a
#: flow is loaded from its file when it is run, and a module nothing imported is one coverage
#: never sees run -- so the flow the interface opens on would read as untouched while these
#: tests were driving it.
CHAT = chat.__name__.rpartition(".")[2]

#: A turn that cannot be taken at all, which is what an account the backend refused looks like
#: from inside a flow.
FAILS = "exit 1"


@pytest.mark.timeout(60)
def test_a_conversation_is_not_a_thing_to_carry_on(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Chat is a conversation with the person, and there is no picking one of those up."""
    monkeypatch.chdir(tmp_path)

    assert not resumes(CHAT)


@pytest.mark.timeout(60)
def test_a_run_of_chat_leaves_nothing_behind_to_pick_up(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """What was said is the backend's log, and nobody is at the prompt to say more."""
    monkeypatch.chdir(tmp_path)

    Runner(CHAT, [ShellAgent(CONFIG)]).run(TASK)

    (epic,) = epics()
    assert not (epic / STATE).exists()


@pytest.mark.timeout(60)
def test_a_chat_whose_opening_turn_cannot_be_taken_says_so(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The first turn is the one that fails out loud, and the reason is the loop's own shape.

    Suppressed, a turn that failed answers with nothing -- and nothing is what the person
    answers with where nobody is at a prompt, which this flow reads as a conversation that is
    over. So a refused account and a finished conversation would be the same run: no output,
    no error and a clean exit, on a flow that had done none of what it was asked.
    """
    monkeypatch.chdir(tmp_path)

    with pytest.raises(subprocess.CalledProcessError):
        Runner(CHAT, [ShellAgent(CONFIG)]).run(FAILS)
