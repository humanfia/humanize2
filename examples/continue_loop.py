"""Continue loop (flowbench: always_continue) -- send the task once, then keep nudging "continue".

kimi --prompt "$(cat TASK.md)"                 # first turn
while true; do kimi --continue --prompt "continue"; sleep 5; done
"""

import time
from pathlib import Path

from flowjanus.agents import AgentBase, KimiCodeCLIAgent


def continue_loop(agent: AgentBase, task: str) -> None:
    agent.run(task)
    while True:
        agent.run("continue")
        time.sleep(5)


if __name__ == "__main__":
    continue_loop(
        KimiCodeCLIAgent(model="kimi-code/k3", effort="high"), Path("TASK.md").read_text()
    )
