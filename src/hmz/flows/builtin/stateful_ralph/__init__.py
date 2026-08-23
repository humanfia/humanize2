"""Stateful ralph (flowbench: stateful_ralph) -- one session, re-sent the task every turn.

hmz exec -f stateful_ralph -a kimi/PROVIDER/MODEL:high "$(cat TASK.md)"

Add `-c budget.yaml` to hold it to something other than the budget it comes with, and
`hmz -f stateful_ralph -c budget.yaml` opens the interface on the same setup.

The session is what this flow is, and it is the one thing a run picked up again cannot have
back: a session is opened rather than reopened, so running this again is a conversation of its
own, starting from the task and the repository with none of the rounds before it in context.
What does carry is which round it is on, kept as `rounds`, and what the loop has spent, kept
as `output` -- so a loop stopped on its fortieth round says round 41 when it is started again,
and remembers nothing else about the forty.

What ends it is the budget. A loop with nothing else to stop it runs until somebody stops it,
which is a bill nobody agreed to and a week of rounds nobody read; so it is held to `budget`
million output tokens, and 0 is the loop that goes on until it is stopped by hand. Output
rather than every kind, because output is what the model is asked to produce and the only
kind a loop of its own accord grows -- and here what goes in grows too, one session being one
conversation that gets longer, which is the context window's business rather than a budget's.

Or a run of rounds that did nothing. A round whose turn failed answers with nothing and spends
nothing, so a loop whose account was refused or whose model it may not run sits under a budget
that never moves and goes round on the same failure for as long as it is left. Three such
rounds in a row end it. What it kept is left rather than cleared: a loop that stalled is one
to fix and start again from, not one that is over.

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

#: How many rounds in a row may answer with nothing before the loop gives up. A round that
#: failed answers with nothing under `suppress` and spends no output tokens, so the budget
#: meant to end the loop never moves for it. Three rather than one, because a round that
#: genuinely had nothing to say is a round like any other and not a reason to stop.
STALLED = 3


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
    session = agent.new()  # one session, held for as long as the flow runs
    stalled = 0
    while True:
        kept["rounds"] = kept.get("rounds", 0) + 1
        print(f"round {kept['rounds']}")
        answered = session(task, suppress=True)
        kept["output"] = spent = before + agent.spent().output
        if held.budget and spent >= held.budget * MILLION:
            print(f"stopping: {spent / MILLION:.2f}M output tokens of {held.budget:g}M")
            # Emptied rather than left, which is what the next run here is handed and reads
            # as a run to start clean rather than as a run to carry on and stop at once.
            kept.clear()
            return
        stalled = 0 if answered else stalled + 1
        if stalled >= STALLED:
            print(f"stopping: {stalled} rounds in a row answered with nothing")
            # Kept rather than cleared: this is a loop that was stopped rather than one that
            # is over, and what stopped it is a thing to fix and carry on from.
            return
        time.sleep(5)
