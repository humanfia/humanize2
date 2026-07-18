"""Stateful ralph (flowbench: always_prompt) -- one session, re-sent the task every turn.

kimi --prompt "$(cat TASK.md)"                                   # first turn opens the session
while true; do kimi --session <id> --prompt "$(cat TASK.md)" || true; sleep 5; done
"""

import subprocess
import time
from contextlib import suppress
from pathlib import Path

from flowjanus.agents import KimiCodeCLIAgent, SessionBase


def stateful_ralph(session: SessionBase, task: str) -> None:
    while True:
        with suppress(subprocess.CalledProcessError):  # flowbench's `|| true`
            session.run(task)  # the first turn opens the session; every later one resumes it
        time.sleep(5)


if __name__ == "__main__":
    stateful_ralph(
        KimiCodeCLIAgent(model="kimi-code/k3", effort="high").start(),
        Path("TASK.md").read_text(),
    )
