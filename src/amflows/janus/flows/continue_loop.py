"""Continue loop (flowbench: continue_loop) -- send the task once, then keep nudging "continue".

kimi --prompt "$(cat TASK.md)"                                   # first turn opens the session
while true; do kimi --continue --prompt "continue" || true; sleep 5; done

    amflows run -f continue_loop -a kimi/kimi-code/k3/high "$(cat TASK.md)"
"""

import subprocess
import time
from contextlib import suppress

from amflows.janus import AgentBase


def run(agents: tuple[AgentBase], task: str) -> None:
    (agent,) = agents
    session = agent.launch()
    # Until a turn lands, keep sending the task: "continue" on its own would open a session that
    # never saw it. After that, resuming keeps the task in context.
    prompt = task
    while True:
        with suppress(subprocess.CalledProcessError):  # flowbench's `|| true`
            session.run(prompt)
            prompt = "continue"
        time.sleep(5)
