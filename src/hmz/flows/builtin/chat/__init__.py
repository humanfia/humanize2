"""Chat -- one agent, one session, and every line typed between turns is a turn of it.

hmz exec -f chat -a claude/MODEL:high "what does this repository do?"

Which is talking to a coding agent, with no loop around it: the flow does what it is told and
then waits to be told again. It is the flow the terminal interface opens on, so that saying
something is all it takes to start. A line typed while a turn is running is put into that turn
rather than becoming another, as it is under any flow.

Two agents, then, and the second of them is you: saying something to the person is asking what
to say next, and what they answer is what they typed. Run from a command line, where nobody is
at a prompt, they answer with nothing and the flow does the one thing it was given and stops.

Nothing of it is kept for a next run to pick up. What was said is the conversation, which the
backend that ran it logs turn by turn, and a session is opened rather than reopened -- so
starting this again is another conversation rather than the last one carried on.
"""

from typing import NamedTuple

from hmz.flows import Agent, Person, flow


class Chat(NamedTuple):
    """The two sides of a conversation."""

    assistant: Agent
    human: Person


@flow
def run(agents: Chat, task: str) -> None:
    # One session, so the turns are a conversation rather than a series of first turns.
    conversation = agents.assistant.new()
    said = task
    while said:
        answered = conversation(said, suppress=True)
        # Saying that to the person is asking what to say next, and what they answer with is
        # what they typed -- or nothing, which is a conversation that is over.
        said = agents.human(answered)
