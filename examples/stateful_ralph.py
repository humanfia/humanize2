"""Stateful ralph (flowbench: stateful_ralph) -- one session, re-sent the task every turn.

kimi --prompt "$(cat TASK.md)"                                   # first turn opens the session
while true; do kimi --continue --prompt "$(cat TASK.md)" || true; sleep 5; done

    janus -f examples/stateful_ralph.py -a kimi/kimi-code/k3/high "$(cat TASK.md)"
"""

import subprocess
import time
from contextlib import suppress

from amflows.janus import AgentBase


def run(agents: tuple[AgentBase], task: str) -> None:
    (agent,) = agents
    session = agent.launch()  # one session, held for as long as the flow runs
    while True:
        with suppress(subprocess.CalledProcessError):  # flowbench's `|| true`
            # The first turn opens the session; every later one resumes it.
            session.run(task)
        time.sleep(5)
