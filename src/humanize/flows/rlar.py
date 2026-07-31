"""RLAR (flowbench: rlar) -- an actor works in one session, and a fresh reviewer reads its work.

    hmz exec -f rlar \
        -a claude/claude-opus-4-8:high -a claude/claude-opus-4-8:high "$(cat TASK.md)"

The actor must remember and the reviewer must not. Give the two the same model and effort and
they are still two agents, which is the point -- a trace reads the actor's session and the
reviewer's rounds as two.

The reviewer answers two things at once: whether the task is finished, and what to say to the
actor about it. The second is the actor's next prompt, word for word, so what the reviewer
noticed is what the actor hears; the first is what ends the loop. Both are read off the object
the reviewer is held to rather than off a marker at the end of a paragraph, so a review that
says the work is done and a review that says the words "it is done" are not the same thing.
"""

import time
from typing import NamedTuple

from pydantic import BaseModel, Field

from humanize.agents import AgentBase


class Agents(NamedTuple):
    """The two the flow drives: one that works in a session, and one that arrives fresh."""

    actor: AgentBase
    reviewer: AgentBase


class Review(BaseModel):
    """What one round's review comes to: whether it is over, and what the actor is told.

    The fields are what the reviewer is asked for -- the descriptions here are the whole of
    the instruction, since they are what the backend is given as the shape to answer in.
    """

    model_config = {"extra": "forbid"}

    done: bool = Field(
        description="True only if the task is completely and correctly done: everything "
        "asked for is implemented, it works, nothing was faked, stubbed or special-cased to "
        "pass, and there is no next step worth taking. False if there is anything at all "
        "left to do or to fix."
    )
    notes: str = Field(
        description="The review itself, written as a message to the coding agent: what is "
        "done, what is wrong or missing, and what to do next, citing specific files, lines "
        "and commands. It is passed on word for word and is all the agent will hear from "
        "you, so leave nothing to be inferred. When done is true, this is what the run "
        "finishes on: say what was built and how it was checked."
    )


REVIEW_PROMPT = """You are a meticulous reviewer, running in the working directory of a coding \
agent that has been given the task below. Use shell tools (cat, ls, git status, git diff, etc.) \
to review what it has actually done against the state of the repository. Be skeptical: treat \
reward hacking -- tests weakened or special-cased, work stubbed out or faked -- as the thing you \
are most there to catch.

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
            review = agents.reviewer(REVIEW_PROMPT + task, suppress=True, schema=Review)
            if review is not None and review.done:
                # The reviewer is the one that says it is over: the actor believing it has
                # finished is what earns a review, and this is the review agreeing.
                print(review.notes)
                return
            prompt = (review.notes if review else "") or prompt
        time.sleep(5)
