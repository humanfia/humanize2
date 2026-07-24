"""Goal loop (flowbench: goal) -- ralph, with the task set as the agent's own goal.

while true; do { printf '/goal '; cat TASK.md; } | claude --print || true; sleep 5; done
"""

import subprocess
import time
from contextlib import suppress
from pathlib import Path

from amflows.janus import AgentBase, ClaudeCodeAgent, ClaudeCodeAgentConfig


def goal_loop(agent: AgentBase, task: str) -> None:
    # Ralph, turn for turn, except that a turn here is a goal: the agent keeps itself going
    # until it has met the task, and the loop is only what starts it over when it stopped
    # without having. Each round is a session of its own, so nothing carries over but the work.
    while True:
        with suppress(subprocess.CalledProcessError):  # flowbench's `|| true`
            agent.launch().pursue(task)
        time.sleep(5)


if __name__ == "__main__":
    goal_loop(
        ClaudeCodeAgent(ClaudeCodeAgentConfig(model="claude-opus-4-8", effort="max")),
        Path("TASK.md").read_text(),
    )
