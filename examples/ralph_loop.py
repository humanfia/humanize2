"""Ralph loop (flowbench: ralph_loop).

while true; do claude --print < TASK.md; sleep 5; done
"""

import time
from pathlib import Path

from flowjanus import AgentBase, ClaudeCodeAgent


def ralph_loop(agent: AgentBase, task: str) -> None:
    while True:
        agent.run(task)
        time.sleep(5)


if __name__ == "__main__":
    ralph_loop(
        ClaudeCodeAgent(model="claude-opus-4-8", effort="high"),
        Path("TASK.md").read_text(),
    )
