"""Continue loop (flowbench: continue_loop) -- send the task once, then keep nudging "continue".

hmz exec -f continue_loop -a kimi/kimi-code/k3:high "$(cat TASK.md)"
"""

import time

from humanize.janus import AgentBase


def run(agents: tuple[AgentBase], task: str) -> None:
    (agent,) = agents
    session = agent.new()
    prompt = task
    while True:
        answered = session(prompt, suppress=True)
        # Until a turn lands, the task is sent again: "continue" on its own would open a
        # session that never saw it.
        if answered:
            prompt = "continue"
        time.sleep(5)
