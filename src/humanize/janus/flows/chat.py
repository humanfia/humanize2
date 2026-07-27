"""Chat -- one agent, one session, and every line typed between turns is a turn of it.

hmz exec -f chat -a claude/claude-opus-5:high "what does this repository do?"

Which is talking to a coding agent, with no loop around it: the flow does what it is told and
then waits to be told again. It is the flow the terminal interface opens on, so that saying
something is all it takes to start. A line typed while a turn is running is put into that turn
rather than becoming another, as it is under any flow.

Run from a command line, where nobody is at a prompt to say anything more, it does the one
thing it was given and stops.
"""

from humanize.janus import AgentBase


def run(agents: tuple[AgentBase], task: str) -> None:
    (agent,) = agents
    # One session, so the turns are a conversation rather than a series of first turns.
    session = agent.new()
    said: str | None = task
    while said:
        session(said, suppress=True)
        said = agent.prompted()
