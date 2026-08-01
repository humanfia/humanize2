"""Stateful ralph (flowbench: stateful_ralph) -- one session, re-sent the task every turn.

hmz exec -f stateful_ralph -a kimi/PROVIDER/MODEL:high "$(cat TASK.md)"
"""

import time

from hmz.agents import AgentBase
from hmz.flows import flow


@flow
def run(agents: tuple[AgentBase], task: str) -> None:
    (agent,) = agents
    session = agent.new()  # one session, held for as long as the flow runs
    while True:
        session(task, suppress=True)
        time.sleep(5)
