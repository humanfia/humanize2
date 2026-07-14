"""Ultra ralph (flowbench: ultra_ralph) -- the ralph loop at maximum effort.

while true; do claude --print --effort ultracode < TASK.md; sleep 5; done
"""

import time
from pathlib import Path

from flowjanus.agents import AgentBase, ClaudeCodeAgent


def ultra_ralph(agent: AgentBase, task: str) -> None:
    while True:
        agent.run(task)
        time.sleep(5)


if __name__ == "__main__":
    ultra_ralph(
        ClaudeCodeAgent(model="claude-opus-4-8", effort="ultracode"),
        Path("TASK.md").read_text(),
    )
