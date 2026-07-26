"""Flame chase (flowbench: flame_chase) -- two agents take turns on the same task.

while true; do
    claude --print < TASK.md || true
    sleep 5
    codex exec  < TASK.md || true
    sleep 5
done

    amflows run -f flame_chase \
        -a claude/claude-opus-4-8/max,codex/gpt-5.6-sol/max "$(cat TASK.md)"
"""

import subprocess
import time
from contextlib import suppress

from amflows.janus import AgentBase


def run(agents: tuple[AgentBase, AgentBase], task: str) -> None:
    while True:
        for agent in agents:
            with suppress(subprocess.CalledProcessError):  # flowbench's `|| true`
                agent.launch().run(task)  # each agent reads the repo, not a history
            time.sleep(5)
