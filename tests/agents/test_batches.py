"""Many turns at once: a batch of them, an awaited one, and the bookkeeping under both.

Nothing here starts a coding agent. What is checked is the fan-out itself -- that a batch is
one session per prompt and answers in the order it was asked, that it runs as wide as it was
told to and no wider, that a turn awaited hands the loop back while it takes, and that an
agent driving ten thousand of them at once still knows what it opened and what it cost.
"""

from __future__ import annotations

import asyncio
import json
import subprocess
import threading
import time
from typing import TYPE_CHECKING, ClassVar

import pytest
from pydantic import BaseModel

from hmz.agents import (
    WINDOW,
    AgentBase,
    AgentConfig,
    Event,
    Meter,
    Question,
    SessionBase,
    Stopped,
    Usage,
)
from tests.stubs import ShellAgent

if TYPE_CHECKING:
    import os
    from collections.abc import Callable, Iterator

CONFIG = AgentConfig(model="m", effort="high")

#: How many turns a test that means "more than a machine would ever really run at once" asks
#: for. Ten thousand of these are ten thousand objects and no processes at all, which is the
#: point: what is checked is this library's bookkeeping under that many, not the CLIs'.
CROWD = 10_000


def _nothing(_prompt: str) -> None:
    """What a turn does before it answers, where the test is only about the answer."""


def _itself(prompt: str) -> str:
    """What a turn answers with, where the test is only about which turn answered."""
    return prompt


def _answered(prompt: str) -> str:
    """A turn that says which prompt it was, so an answer cannot pass for another's."""
    return f"answered: {prompt}"


def _as_json(prompt: str) -> str:
    """A turn that answers as an object, for a flow that asked for a shape."""
    return json.dumps({"text": prompt})


class _InProcessSession(SessionBase):
    """A session that answers here, so that ten thousand of them cost ten thousand objects.

    What a turn does before it answers is the test's own: a barrier to wait on, a failure to
    raise, a moment to hold. Everything else -- the session opening under an id of its own,
    what it says it cost, the answer the turn ends on -- is what a backend does, said here.
    """

    #: Held to the shape rather than asked for it, so that what a turn is given is the prompt
    #: the test wrote and nothing else.
    shapes: ClassVar[bool] = True

    def _stream(
        self, prompt: str, *, schema: type[BaseModel] | None = None
    ) -> Iterator[Event]:
        del schema
        agent = self._agent
        assert isinstance(agent, _InProcessAgent)
        agent.doing(
            prompt
        )  # before the session opens: a turn that failed opened nothing
        if self._id is None:
            self._adopt(f"session-{agent.numbered()}")
        self._spends(Usage(input=10, output=5))
        yield Event(kind="result", text=agent.answers(prompt), spent=Usage(output=5))


class _InProcessAgent(AgentBase):
    """An agent whose turns run here, doing whatever the test hands it before they answer."""

    def __init__(
        self,
        *,
        doing: Callable[[str], None] | None = None,
        answers: Callable[[str], str] | None = None,
        name: str | None = None,
    ) -> None:
        """Initializes an agent that has opened nothing.

        Args:
          doing: What a turn does before it answers, which is where a test puts the waiting,
            the counting or the failing it is about. Nothing at all by default.
          answers: What a turn answers with, given the prompt. The prompt itself by default.
          name: What to call it.
        """
        super().__init__(CONFIG, name=name)
        self.doing: Callable[[str], None] = doing or _nothing
        self.answers: Callable[[str], str] = answers or _itself
        self.goals: list[str] = []
        self._counted = 0
        self._counting = threading.Lock()

    def numbered(self) -> int:
        """The next number, so that every session of this agent opens under one of its own."""
        with self._counting:
            self._counted += 1
            return self._counted

    def new(self, cwd: str | os.PathLike[str] | None = None) -> _InProcessSession:
        return _InProcessSession(self, cwd)


class _Widest:
    """How many turns were running at once, at the widest moment there was."""

    def __init__(self) -> None:
        self.now = 0
        self.widest = 0
        self._lock = threading.Lock()

    def holds(self, _prompt: str) -> None:
        """One turn, held long enough that whatever else is running is running beside it."""
        with self._lock:
            self.now += 1
            self.widest = max(self.widest, self.now)
        time.sleep(0.02)
        with self._lock:
            self.now -= 1


