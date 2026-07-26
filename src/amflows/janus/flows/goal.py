"""Goal loop (flowbench: goal) -- ralph, with the task set as the agent's own goal.

while true; do { printf '/goal '; cat TASK.md; } | claude --print || true; sleep 5; done

    amflows run -f goal -a claude/claude-opus-4-8/max "$(cat TASK.md)"
"""

import subprocess
import time
from contextlib import suppress

from amflows.janus import AgentBase


def run(agents: tuple[AgentBase], task: str) -> None:
    (agent,) = agents
    # Ralph, turn for turn, except that a turn here is a goal: the agent keeps itself going
    # until it has met the task, and the loop is only what starts it over when it stopped
    # without having. Each round is a session of its own, so nothing carries over but the work.
    while True:
        with suppress(subprocess.CalledProcessError):  # flowbench's `|| true`
            agent.launch().pursue(task)
        time.sleep(5)
