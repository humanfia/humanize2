"""Continue loop (flowbench: continue_loop) -- send the task once, then keep nudging "continue".

kimi --prompt "$(cat TASK.md)"                                   # first turn opens the session
while true; do kimi --continue --prompt "continue" || true; sleep 5; done
"""

import subprocess
import time
from contextlib import suppress
from pathlib import Path

from amflows.janus import KimiCodeCLIAgent, KimiCodeCLIAgentConfig, SessionBase


def continue_loop(session: SessionBase, task: str) -> None:
    # Until a turn lands, keep sending the task: "continue" on its own would open a session that
    # never saw it. After that, resuming keeps the task in context.
    prompt = task
    while True:
        with suppress(subprocess.CalledProcessError):  # flowbench's `|| true`
            session.run(prompt)
            prompt = "continue"
        time.sleep(5)


if __name__ == "__main__":
    continue_loop(
        KimiCodeCLIAgent(
            KimiCodeCLIAgentConfig(model="kimi-code/k3", effort="high")
        ).launch(),
        Path("TASK.md").read_text(),
    )
