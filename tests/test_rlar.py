"""The RLAR loop: an actor that remembers, a reviewer that does not, and the way out.

Nothing here runs a coding agent. What is checked is the shape of the loop: the actor keeps one
session across the rounds, each round's review is the actor's next prompt word for word, and the
run ends when the reviewer says the task is done rather than when the actor believes it is.
"""

from __future__ import annotations

import itertools
import json
from typing import TYPE_CHECKING

import pytest

from humanize.agents import AgentBase, AgentConfig, Event, SessionBase
from humanize.flows import rlar

if TYPE_CHECKING:
    import os
    from collections.abc import Callable, Iterator

    from pydantic import BaseModel

CONFIG = AgentConfig(model="m", effort="high")


class _Scripted(AgentBase):
    """An agent whose every turn is what the test said it would be."""

    def __init__(self, name: str, doing: Callable[[str], str]) -> None:
        super().__init__(CONFIG, name=name)
        self.doing = doing
        #: Every prompt it was given, in order, which is what a test reads the run off.
        self.heard: list[str] = []

    def new(self, cwd: str | os.PathLike[str] | None = None) -> _ScriptedSession:
        return _ScriptedSession(self, cwd)


#: What the stand-in names each session it opens, so that a test can count them: a flow that
#: holds one session and one that opens one a round are what this suite is about.
_NAMES = itertools.count(1)


class _ScriptedSession(SessionBase):
    def _stream(
        self, prompt: str, *, schema: type[BaseModel] | None = None
    ) -> Iterator[Event]:
        # A stand-in for a backend that cannot be held to a shape: it was asked for one in
        # the prompt, and what it says is read back.
        del schema
        agent = self._agent
        assert isinstance(agent, _Scripted)
        agent.heard.append(prompt)
        said = agent.doing(prompt)
        if said:  # a turn that landed opens the session, as it does on a real backend
            self._adopt(f"session-{next(_NAMES)}")
        yield Event(kind="result", text=said)


def _review(*, done: bool, notes: str) -> str:
    """One review, as the reviewer is held to answer it."""
    return json.dumps({"done": done, "notes": notes})


def _slept(seconds: float) -> None:
    """Stands in for the wait between rounds, which is for a real agent."""


@pytest.fixture(autouse=True)
def _no_waiting(monkeypatch: pytest.MonkeyPatch) -> None:
    """The five seconds between rounds are for a real agent, not for a suite."""
    monkeypatch.setattr(rlar.time, "sleep", _slept)


def test_the_review_is_the_actors_next_prompt_and_the_reviewer_ends_the_run() -> None:
    rounds = {"at": 0}

    def reviewing(_: str) -> str:
        rounds["at"] += 1
        if rounds["at"] < 2:
            return _review(
                done=False, notes="undo works, redo does not: see editor.py:40"
            )
        return _review(done=True, notes="both work, and the tests cover them")

    actor = _Scripted("actor", lambda _: "done what I could")
    reviewer = _Scripted("reviewer", reviewing)

    rlar.run(rlar.Agents(actor=actor, reviewer=reviewer), "add undo/redo")

    # The task opens the run, and what the reviewer said is the next prompt, word for word.
    assert actor.heard == [
        "add undo/redo",
        "undo works, redo does not: see editor.py:40",
    ]
    # One session, held across the rounds: the actor is the side that has to remember.
    assert len(actor.opened) == 1
    # And a new one per round for the reviewer, which is the side that must not.
    assert len(reviewer.opened) == 2
    # Handed the task each time, never having seen it.
    assert all(prompt.startswith(rlar.REVIEW_PROMPT) for prompt in reviewer.heard)
    assert all("add undo/redo" in prompt for prompt in reviewer.heard)


def test_a_review_that_never_arrived_leaves_the_round_to_be_taken_again() -> None:
    """A turn that failed, and an answer that is not a review, are the same thing here."""
    rounds = {"at": 0}

    def reviewing(_: str) -> str:
        rounds["at"] += 1
        if rounds["at"] < 2:
            return "I could not tell, sorry."  # not a review, whatever else it is
        return _review(done=True, notes="it holds")

    actor = _Scripted("actor", lambda _: "done what I could")

    rlar.run(
        rlar.Agents(actor=actor, reviewer=_Scripted("reviewer", reviewing)),
        "add undo/redo",
    )

    # The actor is asked the same thing again rather than sent on by a review nobody wrote.
    assert actor.heard == ["add undo/redo", "add undo/redo"]


def test_a_turn_that_failed_is_not_reviewed() -> None:
    """Only a landed turn earns a review: there is nothing yet for a reviewer to read."""
    turns = {"at": 0}

    def working(_: str) -> str:
        turns["at"] += 1
        return "" if turns["at"] == 1 else "there you go"

    reviewer = _Scripted("reviewer", lambda _: _review(done=True, notes="it holds"))

    rlar.run(
        rlar.Agents(actor=_Scripted("actor", working), reviewer=reviewer), "add undo"
    )

    assert len(reviewer.heard) == 1  # the first round wrote nothing to review
