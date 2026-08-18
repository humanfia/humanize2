"""`hmz fallback` -- the steps between places, said as arguments rather than walked.

The store itself is `hmz.fallbacks`, and what a turn does with it is checked where the agents
are. What is checked here is the line: that it is the same file `/fallback` keeps, that what
one line writes the next line reads back, that a step nothing can be made of is a refusal
rather than a file with nonsense in it, and that nothing here has to load a terminal interface
to read one.
"""

from __future__ import annotations

import pytest

from hmz import cli, fallbacks, home


def run(*argv: str) -> int:
    """Carries out one `hmz fallback` line, as `hmz` itself would."""
    return cli.main(["fallback", *argv])


def poisons(said: str) -> None:
    """Puts exactly this in the file, which is what somebody editing it by hand does."""
    home().mkdir(parents=True, exist_ok=True)
    (home() / "fallbacks.json").write_text(said, encoding="utf-8")


def test_one_written_down_is_one_the_interface_would_find() -> None:
    """One place a thing is kept is one place it is kept, whichever way somebody reached it."""
    assert run("add", "claude/claude-opus-5", "codex/gpt-5.6-sol") == 0

    assert fallbacks.falls() == [
        fallbacks.Falls("claude/claude-opus-5", "codex/gpt-5.6-sol")
    ]


def test_a_place_is_three_things_and_the_account_is_one_of_them() -> None:
    """Two agents of one CLI at one model on two accounts are two places to say."""
    assert run("add", "claude@work/claude-opus-5", "codex@key/gpt-5.6-sol") == 0

    assert fallbacks.chain("claude@work/claude-opus-5") == [
        "claude@work/claude-opus-5",
        "codex@key/gpt-5.6-sol",
    ]
    # And the same CLI at the same model as this machine is signed in is another place.
    assert fallbacks.chain("claude/claude-opus-5") == ["claude/claude-opus-5"]


def test_what_one_line_wrote_the_next_reads_back(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A listing is what there is, one step a line, in the order they were written."""
    run("add", "claude/a", "codex/b")
    run("add", "codex/b", "dsh/c")
    capsys.readouterr()

    assert run("list") == 0

    assert capsys.readouterr().out.splitlines() == [
        "claude/a  ->  falls back to codex/b",
        "codex/b  ->  falls back to dsh/c",
    ]


def test_the_walk_is_what_is_shown_rather_than_the_one_step(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Because the walk is what a failed turn actually does."""
    run("add", "claude/a", "codex/b")
    run("add", "codex/b", "dsh/c")
    capsys.readouterr()

    assert run("show", "claude/a") == 0

    assert capsys.readouterr().out.splitlines() == [
        "1. claude/a",
        "2. codex/b",
        "3. dsh/c",
    ]


def test_a_place_that_falls_back_nowhere_says_so(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """An empty answer that explains nothing reads as a command that did not work."""
    assert run("show", "claude/a") == 0

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
    assert run("add", "nothing-is-called-this/a", "codex/b") == 1
    assert "is not a place" in capsys.readouterr().err

    assert run("add", "claude/a", "claude/a") == 1
    assert "cannot fall back to itself" in capsys.readouterr().err

    assert run("show", "nothing-is-called-this/a") == 1
    assert "expected CLI" in capsys.readouterr().err

    assert fallbacks.falls() == []


def test_taking_one_away_is_a_place_that_falls_back_nowhere_again(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """And taking away one that is not there says so rather than reporting success."""
    run("add", "claude/a", "codex/b")
    capsys.readouterr()

    assert run("remove", "claude/a") == 0
    assert fallbacks.falls() == []

    assert run("remove", "claude/a") == 1
    assert "nothing written down" in capsys.readouterr().err


def test_writing_one_again_says_the_new_thing_and_not_both() -> None:
    """One place has one place to go: a chain that forked would be one nothing can walk."""
    run("add", "claude/a", "codex/b")
    run("add", "claude/a", "dsh/c")

    assert fallbacks.chain("claude/a") == ["claude/a", "dsh/c"]


def test_how_often_a_failed_turn_is_taken_again_is_said_on_the_same_command(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """One thing went wrong, so one command says both what to try and where to go."""
    assert run("retry", "claude/a", "3", "-p", "exponential", "-t", "90") == 0

    said = fallbacks.tried("claude/a")
    assert (said.tries, said.policy, said.timeout) == (3, "exponential", 90.0)
    assert "tried 3 more times, exponential, up to 90s" in capsys.readouterr().out

    # And it is on the listing beside where the turn goes next, both being one answer.
    run("add", "claude/a", "codex/b")
    capsys.readouterr()
    assert run("list") == 0
    assert (
        "claude/a  ->  3 more tries, exponential, up to 90s; falls back to codex/b"
        in capsys.readouterr().out
    )


def test_tries_written_against_a_place_that_goes_nowhere_are_still_kept() -> None:
    """Trying again is worth having on its own: not every place has somewhere to go."""
    assert run("retry", "claude/a", "2") == 0

    assert fallbacks.tried("claude/a").tries == 2
    assert fallbacks.chain("claude/a") == ["claude/a"]


def test_a_policy_nobody_has_is_refused_where_it_was_typed(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A setting to correct rather than a turn that waits some way nobody asked for."""
    with pytest.raises(SystemExit):
        run("retry", "claude/a", "1", "-p", "nonesuch")

    assert "invalid choice" in capsys.readouterr().err
    assert fallbacks.falls() == []


def test_seconds_no_waiting_can_be_made_of_are_refused_where_they_were_typed(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """`inf` is a limit that never arrives and `nan` is not a length of time at all.

    And neither is JSON: written down, they are a bare `Infinity` or `NaN` token, which is a
    file the next reader of it may not be able to read. No limit at all is spelled `0`.
    """
    for said in ("inf", "nan", "1e309"):
        assert run("retry", "claude/a", "3", "-t", said) == 1
        assert "not debts or infinities" in capsys.readouterr().err

    assert fallbacks.falls() == []
    assert not (home() / "fallbacks.json").exists()


def test_a_count_nothing_can_be_made_of_is_read_past_rather_than_ending_runs() -> None:
    """Every failed turn on this machine reads this file, and `int` will not take an `inf`.

    Which arrives two ways: a hand-written `Infinity`, and the `1e400` that is JSON anybody
    would accept and comes back as the same infinity.
    """
    poisons(
        '[{"spec": "claude/a", "to": "codex/b", "tries": Infinity},'
        ' {"spec": "dsh/c", "to": "", "tries": 1e400}]'
    )

    # What could not be read is the number, so the step is still the step it names -- and a
    # place left saying nothing at all is a place nothing was said about.
    assert fallbacks.falls() == [fallbacks.Falls("claude/a", "codex/b")]
    assert fallbacks.chain("claude/a") == ["claude/a", "codex/b"]
    assert fallbacks.tried("dsh/c") == fallbacks.Falls("dsh/c")
    assert run("list") == 0


def test_a_limit_that_never_arrives_is_read_as_no_limit_at_all() -> None:
    """A `nan` loses every comparison it is in, so a turn held to one is held to nothing."""
    poisons(
        '[{"spec": "claude/a", "to": "codex/b", "tries": 2, "timeout": NaN},'
        f' {{"spec": "dsh/c", "to": "codex/b", "tries": 2, "timeout": 1{"0" * 400}}}]'
    )

    assert [one.timeout for one in fallbacks.falls()] == [0.0, 0.0]
