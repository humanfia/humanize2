"""Fixed-TPS ralph (flowbench: fixed_tps_ralph) -- a ralph loop held to an output rate.

    hmz exec -f fixed_tps_ralph -a claude/claude-opus-4-8:high "$(cat TASK.md)"

Add `-c tps.yaml` to say which rate to hold it to rather than take the one it comes with, and
`hmz -f fixed_tps_ralph -c tps.yaml` opens the interface on the same setup.

The ralph loop with a governor on it: a fresh session every turn, and between the turns two
dials turned to hold the agent to `tps` output tokens a second.

The first is how hard it thinks. A harder effort is more reasoning and more of it written
down, so an agent under the rate is asked to think harder and one over it is asked to think
less -- one rung of its own model's ladder per round, so that the loop settles rather than
swings. The second is the wait after a turn: what a turn produced ought to have taken
`made / tps` seconds, and resting the difference off is what spreads it over them. Between
them they cover both directions -- the hardest effort a model has is the ceiling on how fast
it can go, and waiting has no ceiling at all.

Which is a flow rather than a setting because it is a policy: what a run is worth an hour is
the sort of thing that changes between projects, and this is one answer to it written down.
"""

import time

from pydantic import BaseModel, Field

from humanize import backends
from humanize.agents import SWARM, AgentBase


class Config(BaseModel):
    """What this flow takes."""

    model_config = {"extra": "forbid"}

    tps: float = Field(
        default=50.0,
        gt=0,
        le=100_000,
        description="output tokens a second to hold the agent to, averaged over the window",
    )
    over: float = Field(
        default=300.0,
        ge=10,
        le=3600,
        description="how far back the rate is measured, in seconds",
    )
    slack: float = Field(
        default=0.15,
        ge=0,
        le=1,
        description="how far off the rate may be before the effort moves, as a fraction of "
        "the target -- 0.15 leaves it alone between 85% and 115% of it",
    )
    rest: float = Field(
        default=5.0,
        ge=0,
        le=600,
        description="the shortest wait between turns, in seconds",
    )


def ladder(agent: AgentBase) -> tuple[str, ...]:
    """The efforts this agent's model takes, hardest first.

    Read out of `humanize.backends`, which is where every other reader of it looks. A model
    that is not written down there -- one an account has and this list does not -- is offered
    its backend's own ladder, since every model of a backend takes the same efforts unless
    that backend says otherwise; a backend nobody knows leaves the agent at what it was
    configured with, which is a loop that governs itself by resting alone.

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
    """Runs the loop, holding the agent to the rate it was set up with.

    Args:
      agents: The one agent it drives.
      task: What it is to do, every turn, from the repository and nothing else.
      config: The rate to hold it to and how to hold it, or None for the defaults.
    """
    (agent,) = agents
    held = config or Config()
    rungs = ladder(agent)
    wide = SWARM if agent.effort.startswith(SWARM) else ""
    at = _at(agent, rungs)
    made = 0.0  # what the agent had produced before this round, so a turn is the rise
    while True:
        began = time.monotonic()
        agent(task, suppress=True)
        took = time.monotonic() - began
        produced, made = agent.spent().output - made, agent.spent().output
        # What that many tokens ought to have taken, less what it did take: resting the
        # difference off is what spreads a turn over the seconds its output is worth.
        resting = max(held.rest, produced / held.tps - took)
        # Moved by how the run is actually going rather than by the turn alone: a rate is
        # what this flow was set up to hold, and one turn is not a rate.
        rate = agent.rate(over=held.over).output
        if rate < held.tps * (1 - held.slack):
            at = max(at - 1, 0)  # under the target: think harder, and write more down
        elif rate > held.tps * (1 + held.slack):
            at = min(
                at + 1, len(rungs) - 1
            )  # over it: think less, and rest the rest off
        agent.effort = f"{wide}{rungs[at]}"
        print(
            f"{produced:.0f} out in {took:.0f}s · {rate:.1f}/{held.tps:g} tps · "
            f"{agent.effort} · resting {resting:.0f}s"
        )
        time.sleep(resting)
