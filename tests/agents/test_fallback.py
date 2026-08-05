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


def test_an_agent_as_this_machine_is_signed_in_is_on_an_account_too(
    accounts: None,
) -> None:
    """One nobody made: the CLI as it is already run, and the start of a chain like any other."""
    agent = ShellAgent(AgentConfig(model="m", effort="high"))

    (only,) = agent.walks()
    assert only.name == ""  # the account this machine is signed into
    assert only.retries == 0  # and nothing written down about it, so tried once
    # Which is not an account anything is run *under*: nothing is added to the environment,
    # nothing is taken out of it, and no path is answered by another.
    assert agent.provider is None
    assert only.swaps() == ()
    assert agent.new()("echo here") == "here"


def test_the_chain_of_an_agent_nobody_gave_an_account_starts_at_this_machines(
    accounts: None,
) -> None:
    """Which is what makes a fallback something an agent gets without being configured at all."""
    providers.points("shell", providers.LOCAL, "spare")
    agent = ShellAgent(AgentConfig(model="m", effort="high"))

    assert [one.name for one in agent.walks()] == ["", "spare"]

    # `main` is not in it at all: the chain begins where the agent is, which is this machine.
    session = agent.new()
    assert session(_FLAKY_HERE) == "spare"
    assert agent.provider is not None
    assert agent.provider.name == "spare"
    # And from there it is an agent under an account like any other.
    assert [one.name for one in agent.walks()] == ["spare"]


def test_the_machines_own_account_is_tried_again_before_the_chain_moves_on(
    accounts: None, tmp_path: Path
) -> None:
    """The tries are written down against it, as they are against any other account."""
    providers.retrying("shell", providers.LOCAL, 2, "none", 0.0)
    providers.points("shell", providers.LOCAL, "spare")
    tally = tmp_path / "tries.txt"

    assert (
        ShellAgent(AgentConfig(model="m", effort="high")).new()(
            _COUNTING.format(at=tally)
        )
        == "spare"
    )

    assert (
        tally.read_text().count("nobody") == 3
    )  # the first try and the two it was given
    assert tally.read_text().count("spare") == 1


def test_what_is_written_down_about_this_machines_account_outlives_the_run(
    accounts: None,
) -> None:
    """Kept under humanize's own home rather than in the tree of accounts it made.

    Taking every account of a backend away must not take this with it, and must not leave a
    stray file among the accounts either: this is not one of the accounts humanize made.
    """
    providers.points("shell", providers.LOCAL, "spare")
    providers.retrying("shell", providers.LOCAL, 1, "constant", 30.0)

    held = providers.find("shell", providers.LOCAL)
    assert held is not None
    assert (held.fallback, held.retries, held.policy, held.timeout) == (
        "spare",
        1,
        "constant",
        30.0,
    )
    assert providers.alone("shell").is_file()
    assert not providers.alone("shell").is_relative_to(providers.where("shell", "main"))
    # And it is not one of the accounts: those are the ones somebody made.
    assert "" not in [one.name for one in providers.providers("shell")]


def test_nothing_may_fall_back_to_the_account_this_machine_is_signed_into(
    accounts: None,
) -> None:
    """The end of the line is what that position means, so nothing may name it."""
    providers.points("shell", "main", "spare")
    assert providers.points("shell", "main", "")

    main = providers.find("shell", "main")
    assert main is not None
    assert main.fallback == ""
    assert [one.name for one in providers.chain(main)] == ["main"]


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


#: The same, for an agent on the account this machine is signed into: there is no `WHOSE` in
#: its environment, so the first try fails on the bare `DOWN` this fixture does not set --
#: which is what a machine with no key exported looks like. Written as a failure of its own so
#: that a local first step is a step that fails.
_FLAKY_HERE = (
    'if [ -z "$WHOSE" ]; then echo "nobody is signed in" >&2; exit 1; fi; echo "$WHOSE"'
)

