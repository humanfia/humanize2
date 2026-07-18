"""Goal loop (flowbench: goal) -- ralph, but the task is handed to the agent's own /goal feature.

while true; do { printf '/goal '; cat TASK.md; } | claude --print || true; sleep 5; done
"""

import subprocess
import time
from contextlib import suppress
from pathlib import Path

from flowjanus.agents import AgentBase, ClaudeCodeAgent


def goal_loop(agent: AgentBase, task: str, *, prefix: str = "/goal ") -> None:
    # Kimi Code needs prefix="/goal -- ", so that its goal parser cannot read the first word of
    # the task as a subcommand.
    while True:
        with suppress(subprocess.CalledProcessError):  # flowbench's `|| true`
            agent.run(prefix + task)  # the agent keeps itself going; the loop just restarts it
        time.sleep(5)


if __name__ == "__main__":
    goal_loop(
        ClaudeCodeAgent(model="claude-opus-4-8", effort="max"),
        Path("TASK.md").read_text(),
    )
