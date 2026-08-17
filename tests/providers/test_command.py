"""`hmz providers` -- the accounts an agent may be run as, said as arguments rather than walked.

What each of these lines actually does is the store's and the login's, and both are checked
where they live. What is checked here is the line: that it reaches them, that one which cannot
be carried out says so and leaves nothing half-made, and that what is printed where a person
can read it never holds a key -- a secret printed once is a secret in a scrollback.

Nobody is at the terminal for any of it, whatever the suite was started with: a line run from
a script has to say everything it means on the line.
"""

from __future__ import annotations

import io
from typing import TYPE_CHECKING

import pytest

from hmz import backends, cli, providers
from tests.providers.test_login import CLAUDE_LOGIN, stand_in
from tests.providers.test_redirect import traced

if TYPE_CHECKING:
    from pathlib import Path

#: A key that is not one, said on the line and never to be seen again.
KEY = "sk-not-a-real-key"

#: The shortest line that makes a provider: one backend, one name, one key of your own.
MINE = ("add", "claude/mine", "-w", "key", "-s", f"ANTHROPIC_API_KEY={KEY}")


def run(*argv: str) -> int:
    """Carries out one `hmz providers` line, as `hmz` itself would."""
    return cli.main(["providers", *argv])


@pytest.fixture(autouse=True)
def _nobody_to_ask(monkeypatch: pytest.MonkeyPatch) -> None:
    """Nothing here may stop to ask a question, and none of these lines needs to."""
    monkeypatch.setattr("sys.stdin", io.StringIO())


