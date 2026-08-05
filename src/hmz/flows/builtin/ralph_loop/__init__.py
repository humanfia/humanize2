"""Ralph loop (flowbench: ralph_loop) -- a fresh session every turn, so nothing carries over.

hmz exec -f ralph_loop -a claude/MODEL:high "$(cat TASK.md)"

Nothing carries over inside a run, and one thing carries between runs: which round it is on,
kept as `rounds`. A loop like this is left going for days and is stopped -- esc, a machine that
goes down, a turn that takes the process with it -- so running it again goes on from the round
it reached rather than back at one. What the agent did is not kept: every round is a session of
its own, written down by the backend that ran it, and the next round starts from the task and
the repository whether or not it is the first.
"""

import time
from typing import Any

from hmz.agents import AgentBase
from hmz.flows import flow


@flow(resumable=True)
def run(agents: tuple[AgentBase], task: str, state: dict[str, Any]) -> None:
    (agent,) = agents
    while True:
        # Said before the turn rather than counted after it, so that a run watched from the
        # outside says which round the one going now is.
        state["rounds"] = state.get("rounds", 0) + 1
        print(f"round {state['rounds']}")
        # A session of its own each turn: the agent starts from the task and the repository,
        # with nothing of the last turn in context.
        agent(task, suppress=True)
        time.sleep(5)
