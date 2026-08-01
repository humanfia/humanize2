"""Where flows come from when they come from somewhere else.

A flowverse is somebody's repository of flows, cloned under humanize's home and offered under
the name it is kept there. Two of them are always there whatever has been fetched -- the ones
in the package and the one the rest come from -- so what is checked here is that the list says
what there is to run rather than what has been downloaded, that fetching one twice is a fetch
rather than a merge, and that the two that are always there cannot be taken away.
"""

from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING

import pytest

from hmz.flows import BUILTIN, OFFICIAL, find, flowverses, found
from hmz.flows import verses as store

if TYPE_CHECKING:
    from pathlib import Path

#: A flow, as short as one can be: the file is what is being fetched, not what it does.
FLOW = '''"""A flow of somebody else's."""

from hmz.agents import AgentBase


def run(agents: tuple[AgentBase], task: str) -> None:
    (agent,) = agents
    agent.new()(task)
'''


def _git(*said: str, at: Path) -> None:
    """Runs one git command in a directory, failing the test if it fails."""
    subprocess.run(["git", "-C", str(at), *said], check=True, capture_output=True)


@pytest.fixture
def theirs(tmp_path: Path) -> Path:
    """A repository of two flows and something they import, to be fetched from."""
    where = tmp_path / "theirs"
    where.mkdir()
    (where / "loop.py").write_text(FLOW)
    (where / "review.py").write_text(FLOW)
    # Not a flow: what the flows beside it import, which is what the underscore means.
    (where / "_shared.py").write_text("HELD = 1\n")
    _git("init", "-b", "main", at=where)
    _git("config", "user.email", "t@example.com", at=where)
    _git("config", "user.name", "t", at=where)
    _git("add", "-A", at=where)
    _git("commit", "-m", "two flows", at=where)
    return where


def test_the_two_that_are_always_there_are_always_there() -> None:
    """One is in the package and one is where the rest come from, so neither is a fetch away."""
    listed = flowverses()

    assert [one.name for one in listed[:2]] == [BUILTIN, OFFICIAL]
    assert all(one.fixed for one in listed[:2])
    # The one nothing is fetched from is the one there is nothing to fetch: it is the package.
    assert listed[0].url == ""
    assert listed[0].fetched
    assert listed[1].url.endswith("humanfia/flowverse")


def test_the_official_one_is_offered_before_it_is_fetched() -> None:
    """Or a list of what there is to run would be a list of what has been downloaded."""
    (official,) = [one for one in flowverses() if one.name == OFFICIAL]

    assert not official.fetched
    assert store.flows(official) == []  # nothing in it yet, and nothing raised about it


@pytest.mark.parametrize("said", ["..", "one/two", "", ".", "/absolute"])
def test_a_name_that_is_not_one_directory_is_refused(said: str) -> None:
    """A flowverse is a directory under humanize's home, and a name that climbs out is not one."""
    with pytest.raises(ValueError, match="not a flowverse name"):
        store.where(said)


def test_one_that_was_added_is_offered_under_the_name_it_was_kept_under(
    theirs: Path,
) -> None:
    added = store.add(str(theirs))

    assert (
        added.name == "theirs"
    )  # the repository's own name, nobody having said otherwise
    assert added.fetched
    assert added.url == str(theirs)  # where it came from, as its own clone says
    assert not added.fixed
    assert [one.name for one in flowverses()] == [BUILTIN, OFFICIAL, "theirs"]
    # Its flows, less the file that is not one.
    assert store.flows(added) == ["loop", "review"]


def test_it_may_be_called_something_else_here(theirs: Path) -> None:
    """Two people's repositories may share a name; the name it is kept under is yours."""
    added = store.add(str(theirs), "mine")

    assert added.name == "mine"
    assert (store.under() / "mine" / "loop.py").is_file()


def test_adding_one_twice_is_refused(theirs: Path) -> None:
    store.add(str(theirs))

    with pytest.raises(ValueError, match="already a flowverse called"):
        store.add(str(theirs))


def test_a_repository_that_is_not_there_says_so(tmp_path: Path) -> None:
    """Said where it was asked for, rather than left as a flowverse with nothing in it."""
    with pytest.raises(OSError, match=r"git|repository"):
        store.add(str(tmp_path / "nowhere"))

    assert [one.name for one in flowverses()] == [BUILTIN, OFFICIAL]


def test_fetching_takes_what_the_repository_says_now(theirs: Path) -> None:
    """A flowverse is a copy of somebody's repository, so a fetch is what it says now."""
    store.add(str(theirs))
    (theirs / "loop.py").write_text(FLOW.replace("A flow", "The same flow, changed"))
    (theirs / "third.py").write_text(FLOW)
    _git("add", "-A", at=theirs)
    _git("commit", "-m", "another", at=theirs)

    again = store.fetch("theirs")

    assert store.flows(again) == ["loop", "review", "third"]
    assert "changed" in (again.at / "loop.py").read_text()