@pytest.fixture
def house(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """This user's home, somewhere temporary: no line here may reach the real one."""
    house = tmp_path / "house"
    house.mkdir()
    monkeypatch.setenv("HOME", str(house))
    for profile in backends.PROFILES:
        monkeypatch.delenv(profile.home_var, raising=False)
    monkeypatch.setenv("STAND_IN_RAN", str(tmp_path / "ran"))
    return house


def test_a_machine_with_no_providers_says_so(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert run("list") == 0

    assert "no providers yet" in capsys.readouterr().out


def test_a_line_naming_no_command_lists_what_there_is(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert run() == 0

    assert "no providers yet" in capsys.readouterr().out


def test_what_was_added_is_what_is_listed(capsys: pytest.CaptureFixture[str]) -> None:
    assert run(*MINE, "--no-login") == 0
    made = capsys.readouterr().out
    assert "claude/mine is written down at" in made

    assert run("list") == 0

    shown = capsys.readouterr().out
    assert "claude/mine" in shown
    assert "key" in shown
    assert "ANTHROPIC_API_KEY" in shown
    assert KEY not in shown
    provider = providers.find("claude", "mine")
    assert provider is not None
    assert dict(provider.env) == {"ANTHROPIC_API_KEY": KEY}


def test_only_one_backends_providers_are_listed_when_one_is_named(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert run(*MINE) == 0
    assert (
        run(
            "add",
            "codex/mine",
            "-w",
            "gateway",
            "-s",
            "CODEX_PROVIDER_URL=https://example.invalid/v1",
            "-s",
            f"CODEX_PROVIDER_KEY={KEY}",
        )
        == 0
    )
    capsys.readouterr()

    assert run("list", "claude-code") == 0

    shown = capsys.readouterr().out
    assert "claude/mine" in shown
    assert "codex/mine" not in shown


def test_listing_a_backend_that_is_not_one_says_so_rather_than_listing_everybody(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A name nothing answers to reads as "all of them", so a typo would report the wrong one."""
    assert run(*MINE) == 0
    capsys.readouterr()

    assert run("list", "nosuchcli") == 1

    said = capsys.readouterr()
    assert "no such coding agent" in said.err
    assert "claude/mine" not in said.out


def test_a_question_with_an_answer_that_is_usually_right_is_not_asked() -> None:
    """`bedrock` needs a profile and takes a region; only one of them is anybody's to say."""
    assert run("add", "claude/aws", "-w", "bedrock", "-s", "AWS_PROFILE=work") == 0

    provider = providers.find("claude", "aws")
    assert provider is not None
    assert dict(provider.env) == {
        "AWS_PROFILE": "work",
        "AWS_REGION": "us-east-1",
        "CLAUDE_CODE_USE_BEDROCK": "1",
    }


def test_a_question_nobody_can_be_asked_is_a_line_to_correct(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert run("add", "claude/mine", "-w", "key", "--no-login") == 1

    assert "nothing to read the answers from" in capsys.readouterr().err
    assert providers.find("claude", "mine") is None


def test_a_set_that_is_not_a_variable_is_a_line_to_correct(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert run("add", "claude/mine", "-w", "key", "-s", "nonsense", "--no-login") == 1

    assert "is not NAME=VALUE" in capsys.readouterr().err
    assert providers.find("claude", "mine") is None


def test_a_backend_nobody_has_heard_of_is_a_line_to_correct(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert run("add", "nope/mine", "--no-login") == 1
    assert "no such coding agent" in capsys.readouterr().err

    assert run("ways", "nope") == 1
    assert "no such coding agent" in capsys.readouterr().err


def test_a_way_the_backend_does_not_offer_is_a_line_to_correct(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert run("add", "claude/mine", "-w", "nope", "--no-login") == 1

    said = capsys.readouterr().err
    assert "has no way in called 'nope'" in said
    assert (
        "hmz providers ways claude" in said
    )  # and what to type to find out what there is


def test_a_name_a_provider_may_not_have_is_a_line_to_correct(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert run("add", "claude/../evil", "-w", "login", "--no-login") == 1

    assert "is not a provider name" in capsys.readouterr().err


@pytest.mark.parametrize("said", ["claude", "/mine"])
def test_something_that_is_not_a_backend_and_a_name_is_a_usage_error(
    said: str, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as stopped:
        run("show", said)

    assert stopped.value.code == 2
    assert "is not CLI/NAME" in capsys.readouterr().err


def test_the_ways_in_are_the_backends_own_and_then_variables_of_your_own(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert run("ways", "claude-code") == 0

    shown = capsys.readouterr().out
    claude = backends.named("claude")
    assert claude is not None
    for way in claude.ways:
        assert way.name in shown
        assert way.about in shown
    assert "claude auth login" in shown  # what the way in runs
    assert "ANTHROPIC_API_KEY" in shown  # and what it asks
    assert providers.ENV.name in shown


def test_what_a_provider_holds_is_shown_without_saying_any_secret(
    house: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert run(*MINE, "--no-login") == 0
    capsys.readouterr()

    assert run("show", "claude/mine") == 0

    shown = capsys.readouterr().out
    provider = providers.find("claude", "mine")
    assert provider is not None
    assert f"claude/{provider.name}" in shown
    assert str(provider.at) in shown
    assert "ANTHROPIC_API_KEY" in shown
    assert KEY not in shown
    for real, instead in provider.swaps():
        assert f"{real} -> {instead}" in shown


def test_what_is_not_there_cannot_be_shown(capsys: pytest.CaptureFixture[str]) -> None:
    assert run("show", "claude/ghost") == 1

    assert "no provider claude/ghost" in capsys.readouterr().err


def test_a_provider_taken_away_is_gone_and_saying_so_twice_is_an_error(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert run(*MINE, "--no-login") == 0
    capsys.readouterr()

    assert run("remove", "claude/mine") == 0
    assert "is gone, credentials and all" in capsys.readouterr().out

    assert run("remove", "claude/mine") == 1
    assert "no provider claude/mine" in capsys.readouterr().err
    assert providers.providers() == []


def test_a_provider_that_was_never_made_cannot_be_signed_in_again(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert run("login", "claude/ghost") == 1

    assert "no provider claude/ghost" in capsys.readouterr().err


def test_a_provider_made_of_answers_has_nothing_to_sign_in_again(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Its key is what it is; correcting one is making it again, not signing in again."""
    assert run(*MINE) == 0
    capsys.readouterr()

    assert run("login", "claude/mine") == 1

    assert "which has nothing to run" in capsys.readouterr().err


def test_a_line_that_says_not_to_sign_in_runs_nothing(
    house: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stand_in(monkeypatch, tmp_path / "bin", "claude", CLAUDE_LOGIN)

    assert run("add", "claude/mine", "-w", "login", "--no-login") == 0

    assert providers.find("claude", "mine") is not None
    assert not (tmp_path / "ran").exists(), "the backend's own way in was run anyway"


@traced
@pytest.mark.timeout(60)
def test_adding_a_provider_signs_it_in_where_the_way_in_has_a_command(
    house: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stand_in(monkeypatch, tmp_path / "bin", "claude", CLAUDE_LOGIN)

    assert run("add", "claude/mine", "-w", "login") == 0

    provider = providers.find("claude", "mine")
    assert provider is not None
    assert (provider.at / "home" / ".credentials.json").exists()
    assert not (house / ".claude" / ".credentials.json").exists()


@traced
@pytest.mark.timeout(60)
def test_signing_in_again_runs_the_way_the_provider_was_made_by(
    house: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Which is the one thing `login` has to get right: nobody says the way a second time."""
    stand_in(monkeypatch, tmp_path / "bin", "claude", CLAUDE_LOGIN)
    assert run("add", "claude/mine", "-w", "login", "--no-login") == 0
    provider = providers.find("claude", "mine")
    assert provider is not None

    assert run("login", "claude/mine") == 0

    assert (tmp_path / "ran").exists()
    assert (provider.at / "home" / ".credentials.json").exists()


def test_an_account_is_asked_what_it_runs_as_soon_as_it_is_made(
    asking: None,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """An account is made to run turns as, and which models those may name is the account's."""
    from hmz import models
    from tests.test_models import CLAUDE, stands_in

    stands_in(monkeypatch, tmp_path / "bin", "claude", CLAUDE)

    assert run(*MINE) == 0

    assert "claude says it runs 2 models as mine" in capsys.readouterr().out
    assert [model.name for model in models.offered("claude", "mine")] == [
        "claude-nine",
        "claude-quick",
    ]


def test_an_account_whose_cli_will_not_say_what_it_runs_is_still_an_account(
    asking: None,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The line was for making the account, and the account was made."""
    from tests.test_models import stands_in

    stands_in(
        monkeypatch, tmp_path / "bin", "claude", "", code=1, says="not signed in\n"
    )

    assert run(*MINE) == 0

    assert providers.find("claude", "mine") is not None
    assert "did not say what it runs" in capsys.readouterr().err


def test_where_an_account_falls_back_to_is_said_from_a_command_line(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A name rather than a mark: each account names the next, and a turn walks the chain."""
    providers.add("claude", "mine", env={"ANTHROPIC_API_KEY": "k"})
    providers.add("claude", "spare", env={"ANTHROPIC_API_KEY": "s"})

    assert run("falls-back", "claude/mine", "spare") == 0

    held = providers.find("claude", "mine")
    assert held is not None
    assert held.fallback == "spare"
    assert "falls back to spare" in capsys.readouterr().out
    # And said with nothing after it, it is the end of the line again.
    assert run("falls-back", "claude/mine") == 0
    ended = providers.find("claude", "mine")
    assert ended is not None
    assert not ended.fallback


def test_a_chain_that_goes_nowhere_is_refused_where_it_was_typed(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Said at the prompt rather than found by the turn that needed somewhere to go."""
    providers.add("claude", "mine", env={"ANTHROPIC_API_KEY": "k"})

    assert run("falls-back", "claude/mine", "nonesuch") == 1

    assert "no claude account called 'nonesuch'" in capsys.readouterr().err


def test_the_account_this_machine_is_signed_into_is_said_as_a_cli_and_no_name(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """`claude/` is it: an account of every backend, and the one nobody had to make."""
    providers.add("claude", "spare", env={"ANTHROPIC_API_KEY": "s"})

    assert run("falls-back", "claude/", "spare") == 0

    held = providers.find("claude", providers.LOCAL)
    assert held is not None
    assert held.fallback == "spare"
    said = capsys.readouterr().out
    assert "claude, as this machine is signed in, falls back to spare" in said

    assert run("show", "claude/") == 0
    shown = capsys.readouterr().out
    assert "way         as this machine is signed in" in shown
    assert "falls to    spare" in shown


def test_the_machines_own_account_is_not_one_to_make_or_take_away(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Nobody made it and nothing is kept for it, so there is nothing to do to it."""
    for doing in ("add", "remove", "login"):
        with pytest.raises(SystemExit) as stopped:
            run(doing, "claude/")
        assert stopped.value.code == 2
        assert "is not CLI/NAME" in capsys.readouterr().err


def test_an_account_several_backends_could_run_says_so_when_it_is_made(
    house: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Said rather than done: a line that did not ask is how somebody finds out it is a thing."""
    del house
    assert run(*MINE, "--no-login") == 0

    said = capsys.readouterr().out
    assert "it could also run pi, opencode, mimo, zcode" in said
    assert "--also" in said
    assert providers.find("pi", "mine") is None  # said, and nothing written


def test_one_line_writes_an_account_down_for_every_backend_that_could_run_it(
    house: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """One configuration, several CLIs: which is what having the same key four times was."""
    del house
    assert run(*MINE, "--no-login", "--also", "all") == 0

    for cli_name in ("pi", "opencode", "mimo", "zcode"):
        held = providers.find(cli_name, "mine")
        assert held is not None
        assert dict(held.env) == {"ANTHROPIC_API_KEY": KEY}
    said = capsys.readouterr().out
    assert KEY not in said  # never a value, wherever it is printed
    assert "pi/mine is written down" in said


def test_the_backends_to_write_it_down_for_may_be_named(
    house: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    del house
    assert run(*MINE, "--no-login", "--also", "opencode") == 0

    assert providers.find("opencode", "mine") is not None
    assert providers.find("pi", "mine") is None
    assert capsys.readouterr().out.count("is written down") == 2


def test_a_backend_that_could_not_run_it_is_a_line_to_correct(
    house: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Rather than a copy skipped quietly: the line asked for something that cannot happen."""
    del house
    assert run(*MINE, "--no-login", "--also", "codex") == 1

    assert "not an account codex could be run as" in capsys.readouterr().err
    assert providers.find("codex", "mine") is None


def test_what_else_an_account_could_run_is_shown_where_it_is_read(
    house: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    del house
    run(*MINE, "--no-login")
    capsys.readouterr()

    assert run("show", "claude/mine") == 0

    said = capsys.readouterr().out
    assert "also runs   pi" in said
    assert "also runs   opencode" in said
