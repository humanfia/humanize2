"""Making a provider: what a way in is asked, what is written down, and where a login lands.

The half that is answers is read straight off the store afterwards -- what a way keeps, what
it sets whatever it was told, what it fills into a backend's own command line. The half that
is a command is driven against a stand-in CLI on PATH: a script that writes a file at the
path the real one writes its credentials to, because where that file lands is the one thing
a real login would tell us and it would cost a browser and an account to ask.

Nothing here may touch the credentials of whoever is running the suite: this user's home is
moved to `tmp_path` for every test that names one, and every backend's own home variable is
taken out of the environment with it.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

from hmz import backends, providers
from hmz.providers import login
from tests.providers.test_redirect import traced

#: A stand-in for `claude auth login`: what a login leaves behind, without the browser.
CLAUDE_LOGIN = """\
import json, os, sys

home = os.environ["HOME"]
os.makedirs(os.path.join(home, ".claude"), exist_ok=True)
with open(os.path.join(home, ".claude", ".credentials.json"), "w") as landed:
    json.dump({"argv": sys.argv[1:], "signed": "the provider"}, landed)
# At a path nothing answers for, so that it says the stand-in ran at all.
open(os.environ["STAND_IN_RAN"], "w").write("ran")
"""

#: A stand-in for `codex login --with-api-key`, which reads the key off its own stdin.
CODEX_KEY = """\
import json, os, sys

key = sys.stdin.readline().strip()
home = os.environ["HOME"]
os.makedirs(os.path.join(home, ".codex"), exist_ok=True)
with open(os.path.join(home, ".codex", "auth.json"), "w") as landed:
    json.dump({"argv": sys.argv[1:], "key": key}, landed)
"""

#: A stand-in for `opencode auth login <url>`, whose home is under the one every program shares.
OPENCODE_LOGIN = """\
import json, os, sys

at = os.path.join(os.environ["HOME"], ".local", "share", "opencode")
os.makedirs(at, exist_ok=True)
with open(os.path.join(at, "auth.json"), "w") as landed:
    json.dump({"argv": sys.argv[1:]}, landed)
"""


def stand_in(monkeypatch: pytest.MonkeyPatch, at: Path, name: str, script: str) -> Path:
    """Puts a program of that name first on PATH, which is what a way in then runs.

    Args:
      monkeypatch: What puts it on PATH, and takes it off again afterwards.
      at: The directory to keep it in.
      name: What the backend is called, since a way in runs the backend.
      script: The Python the stand-in is.

    Returns:
      The program.
    """
    at.mkdir(parents=True, exist_ok=True)
    program = at / name
    program.write_text(f"#!{sys.executable}\n{script}")
    program.chmod(0o755)
    monkeypatch.setenv("PATH", f"{at}{os.pathsep}{os.environ['PATH']}")
    return program


def way(cli: str, name: str) -> backends.Way:
    """The way in of that name, which every test that asks for one names one there is."""
    found = login.way_of(cli, name)
    assert found is not None, f"{cli} offers no way in called {name!r}"
    return found


@pytest.fixture
def house(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """This user's home, somewhere temporary: nothing here may read or write the real one."""
    house = tmp_path / "house"
    house.mkdir()
    monkeypatch.setenv("HOME", str(house))
    for profile in backends.PROFILES:
        monkeypatch.delenv(profile.home_var, raising=False)
    monkeypatch.setenv("STAND_IN_RAN", str(tmp_path / "ran"))
    return house


# ------------------------------------------------------------ what is asked


def test_a_way_is_found_under_the_name_the_backend_offers_it_by() -> None:
    found = login.way_of("claude-code", "bedrock")

    assert found is not None
    assert found.name == "bedrock"
    assert login.way_of("claude", "env") is providers.ENV
    assert login.way_of("claude", "nope") is None
    assert login.way_of("nope", "login") is None


