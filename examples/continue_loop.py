"""Continue loop (flowbench: always_continue) -- send the task once, then keep nudging "continue".

kimi --prompt "$(cat TASK.md)"                                   # first turn opens the session
while true; do kimi --session <id> --prompt "continue" || true; sleep 5; done
"""

import subprocess
import time
from contextlib import suppress
from pathlib import Path

from flowjanus.agents import KimiCodeCLIAgent, SessionBase


def continue_loop(session: SessionBase, task: str) -> None:
    while True:
        with suppress(subprocess.CalledProcessError):  # flowbench's `|| true`
            # Until the session opens, keep sending the task: "continue" on its own would open
            # one that never saw it. After that, resuming keeps the task in context.
            session.run("continue" if session.session_id else task)
        time.sleep(5)


if __name__ == "__main__":
    continue_loop(
        KimiCodeCLIAgent(model="kimi-code/k3", effort="high").start(),
        Path("TASK.md").read_text(),
    )