#: The stand-in as one line a shell session runs, since that agent takes its prompt as a
#: script: the same two-branch behaviour, written where the prompt goes.
_FLAKY_AS_SCRIPT = (
    'if [ -n "$DOWN" ]; then echo "the account is down" >&2; exit 1; fi; '
    'echo "${WHOSE:-nobody}"'
)

#: The same, writing down which account each try was taken under. A turn under the account
#: this machine is signed into has no `WHOSE`, and fails for having none.
_COUNTING = (
    'echo "${{WHOSE:-nobody}}" >> {at}; '
    'if [ -n "$DOWN" ] || [ -z "$WHOSE" ]; then echo "down" >&2; exit 1; fi; '
    'echo "${{WHOSE}}"'
)


def test_a_session_holding_a_process_open_starts_another_once_the_agent_has_moved(
    accounts: None, tmp_path: Path
) -> None:
    """What it is holding was started as an account it has left, and nothing changes under it.

    Let go of by the thread taking the turn rather than by the one that moved the agent: a
    process another thread is reading is not one to reach across and kill.
    """
    agent = _agent("main")
    session = agent.new()
    # What a session that holds a process open writes down when it starts one. A session that
    # is one command per turn holds nothing, so it has nothing to go stale.
    session._as = "main"

    assert not session.elsewhere()

    spare = providers.find("shell", "spare")
    assert spare is not None
    agent.fall_back(spare)

    assert (
        session.elsewhere()
    )  # so its next turn starts one as the account it is on now
    assert agent.provider is not None
    assert agent.provider.name == "spare"


def test_a_chain_read_again_between_two_tries_is_walked_forwards(
    accounts: None,
) -> None:
    """Two sessions of one agent fail at once, and neither drags it back to a dead account."""
    providers.points("shell", "main", "second")
    providers.points("shell", "second", "spare")
    agent = _agent("main")

    # As though another session had already moved it on: the turn takes it from where the
    # agent is now, and the accounts it has already tried are not tried again.
    one = agent.new()
    # `spare` points back at `main`, so a chain read again mid-turn could walk round forever.
    providers.points("shell", "spare", "main")
    with pytest.raises(subprocess.CalledProcessError):
        one(_FLAKY_AS_SCRIPT.replace('echo "${WHOSE:-nobody}"', "exit 1"))

    assert agent.provider is not None
    assert agent.provider.name == "spare"  # the end of what there was to try


def test_a_turn_stopped_between_tries_is_stopped(accounts: None) -> None:
    """A run ended by hand is ended, not carried on under the next account along.

    Esc reaches an agent whose turn is in the wait between two tries, or between two
    accounts, and neither is a moment to go on from.
    """
    import threading

    from hmz.agents import Stopped

    providers.retrying("shell", "main", 3, "constant", 0.0)
    providers.points("shell", "main", "spare")
    agent = _agent("main")
    session = agent.new()
    threading.Timer(0.3, agent.stop).start()

    # The first try takes a second and fails; the stop lands while it is running, and the
    # try after it is where the loop finds out.
    with pytest.raises(Stopped):
        session('sleep 1; echo "the account is down" >&2; exit 1')

    assert agent.provider is not None
    assert agent.provider.name == "main"  # it never moved


def test_a_turn_does_not_drag_the_agent_back_onto_an_account_it_has_left(
    accounts: None,
) -> None:
    """Two sessions of one agent fail at once, and the slower one must not undo the faster.

    Its own view of the chain is a snapshot taken when its round began; by the time it comes
    to move, the agent may already be further along than the step that snapshot names.
    """
    providers.points("shell", "main", "second")
    providers.points("shell", "second", "spare")
    agent = _agent("main")
    spare = providers.find("shell", "spare")
    assert spare is not None

    # As though another session had walked the whole chain while this turn was running.
    agent.fall_back(spare)
    session = agent.new()

    assert session(_FLAKY_AS_SCRIPT) == "spare"
    assert agent.provider is not None
    assert agent.provider.name == "spare"
