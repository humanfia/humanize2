"""The one import a flow writes, and what answers to it.

Three things nothing else checks. That `hmz.flows` really is the whole of what a flow needs --
which is only true while the flows humanize itself ships name nothing else, since they are the
worked example every other flow is copied from. That everything it says it offers is reachable,
the vocabulary being handed through by name rather than imported. And that the drivers answer
to the interfaces a flow is written against, which is stated for a type checker where the
interfaces are declared and is worth having said once where a run of the suite can hear it.
"""

from __future__ import annotations

import ast
from typing import TYPE_CHECKING, Protocol

import pytest

import hmz.flows
from hmz.agents import HumanAgent
from hmz.agents import Unrecoverable as AgentUnrecoverable
from hmz.flows import BUILTIN_AT, Agent, Person, Session
from hmz.flows import Unrecoverable as FlowUnrecoverable

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

#: What a flow may name of humanize's own, which is one thing. Everything else it needs --
#: the vocabulary a turn is described in, the facts about the CLIs, where humanize keeps what
#: outlives a run -- is handed through from there.
ONLY = "hmz.flows"


def _flows() -> Iterator[Path]:
    """Every Python file in the flows humanize itself ships."""
    return BUILTIN_AT.rglob("*.py")


def _named(source: Path) -> set[str]:
    """Every module of humanize's own that one file names in an import."""
    said: set[str] = set()
    for node in ast.walk(ast.parse(source.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            said.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            said.add(node.module)
    return {one for one in said if one.split(".")[0] == "hmz"}


@pytest.mark.parametrize("source", sorted(_flows()), ids=lambda one: one.parent.name)
def test_a_flow_humanize_ships_names_nothing_of_humanize_but_hmz_flows(
    source: Path,
) -> None:
    """These are the worked example; a flow copied from one inherits what it imports."""
    assert _named(source) <= {ONLY}


@pytest.mark.parametrize("name", sorted(hmz.flows.__all__))
def test_everything_it_offers_is_there(name: str) -> None:
    """A name in `__all__` with nothing behind it is an import that fails at the first run."""
    assert getattr(hmz.flows, name, None) is not None


def test_a_name_it_does_not_offer_is_an_attribute_error() -> None:
    """Handing names through must not turn a typo into something that is silently None."""
    with pytest.raises(AttributeError):
        _ = hmz.flows.ClaudeCodeAgent  # type: ignore[attr-defined]


def test_an_unrecoverable_turn_is_the_same_exception_a_flow_can_catch() -> None:
    """The flow-facing vocabulary is handed through, not redefined at the boundary."""
    assert FlowUnrecoverable is AgentUnrecoverable


def _members(protocol: type) -> set[str]:
    """What one interface asks for, by name.

    Args:
      protocol: The interface.

    Returns:
      One name per member it declares, its own and whatever it is itself an interface of.
      `__call__` is among them where it is declared, an agent and a session both being things
      a flow calls; the rest of the dunders are Python's and are not part of the contract.
    """
    said: set[str] = set()
    for one in protocol.__mro__:
        if one in (object, Protocol):
            continue
        held = set(vars(one)) | set(getattr(one, "__annotations__", {}))
        said.update(
            name for name in held if not name.startswith("_") or name == "__call__"
        )
    return said


def _answers(driver: object) -> set[str]:
    """What one driver has, by name.

    Args:
      driver: A driver, made rather than named: an attribute written in `__init__` -- the
        cycle the run is written into is one -- is on the agent rather than on its class, and
        is as much what the driver has as a method is.

    Returns:
      Everything reachable on it.
    """
    return set(dir(driver))


def test_the_drivers_answer_to_what_a_flow_drives() -> None:
    """Structurally, since the arrow points one way: `hmz.agents` never names a flow.

    Against a driver that was made rather than against the classes, and against the one driver
    that can be made without a coding agent behind it: the person is an `AgentBase` and their
    turn is a `SessionBase`, so what is checked here is the pair every backend is driven as.
    """
    person = HumanAgent()
    for interface, driver in (
        (Agent, person),
        (Person, person),
        (Session, person.new()),
    ):
        missing = {one for one in _members(interface) if one not in _answers(driver)}
        assert not missing, (
            f"{type(driver).__name__} does not answer to {interface.__name__}: {missing}"
        )
