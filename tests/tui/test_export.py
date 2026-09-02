"""`/export` -- the whole run, packaged up to send to whoever is being asked to fix something.

What is on the screen was never the run. The turns went to a coding agent that wrote its own
log, under an id of its own, and the run points at that log by a link -- which is worth nothing
the moment the archive leaves this machine. So `/export` follows every one of them and carries
what is behind it, with the transcript in beside them as the text it was written as.

Driven headlessly, as every test of the interface is.
"""

from __future__ import annotations

import json
import os
import sys
import tarfile
from typing import TYPE_CHECKING

import pytest

from hmz.runtime.epic import epics
from hmz.runtime.exporting import MANIFEST, TRANSCRIPT
from hmz.tui import Humanize
from hmz.tui.pick import Does, Epics
from tests.stubs import written

from .test_app import _transcript, onto, rows, until

if TYPE_CHECKING:
    from pathlib import Path

    from textual.pilot import Pilot

#: A flow that opens one session and says one thing, so that there is a run to package up.
PLAIN = '''"""Runs once, and says what it was told."""

from hmz.coganchor.agents import AgentBase
from hmz.flows import flow


@flow
def run(agents: tuple[AgentBase], task: str) -> None:
    agents[0].new()(task)
'''

#: A `claude` that answers whatever it is told and logs the session where Claude Code logs
#: one, since what a bundle carries is what the backend wrote rather than what humanize did.
QUIET = """
import json, os, pathlib, sys

flags = dict(zip(sys.argv, sys.argv[1:]))
ident = flags["--session-id"]
under = pathlib.Path(os.environ["CLAUDE_CONFIG_DIR"]) / "projects" / "-a-project"
under.mkdir(parents=True, exist_ok=True)
(under / (ident + ".jsonl")).write_text(
    json.dumps({"type": "user", "text": "what the agent was told"}) + "\\n"
)
print(json.dumps({"type": "system", "session_id": ident}), flush=True)
print(json.dumps({"type": "result", "result": "done"}), flush=True)
"""


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A directory with a flow in it, a fake `claude` to drive it, and a log for it to write."""
    binaries = tmp_path / "bin"
    binaries.mkdir()
    fake = binaries / "claude"
    fake.write_text(f"#!{sys.executable}\n{QUIET}")
    fake.chmod(0o755)
    monkeypatch.setenv("PATH", f"{binaries}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "claude-home"))
    where = tmp_path / ".humanize/flows"
    where.mkdir(parents=True)
    written(where, "plain", PLAIN)
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _ran(task: str) -> None:
    """Runs the flow here the way a command line would, so there is an epic to export."""
    from hmz.coganchor.agents import driver
    from hmz.runtime.runner import Runner

    agent, config = driver("claude")
    Runner("plain", [agent(config(model="m", effort="high"))]).run(task)


def _held(at: Path) -> dict[str, str]:
    """Everything one bundle holds, by the name it is under inside the run's own directory."""
    held: dict[str, str] = {}
    with tarfile.open(at) as opened:
        for one in opened.getmembers():
            handle = opened.extractfile(one)
            held[one.name.partition("/")[2]] = (
                handle.read().decode("utf-8") if handle is not None else ""
            )
    return held


async def _exports(app: Humanize, driver: Pilot[None]) -> None:
    """Types `/export` and waits for it to have said where the archive landed."""
    await driver.press(*"/export")
    await driver.press("enter")
    await until(lambda: "epic.tar.gz" in _transcript(app), driver)


@pytest.mark.timeout(90)
async def test_exporting_a_run_writes_the_whole_of_it(workspace: Path) -> None:
    """Its own record, the session the backend logged, and the screen beside them."""
    _ran("do the thing")

    app = Humanize()
    async with app.run_test() as driver:
        await driver.press("h", "i")
        await driver.press("enter")
        await until(lambda: "hi" in _transcript(app), driver)
        await _exports(app, driver)
        said = _transcript(app)

    (epic,) = epics(workspace)
    at = workspace / ".humanize" / f"{epic.name}.epic.tar.gz"
    assert at.is_file()
    assert str(at) in said or f"{epic.name}.epic.tar.gz" in said
    held = _held(at)
    assert "epic.jsonl" in held
    assert TRANSCRIPT in held
    assert [one for one in held if one.startswith("sessions/")], held
    # And the session came as its contents rather than as the link the epic keeps.
    log = next(one for one in held if one.startswith("sessions/"))
    assert held[log].strip()


@pytest.mark.timeout(90)
async def test_the_transcript_in_it_is_what_was_written(workspace: Path) -> None:
    """The text the transcript was written as, not the rows it was drawn as."""
    _ran("go")

    app = Humanize()
    async with app.run_test() as driver:
        await _exports(app, driver)
        said = _transcript(app)

    (epic,) = epics(workspace)
    held = _held(workspace / ".humanize" / f"{epic.name}.epic.tar.gz")
    # Exactly what the widget held when the key was pressed, which is where the two lines
    # the export itself wrote come after it.
    assert held[TRANSCRIPT]
    assert said.startswith(held[TRANSCRIPT])


@pytest.mark.timeout(90)
async def test_the_manifest_says_what_it_is_of(workspace: Path) -> None:
    """Which run, which flow, which agents, and what each backend was when it ran."""
    _ran("do the thing")

    app = Humanize()
    async with app.run_test() as driver:
        await _exports(app, driver)

    (epic,) = epics(workspace)
    said = json.loads(
        _held(workspace / ".humanize" / f"{epic.name}.epic.tar.gz")[MANIFEST]
    )
    assert said["epic"] == epic.name
    assert said["run"]["task"] == "do the thing"
    assert said["agents"][0]["backend"] == "claude"
    assert "claude" in said["backends"]


@pytest.mark.timeout(60)
async def test_a_directory_nothing_has_been_run_in_says_so(workspace: Path) -> None:
    """Rather than writing an archive of a run there is none of."""
    app = Humanize()
    async with app.run_test() as driver:
        await driver.press(*"/export")
        await driver.press("enter")
        await until(lambda: "nothing has been run here" in _transcript(app), driver)

    assert not list((workspace / ".humanize").glob("*.tar.gz"))


@pytest.mark.timeout(90)
async def test_a_run_out_of_the_list_is_exported_from_the_menu_under_it(
    workspace: Path,
) -> None:
    """Exporting an old run belongs beside gathering its trace: both are reading one back."""
    _ran("do the thing")

    app = Humanize()
    async with app.run_test() as driver:
        await driver.press(*"/epics")
        await driver.press("enter")
        await until(lambda: isinstance(app.screen, Epics), driver)
        sheet = app.screen
        await driver.press("enter")
        await until(lambda: isinstance(app.screen, Does), driver)
        assert "export" in rows(app)
        await onto(app, driver, "export")
        await driver.press("enter")
        await until(lambda: app.screen is sheet, driver)
        await until(lambda: "epic.tar.gz" in _transcript(app), driver)

    (epic,) = epics(workspace)
    at = workspace / ".humanize" / f"{epic.name}.epic.tar.gz"
    assert at.is_file()
    # No transcript in this one: what is on the screen is not this run, which may be a week old.
    assert TRANSCRIPT not in _held(at)
