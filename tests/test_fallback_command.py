"""`hmz fallback` -- the steps between agents, said as arguments rather than walked.

The store itself is `hmz.fallbacks`, and what a turn does with it is checked where the agents
are. What is checked here is the line: that it is the same file `/fallback` keeps, that what
one line writes the next line reads back, that a step nothing can be made of is a refusal
rather than a file with nonsense in it, and that nothing here has to load a terminal interface
to read one.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from hmz import cli, fallbacks

if TYPE_CHECKING:
    import pytest


def run(*argv: str) -> int:
    """Carries out one `hmz fallback` line, as `hmz` itself would."""
    return cli.main(["fallback", *argv])


def test_one_written_down_is_one_the_interface_would_find() -> None:
    """One place a thing is kept is one place it is kept, whichever way somebody reached it."""
    assert run("add", "claude/claude-opus-5:high", "codex/gpt-5.6-sol:high") == 0

    assert fallbacks.falls() == [
        fallbacks.Falls("claude/claude-opus-5:high", "codex/gpt-5.6-sol:high")
    ]


def test_an_account_is_part_of_which_agent_this_is() -> None:
    """Two agents of one CLI at one model on two accounts are two things to say."""
    assert (
        run("add", "claude@work/claude-opus-5:high", "codex@key/gpt-5.6-sol:high") == 0
    )

    assert fallbacks.chain("claude@work/claude-opus-5:high") == [
        "claude@work/claude-opus-5:high",
        "codex@key/gpt-5.6-sol:high",
    ]
    # And the same agent as this machine is signed in is a different agent.
    assert fallbacks.chain("claude/claude-opus-5:high") == ["claude/claude-opus-5:high"]


def test_what_one_line_wrote_the_next_reads_back(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A listing is what there is, one step a line, in the order they were written."""
    run("add", "claude/a:high", "codex/b:high")
    run("add", "codex/b:high", "dsh/c:high")
    capsys.readouterr()

    assert run("list") == 0

    assert capsys.readouterr().out.splitlines() == [
        "claude/a:high  ->  codex/b:high",
        "codex/b:high  ->  dsh/c:high",
    ]


def test_the_walk_is_what_is_shown_rather_than_the_one_step(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Because the walk is what a failed turn actually does."""
    run("add", "claude/a:high", "codex/b:high")
    run("add", "codex/b:high", "dsh/c:high")
    capsys.readouterr()

    assert run("show", "claude/a:high") == 0

    assert capsys.readouterr().out.splitlines() == [
        "1. claude/a:high",
        "2. codex/b:high",
        "3. dsh/c:high",
    ]


def test_an_agent_that_falls_back_nowhere_says_so(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """An empty answer that explains nothing reads as a command that did not work."""
    assert run("show", "claude/a:high") == 0

    said = capsys.readouterr().out
    assert "falls back nowhere" in said


def test_an_empty_listing_says_which_line_writes_one_down(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Where somebody finds out what the command is for is where it says nothing yet."""
    assert run("list") == 0

    assert "hmz fallback add" in capsys.readouterr().out


def test_a_step_nothing_can_be_made_of_is_refused_where_it_is_written(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Rather than found by the turn that needed it, an hour into a loop."""
    assert run("add", "nothing-is-called-this/a:high", "codex/b:high") == 1
    assert "is not an agent" in capsys.readouterr().err

    assert run("add", "claude/a:high", "claude/a:high") == 1
    assert "cannot fall back to itself" in capsys.readouterr().err

    assert run("show", "nothing-is-called-this/a:high") == 1
    assert "expected CLI" in capsys.readouterr().err

    assert fallbacks.falls() == []


def test_taking_one_away_is_an_agent_that_falls_back_nowhere_again(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """And taking away one that is not there says so rather than reporting success."""
    run("add", "claude/a:high", "codex/b:high")
    capsys.readouterr()

    assert run("remove", "claude/a:high") == 0
    assert fallbacks.falls() == []

    assert run("remove", "claude/a:high") == 1
    assert "nothing written down" in capsys.readouterr().err


def test_writing_one_again_says_the_new_thing_and_not_both() -> None:
    """One agent has one place to go: a chain that forked would be one nothing can walk."""
    run("add", "claude/a:high", "codex/b:high")
    run("add", "claude/a:high", "dsh/c:high")

    assert fallbacks.chain("claude/a:high") == ["claude/a:high", "dsh/c:high"]
