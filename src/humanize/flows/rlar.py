"""RLAR (flowbench: rlar) -- an actor works in one session, and a fresh reviewer reads its work.

    hmz exec -f rlar \
        -a claude/claude-opus-4-8:high -a claude/claude-opus-4-8:high "$(cat TASK.md)"

The actor must remember and the reviewer must not. Nothing between them parses anything: the
review is the actor's next prompt, word for word, so what the reviewer noticed is what the
actor hears. Give the two the same model and effort and they are still two agents, which is
the point -- a trace reads the actor's session and the reviewer's rounds as two.
"""

import time
from typing import NamedTuple

from humanize.agents import AgentBase


class Agents(NamedTuple):
    """The two the flow drives: one that works in a session, and one that arrives fresh."""

    actor: AgentBase
    reviewer: AgentBase


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


def run(agents: Agents, task: str) -> None:
    # The actor remembers, and a session held across the rounds is how.
    working = agents.actor.new()
    prompt = task
    while True:
        worked = working(prompt, suppress=True)
        # Only a landed turn earns a review, and the reviewer's is the actor's next prompt.
        # A turn that failed answers with nothing, so the round is taken again rather than
        # advanced past a review the actor never saw -- the opening one included.
        if worked:
            # A new session each round, so the reviewer reads the repository rather than its
            # own earlier reviews -- and is handed the task again, never having seen it.
            review = agents.reviewer(REVIEW_PROMPT + task, suppress=True)
            prompt = review or prompt
        time.sleep(5)
