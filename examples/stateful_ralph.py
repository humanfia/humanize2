"""Stateful ralph (flowbench: always_prompt) -- keep re-sending the task in a continued session.

kimi --prompt "$(cat TASK.md)"                 # first turn
while true; do kimi --continue --prompt "$(cat TASK.md)"; sleep 5; done
"""

import time
from pathlib import Path

from flowjanus import AgentBase, KimiCodeCLIAgent


def stateful_ralph(agent: AgentBase, task: str) -> None:
    agent.run(task)
    while True:
        agent.run(task)
        time.sleep(5)


if __name__ == "__main__":
    stateful_ralph(KimiCodeCLIAgent(model="kimi-code/k3"), Path("TASK.md").read_text())
