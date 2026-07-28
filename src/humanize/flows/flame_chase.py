"""Flame chase (flowbench: flame_chase) -- two agents take turns on the same task.

hmz exec -f flame_chase \
    -a claude/claude-opus-4-8:max -a codex/gpt-5.6-sol:max "$(cat TASK.md)"
"""

import time

from humanize.janus import AgentBase


def run(agents: tuple[AgentBase, AgentBase], task: str) -> None:
    while True:
        for agent in agents:
            agent(task, suppress=True)  # each agent reads the repository, not a history
            time.sleep(5)
