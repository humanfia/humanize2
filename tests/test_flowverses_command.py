"""`hmz flowverses` -- where flows come from, said as arguments rather than walked.

What each of these lines actually does to the clone under humanize's home is the store's, and
is checked in `test_flowverses.py`. What is checked here is the line: that it reaches the same
store the interface's `/flow` walks, that a flowverse added by one is a flow the rest of
humanize can find by name, that a line which cannot be carried out says so rather than raising
at whoever typed it, and that every name it prints is one `-f` would take.

Where the reading happens is checked here too, both halves of it: `show` imports the files,
because what a file holds is not a fact its name carries, and nothing else does -- a repository
just cloned off the internet is not one to run unasked.
"""

from __future__ import annotations

import shutil
import subprocess
from typing import TYPE_CHECKING

import pytest

from hmz import cli, flows
from hmz.flows import ENTRY
from hmz.flows import verses as store
from tests.stubs import written
from tests.test_flowverses import FLOW

if TYPE_CHECKING:
    from pathlib import Path

#: One file holding two flows, each called `<file>:<inside>`. What makes a filename the wrong
#: thing to build a flow name out of.
MANY = '''"""Two phases of one thing."""

from hmz.agents import AgentBase
from hmz.flows import flow


@flow(name="first")
def first(agents: tuple[AgentBase], task: str) -> None:
    """Opens it."""
    (agent,) = agents
    agent.new()(task)


@flow(name="second")
def second(agents: tuple[AgentBase], task: str) -> None:
    """Closes it."""
    (agent,) = agents
    agent.new()(task)
'''


def run(*argv: str) -> int:
    """Carries out one `hmz flowverses` line, as `hmz` itself would."""
    return cli.main(["flowverses", *argv])


def _git(*said: str, at: Path) -> None:
    """Runs one git command in a directory, failing the test if it fails."""
    subprocess.run(["git", "-C", str(at), *said], check=True, capture_output=True)


def _commit(at: Path, why: str) -> None:
    """Writes down whatever is in a repository just now."""
    _git("add", "-A", at=at)
    _git("commit", "-m", why, at=at)


@pytest.fixture
def theirs(tmp_path: Path) -> Path:
    """A repository of two flows and something they import, to be fetched from."""
    where = tmp_path / "theirs"
    (where / store.FLOWS).mkdir(parents=True)
    written(where / store.FLOWS, "loop", FLOW)
    written(where / store.FLOWS, "review", FLOW)
    # Not a flow: what the flows beside it import, which is what the underscore means.
    (where / store.FLOWS / "_shared.py").write_text("HELD = 1\n")
    _git("init", "-b", "main", at=where)
    _git("config", "user.email", "t@example.com", at=where)
    _git("config", "user.name", "t", at=where)
    _commit(where, "two flows")
    return where


