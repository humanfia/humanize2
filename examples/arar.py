"""ARAR (flowbench: arar) -- an executor works in one session, and a fresh reviewer judges it.

kimi --prompt "$(cat TASK.md)"                          # first turn opens the executor's session
while true; do
    judge=$(kimi --prompt "$JUDGE_PROMPT")              # a new session each round: no memory
    verdict=$(jq -r .verdict <<< "$judge"); reason=$(jq -r .reason <<< "$judge")
    kimi --session <executor> \
        --prompt "Reviewer verdict: $verdict. $reason — Please continue working."
    sleep 5
done

This is the flow the split pays off in: the executor must remember, the reviewer must not.
"""

import json
import re
import subprocess
import time
from contextlib import suppress
from pathlib import Path

from flowjanus.agents import AgentBase, KimiCodeCLIAgent, SessionBase

JUDGE_PROMPT = """You are a strict task-completion auditor running in the working directory of a \
coding agent. Use shell tools (cat, ls, git status, git diff, etc.) to verify the agent work \
against the actual state of the repository.

Determine whether the agent GENUINELY completed the task below. Rules:
- "complete": The working directory shows concrete evidence of real work (code changes on disk, \
command output, etc.) that matches the task.
- "incomplete": The agent is stopping without finishing, or claims completion without evidence on \
disk. Reward hacking must be classified as incomplete.
- "suspended": The agent stopped to request input or approval that will not arrive.
- "waiting": The agent is waiting for an external event or process to complete before it can \
proceed.

Be skeptical. Prefer concrete evidence from the file system over any claims.

Reply with only a JSON object of the form {"verdict": "complete" | "incomplete" | "suspended" | \
"waiting", "reason": "<brief explanation citing specific evidence>"}.

Task (TASK.md):
"""


def arar(executor: SessionBase, reviewer: AgentBase, task: str) -> None:
    audit = JUDGE_PROMPT + task

    # Retry until the session exists, or the verdicts would go to an executor that never
    # saw the task.
    while executor.session_id is None:
        with suppress(subprocess.CalledProcessError):  # flowbench's `|| true`
            executor.run(task)
        time.sleep(5)

    while True:
        verdict, reason = "incomplete", "No reason provided."  # what flowbench falls back to
        with suppress(subprocess.CalledProcessError, IndexError, json.JSONDecodeError, KeyError):
            # The reviewer is the bare agent, so every round audits the repo with no memory of
            # the last one. Its verdict is the last JSON object it prints.
            payload = json.loads(re.findall(r"\{[^{}]*\}", reviewer.run(audit))[-1])
            verdict, reason = payload["verdict"], payload["reason"]

        with suppress(subprocess.CalledProcessError):
            executor.run(f"Reviewer verdict: {verdict}. {reason} — Please continue working.")
        time.sleep(5)


if __name__ == "__main__":
    agent = KimiCodeCLIAgent(model="kimi-code/k3", effort="high")
    arar(agent.start(), agent, Path("TASK.md").read_text())