class _Landed:
    """How many turns got as far as answering, however they were started."""

    def __init__(self) -> None:
        self.count = 0
        self._lock = threading.Lock()

    def notes(self, _prompt: str) -> None:
        with self._lock:
            self.count += 1


def _watched(
    said: list[Event], whose: list[SessionBase | None] | None = None
) -> Callable[[AgentBase, SessionBase | None, Event], None]:
    """A watcher that keeps everything a turn of the agent said, whichever thread said it."""

    def heard(_agent: AgentBase, session: SessionBase | None, event: Event) -> None:
        said.append(event)
        if whose is not None:
            whose.append(session)

    return heard


def _explodes(at: str) -> Callable[[str], None]:
    """A turn that fails for one prompt and holds a moment for every other one."""

    def doing(prompt: str) -> None:
        if prompt == at:
            raise subprocess.CalledProcessError(3, ["agent"], "", "no")
        time.sleep(0.05)

    return doing


def _both(
    first: Callable[[str], None], then: Callable[[str], None]
) -> Callable[[str], None]:
    """Two things for a turn to do, in order, which is how a test asks for both."""

    def doing(prompt: str) -> None:
        first(prompt)
        then(prompt)

    return doing


def test_a_batch_is_one_turn_per_prompt_and_answers_in_the_order_it_was_asked() -> None:
    agent = _InProcessAgent(answers=_answered)
    asked = [f"prompt-{at}" for at in range(50)]

    answered = agent.batch(asked)

    assert answered == [f"answered: {prompt}" for prompt in asked]
    # A session apiece, none of them kept: which is what calling the agent is, fifty times at
    # once rather than fifty times over.
    assert len(set(agent.opened)) == 50
    assert agent.sessions == []


def test_a_batch_of_nothing_runs_nothing() -> None:
    agent = _InProcessAgent()

    assert agent.batch([]) == []
    assert agent.opened == []


def test_a_batch_runs_its_turns_at_once() -> None:
    """Every turn of a batch runs while every other one does, unless it was told a number.

    Checked with a barrier rather than a clock: if any turn of it were waiting for another to
    finish, none of them would ever arrive, and the barrier says so rather than the suite
    quietly getting slower.
    """
    together = threading.Barrier(64, timeout=30)

    def waits(_prompt: str) -> None:
        together.wait()

    agent = _InProcessAgent(doing=waits)

    answered = agent.batch([f"prompt-{at}" for at in range(64)])

    assert len(answered) == 64
    assert not together.broken


def test_a_batch_runs_as_many_at_once_as_it_was_told_to_and_no_more() -> None:
    widest = _Widest()
    agent = _InProcessAgent(doing=widest.holds)

    answered = agent.batch([f"prompt-{at}" for at in range(24)], at_once=4)

    assert len(answered) == 24
    assert widest.widest == 4


def test_a_batch_takes_the_shape_a_flow_asked_the_answers_in() -> None:
    class Review(BaseModel):
        done: bool
        notes: str

    agent = _InProcessAgent(
        answers=lambda prompt: json.dumps({"done": True, "notes": prompt})
    )

    reviews = agent.batch(["one", "two"], schema=Review)

    assert [review and review.notes for review in reviews] == ["one", "two"]
    assert all(review is not None and review.done for review in reviews)


def test_a_batch_that_failed_says_so_once_every_turn_of_it_has_landed() -> None:
    """A turn already running cannot be taken back, so the batch waits before it raises."""
    landed = _Landed()
    agent = _InProcessAgent(doing=_both(_explodes("prompt-3"), landed.notes))

    with pytest.raises(subprocess.CalledProcessError):
        agent.batch([f"prompt-{at}" for at in range(8)])

    assert landed.count == 7  # every turn but the one that failed


def test_a_batch_told_to_suppress_answers_with_nothing_for_the_turn_that_failed() -> (
    None
):
    agent = _InProcessAgent(doing=_explodes("prompt-3"))

    answered = agent.batch([f"prompt-{at}" for at in range(8)], suppress=True)

    assert answered[3] == ""  # the one that failed, and every other one landed
    assert [said for said in answered if said] == [
        f"prompt-{at}" for at in range(8) if at != 3
    ]
    assert len(agent.opened) == 7  # a turn that failed opened nothing


