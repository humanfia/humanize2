"""ARAR (flowbench: arar) -- an executor works, a reviewer judges it, and the verdict is fed back.

kimi --prompt "$(cat TASK.md)"                 # first turn: the executor
while true; do
    verdict=$(kimi --prompt "$JUDGE_PROMPT")   # the reviewer inspects the repo
    kimi --session <executor> --prompt "Reviewer verdict: $verdict — Please continue working."
    sleep 5
done
"""

import time
from pathlib import Path

from flowjanus import AgentBase, KimiCodeCLIAgent

JUDGE_PROMPT = """You are a strict task-completion auditor in the working directory of a coding \
agent. Use shell tools to verify the agent's work against the actual repository, and reply with a \
verdict (complete/incomplete) and a brief reason.

Task:
"""


def arar(executor: AgentBase, reviewer: AgentBase, task: str) -> None:
    executor.run(task)
    while True:
        verdict = reviewer.run(JUDGE_PROMPT + task)
        executor.run(f"Reviewer verdict: {verdict} — Please continue working.")
        time.sleep(5)


if __name__ == "__main__":
    agent = KimiCodeCLIAgent(model="kimi-code/k3")
    arar(agent, agent, Path("TASK.md").read_text())
