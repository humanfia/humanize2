"""Stateful ralph (flowbench: stateful_ralph) -- one session, re-sent the task every turn.

hmz exec -f stateful_ralph -a kimi/PROVIDER/MODEL:high "$(cat TASK.md)"

The session is what this flow is, and it is the one thing a run picked up again cannot have
back: a session is opened rather than reopened, so running this again is a conversation of its
own, starting from the task and the repository with none of the rounds before it in context.
What does carry is which round it is on, kept as `rounds` -- so a loop stopped on its fortieth
round says round 41 when it is started again, and remembers nothing else about the forty.
"""

import time
from typing import Any

from hmz.flows import Agent, flow


@flow(resumable=True)
def run(agents: tuple[Agent], task: str, state: dict[str, Any]) -> None:
    (agent,) = agents
    session = agent.new()  # one session, held for as long as the flow runs
    while True:
        state["rounds"] = state.get("rounds", 0) + 1
        print(f"round {state['rounds']}")
        session(task, suppress=True)
        time.sleep(5)
