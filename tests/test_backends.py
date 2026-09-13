"""What is written down about each coding agent CLI, and how a name is read back into it."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from hmz.coganchor import backends

if TYPE_CHECKING:
    from pathlib import Path


def test_every_backend_answers_to_its_own_name() -> None:
    for profile in backends.PROFILES:
        assert profile.name in profile.aliases
        assert backends.named(profile.name) is profile


def test_no_two_backends_answer_to_one_name() -> None:
    spellings = [alias for profile in backends.PROFILES for alias in profile.aliases]
    assert len(spellings) == len(set(spellings))


def test_a_home_of_its_own_is_moved_whole(monkeypatch: pytest.MonkeyPatch) -> None:
    claude = backends.named("claude")
    assert claude is not None
    monkeypatch.setenv(claude.home_var, "/elsewhere/claude")
    assert str(claude.directory()) == "/elsewhere/claude"


def test_a_home_shared_with_every_program_keeps_its_own_directory_under_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`XDG_DATA_HOME` says where everything keeps its data, not where opencode keeps its."""
    opencode = backends.named("opencode")
    assert opencode is not None
    monkeypatch.setenv("XDG_DATA_HOME", "/elsewhere/share")
    assert str(opencode.directory()) == "/elsewhere/share/opencode"
    monkeypatch.delenv("XDG_DATA_HOME")
    assert str(opencode.directory()).endswith(".local/share/opencode")


def test_an_agent_is_read_off_a_command_line() -> None:
    place, profile, model, effort, provider = backends.read(
        "pi/openai-codex/gpt-5.5:high"
    )
    assert (profile.name, model, effort) == ("pi", "openai-codex/gpt-5.5", "high")
    assert place == ""  # filling whichever place the flow takes next
    assert provider == ""  # as whoever is at this machine already runs it
    _, profile, model, effort, _ = backends.read("mimocode/xiaomi/mimo-v2.5:low")
    assert (profile.name, model, effort) == ("mimo", "xiaomi/mimo-v2.5", "low")
    # Read from both ends, so a model holding slashes of its own keeps every one of them.
    _, profile, model, effort, _ = backends.read(
        "claude/azure/anthropic/claude-haiku-4-5:high"
    )
    assert (profile.name, model, effort) == (
        "claude",
        "azure/anthropic/claude-haiku-4-5",
        "high",
    )


def test_an_agent_may_name_the_place_it_fills() -> None:
    """Which is a field of the tuple of agents the flow declares, so it is an identifier."""
    place, profile, model, _, provider = backends.read(
        "reviewer=claude@deepseek/claude-opus-5:high"
    )
    assert (place, profile.name, model, provider) == (
        "reviewer",
        "claude",
        "claude-opus-5",
        "deepseek",
    )
    with pytest.raises(ValueError, match="is not a place a flow could declare"):
        backends.read("a reviewer=claude/m:high")
    with pytest.raises(ValueError, match="is not a place a flow could declare"):
        backends.read("=claude/m:high")


def test_one_spec_is_one_agent_however_many_a_line_names() -> None:
    """A `,` separates them, so one holding a comma is a list nobody split."""
    with pytest.raises(ValueError, match="expected one agent"):
        backends.read("claude/m:high,codex/m:high")


def test_the_written_out_form_is_gone_and_says_what_to_write_instead() -> None:
    """`=` and `,` name the place an agent fills now, so the two spellings cannot coexist."""
    for said in (
        "cli=claude",
        "model=m",
        "effort=high",
        "provider=work",
        "service_tier=fast",
        "config.model_context_window=1000000",
        "config.allowed_tools=Bash(git diff *)",
    ):
        with pytest.raises(ValueError, match=r"is gone: an agent is written"):
            backends.read(said)


def test_an_agent_may_name_the_account_it_runs_as() -> None:
    """Two agents of one CLI are two accounts when the line says so."""
    _, profile, model, effort, provider = backends.read(
        "claude@deepseek/claude-opus-5:high"
    )
    assert (profile.name, model, effort, provider) == (
        "claude",
        "claude-opus-5",
        "high",
        "deepseek",
    )
    # A CLI is never spelled with an `@` in it, so the model keeps whatever it holds.
    _, profile, model, _, provider = backends.read("kimi@mine/kimi-code/k3:max")
    assert (profile.name, model, provider) == ("kimi", "kimi-code/k3", "mine")
    with pytest.raises(ValueError, match="expected an account after @"):
        backends.read("claude@/m:high")


@pytest.mark.parametrize(
    "said", ["permission=read-only", "permission=bypass", "web_search=off"]
)
def test_what_the_flow_says_is_not_a_line_to_say_it_on(said: str) -> None:
    """What an agent may do and whether it reads the internet are the flow's, and only its."""
    with pytest.raises(ValueError, match="is the flow's to say"):
        backends.read(said)


