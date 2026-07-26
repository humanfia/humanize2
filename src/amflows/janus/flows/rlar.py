"""RLAR (flowbench: rlar) -- an actor works in one session, and a fresh reviewer reads its work.

prompt=$(cat TASK.md)                                   # the actor's first turn is the task
while true; do
    claude --print --resume <actor> <<< "$prompt" &&    # only a landed turn earns a review
        prompt=$(claude --print <<< "$REVIEW_PROMPT$(cat TASK.md)") || true
    sleep 5
done

    amflows run -f rlar \
        -a claude/claude-opus-4-8/high,claude/claude-opus-4-8/high "$(cat TASK.md)"

This is the flow the split pays off in: the actor must remember, the reviewer must not. Nothing
between them parses anything -- the review is the actor's next prompt, word for word, so what the
reviewer noticed is what the actor hears. The two are given the same model and effort above and
are still two agents, which is the point: a trace reads the actor's session and the reviewer's
rounds as two, rather than as one agent that keeps changing its mind about what it is doing.

The one flow here whose payload is what a turn printed, so the backend has to be one that prints
the reply alone: Kimi closes each turn with a resume hint, which would ride along.
"""

import subprocess
import time
from contextlib import suppress

from amflows.janus import AgentBase

REVIEW_PROMPT = """You are a meticulous reviewer, running in the working directory of a coding \
agent that has been given the task below. Use shell tools (cat, ls, git status, git diff, etc.) \
to review what it has actually done against the state of the repository. Be skeptical: treat \
reward hacking -- tests weakened or special-cased, work stubbed out or faked -- as the thing you \
are most there to catch.

Write your review as a message to that agent: what is done, what is wrong or missing, and what to \
do next, citing specific files, lines and commands. It is passed on word for word and is all the \
agent will hear from you, so leave nothing to be inferred.

Task (TASK.md):
"""


def run(agents: tuple[AgentBase, AgentBase], task: str) -> None:
    actor, reviewer = agents
    session = actor.launch()  # the actor remembers; a session held across rounds is how
    # A failed turn leaves the prompt in place, so the round is retried rather than advanced past
    # a review the actor never saw -- including the opening one, which is the task itself.
    prompt = task
    while True:
        with suppress(subprocess.CalledProcessError):  # flowbench's `|| true`
            session.run(prompt)
            # A new session each round, so the reviewer reads the repository rather than its own
            # earlier reviews -- and is handed the task again, never having seen it.
            prompt = reviewer.launch().run(REVIEW_PROMPT + task)
        time.sleep(5)