def test_a_way_still_has_to_be_told_whatever_it_has_no_answer_for() -> None:
    gateway = way("claude", "gateway")

    assert login.asked(gateway, {}) == ["ANTHROPIC_BASE_URL", "ANTHROPIC_AUTH_TOKEN"]
    assert login.asked(gateway, {"ANTHROPIC_BASE_URL": "https://x.invalid"}) == [
        "ANTHROPIC_AUTH_TOKEN"
    ]
    assert (
        login.asked(gateway, {"ANTHROPIC_BASE_URL": "x", "ANTHROPIC_AUTH_TOKEN": "y"})
        == []
    )


def test_a_question_with_an_answer_that_is_usually_right_is_not_one_to_ask() -> None:
    assert login.asked(way("claude", "bedrock"), {}) == ["AWS_PROFILE"]
    assert login.asked(way("claude", "login"), {}) == []
    assert login.asked(providers.ENV, {}) == []


# --------------------------------------------------------- what is written down


def test_a_provider_is_what_its_way_in_was_answered_with(house: Path) -> None:
    provider = login.make(
        "claude",
        "mine",
        way("claude", "gateway"),
        {
            "ANTHROPIC_BASE_URL": "https://example.invalid/anthropic",
            "ANTHROPIC_AUTH_TOKEN": "not-a-real-token",
        },
    )

    assert provider.way == "gateway"
    assert dict(provider.env) == {
        "ANTHROPIC_BASE_URL": "https://example.invalid/anthropic",
        "ANTHROPIC_AUTH_TOKEN": "not-a-real-token",
    }
    assert providers.find("claude", "mine") == provider


def test_an_answer_a_way_does_not_keep_is_not_written_down_anywhere(
    house: Path,
) -> None:
    """Codex reads its key into its own store: a second copy is a second place to leak it."""
    provider = login.make(
        "codex", "mine", way("codex", "key"), {"OPENAI_API_KEY": "sk-not-a-real-key"}
    )

    assert dict(provider.env) == {}
    assert "sk-not-a-real-key" not in (provider.at / "provider.json").read_text()


def test_what_a_way_sets_whatever_it_was_answered_is_set(house: Path) -> None:
    """The variable that switches a backend onto a vendor's cloud is nobody's to type."""
    provider = login.make(
        "claude", "mine", way("claude", "bedrock"), {"AWS_PROFILE": "work"}
    )

    assert dict(provider.env) == {
        "AWS_PROFILE": "work",
        "AWS_REGION": "us-east-1",  # the answer nobody was asked for
        "CLAUDE_CODE_USE_BEDROCK": "1",
    }


def test_an_answer_is_filled_into_what_the_backend_takes_on_its_command_line(
    house: Path,
) -> None:
    """Codex takes a provider as settings rather than as variables, so a way carries arguments."""
    provider = login.make(
        "codex",
        "mine",
        way("codex", "gateway"),
        {
            "CODEX_PROVIDER_URL": "https://example.invalid/v1",
            "CODEX_PROVIDER_KEY": "not-a-real-key",
        },
    )

    assert (
        "model_providers.humanize.base_url=https://example.invalid/v1" in provider.args
    )
    assert "model_providers.humanize.wire_api=chat" in provider.args
    assert provider.env["CODEX_PROVIDER_KEY"] == "not-a-real-key"


def test_variables_of_your_own_are_kept_whatever_they_are_called(house: Path) -> None:
    """The way in every backend has: nothing declares these, so nothing may drop them."""
    provider = login.make("pi", "mine", providers.ENV, {"PI_API_KEY": "not-a-real-key"})

    assert dict(provider.env) == {"PI_API_KEY": "not-a-real-key"}


def test_an_answer_nobody_gave_is_not_a_variable_set_to_nothing(house: Path) -> None:
    provider = login.make(
        "claude", "mine", way("claude", "key"), {"ANTHROPIC_API_KEY": ""}
    )

    assert dict(provider.env) == {}


def test_making_a_provider_makes_the_places_its_login_will_write_to(
    house: Path,
) -> None:
    provider = login.make("claude", "mine", way("claude", "login"))

    assert provider.swaps()
    for _, instead in provider.swaps():
        assert Path(instead).parent.is_dir()


def test_a_provider_that_could_not_be_named_is_not_made(house: Path) -> None:
    with pytest.raises(ValueError, match="is not a provider name"):
        login.make("claude", "../evil", way("claude", "login"))
    with pytest.raises(ValueError, match="no such coding agent"):
        login.make("nope", "mine", providers.ENV)


