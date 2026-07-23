"""The one gate every subpackage's agent-driving tests share.

`pytest_addoption` is honoured only in a root conftest, so `--run-agents` has to live
here rather than beside the tests it gates; the `agent` marker it keys on is registered
by `pytest_configure` below.
"""

from __future__ import annotations

import pytest


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