def test_a_line_naming_no_command_lists_what_there_is(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """As `hmz providers` does: the question a bare noun asks is what there is."""
    assert run() == 0

    shown = capsys.readouterr().out
    assert store.BUILTIN in shown
    assert store.OFFICIAL in shown


def test_the_one_the_rest_come_from_is_listed_before_it_is_fetched(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A list of what there is to run is not a list of what has been downloaded."""
    assert run("list") == 0

    official = next(
        line for line in capsys.readouterr().out.splitlines() if store.OFFICIAL in line
    )
    assert "not fetched" in official
    assert "humanfia/flowverse" in official


def test_what_was_added_is_listed_as_fetched_and_where_from(
    theirs: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert run("add", str(theirs), "mine") == 0
    made = capsys.readouterr().out
    assert "mine is fetched into" in made
    # Where to ask what it holds, rather than the answer: reading it is a line of its own.
    assert "hmz flowverses show mine" in made

    assert run("list") == 0

    mine = next(line for line in capsys.readouterr().out.splitlines() if "mine" in line)
    assert "fetched" in mine
    assert str(theirs) in mine


def test_what_was_added_is_a_flow_the_rest_of_humanize_finds_by_name(
    theirs: Path,
) -> None:
    """Which is the whole point of adding one: the line is a different way to the same store."""
    assert run("add", str(theirs), "mine") == 0

    assert flows.find("mine/loop").endswith(f"mine/{store.FLOWS}/loop/{ENTRY}")
    assert [one.name for one in flows.found() if one.whose == "mine"] == [
        "mine/loop",
        "mine/review",
    ]


def test_a_flowverse_is_called_what_its_repository_is_called_when_nothing_says_otherwise(
    theirs: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """As `git clone` names the directory it makes, and for the same reason."""
    assert run("add", str(theirs)) == 0

    assert "theirs is fetched into" in capsys.readouterr().out
    assert store.named("theirs") is not None


def test_what_one_holds_is_shown_under_the_name_each_flow_is_offered_by(
    theirs: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """`mine/loop` rather than `loop`: the spelling `-f` takes, which nothing stands in for."""
    assert run("add", str(theirs), "mine") == 0
    capsys.readouterr()

    assert run("show", "mine") == 0

    shown = capsys.readouterr().out
    assert "holds       mine/loop" in shown
    assert "holds       mine/review" in shown
    # What the flows beside them import is not one of them, and is not offered as one.
    assert "_shared" not in shown
    assert str(theirs) in shown


def test_every_name_shown_is_a_name_the_rest_of_humanize_offers(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The one thing this command must never get wrong: a name `-f` would refuse.

    A filename is not a flow name. One file may hold several flows, each called
    `<file>:<inside>`, and the file beside them may hold none at all -- a `conftest.py` is not
    a flow however much its name looks like one. So what is shown is asked of the same place
    the rest of humanize asks, and this pins the two together.
    """
    where = tmp_path / "several"
    (where / store.FLOWS).mkdir(parents=True)
    written(where / store.FLOWS, "phases", MANY)
    written(where / store.FLOWS, "one", FLOW)
    # Beside the flows, and not one: it runs, and leaves no flow behind.
    (where / store.FLOWS / "conftest.py").write_text(
        '"""Sets their tests up, and is not a flow."""\n'
    )
    _git("init", "-b", "main", at=where)
    _git("config", "user.email", "t@example.com", at=where)
    _git("config", "user.name", "t", at=where)
    _commit(where, "two flows in one file, one in another, and a conftest")

    assert run("add", str(where), "several") == 0
    capsys.readouterr()
    assert run("show", "several") == 0

    shown = [
        line.split()[1]
        for line in capsys.readouterr().out.splitlines()
        if line.startswith("holds")
    ]
    assert shown == [one.name for one in flows.found() if one.whose == "several"]
    assert shown == ["several/one", "several/phases:first", "several/phases:second"]
    # The file that holds no flow is not offered as one, however much its name looks like it.
    assert not any("conftest" in name for name in shown)


def test_the_flows_humanize_ships_are_shown_by_the_bare_names_they_are_offered_by(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Nothing was fetched for them, so nothing qualifies them: `chat`, not `builtin/chat`."""
    assert run("show", store.BUILTIN) == 0

    shown = capsys.readouterr().out
    assert "holds       chat" in shown
    assert f"holds       {store.BUILTIN}/" not in shown
    # Fetched from nowhere, because they are in the package rather than in a repository.
    assert "the flows humanize ships" in shown
    # And the rest of what `show` says about one, each of which is a line somebody reads.
    builtin = store.named(store.BUILTIN)
    assert builtin is not None
    assert f"kept in     {builtin.at}" in shown
    assert "always here" in shown


def test_one_that_has_not_been_fetched_says_so_rather_than_saying_it_holds_nothing(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert run("show", store.OFFICIAL) == 0

    shown = capsys.readouterr().out
    assert "fetched     no" in shown
    assert f"hmz flowverses fetch {store.OFFICIAL}" in shown


def test_fetching_again_takes_what_the_repository_now_holds(
    theirs: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A flowverse is a copy of somebody else's repository, so a fetch is what they now have."""
    assert run("add", str(theirs), "mine") == 0
    written(theirs / store.FLOWS, "nightly", FLOW)
    shutil.rmtree(theirs / store.FLOWS / "review")
    _commit(theirs, "one more, one fewer")
    capsys.readouterr()

    assert run("fetch", "mine") == 0

    assert "mine is fetched from" in capsys.readouterr().out
    assert run("show", "mine") == 0
    shown = capsys.readouterr().out
    assert "mine/nightly" in shown
    assert "mine/review" not in shown


def test_taking_one_away_takes_its_flows_with_it(
    theirs: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert run("add", str(theirs), "mine") == 0
    kept = store.where("mine")
    capsys.readouterr()

    assert run("remove", "mine") == 0

    assert "mine is gone" in capsys.readouterr().out
    assert not kept.exists()
    assert store.named("mine") is None


@pytest.mark.parametrize("quietly", ["-q", "--quiet"])
def test_the_quiet_list_is_one_name_a_line_and_nothing_else(
    quietly: str, theirs: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A list a script reads is a list of one thing a line, on either spelling of the flag.

    Split on lines rather than on whitespace: a line apiece is what is promised, and a check
    that split on spaces would pass just as happily if they all came out on one.
    """
    assert run("add", str(theirs), "mine") == 0
    capsys.readouterr()

    assert run("list", quietly) == 0

    assert capsys.readouterr().out.splitlines() == [
        store.BUILTIN,
        store.OFFICIAL,
        "mine",
    ]


def test_adding_one_and_listing_them_run_nothing_in_any_of_them(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Reading a flow means running it, and neither of those lines was asked to run anything.

    A repository that has just been cloned off the internet is the last thing to import
    unasked: fetching one is not the same as saying to run it this second, and listing which
    places there are is not asking about any of them.
    """
    ran = _loud(tmp_path)

    assert run("add", str(tmp_path / "loud"), "loud") == 0
    assert run("list") == 0

    assert not ran.exists()
    # And it says where to ask rather than reading it to answer now.
    assert "hmz flowverses show loud" in capsys.readouterr().out


def test_asking_what_one_holds_is_the_line_that_reads_it(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Which is the honest half of the same contract, and the interface's own behaviour.

    What a file holds is not a fact its name carries, so there is no cheap answer to what `-f`
    would take -- only an import. It happens here, where it was asked for, and nowhere else.
    """
    ran = _loud(tmp_path)
    assert run("add", str(tmp_path / "loud"), "loud") == 0
    assert not ran.exists()
    capsys.readouterr()

    assert run("show", "loud") == 0

    assert ran.exists(), "show says what -f takes, which it can only do by reading them"
    # It ran, and left no flow behind, so it is not offered as one.
    assert "holds       nothing that is a flow" in capsys.readouterr().out


def _loud(tmp_path: Path) -> Path:
    """A flowverse whose one file says so when it is imported, and the file it says it in."""
    where = tmp_path / "loud"
    (where / store.FLOWS).mkdir(parents=True)
    ran = tmp_path / "ran"
    written(
        where / store.FLOWS,
        "shouts",
        f"import pathlib\n\npathlib.Path({str(ran)!r}).write_text('ran')\n",
    )
    _git("init", "-b", "main", at=where)
    _git("config", "user.email", "t@example.com", at=where)
    _git("config", "user.name", "t", at=where)
    _commit(where, "one file that tells")
    return ran


@pytest.mark.parametrize("doing", ["show", "fetch", "remove"])
def test_a_name_no_flowverse_answers_to_is_reported_rather_than_raised(
    doing: str, capsys: pytest.CaptureFixture[str]
) -> None:
    assert run(doing, "nope") == 1

    assert "no flowverse called 'nope'" in capsys.readouterr().err


def test_adding_one_under_a_name_already_taken_says_so_and_keeps_the_first(
    theirs: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert run("add", str(theirs), "mine") == 0
    capsys.readouterr()

    assert run("add", str(theirs), "mine") == 1

    assert "already a flowverse called 'mine'" in capsys.readouterr().err
    mine = store.named("mine")
    assert mine is not None
    assert store.flows(mine) == ["loop", "review"]


def test_a_name_that_climbs_out_of_where_they_are_kept_is_refused(
    theirs: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A flowverse name is one directory, and one that is not is not a name."""
    assert run("add", str(theirs), "../escape") == 1

    assert "is not a flowverse name" in capsys.readouterr().err
    assert not (store.under().parent / "escape").exists()


def test_a_repository_that_cannot_be_fetched_is_reported_rather_than_raised(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """What git said, said where whoever typed the line can read it."""
    assert run("add", str(tmp_path / "nowhere")) == 1

    said = capsys.readouterr().err
    assert said.startswith("hmz: ")
    # Git's own reason, and not just our prefix: a handler that threw the reason away and
    # printed a bare `hmz:` would pass a test that only looked for the prefix.
    assert "does not exist" in said or "not a git repository" in said
    assert store.named("nowhere") is None


def test_a_clone_that_failed_leaves_the_name_free_to_use_again(
    theirs: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Or a fetch that was killed part-way is a name nobody can have until they go digging.

    git tidies up after its own failures; it cannot tidy up after being killed for taking too
    long, so what it had written by then is taken away here instead.
    """
    assert run("add", str(tmp_path / "nowhere"), "mine") == 1
    capsys.readouterr()

    assert not store.where("mine").exists()
    assert run("add", str(theirs), "mine") == 0
    assert "mine is fetched into" in capsys.readouterr().out


@pytest.mark.parametrize("name", [store.BUILTIN, store.OFFICIAL])
def test_neither_of_the_two_that_are_always_there_can_be_added_over(
    name: str, theirs: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Cloned into either slot, a stranger's repository is not one anybody could reach.

    `builtin` is skipped when the flowverses are listed, so it would sit there offering
    nothing; `official` is listed with humanize's own URL against it, so it would be shown as
    humanize's own. Both are refused where the name is given rather than found out afterwards.
    """
    assert run("add", str(theirs), name) == 1

    assert name in capsys.readouterr().err
    # Nothing was cloned into either slot, so what is there is still humanize's own.
    assert not store.where(name).exists()
    one = store.named(name)
    assert one is not None
    assert one.fixed
    # `review` is the fixture's own and nothing humanize ships, so it is only there if the
    # clone went through.
    assert not any(offered.name.endswith("review") for offered in flows.found())


def test_where_a_flowverse_came_from_is_printed_without_what_was_signed_into_it(
    theirs: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A private flowverse in CI is added with a token in its URL, and git keeps it verbatim.

    This line is printed every time the flowverses are listed, so a token printed once is a
    token in the log of every job that ran it.
    """
    assert run("add", str(theirs), "ours") == 0
    config = store.where("ours") / ".git" / "config"
    config.write_text(
        config.read_text().replace(
            str(theirs), "https://x-access-token:ghp_secret@github.com/org/flows"
        )
    )
    capsys.readouterr()

    assert run("list") == 0
    assert run("show", "ours") == 0

    shown = capsys.readouterr().out
    assert "ghp_secret" not in shown
    assert "x-access-token" not in shown
    assert "https://***@github.com/org/flows" in shown


def test_a_directory_that_is_not_a_clone_is_not_called_humanizes_own(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """An empty URL means two things, and only one of them is the package.

    Flows dropped into the flowverses home by hand are offered like any others -- the docs
    invite exactly that -- so where they came from is a question with no answer rather than an
    answer of humanize's own.
    """
    byhand = store.where("byhand") / store.FLOWS
    byhand.mkdir(parents=True)
    written(byhand, "one", FLOW)

    assert run("list") == 0

    listed = next(
        line
        for line in capsys.readouterr().out.splitlines()
        if line.startswith("byhand")
    )
    assert "the flows humanize ships" not in listed


def test_a_url_with_a_percent_in_it_does_not_stop_the_line(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A percent-encoded password is an ordinary URL, and every line here reads that URL."""
    where = tmp_path / "pct%40dir"
    (where / store.FLOWS).mkdir(parents=True)
    written(where / store.FLOWS, "one", FLOW)
    _git("init", "-b", "main", at=where)
    _git("config", "user.email", "t@example.com", at=where)
    _git("config", "user.name", "t", at=where)
    _commit(where, "one flow, behind a percent")

    assert run("add", str(where), "pct") == 0
    capsys.readouterr()

    assert run("list") == 0
    assert "pct" in capsys.readouterr().out
    assert run("show", "pct") == 0
    assert "pct/one" in capsys.readouterr().out


def test_the_flows_humanize_ships_cannot_be_fetched(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """They are in the package, so there is nowhere to fetch them from."""
    assert run("fetch", store.BUILTIN) == 1

    assert "nothing to fetch" in capsys.readouterr().err


@pytest.mark.parametrize("name", [store.BUILTIN, store.OFFICIAL])
def test_neither_of_the_two_that_are_always_there_can_be_taken_away(
    name: str, capsys: pytest.CaptureFixture[str]
) -> None:
    assert run("remove", name) == 1

    assert "always here" in capsys.readouterr().err
