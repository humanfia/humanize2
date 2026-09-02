"""The flows there are and the places they come from, reached through the SDK.

A command line, the interface and a daemon each ask this rather than the three modules behind
it, so what is checked here is that all three would get the same answer: a flowverse added
from here is one the listing offers a moment later, a flow's name resolves to the file it is
written in, and the handful of answers every way in needs -- what a flow takes, what it says
about itself, whether it can be picked up -- come off the flow rather than off a second copy
of the facts.

The flowverse fetched from is a git repository under `tmp_path`. Nothing here reaches a
network, and nothing starts a coding agent.
"""

from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING

import pytest

from hmz.flows import ENTRY, FLOWS, LOCAL, OFFICIAL, USER, NotAFlow
from hmz.sdk import Hmz
from tests.stubs import written

if TYPE_CHECKING:
    from pathlib import Path

#: A flow, as short as one can be, that says a line about itself and takes one agent.
FLOW = '''"""A flow of somebody else's."""

from hmz.flows import Agent, flow


@flow
def run(agents: tuple[Agent], task: str) -> None:
    (agent,) = agents
    agent.new()(task)
'''

#: One that says it can be picked up where the last run of it left off, and takes a setting.
KEEPS = '''"""A flow that is picked up."""

from typing import Any

from pydantic import BaseModel

from hmz.flows import Agent, flow


class Config(BaseModel):
    """What it takes."""

    rounds: int = 1


@flow(resumable=True)
def run(
    agents: tuple[Agent],
    task: str,
    config: Config | None = None,
    state: dict[str, Any] | None = None,
) -> None:
    (agent,) = agents
'''


def _git(*said: str, at: Path) -> None:
    """Runs one git command in a directory, failing the test if it fails."""
    subprocess.run(["git", "-C", str(at), *said], check=True, capture_output=True)


