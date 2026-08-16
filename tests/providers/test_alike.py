"""One account, several backends: a vendor's credential is the vendor's rather than a CLI's.

An Anthropic key is an Anthropic key whether Claude Code, pi, opencode or mimocode is holding
it, and a Claude subscription token is one under whatever name each of them reads it under. So
an account made for one backend is often an account several others could be run as -- and
making the same key four times by hand is four places to correct when it is rotated.

What cannot travel is an account that is not variables at all: a subscription signed into
writes the CLI's own credential store, in that CLI's own format, and nothing else reads it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from hmz import backends, providers

if TYPE_CHECKING:
    from pathlib import Path


def test_a_vendor_key_is_an_account_every_backend_that_reads_it_could_run() -> None:
    """Worked out from what each backend says it would take an account from."""
    one = providers.add("claude", "work", "key", {"ANTHROPIC_API_KEY": "sk-x"})

    assert providers.serves(one) == ("pi", "opencode", "mimo", "zcode")


def test_one_credential_under_two_names_is_one_credential() -> None:
    """A CLI that named a vendor's credential after itself named the same thing."""
    one = providers.add("claude", "sub", "token", {"CLAUDE_CODE_OAUTH_TOKEN": "t"})

    assert providers.serves(one) == ("pi",)
    assert backends.serves(one.env, "pi") == {"ANTHROPIC_OAUTH_TOKEN": "t"}


def test_an_account_that_is_files_rather_than_variables_travels_nowhere() -> None:
    """A subscription signed into is the CLI's own store, in that CLI's own format."""
    one = providers.add("claude", "signed-in", "login", {})

    assert providers.serves(one) == ()


def test_a_credential_the_other_backend_has_no_name_for_is_not_one_it_could_run() -> (
    None
):
    """Every part of an account has to travel, or the account does not."""
    one = providers.add(
        "codex",
        "gate",
        "gateway",
        {"CODEX_PROVIDER_URL": "https://x", "CODEX_PROVIDER_KEY": "k"},
    )

    assert providers.serves(one) == ()
    assert backends.serves(one.env, "opencode") is None


def test_copying_one_writes_it_down_under_the_names_that_backend_reads(
    tmp_path: Path,
) -> None:
    """The same account, spelled as the backend it is being copied to reads it."""
    del tmp_path
    one = providers.add("claude", "sub", "token", {"CLAUDE_CODE_OAUTH_TOKEN": "t"})

    copied = providers.copies(one, "pi")

    assert copied.cli == "pi"
    assert copied.name == "sub"  # the same name: it is the same account
    assert dict(copied.env) == {"ANTHROPIC_OAUTH_TOKEN": "t"}
    held = providers.find("pi", "sub")
    assert held is not None
    assert dict(held.env) == {"ANTHROPIC_OAUTH_TOKEN": "t"}


def test_a_copy_says_it_was_made_by_the_way_that_asks_for_exactly_it() -> None:
    """So a copied key reads as that backend's key way rather than as something unnamed."""
    one = providers.add("codex", "work", "key", {"OPENAI_API_KEY": "sk-x"})

    assert (
        providers.copies(one, "qwen").way == providers.ENV.name
    )  # qwen's key asks two
    assert (
        providers.copies(one, "pi").way == providers.ENV.name
    )  # pi's only way is a login


def test_copying_over_one_already_there_is_how_a_key_is_rotated_everywhere() -> None:
    """Which is the point of copying it in the first place: one place to correct."""
    one = providers.add("claude", "work", "key", {"ANTHROPIC_API_KEY": "old"})
    providers.copies(one, "opencode")

    rotated = providers.add("claude", "work", "key", {"ANTHROPIC_API_KEY": "new"})
    providers.copies(rotated, "opencode")

    held = providers.find("opencode", "work")
    assert held is not None
    assert dict(held.env) == {"ANTHROPIC_API_KEY": "new"}
    # And the credentials that were already in its directory are left where they are.
    assert len(providers.providers("opencode")) == 1


def test_a_backend_that_could_not_run_it_is_refused_rather_than_written_down() -> None:
    """A copy that would be an account nothing can be run as is not a copy to make."""
    one = providers.add("claude", "signed-in", "login", {})

    with pytest.raises(ValueError, match="not an account"):
        providers.copies(one, "codex")
    assert providers.find("codex", "signed-in") is None


def test_a_name_no_backend_answers_to_is_refused() -> None:
    one = providers.add("claude", "work", "key", {"ANTHROPIC_API_KEY": "sk-x"})

    with pytest.raises(ValueError, match="not an account"):
        providers.copies(one, "not-a-backend")


def test_every_name_a_credential_goes_by_is_written_down_once() -> None:
    """The sameness is the fact; which backends read it is already written elsewhere."""
    assert backends.alike("ANTHROPIC_OAUTH_TOKEN") == (
        "CLAUDE_CODE_OAUTH_TOKEN",
        "ANTHROPIC_OAUTH_TOKEN",
    )
    # And a credential nothing else has a name for goes by its own name alone.
    assert backends.alike("CODEX_PROVIDER_URL") == ("CODEX_PROVIDER_URL",)
    named = [name for held in backends.ALIKE for name in held]
    assert len(named) == len(set(named)), "a variable is one credential, not two"
