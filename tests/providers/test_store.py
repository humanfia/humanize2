"""What a provider is on disk: written down, read back, listed, and taken away.

The store is the half of this layer that touches a filesystem and nothing else -- it reaches
no CLI and starts no process -- so what is checked here is that a provider survives the round
trip, that a listing is what can actually be run, that a name which is not a name is refused
before it becomes a directory, and that the paths a turn is answered at are the backend's own
and nobody else's.
"""

from __future__ import annotations

import json
import os
import re
import stat
import sys
from pathlib import Path

import pytest

from hmz import backends, home, providers
from hmz.providers import store

#: The moment a provider was made, as it is written down: UTC, to the second.
_MADE = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z")

#: Names a directory could hold and a provider may not have: one that climbs out of the
#: place it names, one a shell or a glob reads as something else, and one that is not there.
_NOT_NAMES = [
    "",
    ".",
    "..",
    "/",
    "sub/name",
    "../evil",
    ".hidden",
    "-dash",
    "two words",
]


def test_a_provider_is_read_back_as_it_was_written_down() -> None:
    written = providers.add(
        "claude",
        "mine",
        way="gateway",
        env={
            "ANTHROPIC_BASE_URL": "https://example.invalid/anthropic",
            "ANTHROPIC_AUTH_TOKEN": "not-a-real-token",
        },
        args=("--flag", "value"),
    )

    read = providers.find("claude", "mine")

    assert read == written
    assert read is not None
    assert read.way == "gateway"
    assert read.env["ANTHROPIC_BASE_URL"] == "https://example.invalid/anthropic"
    assert read.args == ("--flag", "value")
    assert _MADE.fullmatch(read.made), read.made


def test_a_provider_is_kept_under_the_name_its_backend_is_called_here() -> None:
    """Whatever the line called it: a directory per backend, not one per spelling of one."""
    provider = providers.add("claude-code", "mine")

    assert provider.cli == "claude"
    assert provider.at == home() / "providers" / "claude" / "mine"
    assert json.loads((provider.at / "provider.json").read_text())["cli"] == "claude"


def test_every_provider_is_listed_by_backend_and_then_by_name() -> None:
    for cli, name in (("kimi", "second"), ("claude", "second"), ("codex", "only")):
        providers.add(cli, name)
    providers.add("claude", "first")

    assert [(one.cli, one.name) for one in providers.providers()] == [
        ("claude", "first"),
        ("claude", "second"),
        ("codex", "only"),
        ("kimi", "second"),
    ]


def test_one_backends_providers_are_listed_on_their_own() -> None:
    providers.add("claude", "mine")
    providers.add("codex", "mine")

    assert [one.cli for one in providers.providers("claude-code")] == ["claude"]


def test_nothing_is_listed_where_nothing_has_ever_been_written_down() -> None:
    """A machine that has made no provider has no such directory, which is not an error."""
    assert not (home() / "providers").exists()
    assert providers.providers() == []


@pytest.mark.parametrize("name", ["ghost", *_NOT_NAMES])
def test_nothing_is_found_for_a_provider_there_is_not(name: str) -> None:
    providers.add("claude", "mine")

    assert providers.find("claude", name) is None


def test_nothing_is_found_for_a_backend_there_is_not() -> None:
    assert providers.find("nope", "mine") is None
    assert providers.providers("nope") == []


@pytest.mark.parametrize("name", _NOT_NAMES)
def test_a_name_that_is_not_a_name_is_refused(name: str) -> None:
    """A provider's name is a directory, and one that climbs out of this one is not a name."""
    with pytest.raises(ValueError, match="is not a provider name"):
        providers.where("claude", name)
    with pytest.raises(ValueError, match="is not a provider name"):
        providers.add("claude", name)
    with pytest.raises(ValueError, match="is not a provider name"):
        providers.remove("claude", name)
    assert not (home() / "providers" / "claude").exists()


def test_a_backend_that_is_not_one_is_refused() -> None:
    for doing in (providers.where, providers.add, providers.remove):
        with pytest.raises(ValueError, match="no such coding agent"):
            doing("nope", "mine")