@pytest.fixture
def theirs(tmp_path: Path) -> Path:
    """A repository of one flow, to be fetched from."""
    where = tmp_path / "theirs"
    (where / FLOWS).mkdir(parents=True)
    written(where / FLOWS, "loop", FLOW)
    _git("init", "-b", "main", at=where)
    _git("config", "user.email", "t@example.com", at=where)
    _git("config", "user.name", "t", at=where)
    _git("add", "-A", at=where)
    _git("commit", "-m", "one flow", at=where)
    return where


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A project with two flows of its own, stood in."""
    where = tmp_path / "project"
    flows = where / ".humanize" / "flows"
    flows.mkdir(parents=True)
    written(flows, "mine", FLOW)
    written(flows, "kept", KEEPS)
    monkeypatch.chdir(where)
    return where


# ------------------------------------------------------------ where flows come from


def test_the_places_are_listed_in_the_order_their_flows_are_offered() -> None:
    assert [one.name for one in Hmz().verses.all()] == [OFFICIAL, LOCAL, USER]


def test_a_name_is_looked_up_in_a_different_order_than_the_flows_are_offered_in() -> (
    None
):
    """Nearest first: this project's own flows answer to a name before the package's do."""
    verses = Hmz().verses

    assert next(one.name for one in verses.nearest()) == LOCAL
    assert {one.name for one in verses.nearest()} == {one.name for one in verses.all()}


def test_a_place_is_found_by_name_and_a_name_none_answers_to_is_nothing() -> None:
    verses = Hmz().verses

    found = verses.find(OFFICIAL)

    assert found is not None
    assert found.name == OFFICIAL
    assert verses.find("not-a-flowverse") is None


def test_a_place_added_here_is_one_the_listing_offers_a_moment_later(
    theirs: Path,
) -> None:
    verses = Hmz().verses

    added = verses.add(str(theirs), "theirs")

    assert added.name == "theirs"
    assert added.fetched
    assert "theirs" in [one.name for one in verses.all()]
    assert [one.name for one in verses.holds(added)] == ["theirs/loop"]
    assert "theirs/loop" in [one.name for one in Hmz().flows.all()]


def test_a_place_is_kept_in_the_directory_this_says_whether_or_not_it_was_fetched() -> (
    None
):
    verses = Hmz().verses

    at = verses.where("theirs")

    assert not at.exists()
    assert at.name == "theirs"


def test_a_place_fetched_again_is_a_fetch_rather_than_a_merge(theirs: Path) -> None:
    verses = Hmz().verses
    verses.add(str(theirs), "theirs")
    written(theirs / FLOWS, "second", FLOW)
    _git("add", "-A", at=theirs)
    _git("commit", "-m", "another flow", at=theirs)

    again = verses.fetch("theirs")

    assert {one.name for one in verses.holds(again)} == {"theirs/loop", "theirs/second"}


def test_a_place_taken_away_is_gone_and_taking_it_away_twice_says_so(
    theirs: Path,
) -> None:
    verses = Hmz().verses
    verses.add(str(theirs), "theirs")

    assert verses.remove("theirs")

    assert verses.find("theirs") is None
    assert not verses.remove("theirs")


def test_the_ones_that_are_always_there_cannot_be_taken_away() -> None:
    with pytest.raises(ValueError, match="not one to take away"):
        Hmz().verses.remove(OFFICIAL)


def test_a_place_that_has_not_been_fetched_holds_nothing_rather_than_failing() -> None:
    """Except for the flows humanize keeps in the package, which are there either way."""
    verses = Hmz().verses
    official = verses.find(OFFICIAL)
    assert official is not None

    if official.fetched:
        pytest.skip("humanize's own flowverse has been fetched on this machine")
    assert [one.name for one in verses.holds(official)] == ["chat"]


def test_what_was_signed_into_a_url_is_not_what_is_printed_of_it() -> None:
    plain = Hmz().verses.plain("https://someone:secret@example.invalid/theirs.git")

    assert "secret" not in plain
    assert "example.invalid/theirs.git" in plain


# ------------------------------------------------------------------- the flows


def test_every_flow_there_is_to_run_is_offered_by_the_name_dash_f_takes(
    project: Path,
) -> None:
    offered = Hmz().flows.all()

    assert ("local", "local/mine") in [(one.whose, one.name) for one in offered]
    assert "chat" in [one.name for one in offered]


def test_a_flow_s_name_is_the_file_it_is_written_in(project: Path) -> None:
    found = Hmz().flows.find("mine")

    assert found == str((project / ".humanize/flows/mine" / ENTRY).resolve())


def test_a_name_nothing_answers_to_comes_back_as_the_name_it_was_asked_by(
    project: Path,
) -> None:
    """Rather than as an exception: whatever asked hears the name, and says so itself."""
    assert Hmz().flows.find("definitely-not-a-flow") == "definitely-not-a-flow"


def test_the_line_a_flow_says_about_itself_is_read_off_the_flow(project: Path) -> None:
    assert Hmz().flows.about("mine") == "A flow of somebody else's."


def test_every_agent_a_flow_needs_chosen_is_read_off_how_it_declared_them(
    project: Path,
) -> None:
    places = Hmz().flows.places("mine")

    assert len(places) == 1
    assert not places[0].person


def test_what_a_flow_can_be_set_up_with_is_its_own_model_and_none_for_one_that_takes_none(
    project: Path,
) -> None:
    flows = Hmz().flows

    model = flows.configures("kept")

    assert model is not None
    assert "rounds" in model.model_fields
    assert flows.configures("mine") is None


def test_whether_a_flow_can_be_picked_up_is_what_the_flow_said(project: Path) -> None:
    flows = Hmz().flows

    assert flows.resumes("kept")
    assert not flows.resumes("mine")


def test_a_flow_forked_into_this_project_is_offered_under_the_name_it_already_had(
    project: Path,
) -> None:
    """Yours are looked in first, so from then on that name means the copy."""
    flows = Hmz().flows

    where = flows.fork("chat")

    # Spelled as this project's own flows are spelled, which is from the project itself.
    assert where == ".humanize/flows/chat"
    assert (project / ".humanize" / "flows" / "chat").is_dir()
    assert flows.find("chat").startswith(str(project))


def test_forking_a_name_nothing_of_which_is_a_flow_is_refused(project: Path) -> None:
    with pytest.raises(ValueError, match="no flow called"):
        Hmz().flows.fork("definitely-not-a-flow")


def test_forking_over_a_flow_of_your_own_is_refused(project: Path) -> None:
    """A copy already there is one to edit, run or take away rather than to write over."""
    flows = Hmz().flows
    flows.fork("chat")

    with pytest.raises(ValueError, match="already a flow of your own"):
        flows.fork("chat")


def test_nothing_is_running_outside_a_run(project: Path) -> None:
    assert Hmz().flows.running() == ()


def test_the_places_flows_come_from_are_reached_from_the_flows_as_well() -> None:
    """One object, so that whatever holds the flows does not have to hold a second thing."""
    held = Hmz()

    assert [one.name for one in held.flows.verses.all()] == [
        one.name for one in held.verses.all()
    ]


# ------------------------------------------------------- what a flow is set up with


def test_what_a_flow_is_set_up_with_is_read_out_of_the_file_it_was_written_in(
    tmp_path: Path,
) -> None:
    said = tmp_path / "setup.yml"
    said.write_text("rounds: 3\nname: mine\n", encoding="utf-8")

    assert Hmz().flows.set_up_from(said) == ({"rounds": 3, "name": "mine"}, None)


def test_a_setup_file_that_is_empty_sets_nothing_up(tmp_path: Path) -> None:
    said = tmp_path / "setup.yml"
    said.write_text("", encoding="utf-8")

    assert Hmz().flows.set_up_from(said) == ({}, None)


def test_a_setup_file_that_is_not_a_mapping_is_refused(tmp_path: Path) -> None:
    said = tmp_path / "setup.yml"
    said.write_text("- one\n- two\n", encoding="utf-8")

    with pytest.raises(ValueError, match="mapping"):
        Hmz().flows.set_up_from(said)


# ------------------------------------------------------------- reading a flow first


def test_a_flow_that_will_run_is_read_and_nothing_is_found(project: Path) -> None:
    assert Hmz().flows.check("mine") == ()


def test_the_reading_that_executes_nothing_is_the_one_that_was_asked_for(
    project: Path,
) -> None:
    """`static` is the whole of what it keeps: pure `ast`, and the flow is never loaded."""
    assert Hmz().flows.check("mine", static=True) == ()


def test_a_flow_that_is_not_an_atlas_compiles_to_no_prophecy(project: Path) -> None:
    assert Hmz().flows.prophecy("mine") is None


def test_a_flow_that_is_not_an_atlas_has_no_prophecy_to_ship(project: Path) -> None:
    with pytest.raises(NotAFlow, match="not an atlas"):
        Hmz().flows.foretell("mine")
