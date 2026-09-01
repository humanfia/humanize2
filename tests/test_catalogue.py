"""The capability catalogue, held to saying only what this installation actually serves.

Honesty tests: every name the catalogue uses is a real moment, a real backend or a real
member of the interfaces a flow is written against, and every backend set is exactly what
the live driver classes declare or what the facts in `hmz.backends` say. The catalogue is
what a compiler steers by, and a capability it invented -- or one that drifted from the
drivers -- is a generated flow that asks for what nothing serves.

The vocabulary those names are drawn from is covered here too: which backends steer a turn
already running, and which capability names a backend's own facts come to. What a capability
does once it has been asked for is covered where it is driven -- steering a real CLI in
`tests/agents` -- and not here.
"""

from __future__ import annotations

import inspect
import sys
from typing import TYPE_CHECKING

from hmz.agents import DRIVEN, EVERYWHERE, Moment
from hmz.backends import PROFILES, Bundled, Hooked, Profile, named
from hmz.flows import Agent, Person, Session
from hmz.flows.checking import briefed, catalogue, offered, surface

if TYPE_CHECKING:
    from hmz.agents.base import SessionBase

#: The backends whose turns can be talked to while they are running, which is the whole of
#: what `steers` claims: each holds its turn open somewhere a later word can reach -- a
#: process reading its stdin, a thread on an app server -- and answers to say the agent has
#: it. Written out rather than read off the classes, since what the classes say is what is
#: on trial.
_STEERING = {"claude", "codex", "kimi", "pi"}


def _sessions() -> dict[str, type[SessionBase]]:
    """The session class each driven backend answers with, as the catalogue reads them.

    Returns:
      The classes, by backend name, read off what each driver's `new` says it answers with.
    """
    held: dict[str, type[SessionBase]] = {}
    for name, (cls, _) in DRIVEN.items():
        told = inspect.signature(cls.new).return_annotation
        if isinstance(told, str):
            told = vars(sys.modules[cls.__module__])[told]
        held[name] = told
    return held


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
    assert {"claude", "codex"} <= told["shape"]
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
        "steer": "interject",
        "fork": "fork",
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


def test_a_backend_that_steers_a_running_turn_says_so_and_one_that_cannot_says_so() -> (
    None
):
    """The four that hold a turn open somewhere a later word reaches, and the rest."""
    sessions = _sessions()
    assert {name for name, one in sessions.items() if one.steers} == _STEERING
    # Each of the others refuses rather than queueing the word behind as another turn, which
    # is what `steers` being False is a promise about.
    for name, one in sessions.items():
        assert one.steers is (name in _STEERING), name


def test_the_catalogue_says_which_backends_steer_and_which_fork() -> None:
    told = {one.name: one.backends for one in catalogue()}
    assert told["steer"] == frozenset(_STEERING)
    # Read off `hmz.backends` rather than off the drivers: a fork is the CLI's own, so the
    # one place a fact about a CLI is written is where the catalogue asks.
    assert told["fork"] == frozenset(
        name for name in DRIVEN if (one := named(name)) is not None and one.forks
    )


def test_the_names_a_backend_serves_are_derived_from_its_own_facts() -> None:
    """`tags` says the vocabulary's word for a fact rather than storing the word too."""
    bare = Profile(
        name="bare", aliases=("bare",), home_var="", home_dir="", logs=(), efforts=()
    )
    assert bare.tags() == {"resume"}  # every CLI here resumes unless it says otherwise
    full = Profile(
        name="full",
        aliases=("full",),
        home_var="",
        home_dir="",
        logs=(),
        efforts=(),
        swarms=True,
        searches=True,
        forks=True,
        resumes=False,
        hooks=Hooked(seam="flag", name="--settings"),
        preloads="NODE_OPTIONS",
        bundles=(Bundled(path="dist/*/cli.js", says="spawnSync("),),
    )
    assert full.tags() == {
        "swarm",
        "search",
        "fork",
        "anchor:hooked",
        "anchor:preloaded",
        "anchor:patched",
    }


def test_only_the_bun_bundles_carry_a_patch_layer_and_the_rest_are_still_empty() -> (
    None
):
    """The patched layer reaches the two single-file Bun executables and no other backend yet.

    The hook and preload layers are still laid down empty -- their units have not landed -- so
    what a run reaches into is exactly the bundles fingerprinted here: Claude Code and opencode,
    the two CLIs shipped as one Bun file, and nothing that is a native binary or a plain script.
    """
    with_bundles = {one.name for one in PROFILES if one.bundles}
    assert with_bundles == {"claude", "opencode"}
    for one in PROFILES:
        assert one.hooks is None, one.name
        assert not one.preloads, one.name
        if one.bundles:
            # Every bundle written down fingerprints on a line rather than a path alone.
            assert all(bundle.says for bundle in one.bundles), one.name


def test_the_catalogue_names_where_an_agents_turns_may_land() -> None:
    told = {one.name: one for one in catalogue()}
    for name in ("remote", "isolated", "managed", "linux", "darwin"):
        # Every backend, since what a machine is is the same question whichever CLI is
        # driven on it -- and what needs saying is said where the place is declared.
        assert told[name].backends == frozenset(), name
        assert told[name].said


def test_an_anchor_nothing_serves_is_left_out_rather_than_read_as_everybodys() -> None:
    told = {one.name: one for one in catalogue() if one.name.startswith("anchor:")}
    # An empty backend set means every backend here, so a way in that has not been built
    # must not be listed at all. The two universal ones always are: every backend is a command
    # line spawned here, and what a spawned turn runs is what an anchor traces. The patched
    # layer is served by the two Bun bundles and so is listed against exactly those; the hook
    # and preload layers are not built yet and are absent.
    assert set(told) == {"anchor:native-cli", "anchor:supervised", "anchor:patched"}
    assert told["anchor:native-cli"].backends == frozenset()
    assert told["anchor:supervised"].backends == frozenset()
    assert told["anchor:patched"].backends == frozenset({"claude", "opencode"})