def test_a_directory_holding_nothing_readable_is_not_a_provider() -> None:
    """The list is what can be run, so what cannot be read is left out rather than raised at."""
    folder = providers.add("claude", "readable").at.parent
    (folder / "empty").mkdir()
    (folder / "broken").mkdir()
    (folder / "broken" / "provider.json").write_text("{ this is not json")
    (folder / "listed").mkdir()
    (folder / "listed" / "provider.json").write_text('["not", "a", "mapping"]')
    unreadable = folder / "unreadable"
    unreadable.mkdir()
    (unreadable / "provider.json").mkdir()  # a directory where a file should be

    assert [one.name for one in providers.providers()] == ["readable"]
    for name in ("empty", "broken", "listed", "unreadable"):
        assert providers.find("claude", name) is None


def test_where_a_provider_is_kept_is_what_it_is_for() -> None:
    """The place is the answer; the file only describes it, and may describe it wrongly."""
    provider = providers.add("claude", "mine")
    (provider.at / "provider.json").write_text(
        json.dumps({"cli": "codex", "name": "somebody-elses", "way": "key"})
    )

    read = providers.find("claude", "mine")

    assert read is not None
    assert (read.cli, read.name, read.way) == ("claude", "mine", "key")


def test_what_a_provider_holds_is_replaced_rather_than_merged() -> None:
    providers.add("claude", "mine", way="key", env={"ANTHROPIC_API_KEY": "not-real"})

    landed = providers.add(
        "claude", "mine", way="gateway", env={"ANTHROPIC_BASE_URL": "https://x.invalid"}
    )

    assert providers.find("claude", "mine") == landed
    assert dict(landed.env) == {"ANTHROPIC_BASE_URL": "https://x.invalid"}


def test_correcting_what_a_provider_holds_does_not_throw_away_its_login() -> None:
    """A key typed wrongly is not a reason to sign in again, so the credentials stay."""
    provider = providers.add("claude", "mine", way="login")
    signed = provider.at / "home" / ".credentials.json"
    signed.parent.mkdir(parents=True, exist_ok=True)
    signed.write_text('{"token": "signed in once"}')

    providers.add(
        "claude", "mine", way="login", env={"ANTHROPIC_BASE_URL": "https://x"}
    )

    assert json.loads(signed.read_text()) == {"token": "signed in once"}


def test_what_holds_keys_is_readable_by_nobody_else() -> None:
    provider = providers.add("claude", "mine", env={"ANTHROPIC_API_KEY": "not-a-key"})

    assert stat.S_IMODE((provider.at / "provider.json").stat().st_mode) == 0o600
    assert stat.S_IMODE(provider.at.stat().st_mode) == 0o700
    # And nothing half-written is left beside it: the file is moved into place whole.
    assert sorted(one.name for one in provider.at.iterdir()) == [
        "home",
        "provider.json",
        "user",
    ]


def test_a_provider_taken_away_is_gone_and_stays_gone() -> None:
    provider = providers.add("claude", "mine", way="login")
    signed = provider.at / "home" / ".credentials.json"
    signed.parent.mkdir(parents=True, exist_ok=True)
    signed.write_text('{"token": "an account this machine can run turns as"}')

    assert providers.remove("claude-code", "mine") is True

    assert not provider.at.exists()
    assert providers.find("claude", "mine") is None
    assert providers.remove("claude", "mine") is False


