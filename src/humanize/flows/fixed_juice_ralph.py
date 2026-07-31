"""Fixed-juice ralph (flowbench: fixed_juice_ralph) -- a ralph loop held to an answer size.

    hmz exec -f fixed_juice_ralph -a claude/claude-opus-4-8:high "$(cat TASK.md)"

Add `-c juice.yaml` to say how much juice to hold it to rather than take the one it comes
with, and `hmz -f fixed_juice_ralph -c juice.yaml` opens the interface on the same setup.

The ralph loop with a governor on it: a fresh session every turn, and between the turns the
effort moved to hold the agent to `juice` output tokens per turn of the model.

Per turn of the *model* -- one request and the answer to it -- rather than per turn of the
flow, which is many of those and as many again of whatever the tools took. That average is
what an effort actually moves: a model asked to think harder writes more in each answer and
takes longer over it. A model asked to think less writes less. So an agent under the target is
asked to think harder and one over it is asked to think less, one rung of its own model's
ladder per round, so that the loop settles rather than swings.

Nothing here is a clock. How long a round takes and what it costs an hour are what the model
and the work make of it; what this holds steady is how much of an answer each turn is worth.

Which is a flow rather than a setting because it is a policy: how much thinking a job is worth
is the sort of thing that changes between projects, and this is one answer to it written down.
"""

import time

from pydantic import BaseModel, Field

from humanize import backends
from humanize.agents import SWARM, AgentBase


class Config(BaseModel):
    """What this flow takes."""

    model_config = {"extra": "forbid"}

    juice: float = Field(
        default=2000.0,
        gt=0,
        description="output tokens an average turn of the model is to come out with, which "
        "is what the effort is moved to hold it to",
    )
    over: float = Field(
        default=300.0,
        ge=10,
        le=3600,
        description="how far back that average is taken, in seconds",
    )
    slack: float = Field(
        default=0.15,
        ge=0,
        le=1,
        description="how far off the average may be before the effort moves, as a fraction "
        "of the target -- 0.15 leaves it alone between 85% and 115% of it",
    )
    rest: float = Field(
        default=5.0,
        ge=0,
        le=600,
        description="how long to wait between rounds, in seconds",
    )


def ladder(agent: AgentBase) -> tuple[str, ...]:
    """The efforts this agent's model takes, hardest first.

    Read out of `humanize.backends`, which is where every other reader of it looks. A model
    that is not written down there -- one an account has and this list does not -- is offered
    its backend's own ladder, since every model of a backend takes the same efforts unless
    that backend says otherwise; a backend nobody knows leaves the agent at what it was
    configured with, which is a loop with nothing to turn.

    Args:
      agent: The agent whose model it is.

    Returns:
      One effort per rung, hardest first, or just the configured one where none is known.
    """
    profile = backends.named(agent.backend)
    if profile is None or not profile.models:
        return (agent.config.effort,)
    named = agent.config.model
    for model in profile.models:
        if model.name == named:
            return model.efforts
    return profile.models[0].efforts


def _at(agent: AgentBase, rungs: tuple[str, ...]) -> int:
    """Which rung the agent is on, or the middle one where it is on none of them.

    Kimi's effort says how wide to run as well as how hard, and the width goes with it: the
    rung is the thinking, and the prefix rides along.

    Args:
      agent: The agent to place.
      rungs: The ladder, hardest first.

    Returns:
      The index of the rung it is on.
    """
    thinking = agent.effort.removeprefix(SWARM)
    if thinking in rungs:
        return rungs.index(thinking)
    return len(rungs) // 2


def run(agents: tuple[AgentBase], task: str, config: Config | None = None) -> None:
    """Runs the loop, holding the agent to the answer size it was set up with.

    Args:
      agents: The one agent it drives.
      task: What it is to do, every turn, from the repository and nothing else.
      config: How much juice to hold it to and how to hold it, or None for the defaults.
    """
    (agent,) = agents
    held = config or Config()
    rungs = ladder(agent)
    wide = SWARM if agent.effort.startswith(SWARM) else ""
    at = _at(agent, rungs)
    while True:
        # A session of its own each round: the agent starts from the task and the repository,
        # with nothing of the last round in context. What carries over is the effort.
        agent(task, suppress=True)
        # What its turns of the model have been coming out with lately. A round that landed
        # no turn at all -- one whose backend failed before it said anything -- leaves nothing
        # to steer by, and the effort is left where it was rather than moved on a zero.
        juice = agent.juice(over=held.over)
        if juice and juice < held.juice * (1 - held.slack):
            at = max(at - 1, 0)  # thin answers: think harder, and write more in each
        elif juice > held.juice * (1 + held.slack):
            at = min(at + 1, len(rungs) - 1)  # long ones: think less, and answer sooner
        agent.effort = f"{wide}{rungs[at]}"
        print(f"{juice:.0f}/{held.juice:g} out per turn · {agent.effort}")
        time.sleep(held.rest)