def test_a_stopped_agent_takes_no_batch_however_it_was_asked() -> None:
    agent = _InProcessAgent()
    agent.stop()

    # Not caught by `suppress`, which covers a turn that failed: a loop that carried on past
    # a stop would never end, and a batch is a loop with its rounds beside each other.
    with pytest.raises(Stopped):
        agent.batch(["one", "two"], suppress=True)


def test_batch_new_opens_as_many_sessions_as_it_was_asked_for() -> None:
    agent = _InProcessAgent()

    held = agent.batch_new(CROWD)

    assert len(held) == CROWD
    assert len({id(session) for session in held}) == CROWD  # every one its own
    assert agent.sessions == held  # oldest first, and all of them still the agent's
    assert agent.opened == []  # a session is not open until a turn has landed in it


def test_batch_new_of_nothing_opens_nothing() -> None:
    agent = _InProcessAgent()

    assert agent.batch_new(0) == []
    assert agent.batch_new(-5) == []
    assert agent.sessions == []


@pytest.mark.timeout(120, method="thread")
def test_an_agent_does_not_grow_by_ten_thousand_sessions_a_flow_dropped() -> None:
    """Dropping one of ten thousand costs what dropping one of two costs."""
    agent = _InProcessAgent()
    kept = agent.new()

    held = agent.batch_new(CROWD)
    del held

    assert agent.sessions == [kept]
    assert len(agent._sessions) == 1  # not even the bookkeeping is left behind


@pytest.mark.timeout(300, method="thread")
def test_ten_thousand_turns_at_once_are_ten_thousand_sessions_and_as_many_answers() -> (
    None
):
    agent = _InProcessAgent(answers=_answered)
    asked = [f"prompt-{at}" for at in range(CROWD)]

    answered = agent.batch(asked, at_once=256)

    assert answered == [f"answered: {prompt}" for prompt in asked]
    # What the run opened and what it cost, counted from every thread of it: a tally that
    # went through unlocked would come out short, and a trace of the run is built on it.
    assert len(set(agent.opened)) == CROWD
    assert agent.spent().output == CROWD * 5


@pytest.mark.timeout(300, method="thread")
def test_a_batch_of_real_processes_keeps_every_turn_apart() -> None:
    """The same fan-out through the plumbing a real backend runs on, rather than beside it.

    Two hundred turns, each of them a process of its own with both its streams teed back
    here: what is checked is that no answer arrives as another turn's, and that every session
    the batch opened is written down under the id its own turn landed with.
    """
    agent = ShellAgent(CONFIG)
    asked = [f"echo turn-{at}" for at in range(200)]

    answered = agent.batch(asked, at_once=32)

    assert answered == [f"turn-{at}" for at in range(200)]
    assert sorted(agent.opened) == sorted(f"turn-{at}" for at in range(200))


@pytest.mark.timeout(300, method="thread")
async def test_a_batch_of_real_processes_awaited_keeps_every_turn_apart() -> None:
    agent = ShellAgent(CONFIG)
    asked = [f"echo turn-{at}" for at in range(200)]

    answered = await agent.abatch(asked, at_once=32)

    assert answered == [f"turn-{at}" for at in range(200)]
    assert sorted(agent.opened) == sorted(f"turn-{at}" for at in range(200))


async def test_a_turn_awaited_is_the_same_turn() -> None:
    agent = _InProcessAgent(answers=_answered)

    assert await agent.aturn("the task") == "answered: the task"
    assert len(agent.opened) == 1  # a session of its own, as calling the agent is

    session = agent.new()
    assert await session.aturn("one") == "answered: one"
    assert await session.aturn("two") == "answered: two"
    assert len(agent.opened) == 2  # the one conversation, twice over


async def test_a_turn_awaited_takes_the_shape_and_suppresses_as_a_turn_does() -> None:
    class Said(BaseModel):
        text: str

    agent = _InProcessAgent(answers=_as_json)
    shaped = await agent.aturn("one", schema=Said)
    assert shaped is not None
    assert shaped.text == "one"

    failing = _InProcessAgent(doing=_explodes("boom"))
    assert await failing.aturn("boom", suppress=True) == ""
    with pytest.raises(subprocess.CalledProcessError):
        await failing.aturn("boom")


