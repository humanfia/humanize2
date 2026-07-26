"""Ralph loop (flowbench: ralph_loop) -- a fresh session every turn, so nothing carries over.

while true; do claude --print < TASK.md || true; sleep 5; done

    amflows run -f ralph_loop -a claude/claude-opus-4-8/high "$(cat TASK.md)"
"""

import subprocess
import time
from contextlib import suppress

from amflows.janus import AgentBase


def run(agents: tuple[AgentBase], task: str) -> None:
    (agent,) = agents
    while True:
        with suppress(subprocess.CalledProcessError):  # flowbench's `|| true`
            # A new session each turn: the agent starts from the task and nothing else.
            agent.launch().run(task)
        time.sleep(5)
