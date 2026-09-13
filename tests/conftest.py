"""The one gate every suite's agent-driving tests share.

`pytest_addoption` is honoured only in a root conftest, so `--run-agents` has to live
here rather than beside the tests it gates; the `agent` marker it keys on is registered
by `pytest_configure` below.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

import hmz.coganchor.models
from hmz.runtime import telemetry

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

    from hmz.coganchor.backends import Model

#: Asking a backend what it runs, before the suite takes it away again. Held here so that a
#: test which is about the asking can have it back.
_ASKS = hmz.coganchor.models.ask


@pytest.fixture(autouse=True)
def _humanize_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Keeps what outlives a run out of the home directory of whoever runs the tests.

    A run writes down its epic and what was typed at it, and neither belongs in the history
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
    # And nothing here forks a run into the background. `hmz` with no command holds the run
    # apart from the terminal, which is right at a prompt and wrong in a suite: a test run
    # with `-s` from a real terminal would otherwise leave a detached interface behind it.
    # The tests that are about the holding turn it back on for themselves.
    monkeypatch.setenv("HUMANIZE_DAEMON", "off")
    # And nothing here fetches the unit prices a bill is worked out from. The interface asks
    # for those as it opens, which is right at a prompt and wrong in a suite: a test must not
    # reach anybody's network, and one that is about the fetching points this at a file.
    monkeypatch.setenv("HUMANIZE_PRICES", "off")
    # Whether the question about reporting has been answered is read once and kept for the
    # life of the process, which is right at a prompt and wrong across a suite: a test that
    # answers it -- and the ones about the question itself do -- leaves the answer behind for
    # every test after it, and the next one that expects to be asked is never asked at all.
    telemetry.again()


@pytest.fixture(autouse=True)
def _nothing_running_yet() -> Iterator[None]:
    """Starts each test with no flow running, on no branch, and leaves neither behind.

    What is running is the process's own, and the branch this task is on is the context's.
    Several tests here hold a flow open on purpose -- two agents working at once is what half
    the interface is about -- and its thread is still alive when the test lets go of it, so
    the next test would find that flow running, say so on its own status line, and call its
    own flows under it.
    """
    _forgotten()
    yield
    _forgotten()


def _forgotten() -> None:
    """Leaves nothing of one test's flows for the next one to run under."""
    from hmz.flows import driving

    driving._RUNNING.clear()
    driving._CLAIMED.clear()
    driving._WRITTEN.clear()
    driving._ON.set(None)


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

    monkeypatch.setattr(hmz.coganchor.models, "ask", refuse)


@pytest.fixture
def asking(_asks_nothing: None, monkeypatch: pytest.MonkeyPatch) -> None:
    """Gives this test the asking back, for one that is about a backend being asked.

    Named after the fixture that took it away, so that it is put back after rather than
    before: two fixtures setting one attribute is the order they run in.
    """
    monkeypatch.setattr(hmz.coganchor.models, "ask", _ASKS)


@pytest.fixture
def priced(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    """Puts one model's unit prices where the interface will read them.

    Written and fetched from a file rather than from the network: what a token costs is
    somebody else's list, and a suite must not go and ask them for it.

    Returns:
      The model that is now listed, at a dollar a million in and five a million out.
    """
    import json

    from hmz.coganchor import prices

    source = tmp_path / "prices-source.json"
    source.write_text(
        json.dumps(
            {
                "currency": "USD",
                "unit": "per 1M tokens",
                "versions": [
                    {
                        "date": "2026-09-10",
                        "models": [
                            {
                                "provider": "Anthropic",
                                "id": "claude-haiku-4.5",
                                "name": "Claude Haiku 4.5",
                                "pricingItems": [
                                    {"category": "input_tokens", "price": 1},
                                    {"category": "output_tokens", "price": 5},
                                    {"category": "cache_read_tokens", "price": 0.1},
                                    {"category": "cache_write_tokens", "price": 1.25},
                                ],
                            }
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv(prices.WHENCE, str(source))
    prices._tried = 0.0
    assert prices.refresh(wait=True)
    return "claude-haiku-4.5"


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
