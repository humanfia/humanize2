"""Chat -- one agent, one session, and every line typed between turns is a turn of it.

hmz exec -f chat -a claude/claude-opus-5:high "what does this repository do?"

Which is talking to a coding agent, with no loop around it: the flow does what it is told and
then waits to be told again. It is the flow the terminal interface opens on, so that saying
something is all it takes to start. A line typed while a turn is running is put into that turn
rather than becoming another, as it is under any flow.

Two agents, then, and the second of them is you: saying something to the person is asking what
to say next, and what they answer is what they typed. Run from a command line, where nobody is
at a prompt, they answer with nothing and the flow does the one thing it was given and stops.
"""

from typing import NamedTuple

from hmz.agents import AgentBase, HumanAgent


class Chat(NamedTuple):
    """The two sides of a conversation."""

    assistant: AgentBase
    human: HumanAgent


def run(agents: Chat, task: str) -> None:
    # One session, so the turns are a conversation rather than a series of first turns.
    conversation = agents.assistant.new()
    said = task
    while said:
        answered = conversation(said, suppress=True)
        # Saying that to the person is asking what to say next, and what they answer with is
        # what they typed -- or nothing, which is a conversation that is over.
        said = agents.human(answered)