def test_fetching_one_that_was_never_fetched_clones_it(
    theirs: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Which is what `official` has done to it the first time somebody wants what is in it."""
    monkeypatch.setattr(store, "OFFICIAL_URL", str(theirs))
    before = store.named(OFFICIAL)
    assert before is not None
    assert not before.fetched

    official = store.fetch(OFFICIAL)

    assert official.fetched
    assert official.fixed  # and it is still the one that cannot be taken away
    assert store.flows(official) == ["loop", "review"]
    assert ("official", "official/loop", "A flow of somebody else's.") in found()


def test_one_that_was_added_may_be_taken_away(theirs: Path) -> None:
    store.add(str(theirs))

    assert store.remove("theirs")
    assert [one.name for one in flowverses()] == [BUILTIN, OFFICIAL]
    assert not store.remove("theirs")  # and again is not an error, it is already gone


@pytest.mark.parametrize("name", [BUILTIN, OFFICIAL])
def test_neither_of_humanize_s_own_may_be_taken_away(name: str) -> None:
    """One is the package and one is where the rest come from: both are always in the list."""
    with pytest.raises(ValueError, match="always here"):
        store.remove(name)


def test_there_is_nothing_to_fetch_for_the_ones_in_the_package() -> None:
    with pytest.raises(ValueError, match="nothing to fetch"):
        store.fetch(BUILTIN)


def test_fetching_something_nobody_added_says_so() -> None:
    with pytest.raises(ValueError, match="no flowverse called"):
        store.fetch("nobodys")


def test_its_flows_are_offered_under_its_name(theirs: Path) -> None:
    """`<flowverse>/<flow>`, so that two flowverses may hold a `loop` apiece."""
    store.add(str(theirs))

    listed = found()

    assert ("theirs", "theirs/loop", "A flow of somebody else's.") in listed
    # And the ones humanize ships are still called by a bare name.
    assert ("builtin", "chat") in [(one.whose, one.name) for one in listed]


def test_a_file_beside_the_flows_that_is_not_one_is_not_offered(theirs: Path) -> None:
    """A repository of flows holds other things: what sets their tests up, what they share."""
    (theirs / "conftest.py").write_text("HELD = 1\n")
    _git("add", "-A", at=theirs)
    _git("commit", "-m", "not a flow", at=theirs)
    store.add(str(theirs))

    assert [one.name for one in found() if one.whose == "theirs"] == [
        "theirs/loop",
        "theirs/review",
    ]


def test_a_flow_that_will_not_import_is_still_offered(theirs: Path) -> None:
    """It is a flow somebody named, and saying so where they pick it beats hiding it."""
    (theirs / "broken.py").write_text("import nothing_of_the_sort\n")
    _git("add", "-A", at=theirs)
    _git("commit", "-m", "a flow that will not load", at=theirs)
    store.add(str(theirs))

    assert ("theirs", "theirs/broken", "") in found()


def test_a_flow_of_a_flowverse_is_found_by_that_name(theirs: Path) -> None:
    store.add(str(theirs))

    assert find("theirs/loop") == str((store.under() / "theirs" / "loop.py").resolve())
    # And a name nothing answers to is handed back as it was given, to be said about.
    assert find("theirs/nothing") == "theirs/nothing"


def test_a_flow_of_your_own_still_wins_a_bare_name(
    theirs: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Nearest first: a flowverse is further away than this project's own flows directory."""
    store.add(str(theirs))
    project = tmp_path / "project"
    (project / ".humanize/flows").mkdir(parents=True)
    (project / ".humanize/flows/loop.py").write_text(FLOW)
    monkeypatch.chdir(project)

    assert find("loop") == str((project / ".humanize/flows/loop.py").resolve())
    # But the flowverse's own name for it is not a name anything of yours can stand in for.
    assert find("theirs/loop") == str((store.under() / "theirs" / "loop.py").resolve())


def test_a_flow_from_a_flowverse_runs_by_that_name(theirs: Path) -> None:
    """Which is the whole point of fetching one: `-f theirs/loop` is a flow to run."""
    from hmz.runner import drives

    store.add(str(theirs))

    assert drives("theirs/loop") == ("",)  # one agent, and the flow calls it nothing


def test_a_flowverse_that_has_not_been_fetched_says_so_rather_than_that_there_is_no_file() -> (
    None
):
    """The name is right and the download has not happened, which is a different thing."""
    from hmz.runner import NotAFlow, drives

    with pytest.raises(NotAFlow, match="has not been fetched yet"):
        drives(f"{OFFICIAL}/rlar")
