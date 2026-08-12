"""What is written down about each coding agent CLI, and how a name is read back into it."""

from __future__ import annotations

import pytest

from hmz import backends


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


def test_an_agent_is_read_off_a_command_line_however_it_is_spelled() -> None:
    profile, model, effort, tier, provider, permission, overrides = backends.read(
        "pi/openai-codex/gpt-5.5:high"
    )
    assert (profile.name, model, effort) == ("pi", "openai-codex/gpt-5.5", "high")
    assert tier == "default"
    assert provider == ""  # as whoever is at this machine already runs it
    assert permission is None  # at the default rung
    assert overrides == ()
    profile, model, effort, _, _, _, _ = backends.read("mimocode/xiaomi/mimo-v2.5:low")
    assert (profile.name, model, effort) == ("mimo", "xiaomi/mimo-v2.5", "low")
    profile, model, effort, _, _, _, _ = backends.read(
        "cli=opencode,model=opencode/big-pickle,effort=xhigh"
    )
    assert (profile.name, model, effort) == ("opencode", "opencode/big-pickle", "xhigh")


def test_an_agent_may_name_the_account_it_runs_as() -> None:
    """Two agents of one CLI are two accounts when the line says so, either way it is written."""
    profile, model, effort, _, provider, _, _ = backends.read(
        "claude@deepseek/claude-opus-5:high"
    )
    assert (profile.name, model, effort, provider) == (
        "claude",
        "claude-opus-5",
        "high",
        "deepseek",
    )
    _, _, _, _, provider, _, _ = backends.read(
        "cli=claude,model=claude-opus-5,effort=high,provider=work"
    )
    assert provider == "work"
    # A CLI is never spelled with an `@` in it, so the model keeps whatever it holds.
    profile, model, _, _, provider, _, _ = backends.read("kimi@mine/kimi-code/k3:max")
    assert (profile.name, model, provider) == ("kimi", "kimi-code/k3", "mine")


def test_an_agent_may_name_its_permission_rung() -> None:
    """Only the written-out form has somewhere unambiguous to put the fourth setting."""
    profile, model, effort, tier, provider, permission, overrides = backends.read(
        "cli=codex,model=gpt-5.6-sol,effort=high,permission=read-only"
    )

    assert (profile.name, model, effort, tier, provider, permission, overrides) == (
        "codex",
        "gpt-5.6-sol",
        "high",
        "default",
        "",
        "read-only",
        (),
    )


def test_a_backend_nobody_has_heard_of_is_a_line_to_correct() -> None:
    assert backends.named("nope") is None
    with pytest.raises(ValueError, match="expected CLI"):
        backends.read("nope/model:high")
    with pytest.raises(
        ValueError,
        match=r"not cli, model, effort, service_tier, provider, permission or config\.KEY",
    ):
        backends.read("cli=claude,model=m,effort=high,machine=elsewhere")


def test_a_codex_agent_may_name_app_server_overrides() -> None:
    """`config.KEY` is that agent's, and Codex passes its pairs to app-server `-c`."""
    profile, _, _, _, _, _, overrides = backends.read(
        "cli=codex,model=gpt-5.6-sol,effort=high,"
        "config.model_context_window=1000000,"
        "config.model_auto_compact_token_limit=900000"
    )
    assert profile.name == "codex"
    assert overrides == (
        ("model_context_window", "1000000"),
        ("model_auto_compact_token_limit", "900000"),
    )
    with pytest.raises(ValueError, match="only accepts allowed_tools"):
        backends.read(
            "cli=claude,model=m,effort=high,config.model_context_window=1000000"
        )


def test_a_claude_agent_may_name_one_native_allowed_tools_rule() -> None:
    profile, _, _, _, _, _, overrides = backends.read(
        "cli=claude,model=claude-opus-5,effort=max,"
        "config.allowed_tools=Bash(git diff *)"
    )
    assert profile.name == "claude"
    assert overrides == (("allowed_tools", "Bash(git diff *)"),)


@pytest.mark.parametrize("backend", ["claude", "codex"])
def test_supported_backends_share_one_service_tier_setting(backend: str) -> None:
    profile, _, _, tier, _, _, overrides = backends.read(
        f"cli={backend},model=m,effort=max,service_tier=fast"
    )
    assert profile.name == backend
    assert tier == "fast"
    assert overrides == ()
