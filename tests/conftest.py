"""The one gate every subpackage's agent-driving tests share.

`pytest_addoption` is honoured only in a root conftest, so `--run-agents` has to live
here rather than beside the tests it gates; the `agent` marker it keys on is registered
by `pytest_configure` below.
"""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _amflows_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Keeps what outlives a run out of the home directory of whoever runs the tests.

    A run writes down its cycle and what was typed at it, and neither belongs in the history
    of the person who only asked for the suite to pass.
    """
    monkeypatch.setenv("AMFLOWS_HOME", str(tmp_path / "amflows-home"))


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
