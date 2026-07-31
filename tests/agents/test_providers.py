"""Which account an agent's turns run as, and what that does to the turn.

Two things reach a backend from a provider: the variables it was made with, which is how a key
or an endpoint gets in, and the paths its credentials are answered by, which is how a login
does. What is checked here is that both reach the turn, that an agent with no provider is run
exactly as it always was, and that two agents of one CLI under two providers are two accounts
-- which is the whole point of the thing.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from typing import TYPE_CHECKING

import pytest

from humanize import providers
from humanize.agents import AgentConfig, ClaudeCodeAgent, ClaudeCodeAgentConfig
from humanize.backends import named
from humanize.machines import MachineBase, MachineConfig
from tests.stubs import HereAnchor, ShellAgent, ShellSession

if TYPE_CHECKING:
    from pathlib import Path

CONFIG = AgentConfig(model="m", effort="high")


class _ClaudeShellSession(ShellSession):
    """A shell session that says it is Claude's, so a provider's real paths are in play."""


class _ClaudeShellAgent(ShellAgent):
    """A shell-backed agent wearing Claude's name, which is what a provider is looked up by."""

    @property
    def backend(self) -> str:
        return "claude"

    def new(self) -> _ClaudeShellSession:
        return _ClaudeShellSession(self)


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Puts this user's home somewhere temporary, so nothing here can read the real one."""
    house = tmp_path / "home"
    (house / ".claude").mkdir(parents=True)
    monkeypatch.setenv("HOME", str(house))
    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)
    # What the machine itself is signed in as, which a turn under a provider must never see.
    (house / ".claude.json").write_text('{"account": "the one at this machine"}')
    (house / ".claude" / ".credentials.json").write_text('{"token": "this machine"}')
    return house


def test_an_agent_with_no_provider_is_run_exactly_as_it_was() -> None:
    agent = ShellAgent(CONFIG)

    assert agent.provider is None
    assert agent.environment() == {}
    assert agent.spawned(["sh", "-c", "echo hi"]) == ["sh", "-c", "echo hi"]
    assert agent.new()("echo hi") == "hi"


def test_a_provider_that_is_variables_is_what_the_turn_is_run_with(home: Path) -> None:
    """A key, an endpoint, an account on somebody's cloud: every CLI reads one as a variable."""
    providers.add(
        "claude",
        "gateway",
        way="gateway",
        env={
            "ANTHROPIC_BASE_URL": "https://example.invalid/anthropic",
            "ANTHROPIC_AUTH_TOKEN": "not-a-real-token",
        },
    )
    agent = _ClaudeShellAgent(AgentConfig(model="m", effort="high", provider="gateway"))

    assert agent.environment() == {
        "ANTHROPIC_BASE_URL": "https://example.invalid/anthropic",
        "ANTHROPIC_AUTH_TOKEN": "not-a-real-token",
    }
    # The turn itself is run with them, on top of what it inherits.
    assert agent.new()('printf %s "$ANTHROPIC_BASE_URL"') == (
        "https://example.invalid/anthropic"
    )
    assert agent.new()('printf %s "$PATH"') == os.environ["PATH"]  # and keeps its own


@pytest.mark.timeout(120, method="thread")
def test_a_turn_under_a_provider_reads_that_providers_credentials(home: Path) -> None:
    """The whole errand: the CLI names its own path and is answered with the provider's."""
    provider = providers.add("claude", "mine", way="login")
    where = provider.at / "user" / ".claude.json"
    where.parent.mkdir(parents=True, exist_ok=True)
    where.write_text('{"account": "the provider"}')
    agent = _ClaudeShellAgent(AgentConfig(model="m", effort="high", provider="mine"))

    said = agent.new()('cat "$HOME/.claude.json"')

    assert json.loads(said) == {"account": "the provider"}
    # And what the machine itself is signed in as is untouched, both ways round.
    assert json.loads((home / ".claude.json").read_text()) == {
        "account": "the one at this machine"
    }


@pytest.mark.timeout(120, method="thread")
def test_what_a_turn_under_a_provider_writes_lands_in_that_provider(home: Path) -> None:
    """A token refreshed mid-run is written back where it was read from, which is the provider."""
    provider = providers.add("claude", "mine", way="login")
    agent = _ClaudeShellAgent(AgentConfig(model="m", effort="high", provider="mine"))

    assert agent.new()('printf refreshed > "$HOME/.claude/.credentials.json"; echo ok')

    assert (provider.at / "home" / ".credentials.json").read_text() == "refreshed"
    assert (
        home / ".claude" / ".credentials.json"
    ).read_text() == '{"token": "this machine"}'