def test_a_backend_nobody_has_heard_of_is_a_line_to_correct() -> None:
    assert backends.named("nope") is None
    with pytest.raises(ValueError, match=r"expected \[NAME=\]CLI"):
        backends.read("nope/model:high")
    with pytest.raises(ValueError, match=r"expected \[NAME=\]CLI"):
        backends.read("builder=nope/model:high")


def _installed_at(directory: Path, name: str) -> Path:
    """Puts a program of that name in a directory, the way an installer would."""
    directory.mkdir(parents=True, exist_ok=True)
    program = directory / name
    program.write_text("#!/bin/sh\nexit 0\n")
    program.chmod(0o755)
    return program


def test_a_cli_the_path_names_is_the_one_that_is_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Whatever somebody put in front stays in front: PATH is looked at first."""
    wanted = _installed_at(tmp_path / "bin", "codex")
    _installed_at(tmp_path / "local", "codex")
    monkeypatch.setenv("PATH", str(tmp_path / "bin"))
    monkeypatch.setattr(backends, "_INSTALLED_AT", (str(tmp_path / "local"),))

    assert backends.program("codex") == str(wanted)


def test_a_cli_installed_where_installers_install_one_is_found_off_any_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A PATH of somebody else's is not a machine with nothing installed on it.

    A notebook kernel, a service and a runtime platform's launcher each hand their child the
    PATH they were given, and an agent installed here is installed either way.
    """
    wanted = _installed_at(tmp_path / "local", "codex")
    monkeypatch.setenv("PATH", str(tmp_path / "empty"))
    monkeypatch.setattr(backends, "_INSTALLED_AT", (str(tmp_path / "local"),))

    assert backends.program("codex") == str(wanted)


def test_a_name_nothing_answers_to_is_no_program(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PATH", str(tmp_path / "empty"))
    monkeypatch.setattr(backends, "_INSTALLED_AT", (str(tmp_path / "local"),))

    assert backends.program("codex") is None


def test_a_command_written_as_a_path_is_that_path_or_nothing(tmp_path: Path) -> None:
    """One somebody wrote down is where they said, rather than a name to go looking for."""
    program = _installed_at(tmp_path / "opt", "codex")
    unrunnable = tmp_path / "opt" / "notes.txt"
    unrunnable.write_text("not a program")

    assert backends.program(str(program)) == str(program)
    assert backends.program(str(unrunnable)) is None


def test_an_account_kept_where_every_program_keeps_its_configuration_moves_with_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Claude keeps one where the vendor's other programs read it, and `XDG_CONFIG_HOME` moves it.

    Which is a third root and not a spelling of either of the others: neither the variable that
    moves the backend's own home nor the user's home reaches it, so a provider that mapped only
    those two would leave the machine's own account readable and answer every turn with it.
    """
    claude = backends.named("claude")
    assert claude is not None
    monkeypatch.setenv("XDG_CONFIG_HOME", "/elsewhere/config")

    kept = {under: real for real, under in claude.credentials()}

    assert kept["config/anthropic"] == "/elsewhere/config/anthropic"


def test_an_endpoint_a_backend_sends_its_credential_to_is_an_account() -> None:
    """A variable naming where the token goes is as much an account as one holding the token.

    `CODEX_AUTHAPI_BASE_URL` is where codex asks whose credential it is holding, and it sends
    that credential to ask; `ANTHROPIC_CONFIG_DIR` moves the whole directory Claude reads one
    out of. Left set, either takes a turn somewhere the provider never named.
    """
    codex = backends.named("codex")
    claude = backends.named("claude")
    assert codex is not None
    assert claude is not None

    assert "CODEX_AUTHAPI_BASE_URL" in codex.accounts()
    assert "ANTHROPIC_CONFIG_DIR" in claude.accounts()


def test_a_turn_is_run_without_every_spelling_of_the_account_not_just_the_written_one() -> (
    None
):
    """A CLI reads a credential's aliases too, so hushing only the written name leaves a leak.

    kimi takes an account from `MOONSHOT_API_KEY` as well as the `KIMI_API_KEY` its ways name,
    and opencode from `GOOGLE_API_KEY` as well as `GEMINI_API_KEY`. `accounts()` is the names a
    backend wrote down; `hushes()` is those and every alias, which is what a provider's turn is
    actually run without -- `serves()` still copies by the written name, so the two differ.
    """
    kimi = backends.named("kimi")
    opencode = backends.named("opencode")
    assert kimi is not None
    assert opencode is not None

    assert "MOONSHOT_API_KEY" not in kimi.accounts()
    assert "MOONSHOT_API_KEY" in kimi.hushes()
    assert "GOOGLE_API_KEY" in opencode.hushes()
    # Every account name is hushed too: the aliases are added to it, never in place of it.
    assert kimi.accounts() <= kimi.hushes()