@pytest.mark.parametrize("profile", backends.PROFILES, ids=lambda one: one.name)
def test_a_turn_is_answered_at_every_path_the_backend_keeps_a_credential_at(
    profile: backends.Profile, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two homes, two roots: a file of the CLI's own under `home/`, one of yours under `user/`."""
    house = tmp_path / "house"
    monkeypatch.setenv("HOME", str(house))
    monkeypatch.delenv(profile.home_var, raising=False)
    provider = providers.add(profile.name, "mine")

    swaps = provider.swaps()

    assert len(swaps) == len(profile.creds)
    for said, (real, instead) in zip(profile.creds, swaps, strict=True):
        if said.startswith("~/"):
            assert real == str(house / said[2:])
            assert instead == str(provider.at / "user" / said[2:])
        else:
            assert real == str(profile.directory() / said)
            assert instead == str(provider.at / "home" / said)
    # Two files of the same name under two homes are two files here, not one written twice.
    assert len({instead for _, instead in swaps}) == len(swaps)


def test_making_a_provider_makes_the_places_its_credentials_will_land() -> None:
    """A CLI writing its credentials file expects the directory to be there; its own is."""
    for cli in ("claude", "kimi", "opencode"):
        provider = providers.add(cli, "mine")
        for _, instead in provider.swaps():
            assert Path(instead).parent.is_dir()
            assert stat.S_IMODE(Path(instead).parent.stat().st_mode) == 0o700


def test_the_command_a_turn_is_spawned_as_names_every_path_it_is_answered_at() -> None:
    provider = providers.add("claude", "mine")

    spawned = provider.command(["claude", "--print"])

    assert spawned[:4] == [sys.executable, "-m", "hmz", "cred"]
    assert spawned[spawned.index("--") + 1 :] == ["claude", "--print"]
    assert len([one for one in spawned if one.startswith("--map=")]) == len(
        provider.swaps()
    )


def test_a_backend_that_names_no_credentials_costs_no_supervisor_at_all() -> None:
    """Nothing to point anywhere is a turn spawned exactly as it would have been."""
    provider = store.Provider(cli="nope", name="mine")

    assert provider.swaps() == ()
    assert provider.command(["sh", "-c", "true"]) == ["sh", "-c", "true"]


def test_a_backend_offers_its_own_ways_in_and_then_variables_of_your_own() -> None:
    claude = backends.named("claude")
    assert claude is not None

    offered = providers.ways("claude-code")

    assert offered[: len(claude.ways)] == claude.ways
    assert offered[-1] is providers.ENV
    assert providers.ways("nope") == ()


def test_deepseek_harness_offers_only_its_api_key_way() -> None:
    offered = providers.ways("deepseek-harness")

    assert [way.name for way in offered] == ["key"]
    assert [one.env for one in offered[0].asks] == ["DEEPSEEK_API_KEY"]


def test_variables_of_your_own_are_read_off_the_lines_they_were_typed_as() -> None:
    said = providers.env_of(
        "ANTHROPIC_BASE_URL=https://example.invalid/?a=b\n"
        "\n"
        "# what this one is for\n"
        "  ANTHROPIC_AUTH_TOKEN = not-a-real-token  \n"
    )

    assert list(said.items()) == [
        ("ANTHROPIC_BASE_URL", "https://example.invalid/?a=b"),
        ("ANTHROPIC_AUTH_TOKEN", "not-a-real-token"),
    ]


@pytest.mark.parametrize("said", ["nonsense", "=value", " = ", "NAME"])
def test_a_line_that_is_not_a_variable_is_a_line_to_correct(said: str) -> None:
    with pytest.raises(ValueError, match="is not NAME=VALUE"):
        providers.env_of(said)


def test_an_answer_is_filled_into_whatever_a_way_wrote_it_into() -> None:
    assert (
        providers.filled("base_url={URL}", {"URL": "https://x"}) == "base_url=https://x"
    )
    # A brace naming nothing is a brace the backend itself is being given.
    assert providers.filled("{model}", {"URL": "https://x"}) == "{model}"


def test_a_turn_with_no_provider_is_given_nothing_on_top_of_what_it_inherits() -> None:
    assert providers.environ(None) == {}


def test_what_a_turn_is_run_with_is_a_copy_of_what_the_provider_holds() -> None:
    provider = providers.add("claude", "mine", env={"ANTHROPIC_API_KEY": "not-a-key"})

    taken = providers.environ(provider)
    taken["ANTHROPIC_API_KEY"] = "somebody else's"

    assert dict(provider.env) == {"ANTHROPIC_API_KEY": "not-a-key"}


def test_every_level_of_the_store_is_this_users_own(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A tree of credentials, and no level of it readable by anybody else."""
    monkeypatch.setenv("HUMANIZE_HOME", str(tmp_path / "held"))

    def loosely(mask: int) -> int:
        """A machine whose umask lets a group write, which is what a shared one does."""
        del mask
        return 0o002

    monkeypatch.setattr(os, "umask", loosely)

    provider = store.add("claude", "mine", env={"ANTHROPIC_API_KEY": "not-a-key"})

    at = provider.at
    for one in (at, at.parent, at.parent.parent, at / "home", at / "user"):
        assert one.stat().st_mode & 0o777 == 0o700, one
    assert (at / "provider.json").stat().st_mode & 0o777 == 0o600
