"""Flame chase (flowbench: flame_chase) -- two agents take turns on the same task.

while true; do
    claude --print < TASK.md
    sleep 5
    codex exec  < TASK.md
    sleep 5
done
"""

import time
from collections.abc import Sequence
from pathlib import Path

from flowjanus import AgentBase, ClaudeCodeAgent, CodexAgent


def flame_chase(agents: Sequence[AgentBase], task: str) -> None:
    while True:
        for agent in agents:
            agent.run(task)
            time.sleep(5)


if __name__ == "__main__":
    flame_chase(
        [
            ClaudeCodeAgent(model="claude-opus-4-8", effort="max"),
            CodexAgent(model="gpt-5.6-sol", effort="max"),
        ],
        Path("TASK.md").read_text(),
    )