# ------------------------------------------------------------- what signs in


def test_a_way_that_is_only_answers_has_nothing_to_sign_in(house: Path) -> None:
    """It was done when it was written down, so there is no command and no status but zero."""
    provider = login.make(
        "claude", "mine", way("claude", "key"), {"ANTHROPIC_API_KEY": "not-a-real-key"}
    )

    assert login.sign_in(provider, way("claude", "key")) == 0


@traced
@pytest.mark.timeout(60)
def test_what_a_login_writes_lands_in_the_provider_and_not_in_this_home(
    house: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The whole errand: the CLI writes the path it always writes, and the provider gets it."""
    stand_in(monkeypatch, tmp_path / "bin", "claude", CLAUDE_LOGIN)
    provider = login.make("claude", "mine", way("claude", "login"))

    assert login.sign_in(provider, way("claude", "login")) == 0

    landed = json.loads((provider.at / "home" / ".credentials.json").read_text())
    assert landed == {"argv": ["auth", "login"], "signed": "the provider"}
    assert (tmp_path / "ran").exists(), "the stand-in never ran"
    # The home itself is the CLI's own and is left where it is; what moved is the credential.
    assert not (house / ".claude" / ".credentials.json").exists()
    assert not (house / ".claude.json").exists()


@traced
@pytest.mark.timeout(60)
def test_a_key_read_off_stdin_lands_in_the_backends_own_store_inside_the_provider(
    house: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The command is fed what it was told to be fed, and keeps it where it keeps its own."""
    stand_in(monkeypatch, tmp_path / "bin", "codex", CODEX_KEY)
    answers = {"OPENAI_API_KEY": "sk-not-a-real-key"}
    provider = login.make("codex", "mine", way("codex", "key"), answers)

    assert login.sign_in(provider, way("codex", "key"), answers) == 0

    landed = json.loads((provider.at / "home" / "auth.json").read_text())
    assert landed == {"argv": ["login", "--with-api-key"], "key": "sk-not-a-real-key"}
    assert not (house / ".codex" / "auth.json").exists()
    assert dict(provider.env) == {}  # and the key itself is written down nowhere


@traced
@pytest.mark.timeout(60)
def test_an_answer_a_way_puts_in_its_own_command_line_is_filled_in(
    house: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """And a home under the directory every program shares is answered like any other."""
    stand_in(monkeypatch, tmp_path / "bin", "opencode", OPENCODE_LOGIN)
    answers = {"OPENCODE_WELLKNOWN": "https://example.invalid/gateway"}
    provider = login.make("opencode", "mine", way("opencode", "wellknown"), answers)

    assert login.sign_in(provider, way("opencode", "wellknown"), answers) == 0

    landed = json.loads((provider.at / "home" / "auth.json").read_text())
    assert landed == {"argv": ["auth", "login", "https://example.invalid/gateway"]}
    assert not (house / ".local" / "share" / "opencode" / "auth.json").exists()
    assert dict(provider.env) == {}  # the URL is the command's, not the turn's


@traced
@pytest.mark.timeout(60)
def test_the_status_a_way_in_came_to_is_the_status_of_signing_in(
    house: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A login that was refused is a provider that is written down and not signed in."""
    stand_in(monkeypatch, tmp_path / "bin", "claude", "import sys\nsys.exit(3)\n")
    provider = login.make("claude", "mine", way("claude", "login"))

    assert login.sign_in(provider, way("claude", "login")) == 3
    assert not (provider.at / "home" / ".credentials.json").exists()


@traced
@pytest.mark.timeout(60)
def test_a_backend_that_is_not_installed_is_a_login_that_did_not_happen(
    house: Path,
) -> None:
    """Rather than a provider that looks signed in: what it comes to is what could not run."""
    missing = backends.Way(
        name="nowhere",
        about="a backend nobody has installed",
        argv=("hmz-no-such-backend",),
    )
    provider = login.make("kimi", "mine", missing)

    assert login.sign_in(provider, missing) != 0
    assert not list((provider.at / "home").iterdir())
