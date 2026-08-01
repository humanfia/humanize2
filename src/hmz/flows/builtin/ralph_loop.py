"""Ralph loop (flowbench: ralph_loop) -- a fresh session every turn, so nothing carries over.

hmz exec -f ralph_loop -a claude/MODEL:high "$(cat TASK.md)"
"""

import time

from hmz.agents import AgentBase


def run(agents: tuple[AgentBase], task: str) -> None:
    (agent,) = agents
    while True:
        # A session of its own each turn: the agent starts from the task and the repository,
        # with nothing of the last turn in context.
        agent(task, suppress=True)
        time.sleep(5)