async def test_a_goal_awaited_is_the_backends_own_goal() -> None:
    class _Goal(_InProcessSession):
        def _pursue(self, objective: str) -> str:
            agent = self._agent
            assert isinstance(agent, _InProcessAgent)
            agent.goals.append(objective)
            return f"pursued: {objective}"

    class _GoalAgent(_InProcessAgent):
        pursues: ClassVar[bool] = True

        def new(self, cwd: str | os.PathLike[str] | None = None) -> _Goal:
            return _Goal(self, cwd)

    context: list[str] = []
    agent = _GoalAgent(doing=context.append)

    assert (
        await agent.apursue("get it done", context="the complete task")
        == "pursued: get it done"
    )
    assert (
        await agent.new().apursue("and again", context="more task material")
        == "pursued: and again"
    )
    assert context == ["the complete task", "more task material"]
    assert agent.goals == ["get it done", "and again"]

    failing = _GoalAgent(doing=_explodes("bad context"))
    assert (
        await failing.apursue("must not start", context="bad context", suppress=True)
        == ""
    )
    assert failing.goals == []


async def test_awaiting_a_turn_hands_the_loop_back_while_the_turn_takes() -> None:
    """A turn is minutes of waiting on a process, and a flow's loop is not to wait inside it."""
    holding = threading.Event()

    def waits(_prompt: str) -> None:
        holding.wait(30)

    agent = _InProcessAgent(doing=waits)
    turning = 0

    async def meanwhile() -> None:
        nonlocal turning
        while not holding.is_set():
            turning += 1
            await asyncio.sleep(0)

    async with asyncio.TaskGroup() as flowing:
        flowing.create_task(meanwhile())
        turn = flowing.create_task(agent.aturn("the task"))
        await asyncio.sleep(0.05)
        holding.set()

    assert turn.result() == "the task"
    assert turning > 1  # the loop kept turning while the turn was out on its own thread


async def test_turns_awaited_on_one_session_are_still_a_sequence() -> None:
    """One conversation is one conversation, however many of its turns are awaited at once."""
    overlapped = False
    running = 0
    counting = threading.Lock()

    def doing(_prompt: str) -> None:
        nonlocal overlapped, running
        with counting:
            running += 1
            overlapped = overlapped or running > 1
        time.sleep(0.01)
        with counting:
            running -= 1

    session = _InProcessAgent(doing=doing).new()

    answered = await asyncio.gather(*(session.aturn(f"turn-{at}") for at in range(8)))

    assert sorted(answered) == [f"turn-{at}" for at in range(8)]
    assert not overlapped


async def test_a_batch_awaited_answers_in_order_and_runs_at_once() -> None:
    together = threading.Barrier(32, timeout=30)

    def waits(_prompt: str) -> None:
        together.wait()

    agent = _InProcessAgent(doing=waits, answers=_answered)
    asked = [f"prompt-{at}" for at in range(32)]

    answered = await agent.abatch(asked)

    assert answered == [f"answered: {prompt}" for prompt in asked]
    assert not together.broken


async def test_a_batch_awaited_runs_as_many_at_once_as_it_was_told_to() -> None:
    widest = _Widest()
    agent = _InProcessAgent(doing=widest.holds)

    answered = await agent.abatch([f"prompt-{at}" for at in range(24)], at_once=4)

    assert len(answered) == 24
    assert widest.widest == 4


async def test_a_batch_awaited_takes_a_shape_and_suppresses() -> None:
    class Said(BaseModel):
        text: str

    agent = _InProcessAgent(answers=_as_json)
    shaped = await agent.abatch(["one", "two"], schema=Said)
    assert [said and said.text for said in shaped] == ["one", "two"]

    failing = _InProcessAgent(doing=_explodes("prompt-1"))
    answered = await failing.abatch([f"prompt-{at}" for at in range(3)], suppress=True)
    assert answered == ["prompt-0", "", "prompt-2"]


async def test_a_batch_awaited_that_failed_says_so_once_every_turn_has_landed() -> None:
    landed = _Landed()
    agent = _InProcessAgent(doing=_both(_explodes("prompt-3"), landed.notes))

    with pytest.raises(subprocess.CalledProcessError):
        await agent.abatch([f"prompt-{at}" for at in range(8)])

    # Nothing was left running with nobody waiting for it: a batch that let the first failure
    # out from under the others would strand every other turn of itself.
    assert landed.count == 7


