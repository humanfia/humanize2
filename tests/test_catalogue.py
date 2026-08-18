"""The capability catalogue, held to saying only what this installation actually serves.

Honesty tests: every name the catalogue uses is a real moment, a real backend or a real
member of the interfaces a flow is written against, and every backend set is exactly what
the live driver classes declare. The catalogue is what a compiler steers by, and a
capability it invented -- or one that drifted from the drivers -- is a generated flow that
asks for what nothing serves.
"""

from __future__ import annotations

from hmz.agents import DRIVEN, EVERYWHERE, Moment
from hmz.flows import Agent, Person, Session
from hmz.flows.checking import briefed, catalogue, offered, surface


def test_every_conditional_moment_is_real_and_exactly_whose_drivers_say() -> None:
    told = {one.name: one for one in catalogue() if one.name.startswith("moment:")}
    outside = {one for one in Moment if one not in EVERYWHERE}
    assert set(told) == {f"moment:{one.value}" for one in outside}
    for moment in outside:
        assert told[f"moment:{moment.value}"].backends == frozenset(
            name for name, (cls, _) in DRIVEN.items() if moment in cls.moments
        )


def test_the_backend_facts_are_the_drivers_own() -> None:
    told = {one.name: one.backends for one in catalogue()}
    assert told["pursue"] == frozenset(
        name for name, (cls, _) in DRIVEN.items() if cls.pursues
    )
    assert told["goal"] == told["pursue"]
    # The two facts a session carries, checked against the backends known to carry them:
    # the sets themselves are read off the session classes, so what is pinned here is that
    # the reading reaches them at all.
    assert {"claude", "codex"} <= told["shapes"]
    assert "claude" in told["tools"]
    for one in catalogue():
        assert one.backends <= set(DRIVEN), one.name


def test_every_ask_the_catalogue_spells_is_on_the_interfaces() -> None:
    """The primitives are described in code, and the code has to be the real interface."""
    asks = surface(Agent) | surface(Session) | surface(Person)
    anchored = {
        "turns": "batch",
        "sessions": "new",
        "budgets": "spent",
        "hooks": "hooks",
        "board": "board",
        "clone": "clone",
        "skills": "loads",
        "pursue": "pursue",
        "tools": "offers",
    }
    said = {one.name: one.said for one in catalogue()}
    for name, member in anchored.items():
        assert member in asks
        assert member in said[name], name
    # And the ones whose anchor is the vocabulary hmz.flows hands through.
    offers = offered()
    for name, word in {
        "subflows": "load",
        "person": "Person",
        "state": "flow",
        "hooks": "Moment",
        "goal": "Goal",
    }.items():
        assert word in offers
        assert word in said[name], name


def test_the_moments_every_backend_reaches_are_everywhere() -> None:
    (moments,) = (one for one in catalogue() if one.name == "moments")
    assert moments.backends == frozenset()
    for one in EVERYWHERE:
        assert f"Moment.{one.name}" in moments.said


def test_the_briefing_mentions_every_capability_and_its_backends() -> None:
    page = briefed()
    for one in catalogue():
        assert f"- {one.name}" in page
        for backend in one.backends:
            assert backend in page
    # The split the compiler steers by: what needs declaring is under the second heading.
    assert "Every backend:" in page
    assert "Only some backends" in page
    assert page.index("- turns:") < page.index("Only some backends")
    assert page.index("Only some backends") < page.index("- pursue")
