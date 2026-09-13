"""The capability catalogue, held to saying only what this installation actually serves.

Honesty tests: every name the catalogue uses is a real moment, a real backend or a real
member of the interfaces a flow is written against, and every backend set is exactly what
the live driver classes declare or what the facts in `hmz.coganchor.backends` say. The catalogue is
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

from hmz.coganchor.agents import DRIVEN, EVERYWHERE, KINDS, Moment
from hmz.coganchor.backends import PROFILES, Bundled, Hooked, Profile, named
from hmz.flows import Agent, Person, Session
from hmz.flows.checking import briefed, catalogue, offered, surface

if TYPE_CHECKING:
    from hmz.coganchor.agents.base import SessionBase

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
    # Read off `hmz.coganchor.backends` rather than off the drivers: a fork is the CLI's own, so the
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
    # `bundles` is set on this profile and names nothing: what a fingerprint says is that a
    # patch could be found in what the CLI shipped, which the bytes on this machine decide
    # rather than the table -- so it is read back where a turn takes that road, not promised
    # here where a flow could ask for it and be given nothing.
    assert full.tags() == {
        "swarm",
        "search",
        "fork",
        "anchor:hooked",
        "anchor:preloaded",
    }


def test_each_layer_names_exactly_the_backends_it_reaches() -> None:
    """All three layers are built now, and each says which CLIs it reaches and no more.

    The hooked layer names the CLIs that take a hook table meant for a single run rather than
    every CLI that happens to have hooks at all; the preload layer, the four whose CLI is a
    plain Node script; the patched layer, the two shipped as one Bun file. A layer half filled
    in would read as a backend that had quietly gained one, which is what this refuses.
    """
    assert {one.name for one in PROFILES if one.hooks is not None} == {"claude", "qwen"}
    assert {one.name for one in PROFILES if one.preloads} == {
        "kimi",
        "mimo",
        "pi",
        "qwen",
    }
    assert {one.name for one in PROFILES if one.bundles} == {"claude", "opencode"}
    for one in PROFILES:
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
    # must not be listed at all, and one only some of them serve must be listed with exactly
    # those. The two universal ones always are: every backend is a command line spawned here,
    # and what a spawned turn runs is what an anchor traces. The other two are served by the
    # CLIs whose profile says so, and are listed against exactly those. There is no
    # `anchor:patched`: nothing takes a turn down that road yet, and a name here would be one
    # a flow could ask for and pass.
    assert set(told) == {
        "anchor:native-cli",
        "anchor:supervised",
        "anchor:hooked",
        "anchor:preloaded",
    }
    assert told["anchor:native-cli"].backends == frozenset()
    assert told["anchor:supervised"].backends == frozenset()
    assert told["anchor:hooked"].backends == frozenset({"claude", "qwen"})
    assert told["anchor:preloaded"].backends == frozenset(
        {"kimi", "mimo", "pi", "qwen"}
    )


#: What each backend's driver reports of what a turn cost, written out rather than read off
#: the drivers -- what the drivers say is what is on trial. `reasoning` is there only for the
#: three that count it beside the output rather than inside it; two say the input and the
#: output alone, each of them counting its cached reads inside the input; and Cursor reports
#: a duration and no tokens at all, which is a run whose every figure is a floor and which
#: says so.
_COUNTING: dict[str, set[str]] = {
    "agy": {"input", "output", "cache_read", "reasoning"},
    "claude": {"input", "output", "cache_read", "cache_write"},
    "codex": {"input", "output"},
    "cursor": set[str](),
    "dsh": {"input", "output", "cache_read", "cache_write"},
    "grok": {"input", "output", "cache_read", "cache_write"},
    "kimi": {"input", "output", "cache_read", "cache_write"},
    "mimo": {"input", "output", "cache_read", "cache_write", "reasoning"},
    "opencode": {"input", "output", "cache_read", "cache_write", "reasoning"},
    "pi": {"input", "output", "cache_read", "cache_write"},
    "qwen": {"input", "output", "cache_read", "cache_write"},
    "zcode": {"input", "output"},
}


def test_what_each_backend_counts_is_what_its_driver_says_it_counts() -> None:
    """And every word of it is a kind humanize has, rather than one CLI's own spelling."""
    assert {name: set(cls.counts) for name, (cls, _) in DRIVEN.items()} == _COUNTING
    for name, (cls, _) in DRIVEN.items():
        assert cls.counts <= set(KINDS), name


def test_each_kind_of_token_is_a_capability_and_whose_is_the_drivers_own() -> None:
    """A flow steering by what a turn cost has to be able to ask before it starts.

    A backend that never counts a kind answers nought for it exactly as one that spent
    nothing does, and a loop bounded by an output count on a backend that reports none is a
    loop that never ends.
    """
    told = {one.name: one for one in catalogue() if one.name.startswith("counts:")}
    assert set(told) == {f"counts:{kind}" for kind in KINDS}
    for kind in KINDS:
        assert told[f"counts:{kind}"].backends == frozenset(
            name for name, (cls, _) in DRIVEN.items() if kind in cls.counts
        )
    # The one that reports nothing is in none of them rather than quietly in all of them.
    for one in told.values():
        assert "cursor" not in one.backends
