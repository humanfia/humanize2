"""An account marked as the fallback, and the turn that carries on under it.

A provider goes down -- a key revoked, a gateway refusing, a subscription out of quota -- and
what a flow sees is a turn that failed. What is checked here is that the turn is run again
under the account marked for it, on the same conversation, and that a run with nowhere to go
still fails the way it always did.
"""

from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING

import pytest

from hmz import backends, providers
from hmz.agents import AgentConfig
from tests.stubs import ShellAgent

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def accounts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Two accounts for one backend: the one an agent runs as, and one to fall back to."""
    monkeypatch.setenv("HUMANIZE_HOME", str(tmp_path / "home"))
    # The stand-in agent's class names the backend `shell`, so that is the backend these are
    # accounts of: added as a CLI of your own, which is a backend like any other.
    backends.remember("shell", ["sh"])
    providers.add("shell", "main", env={"DOWN": "1", "WHOSE": "main"})
    providers.add("shell", "spare", env={"WHOSE": "spare"})


def _agent(provider: str) -> ShellAgent:
    """An agent whose turns run a shell script, as whichever account it was given."""
    return ShellAgent(AgentConfig(model="m", effort="high", provider=provider))


def test_an_account_is_marked_as_the_fallback_and_only_one_is(accounts: None) -> None:
    """Marking a second unmarks the first: a fallback is where a turn goes, and one place."""
    assert providers.falls_back("shell") is None
    providers.marks("shell", "spare", fallback=True)
    spare = providers.falls_back("shell")
    assert spare is not None
    assert spare.name == "spare"

    providers.marks("shell", "main", fallback=True)
    main = providers.falls_back("shell")
    assert main is not None
    assert main.name == "main"
    assert [one.fallback for one in providers.providers("shell")] == [True, False]


def test_the_mark_outlives_the_run(accounts: None) -> None:
    """It is written down beside the account rather than held for one session."""
    providers.marks("shell", "spare", fallback=True)
    found = providers.find("shell", "spare")
    assert found is not None
    assert found.fallback is True


def test_a_turn_whose_account_failed_carries_on_under_the_fallback(
    accounts: None, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The same session, under the other account, without the flow being told to retry."""
    providers.marks("shell", "spare", fallback=True)
    agent = _agent("main")
    session = agent.new()

    # `main` sets DOWN and so fails; `spare` does not, and answers as itself.
    assert session(_FLAKY_AS_SCRIPT) == "spare"
    assert agent.provider is not None
    assert agent.provider.name == "spare"


def test_a_turn_with_nowhere_to_fall_back_to_fails_as_it_always_did(
    accounts: None,
) -> None:
    """No mark, no second try: a failed turn is a failed turn."""
    with pytest.raises(subprocess.CalledProcessError):
        _agent("main").new()(_FLAKY_AS_SCRIPT)


def test_an_agent_already_running_as_the_fallback_does_not_move(accounts: None) -> None:
    """There is nowhere to go from the place a turn already fell back to."""
    providers.marks("shell", "main", fallback=True)
    agent = _agent("main")
    assert agent.falls_back() is None
    with pytest.raises(subprocess.CalledProcessError):
        agent.new()(_FLAKY_AS_SCRIPT)


#: The stand-in as one line a shell session runs, since that agent takes its prompt as a
#: script: the same two-branch behaviour, written where the prompt goes.
_FLAKY_AS_SCRIPT = (
    'if [ -n "$DOWN" ]; then echo "the account is down" >&2; exit 1; fi; '
    'echo "${WHOSE:-nobody}"'
)
