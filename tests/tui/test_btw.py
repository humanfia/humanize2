"""Side questions read a flow without becoming turns of that flow."""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING, ClassVar

import pytest

from hmz.agents import AgentBase, AgentConfig, Event, SessionBase
from hmz.kept import Runs
from hmz.tui import Humanize
from hmz.tui.app import _OWN
from hmz.tui.btw import format_snapshot
from hmz.tui.selecting import Transcript

if TYPE_CHECKING:
    import os
    from collections.abc import Callable, Iterator

    from pydantic import BaseModel
    from textual.pilot import Pilot


CONFIG = AgentConfig(model="m", effort="high")


class SideSession(SessionBase):
    """A deterministic session that records the prompt and answers once."""

    prompts: ClassVar[list[str]] = []

    def _stream(
        self, prompt: str, *, schema: type[BaseModel] | None = None
    ) -> Iterator[Event]:
        del schema
        self.prompts.append(prompt)
        yield Event(kind="result", text="The builder is checking the test suite.")


class SideAgent(AgentBase):
    """An agent whose side turns never touch the filesystem."""

    def new(self, cwd: str | os.PathLike[str] | None = None) -> SideSession:
        return SideSession(self, cwd)


class MainSession(SideSession):
    """A held primary session, distinguishable from the side session."""


class MainAgent(SideAgent):
    def new(self, cwd: str | os.PathLike[str] | None = None) -> MainSession:
        return MainSession(self, cwd)


async def until(ready: Callable[[], bool], driver: Pilot[None]) -> None:
    """Pumps the interface until a background side turn has posted its answer."""
    deadline = time.monotonic() + 10.0
    while not ready() and time.monotonic() < deadline:
        await driver.pause()
        await asyncio.sleep(0.01)
    await driver.pause()


def _transcript(app: Humanize) -> str:
    return app.query_one(Transcript).text


@pytest.mark.timeout(60)
async def test_btw_is_offered_and_does_not_enqueue_a_primary_message() -> None:
    """The command is a side turn, not another line for the running flow."""
    app = Humanize()
    primary = MainAgent(CONFIG)
    held = primary.new()
    app._agents = [primary]
    app._models = [Runs("claude/m:high")]
    app._queued = ["keep working"]
    app._given = [(primary.id, "already handed")]
    app._monitor.begins(primary.id, "m")
    before_sessions = list(primary.sessions)
    SideSession.prompts.clear()

    async with app.run_test() as driver:
        await driver.press(*"/btw what is happening?")
        await driver.press("enter")
        await until(lambda: "The builder is checking" in _transcript(app), driver)

        assert app._queued == ["keep working"]
        assert app._given == [(primary.id, "already handed")]
        assert primary.sessions == before_sessions
        assert len(SideSession.prompts) == 1
        assert "what is happening?" in SideSession.prompts[0]
        assert "finished: no" in SideSession.prompts[0]

    del held


def test_btw_snapshot_format_includes_runtime_progress() -> None:
    """The prompt gives the side agent facts instead of guessing a static flow graph."""
    from hmz.tui.btw import AgentProgress, FlowSnapshot, Observation

    snapshot = FlowSnapshot(
        flow="review",
        task="run the tests",
        workspace="/tmp/project",
        elapsed=12.5,
        finished=False,
        agents=(AgentProgress("builder", "m", 2, True),),
        handovers=(("builder", "reviewer", 1),),
        observations=(Observation("builder", "tool", "Bash uv run pytest", 1.0),),
        waiting=1,
    )

    prompt = format_snapshot(snapshot, "is the reviewer waiting?")

    assert "flow: review" in prompt
    assert "builder: working, 2 turn(s)" in prompt
    assert "builder -> reviewer: 1 time(s)" in prompt
    assert "Bash uv run pytest" in prompt
    assert "is the reviewer waiting?" in prompt


def test_btw_is_listed_as_a_command() -> None:
    from hmz.tui.complete import about, offered, takes

    assert "btw" in _OWN
    assert about("btw")
    assert takes("btw") == "<question>"
    assert "/btw" in offered("/b", _OWN)