async def test_a_batch_awaited_of_nothing_runs_nothing() -> None:
    assert await _InProcessAgent().abatch([]) == []


@pytest.mark.timeout(600, method="thread")
async def test_ten_thousand_turns_awaited_at_once_all_land() -> None:
    """The number this is all for: ten thousand conversations, every one of them answered.

    A thousand of them running at a time rather than ten thousand threads at a time, which is
    what `at_once` is a word on the call for: how wide a machine can go is a question about
    that machine, and asking for more than it will run at once is not a reason to lose any of
    the ten thousand.
    """
    agent = _InProcessAgent(answers=_answered)
    asked = [f"prompt-{at}" for at in range(CROWD)]

    answered = await agent.abatch(asked, at_once=1_000)

    assert answered == [f"answered: {prompt}" for prompt in asked]
    assert len(set(agent.opened)) == CROWD
    assert agent.spent().input == CROWD * 10


@pytest.mark.timeout(300, method="thread")
def test_what_an_agent_opened_is_every_session_whichever_thread_opened_it() -> None:
    """Two thousand turns at once, read from another thread while they are still landing."""
    agent = _InProcessAgent()
    watching: list[Event] = []
    faults: list[str] = []
    stop = threading.Event()

    def reads() -> None:
        widest = 0
        while not stop.is_set():
            said = agent.opened
            if len(said) < widest:
                faults.append("what an agent opened went backwards")
            if len(set(said)) != len(said):
                faults.append("a session was written down twice")
            widest = max(widest, len(said))
            len(agent.sessions)

    reader = threading.Thread(target=reads)
    reader.start()
    try:
        # Hung on while the turns are running, which is what an interface does to a flow that
        # has already started: neither the hanging nor the saying may lose the other.
        agent.watch(_watched(watching))
        agent.batch([f"prompt-{at}" for at in range(2_000)], at_once=64)
    finally:
        stop.set()
        reader.join()

    assert faults == []
    assert len(set(agent.opened)) == 2_000
    # Every turn is bracketed by the two events that say whose it was, and nothing watching
    # the agent lost one of them.
    assert sum(event.kind == "begins" for event in watching) == 2_000
    assert sum(event.kind == "ends" for event in watching) == 2_000


def test_what_is_watching_is_told_which_conversation_said_it() -> None:
    """An agent may be holding ten at once, and a watcher has to be able to tell them apart.

    To show one conversation rather than ten interleaved, and to have somewhere to say the
    next thing back to -- which is what attaching to one of them is.
    """
    agent = _InProcessAgent(answers=_answered)
    said: list[Event] = []
    whose: list[SessionBase | None] = []
    agent.watch(_watched(said, whose))
    one, two = agent.new(), agent.new()

    one("first")

    # Every event of a turn is that conversation's, the two that bracket it included.
    assert [event.kind for event in said] == ["begins", "result", "ends"]
    assert set(whose) == {one}

    said.clear()
    whose.clear()
    two("second")
    assert set(whose) == {two}

    # And what the agent says rather than one of them says so, by naming none.
    said.clear()
    whose.clear()
    agent.asked(Question(text="Which way?"))
    assert [event.kind for event in said] == ["asks"]
    assert whose == [None]


def test_a_meter_keeps_the_window_rather_than_the_whole_run() -> None:
    """A run nobody reads a rate off may not grow by every request it ever made."""
    meter = Meter()
    began = time.monotonic()

    for at in range(100):  # a thousand seconds of them, which is more than the window
        meter.spend(Usage(input=1, output=1), now=began + at * 10)

    assert len(meter._recent) <= WINDOW / 10 + 1
    assert all(when >= began + 990 - WINDOW for when, _, _ in meter._recent)
    assert meter.spent().output == 100  # and what the run came to is still all of it


def test_a_meter_counts_what_every_thread_spent() -> None:
    meter = Meter()

    def spends() -> None:
        for _ in range(500):
            meter.spend(Usage(input=2, output=1))

    spending = [threading.Thread(target=spends) for _ in range(16)]
    for thread in spending:
        thread.start()
    for thread in spending:
        thread.join()

    assert meter.spent().output == 16 * 500
    assert meter.spent().input == 16 * 1000
