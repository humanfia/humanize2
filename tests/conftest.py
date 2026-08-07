"""The one gate every suite's agent-driving tests share.

`pytest_addoption` is honoured only in a root conftest, so `--run-agents` has to live
here rather than beside the tests it gates; the `agent` marker it keys on is registered
by `pytest_configure` below.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

import hmz.models

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

    from hmz.backends import Model

#: Asking a backend what it runs, before the suite takes it away again. Held here so that a
#: test which is about the asking can have it back.
_ASKS = hmz.models.ask


@pytest.fixture(autouse=True)
def _humanize_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Keeps what outlives a run out of the home directory of whoever runs the tests.

    A run writes down its cycle and what was typed at it, and neither belongs in the history
    of the person who only asked for the suite to pass.

    And nothing here reports anything anywhere. Every test starts with a home nobody has
    answered a question in, which is what humanize reads as a first start -- so without this
    the suite would put the question to a machine nobody is sitting at, and a crash a test
    made on purpose would be filed as a crash.

    The mirrors coganchor has been pointed at are recorded outside the mirror itself, and so
    outlive the temporary directory a test made one in: a suite writing those into the cache
    of whoever ran it leaves one per test there forever, and reads one back as soon as pytest
    hands out a temporary path some run of nine days ago had already used.
    """
    monkeypatch.setenv("HUMANIZE_HOME", str(tmp_path / "humanize-home"))
    monkeypatch.setenv("HUMANIZE_SENTRY", "off")
    monkeypatch.setenv("HUMANIZE_SHADOWS", str(tmp_path / "shadows"))


@pytest.fixture(autouse=True)
def _nothing_running_yet() -> Iterator[None]:
    """Starts each test with no flow running, and leaves none behind.

    What is running is one list for the process. Several tests here hold a flow open on
    purpose -- two agents working at once is what half the interface is about -- and its
    thread is still alive when the test lets go of it, so the next test would find that flow
    running and say so on its own status line.
    """
    from hmz.flows import driving

    driving._RUNNING.clear()
    yield
    driving._RUNNING.clear()


@pytest.fixture(autouse=True)
def _asks_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stops anything here starting a real coding agent to find out what it runs.

    An account made is asked what it runs, and the interface asks every backend installed
    here as it opens. Both are right, and neither is something a suite should be doing on
    whoever's machine is running it -- so it is refused, and a test that is about the asking
    asks for `asking` and has it back.
    """

    def refuse(cli: str, provider: str = "", seconds: float = 0.0) -> tuple[Model, ...]:
        raise AssertionError(f"the suite does not start {cli} to ask what it runs")

    monkeypatch.setattr(hmz.models, "ask", refuse)


@pytest.fixture
def asking(_asks_nothing: None, monkeypatch: pytest.MonkeyPatch) -> None:
    """Gives this test the asking back, for one that is about a backend being asked.

    Named after the fixture that took it away, so that it is put back after rather than
    before: two fixtures setting one attribute is the order they run in.
    """
    monkeypatch.setattr(hmz.models, "ask", _ASKS)


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers", "agent: end-to-end test that drives a real coding agent binary"
    )


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--run-agents",
        action="store_true",
        default=False,
        help="also run the end-to-end tests that drive real coding agents",
    )


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    if config.getoption("--run-agents"):
        return
    skip = pytest.mark.skip(
        reason="needs --run-agents (drives real agents, costs tokens)"
    )
    for item in items:
        if "agent" in item.keywords:
            item.add_marker(skip)
