"""Flame chase (flowbench: flame_chase) -- two agents take turns on the same task.

while true; do
    claude --print < TASK.md || true
    sleep 5
    codex exec  < TASK.md || true
    sleep 5
done
"""

import subprocess
import time
from collections.abc import Sequence
from contextlib import suppress
from pathlib import Path

from flowjanus.agents import AgentBase, ClaudeCodeAgent, CodexAgent


def flame_chase(agents: Sequence[AgentBase], task: str) -> None:
    while True:
        for agent in agents:
            with suppress(subprocess.CalledProcessError):  # flowbench's `|| true`
                agent.run(task)  # throwaway sessions: each agent reads the repo, not a history
            time.sleep(5)


if __name__ == "__main__":
    flame_chase(
        [
            ClaudeCodeAgent(model="claude-opus-4-8", effort="max"),
            CodexAgent(model="gpt-5.6-sol", effort="max"),
        ],
        Path("TASK.md").read_text(),
    )
