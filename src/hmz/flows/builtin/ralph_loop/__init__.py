"""Ralph loop (flowbench: ralph_loop) -- a fresh session every turn, so nothing carries over.

hmz exec -f ralph_loop -a claude/MODEL:high "$(cat TASK.md)"

Add `-c budget.yaml` to hold it to something other than the budget it comes with, and
`hmz -f ralph_loop -c budget.yaml` opens the interface on the same setup.

Nothing carries over inside a run, and two things carry between runs: which round it is on,
kept as `rounds`, and what it has spent, kept as `output`. A loop like this is left going for
days and is stopped -- esc, a machine that goes down, a turn that takes the process with it --
so running it again goes on from the round it reached rather than back at one. What the agent
did is not kept: every round is a session of its own, written down by the backend that ran it,
and the next round starts from the task and the repository whether or not it is the first.

What ends it is the budget. A loop with nothing else to stop it runs until somebody stops it,
which is a bill nobody agreed to and a week of rounds nobody read; so it is held to `budget`
million output tokens, and 0 is the loop that goes on until it is stopped by hand. Output
rather than every kind, because output is what the model is asked to produce and the only
kind a loop of its own accord grows: what goes in is the task and the repository, and a round
that read more of them is not a round that did more.

The spend is kept because the rounds are. A budget that started again at nothing every time
the loop was picked up would be no budget at all for the loop a week of restarts is, so what
is counted is every run of this flow in this workspace. A loop that has spent it is over, and
what is over is not picked up: it clears what it kept, so the next run here opens on a budget
of its own and at round one rather than stopping before it has taken a turn.
"""

import time
from typing import Any

from pydantic import BaseModel, Field

from hmz.flows import Agent, flow

#: Output tokens in one of the millions a budget is written in. The budget is written that
#: way because that is the size these loops come in: a round of one is thousands, and a day
#: of rounds is millions.
MILLION = 1_000_000.0


class Config(BaseModel):
    """What this flow takes."""

    model_config = {"extra": "forbid"}

    budget: float = Field(
        default=10.0,
        ge=0,
        description="millions of output tokens the loop may spend before it stops, counted "
        "across every run of it in this workspace, or 0 to go on until it is stopped",
    )


@flow(resumable=True)
def run(
    agents: tuple[Agent],
    task: str,
    config: Config | None = None,
    state: dict[str, Any] | None = None,
) -> None:
    (agent,) = agents
    held = config or Config()
    kept = state if state is not None else {}
    # What the runs before this one spent, which this run's own is added to: an agent counts
    # what it has spent since it was made, and the loop is older than any of them.
    before = kept.get("output", 0.0)
    while True:
        # Said before the turn rather than counted after it, so that a run watched from the
        # outside says which round the one going now is.
        kept["rounds"] = kept.get("rounds", 0) + 1
        print(f"round {kept['rounds']}")
        # A session of its own each turn: the agent starts from the task and the repository,
        # with nothing of the last turn in context.
        agent(task, suppress=True)
        kept["output"] = spent = before + agent.spent().output
        if held.budget and spent >= held.budget * MILLION:
            print(f"stopping: {spent / MILLION:.2f}M output tokens of {held.budget:g}M")
            # Emptied rather than left, which is what the next run here is handed and reads
            # as a run to start clean rather than as a run to carry on and stop at once.
            kept.clear()
            return
        time.sleep(5)
