"""`hmz agents` -- the agents kept under a name, said as arguments rather than walked.

The store itself is `hmz.kept`, and what it writes is checked where the interface's own menu
is. What is checked here is the line: that it is the same file `/agents` keeps, that what one
line writes down the next line reads back, that a name already taken is a refusal rather than
a quiet overwrite, and that nothing here has to load a terminal interface to read a file.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from hmz import cli
from hmz.kept import Kept, Runs, Templates

if TYPE_CHECKING:
    import pytest


def run(*argv: str) -> int:
    """Carries out one `hmz agents` line, as `hmz` itself would."""
    return cli.main(["agents", *argv])


def test_one_written_down_is_one_the_interface_would_find() -> None:
    """One place a thing is kept is one place it is kept, whichever way somebody reached it."""
    assert run("add", "mine", "claude/claude-opus-5:high") == 0

    kept = Templates().find("mine")
    assert kept is not None
    assert kept.runs.spec == "claude/claude-opus-5:high"


def test_the_account_and_the_rest_are_written_down_too() -> None:
    """An agent is a CLI, an account, a model at an effort, and what it may do."""
    assert (
        run(
            "add",
            "remote",
            "codex@work/gpt-5.6:high",
            "--anchor",
            "ssh://build-box",
            "--no-goals",
        )
        == 0
    )

    kept = Templates().find("remote")
    assert kept is not None
    assert kept.runs.provider == "work"
    assert kept.runs.anchor == "ssh://build-box"
    assert kept.runs.goals is False


def test_what_one_line_wrote_the_next_reads_back(
    capsys: pytest.CaptureFixture[str],
) -> None:
    run("add", "mine", "claude/claude-opus-5:high")
    capsys.readouterr()

    assert run("show", "mine") == 0

    said = capsys.readouterr().out
    assert "claude-opus-5" in said
    assert "as this machine is signed in" in said  # rather than a blank


def test_the_names_alone_are_what_a_script_reads(
    capsys: pytest.CaptureFixture[str],
) -> None:
    Templates().keep(
        [Kept("one", Runs("claude/a:high")), Kept("two", Runs("codex/b:high"))]
    )

    assert run("list", "-q") == 0

    assert capsys.readouterr().out.split() == ["one", "two"]


def test_a_name_already_taken_is_refused_rather_than_written_over(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Writing one down is not a thing to do to somebody else's agent by accident."""
    run("add", "mine", "claude/claude-opus-5:high")
    capsys.readouterr()

    assert run("add", "mine", "codex/gpt-5.6:high") == 1

    assert "already an agent called mine" in capsys.readouterr().err
    kept = Templates().find("mine")
    assert kept is not None
    assert kept.runs.spec == "claude/claude-opus-5:high"  # left as it was

    # And said again with --force, which is the line that means it.
    assert run("add", "mine", "codex/gpt-5.6:high", "--force") == 0
    kept = Templates().find("mine")
    assert kept is not None
    assert kept.runs.spec == "codex/gpt-5.6:high"
    assert len(Templates().all()) == 1  # written over rather than written twice


def test_an_agent_that_is_not_one_is_refused_where_it_was_typed(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert run("add", "mine", "nosuchcli/model:high") == 1

    assert "expected CLI" in capsys.readouterr().err
    assert Templates().all() == []


def test_a_permission_no_rung_answers_to_is_refused(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert run("add", "mine", "cli=claude,model=m,effort=high,permission=whatever") == 1

    assert "permission must be one of" in capsys.readouterr().err


def test_one_is_taken_away_and_the_rest_are_left(
    capsys: pytest.CaptureFixture[str],
) -> None:
    Templates().keep(
        [Kept("one", Runs("claude/a:high")), Kept("two", Runs("codex/b:high"))]
    )

    assert run("remove", "one") == 0

    assert [one.name for one in Templates().all()] == ["two"]
    assert run("remove", "one") == 1  # gone, and said so rather than silently again
    assert "no agent one" in capsys.readouterr().err


def test_nothing_written_down_says_so_rather_than_nothing(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert run("list") == 0

    said = capsys.readouterr().out
    assert "no agents written down yet" in said
    assert "hmz agents add" in said  # and what the line to write one is
