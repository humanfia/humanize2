"""Goal loop (flowbench: goal) -- ralph, with the task set as the agent's own goal.

hmz exec -f goal -a claude/claude-opus-4-8:max "$(cat TASK.md)"
"""

import time

from humanize.agents import AgentBase


def run(agents: tuple[AgentBase], task: str) -> None:
    (agent,) = agents
    while True:
        # A turn here is a goal: the agent keeps itself going until it has met the task, and
        # the loop is only what starts it over when it stopped without having.
        agent.pursue(task, suppress=True)
        time.sleep(5)
