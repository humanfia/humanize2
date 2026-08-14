"""An agent that is not quite the one you were handed, which is a second agent.

What an agent is, is settled where it is made. A flow is handed agents and drives them; what
each of them runs, where its turns land, what it is called and which of a flow's skills it
carries are answers somebody already gave -- at a prompt, on a command line, in a settings
file -- and a flow that could change one of them would be a flow rewriting the choice the run
was started with.

So there is one way to have an agent that differs, and it makes one: `clone` says what is to
be different and nothing about it can be said afterwards. Two agents, which is what they are --
the clone has opened nothing, spent nothing, is watched by nobody and is being written down
nowhere.
"""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

import pytest

from hmz.agents import AgentConfig, Event, HumanAgent, Moment
from hmz.agents.skills import Loaded
from hmz.flows import Agent, Driven
from tests.stubs import ShellAgent

if TYPE_CHECKING:
    from pathlib import Path

CONFIG = AgentConfig(model="m", effort="high")


def test_a_clone_is_a_second_agent_rather_than_the_first_one_changed() -> None:
    """A trace that read them as one would read two efforts as one agent changing its mind."""
    agent = ShellAgent(CONFIG)

    careful = agent.clone(config=replace(agent.config, effort="max"))

    assert careful is not agent
    assert careful.id != agent.id
    assert careful.config.effort == "max"
    assert agent.config.effort == "high"  # and the one it came from is untouched


def test_everything_the_call_does_not_name_is_the_agent_it_came_from() -> None:
    """Which is what makes it a clone rather than another agent built from nothing."""
    agent = ShellAgent(
        AgentConfig(model="m", effort="high", permission="read-only", provider="mine")
    )

    same = agent.clone()

    assert same.config == agent.config
    assert type(same) is type(agent)


def test_a_clone_given_a_name_is_that_agent_and_one_given_none_is_its_own() -> None:
    """Two agents sharing a name are one agent to a trace, which is sometimes what is meant."""
    agent = ShellAgent(CONFIG, name="builder")

    assert agent.clone(name="reviewer").id == "reviewer"
    assert agent.clone().id != "builder"


def test_a_clone_carries_what_it_came_from_carries_unless_it_is_told_otherwise(
    tmp_path: Path,
) -> None:
    """The skills are the flow's, and a clone is being driven by the same flow."""
    reading = Loaded("reading", tmp_path / "reading", "this flow")
    writing = Loaded("writing", tmp_path / "writing", "this flow")
    agent = ShellAgent(CONFIG)
    agent.loads([reading, writing])

    assert agent.clone().loaded == (reading, writing)
    assert agent.clone(skills=[writing]).loaded == (writing,)
    assert agent.clone(skills=()).loaded == ()
    assert agent.loaded == (reading, writing)  # and the original still carries both


def test_a_clone_has_none_of_what_a_run_puts_on_an_agent() -> None:
    """It has opened nothing, spent nothing, is watched by nobody and is hooked to nothing."""
    agent = ShellAgent(CONFIG)
    said: list[Event] = []
    agent.watch(lambda _agent, _session, event: said.append(event))
    agent.cycle = None
    agent.new()("echo hi")
    with agent.hooks.on(Moment.STOP, lambda occasion: None):
        made = agent.clone()

    assert agent.opened  # the one that ran has a conversation behind it
    assert made.opened == []
    assert made.sessions == []
    assert made.spent().total == 0
    assert not made.hooks._hung.get(Moment.STOP)
    made.new()("echo hi")
    # And nothing it does reaches what was watching the agent it came from.
    assert not any(one.text == "echo hi" for one in said[len(said) :])


def test_a_clone_of_a_stopped_agent_is_one_that_may_take_a_turn() -> None:
    """A stop is a thing that happened to a run rather than a thing an agent is."""
    agent = ShellAgent(CONFIG)
    agent.stop()

    assert agent.stopped
    assert not agent.clone().stopped


def test_cloning_the_person_at_the_prompt_is_a_person() -> None:
    """They are made rather than configured, so making another is making another of those."""
    person = HumanAgent()

    assert isinstance(person.clone(), HumanAgent)
    assert person.clone(name="you").id == "you"


def test_a_clone_is_refused_a_config_its_backend_cannot_express() -> None:
    """Said where the clone is made, which is where every other agent is refused one."""
    agent = ShellAgent(CONFIG)

    with pytest.raises(ValueError, match="service tier"):
        agent.clone(config=replace(agent.config, service_tier="fast"))


def test_what_a_flow_may_ask_of_an_agent_does_not_include_setting_it_up() -> None:
    """The line between the two is who is entitled to say what an agent is.

    A flow declares `Agent` and is handed one, so what it can reach is what it may ask. The
    settling is on `Driven`, which is how whoever hands an agent over holds it -- the runner
    before the first turn, the calling of one flow by another, and the interface when somebody
    watching a run says this agent is to go on as something else.
    """
    asks = {name for name in dir(Agent) if not name.startswith("_")}
    settles = {name for name in dir(Driven) if not name.startswith("_")} - asks

    assert settles == {"disable_goals", "loads", "reconfigure", "rename", "runs_on"}
    assert "clone" in asks
    # And the driver answers to both, which is what makes the split a contract rather than
    # two names for one thing: a flow reaches half of it, and the run reaches all of it.
    made = ShellAgent(CONFIG)
    assert not [name for name in asks | settles if not hasattr(made, name)]
