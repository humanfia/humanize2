"""The chain of accounts a turn walks when one of them goes down, and the tries along it.

A provider goes down -- a key revoked, a gateway refusing, a subscription out of quota -- and
what a flow sees is a turn that failed. Each account says how many times a turn under it is
tried again, how long to wait between tries, and which account to carry on under once those
are spent; each of those names the next, so what a turn walks is a chain. What is checked here
is that it is walked in order, inside the conversation that was running, that a loop in it
ends, and that an agent with nowhere to go still fails the way it always did.
"""

from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING

import pytest

from hmz import backends, providers
from hmz.agents import AgentConfig
from hmz.providers import retry
from tests.stubs import ShellAgent

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def accounts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Three accounts for one backend: two that are down, and one that answers."""
    monkeypatch.setenv("HUMANIZE_HOME", str(tmp_path / "home"))
    # The stand-in agent's class names the backend `shell`, so that is the backend these are
    # accounts of: added as a CLI of your own, which is a backend like any other.
    backends.remember("shell", ["sh"])
    providers.add("shell", "main", env={"DOWN": "1", "WHOSE": "main"})
    providers.add("shell", "second", env={"DOWN": "1", "WHOSE": "second"})
    providers.add("shell", "spare", env={"WHOSE": "spare"})


def _agent(provider: str) -> ShellAgent:
    """An agent whose turns run a shell script, as whichever account it was given."""
    return ShellAgent(AgentConfig(model="m", effort="high", provider=provider))


def test_an_account_says_which_one_it_falls_back_to(accounts: None) -> None:
    """A name rather than a mark: what a turn walks is a chain, and each names the next."""
    assert providers.points("shell", "main", "second")
    assert providers.points("shell", "second", "spare")

    main = providers.find("shell", "main")
    assert main is not None
    assert main.fallback == "second"
    assert [one.name for one in providers.chain(main)] == ["main", "second", "spare"]
    # And it outlives the run: it is written down beside the account.
    assert providers.find("shell", "second") is not None


def test_a_chain_that_points_nowhere_or_at_itself_is_refused(accounts: None) -> None:
    """Both are a chain that goes nowhere, said where it is written rather than on the turn."""
    with pytest.raises(ValueError, match="cannot fall back to itself"):
        providers.points("shell", "main", "main")
    with pytest.raises(ValueError, match="no shell account called 'nonesuch'"):
        providers.points("shell", "main", "nonesuch")
    assert not providers.points("shell", "nobody", "spare")


def test_a_loop_in_the_chain_is_walked_once_and_ends(accounts: None) -> None:
    """A chain that came round on itself would otherwise be a run that never stopped."""
    providers.points("shell", "main", "second")
    providers.points("shell", "second", "main")
    main = providers.find("shell", "main")
    assert main is not None

    assert [one.name for one in providers.chain(main)] == ["main", "second"]


def test_a_turn_walks_the_chain_to_the_account_that_answers(accounts: None) -> None:
    """The same session, one account after the next, without the flow being told to retry."""
    providers.points("shell", "main", "second")
    providers.points("shell", "second", "spare")
    agent = _agent("main")
    session = agent.new()

    # `main` and `second` both set DOWN and so fail; `spare` does not, and says who it is.
    assert session(_FLAKY_AS_SCRIPT) == "spare"
    assert agent.provider is not None
    assert agent.provider.name == "spare"
    # And it stays there: the account that went down is not one to try again each turn.
    assert [one.name for one in agent.walks() if one] == ["spare"]


def test_a_turn_with_nowhere_to_fall_back_to_fails_as_it_always_did(
    accounts: None,
) -> None:
    """No chain, no second account: a failed turn is a failed turn."""
    with pytest.raises(subprocess.CalledProcessError):
        _agent("main").new()(_FLAKY_AS_SCRIPT)


def test_an_account_is_tried_again_before_the_chain_moves_on(
    accounts: None, tmp_path: Path
) -> None:
    """A gateway that answered 503 is the same call away from working, so it gets one."""
    providers.retrying("shell", "main", 2, "none", 0.0)
    providers.points("shell", "main", "spare")
    tally = tmp_path / "tries.txt"
    agent = _agent("main")

    assert agent.new()(_COUNTING.format(at=tally)) == "spare"

    # Three tries under the account that was down -- the first and the two it was given --
    # and then the one under the account that answered.
    assert tally.read_text().count("main") == 3
    assert tally.read_text().count("spare") == 1


def test_the_tries_stop_when_the_time_they_were_given_is_spent(
    accounts: None, tmp_path: Path
) -> None:
    """Checked before the wait, so a turn is never started knowing it is already past."""
    providers.retrying("shell", "main", 5, "constant", 0.5)
    tally = tmp_path / "tries.txt"

    with pytest.raises(subprocess.CalledProcessError):
        _agent("main").new()(_COUNTING.format(at=tally))

    # One wait of a second is already more than the half-second it was given, so the first
    # try is the only one taken.
    assert tally.read_text().count("main") == 1


def test_an_agent_as_this_machine_is_signed_in_takes_its_turn_once(
    accounts: None,
) -> None:
    """It is an account humanize did not make, so there is nothing written down about it."""
    agent = ShellAgent(AgentConfig(model="m", effort="high"))

    assert agent.walks() == (None,)
    assert agent.new()("echo here") == "here"


def test_the_waits_are_the_ones_everybody_uses() -> None:
    """Each under the name it is known by, and none of them invented here."""
    assert [retry.waits("constant", at) for at in (1, 2, 3, 4)] == [0.0, 1.0, 1.0, 1.0]
    assert [retry.waits("linear", at) for at in (1, 2, 3, 4)] == [0.0, 1.0, 2.0, 3.0]
    assert [retry.waits("exponential", at) for at in (1, 2, 3, 4)] == [
        0.0,
        1.0,
        2.0,
        4.0,
    ]
    assert [retry.waits("fibonacci", at) for at in (1, 2, 3, 4, 5)] == [
        0.0,
        1.0,
        1.0,
        2.0,
        3.0,
    ]
    assert [retry.waits("none", at) for at in (1, 2, 3)] == [0.0, 0.0, 0.0]
    # Full jitter is anywhere up to the exponential wait, which is what keeps a flow's agents
    # from all coming back on the same second.
    assert all(0.0 <= retry.waits("exponential-jitter", 4) <= 4.0 for _ in range(20))
    # However far it climbs, no single wait is longer than a turn.
    assert retry.waits("exponential", 40) == retry.CEILING
    # A policy nobody recognises waits the way the default does rather than not at all.
    assert 0.0 <= retry.waits("nonesuch", 3) <= 2.0


def test_a_policy_that_is_not_one_is_refused_where_it_is_written(
    accounts: None,
) -> None:
    """A setting to correct, rather than a turn that finds out about it hours in."""
    with pytest.raises(ValueError, match="is not a retry policy"):
        providers.retrying("shell", "main", 1, "nonesuch", 0.0)
    with pytest.raises(ValueError, match="not debts"):
        providers.retrying("shell", "main", -1, "constant", 0.0)


#: The stand-in as one line a shell session runs, since that agent takes its prompt as a
#: script: the same two-branch behaviour, written where the prompt goes.
_FLAKY_AS_SCRIPT = (
    'if [ -n "$DOWN" ]; then echo "the account is down" >&2; exit 1; fi; '
    'echo "${WHOSE:-nobody}"'
)

#: The same, writing down which account each try was taken under.
_COUNTING = (
    'echo "${{WHOSE:-nobody}}" >> {at}; '
    'if [ -n "$DOWN" ]; then echo "the account is down" >&2; exit 1; fi; '
    'echo "${{WHOSE:-nobody}}"'
)
