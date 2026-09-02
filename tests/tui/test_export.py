"""The whole run, packaged up to send to whoever is being asked to fix something.

What is on the screen was never the run. The turns went to a coding agent that wrote its own
log, under an id of its own, and the run points at that log by a link -- which is worth nothing
the moment the archive leaves this machine. So a bundle follows every one of them and carries
what is behind it.

Asked for from `/epics`, which is where the runs of this directory are: exporting one belongs
beside gathering its trace, both being things done to a run that has already happened rather
than to whichever run this screen happens to be showing.

Driven headlessly, as every test of the interface is.
"""

from __future__ import annotations

import os
import sys
import tarfile
from typing import TYPE_CHECKING

import pytest

from hmz.runtime.epic import epics
from hmz.runtime.exporting import TRANSCRIPT
from hmz.tui import Humanize
from hmz.tui.pick import Does, Epics
from tests.stubs import written

from .test_app import _transcript, onto, rows, until

if TYPE_CHECKING:
    from pathlib import Path

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


@pytest.mark.timeout(60)
async def test_packaging_a_run_up_is_not_a_command_of_its_own() -> None:
    """It is a thing done to a run that has already happened, so it is offered where those are.

    A command would be about whichever run this screen happens to show, which is one of the
    runs in the list and not always the one somebody means -- and it would be a second way in
    to what `/epics` already offers about the run under its cursor.
    """
    from hmz.tui.app import _BY_NAME, _COMMANDS
    from hmz.tui.complete import offered

    assert "export" not in _BY_NAME
    assert "/export" not in offered("/", _COMMANDS)

    app = Humanize()
    async with app.run_test() as driver:
        await driver.press(*"/export")
        await driver.press("enter")
        await until(lambda: "no such command" in _transcript(app), driver)

        assert app.is_running  # a line that is not a command leaves the interface up


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
