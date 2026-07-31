"""What is written down about each coding agent CLI, and how a name is read back into it."""

from __future__ import annotations

import pytest

from humanize import backends


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
    profile, model, effort = backends.read("pi/openai-codex/gpt-5.5:high")
    assert (profile.name, model, effort) == ("pi", "openai-codex/gpt-5.5", "high")
    profile, model, effort = backends.read("mimocode/xiaomi/mimo-v2.5:low")
    assert (profile.name, model, effort) == ("mimo", "xiaomi/mimo-v2.5", "low")
    profile, model, effort = backends.read(
        "cli=opencode,model=opencode/big-pickle,effort=xhigh"
    )
    assert (profile.name, model, effort) == ("opencode", "opencode/big-pickle", "xhigh")


def test_a_backend_nobody_has_heard_of_is_a_line_to_correct() -> None:
    assert backends.named("nope") is None
    with pytest.raises(ValueError, match="expected CLI/MODEL:EFFORT"):
        backends.read("nope/model:high")