@pytest.mark.timeout(180, method="thread")
def test_two_agents_of_one_cli_under_two_providers_are_two_accounts(home: Path) -> None:
    """The flame-chase case: one flow, one CLI, two accounts, at the same time."""
    for name in ("first", "second"):
        provider = providers.add("claude", name, way="login")
        where = provider.at / "user" / ".claude.json"
        where.parent.mkdir(parents=True, exist_ok=True)
        where.write_text(json.dumps({"account": name}))
    agents = [
        _ClaudeShellAgent(AgentConfig(model="m", effort="high", provider=name))
        for name in ("first", "second")
    ]

    said = [agent.new()('cat "$HOME/.claude.json"') for agent in agents]

    assert [json.loads(one)["account"] for one in said] == ["first", "second"]


@pytest.mark.timeout(180, method="thread")
def test_two_accounts_run_at_the_same_time_without_reading_each_others(
    home: Path,
) -> None:
    """At once rather than one after the other, which is how a flow would drive them."""
    import asyncio

    for name in ("first", "second"):
        provider = providers.add("claude", name, way="login")
        where = provider.at / "user" / ".claude.json"
        where.parent.mkdir(parents=True, exist_ok=True)
        where.write_text(json.dumps({"account": name}))
    agents = [
        _ClaudeShellAgent(AgentConfig(model="m", effort="high", provider=name))
        for name in ("first", "second")
    ]

    async def both() -> list[str]:
        return list(
            await asyncio.gather(
                *(
                    agent.aturn('sleep 0.2; cat "$HOME/.claude.json"')
                    for agent in agents
                )
            )
        )

    said = asyncio.run(both())

    assert [json.loads(one)["account"] for one in said] == ["first", "second"]


