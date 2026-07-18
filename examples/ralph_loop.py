"""Ralph loop (flowbench: ralph_loop) -- a fresh session every turn, so nothing carries over.

while true; do claude --print < TASK.md || true; sleep 5; done
"""

import subprocess
import time
from contextlib import suppress
from pathlib import Path

from flowjanus.agents import AgentBase, ClaudeCodeAgent


def ralph_loop(agent: AgentBase, task: str) -> None:
    while True:
        with suppress(subprocess.CalledProcessError):  # flowbench's `|| true`
            agent.run(task)  # a throwaway session: the agent starts from the task each time
        time.sleep(5)


if __name__ == "__main__":
    ralph_loop(
        ClaudeCodeAgent(model="claude-opus-4-8", effort="high"),
        Path("TASK.md").read_text(),
    )