def test_a_key_left_lying_about_does_not_outrank_the_account_it_was_told(
    home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """These CLIs take a key from the environment over the one they were signed in with.

    So a turn under a provider is run without every variable its backend would read an
    account from -- an `ANTHROPIC_API_KEY` in somebody's shell profile would otherwise be the
    account the turn was taken as, and the bill the first thing to say so.
    """
    monkeypatch.setenv("ANTHROPIC_API_KEY", "the one in the shell")
    monkeypatch.setenv("CLAUDE_CODE_USE_BEDROCK", "1")
    providers.add("claude", "mine", way="login")
    agent = _ClaudeShellAgent(AgentConfig(model="m", effort="high", provider="mine"))

    assert "ANTHROPIC_API_KEY" in agent.hushed()
    assert (
        agent.new()('printf "[%s]" "$ANTHROPIC_API_KEY$CLAUDE_CODE_USE_BEDROCK"')
        == "[]"
    )
    # And what is none of the account's business is left exactly as it was found.
    assert agent.new()('printf %s "$PATH"') == os.environ["PATH"]


def test_a_provider_keeps_the_variables_it_set_itself(
    home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "the one in the shell")
    providers.add(
        "claude", "gateway", way="gateway", env={"ANTHROPIC_API_KEY": "its own"}
    )
    agent = _ClaudeShellAgent(AgentConfig(model="m", effort="high", provider="gateway"))

    assert "ANTHROPIC_API_KEY" not in agent.hushed()
    assert agent.new()('printf %s "$ANTHROPIC_API_KEY"') == "its own"


def test_an_agent_with_no_provider_is_run_with_the_environment_it_was_started_in(
    home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Nothing is taken away from an agent nobody said anything about."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "the one in the shell")
    agent = _ClaudeShellAgent(AgentConfig(model="m", effort="high"))

    assert agent.hushed() == frozenset()
    assert agent.new()('printf %s "$ANTHROPIC_API_KEY"') == "the one in the shell"


def test_an_agent_told_of_an_account_there_is_none_of_says_so(home: Path) -> None:
    """Rather than quietly running as whoever is signed in here, which is the wrong account."""
    agent = _ClaudeShellAgent(AgentConfig(model="m", effort="high", provider="nowhere"))

    with pytest.raises(ValueError, match="no claude provider called 'nowhere'"):
        _ = agent.provider


def test_what_a_provider_adds_to_the_command_line_is_added_to_the_backends(
    home: Path,
) -> None:
    """Codex takes a provider as settings rather than variables, so a way may carry arguments."""
    providers.add(
        "claude", "mine", way="gateway", env={"X": "1"}, args=("--flag", "value")
    )
    agent = _ClaudeShellAgent(AgentConfig(model="m", effort="high", provider="mine"))

    spawned = agent.spawned(["claude", "--print"])

    assert spawned[:4] == [sys.executable, "-m", "humanize", "cred"]
    # The backend's own line, the provider's arguments at the end of it.
    assert spawned[spawned.index("--") + 1 :] == [
        "claude",
        "--print",
        "--flag",
        "value",
    ]


@dataclass(frozen=True, kw_only=True)
class _StubMachineConfig(MachineConfig):
    """A machine that is only ever said to be started, holding the anchor it hands back."""

    anchor: HereAnchor

    def create(self) -> _StubMachine:
        return _StubMachine(self)


class _StubMachine(MachineBase):
    def __init__(self, config: _StubMachineConfig) -> None:
        super().__init__(config)
        self._anchor = config.anchor

    def start(self) -> HereAnchor:
        return self._anchor

    def stop(self) -> None:
        """Nothing was started, so there is nothing to take down."""


def test_a_turn_that_is_anchored_and_under_a_provider_is_supervised_once(
    home: Path,
) -> None:
    """A process has one tracer, so the anchor is told what to answer rather than wrapped."""
    providers.add("claude", "mine", way="login")
    anchor = HereAnchor(target="tcp://stub:0")
    agent = _ClaudeShellAgent(
        AgentConfig(
            model="m",
            effort="high",
            provider="mine",
            machine=_StubMachineConfig(anchor=anchor),
        )
    )

    spawned = agent.spawned(["claude", "--print"])

    # Nothing of ours around it: the anchor's own supervisor is the one that will run it.
    assert spawned == ["claude", "--print"]
    assert anchor.seen == [["claude", "--print"]]
    assert anchor.kept == [[]]  # a login carries no variables, so none are held back
    (answered,) = anchor.answered
    assert (
        str(home / ".claude" / ".credentials.json"),
        str(providers.where("claude", "mine") / "home" / ".credentials.json"),
    ) in answered


def test_an_anchored_turn_keeps_its_providers_variables_off_the_target(
    home: Path,
) -> None:
    """A key crossing to another machine is a key on that machine, so it does not cross.

    Everything an agent exports is inherited by every command it runs on the target, so the
    variables a provider hands it are named as the agent's own and dropped on the way over.
    """
    providers.add(
        "claude", "gateway", way="gateway", env={"ANTHROPIC_AUTH_TOKEN": "not-a-token"}
    )
    anchor = HereAnchor(target="tcp://stub:0")
    agent = _ClaudeShellAgent(
        AgentConfig(
            model="m",
            effort="high",
            provider="gateway",
            machine=_StubMachineConfig(anchor=anchor),
        )
    )

    agent.spawned(["claude", "--print"])

    assert anchor.kept == [["ANTHROPIC_AUTH_TOKEN"]]


def test_a_provider_of_a_backend_with_no_credentials_named_is_only_variables() -> None:
    """A stand-in backend has no paths written down, so there is nothing to supervise."""
    agent = ShellAgent(CONFIG)

    assert named(agent.backend) is None
    assert agent.spawned(["sh", "-c", "true"]) == ["sh", "-c", "true"]


def test_a_provider_reaches_the_command_a_real_backend_builds(
    home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Read off the real driver rather than a stand-in: the seam is on the agent, not the CLI."""
    providers.add("claude", "mine", way="key", env={"ANTHROPIC_API_KEY": "not-real"})
    agent = ClaudeCodeAgent(
        ClaudeCodeAgentConfig(model="claude-opus-5", effort="high", provider="mine")
    )

    assert agent.environment() == {"ANTHROPIC_API_KEY": "not-real"}
    spawned = agent.spawned(["claude", "--print"])
    assert spawned[:4] == [sys.executable, "-m", "humanize", "cred"]
    assert any(f"--map={home}/.claude/.credentials.json=" in one for one in spawned), (
        spawned
    )
